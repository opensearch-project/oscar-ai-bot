# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""maven / Gradle ecosystem strategy (OpenSearch plugins + core).

One worker, two declaration styles — it branches on how the repo declares
dependency versions:

  - **core** (``gradle/libs.versions.toml`` present) — OpenSearch core and any
    repo using a Gradle version catalog. The fix bumps the ``[versions]`` key the
    coordinate maps to (via its ``[libraries]`` ``version.ref``). A coordinate not
    in the catalog is declared directly in a submodule ``build.gradle`` (literal,
    ext var, or a module-local ``versions << ['X': '...']`` map used as
    ``${versions.X}``) — the fix falls back to the shared build.gradle path
    (``_apply_build_gradle_fix``) for those. Either way ``regenerate`` runs ``./gradlew updateShas`` to rewrite the
    per-module ``.jar.sha1`` dependency-license checksums so the
    ``dependencyLicenses`` precommit passes.
  - **plugin** (no catalog) — OpenSearch Gradle plugins. The fix edits the
    vulnerable dependency's version where it's declared in ``build.gradle``; there
    is no lockfile/checksum, so ``regenerate`` is a no-op — the text edit is the
    whole fix.

Plugin declaration forms handled:
  - **force literal** — ``resolutionStrategy { force "group:artifact:1.2.3" }``
  - **direct-dep literal** — ``implementation "group:artifact:1.2.3"``
  - **in-repo ext var** — ``force "group:artifact:${foo_version}"`` where
    ``foo_version = '1.2.3'`` is defined in this repo (build.gradle / gradle.properties)

Transitive dependencies (not declared anywhere, classified ``transitive`` by
origin_classifier) are pinned with a ``resolutionStrategy.force`` in the module that
resolves them: origin names the resolving build.gradle(s) — a single one is pinned
there (submodule scope, matching security#6550), several (or unusable origin) fall
back to a root ``allprojects`` cascade. Only when no direct declaration is found, so
a stale ``transitive`` classification can't override an on-HEAD declaration.
Per-owner multi-module pinning is deferred.

Out of scope (raised as ``RemediationUnsupported`` — a real CVE we can't auto-fix,
not an error): ``core_inherited`` (owned by core, fix upstream); undeclared and not
transitive (advisory package may not match this repo); and version indirection we
can't edit (``System.getProperty(...)`` etc.).
"""

import functools
import glob
import logging
import os
import re
import subprocess

import llm_planner
from remediation import (RemediationError, RemediationUnsupported, at_or_above,
                         new_branch_name)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

name = "maven"

# Files we scan for declarations and for resolving in-repo version variables.
_GRADLE_GLOBS = ("**/build.gradle", "**/gradle.properties")

# A Gradle version catalog at this path marks a "core"-style repo (OpenSearch
# core and anything else using a catalog); its absence marks a plugin.
_CATALOG_REL = os.path.join("gradle", "libs.versions.toml")

# Core checksum regen: ``updateShas`` downloads every dependency jar to rewrite
# the per-module ``.jar.sha1`` files (see regenerate). It's the long pole — a
# full run over core is ~2 min cold (gradle download + buildSrc compile + jar
# downloads), so the timeout is generous but still bounds a hung build.
_GRADLE_TASK = "updateShas"
_GRADLE_TIMEOUT = 900

# OpenSearch core's version catalog on main — source of truth for versions plugins
# inherit via ``${versions.X}``. Read-only lookup; see _core_managed_version.
_CORE_CATALOG_URL = (
    "https://raw.githubusercontent.com/opensearch-project/OpenSearch/"
    "main/gradle/libs.versions.toml"
)
_CORE_CATALOG_TIMEOUT = 15


def build_context(event, write_owner, base_owner):
    """Resolve the L2L event into a context dict for the shared flow.

    ``package`` arrives as a maven coordinate in either ``group/artifact`` (the
    scans-cluster form) or ``group:artifact`` (the advisory form); both normalize
    to the ``group:artifact`` used in build.gradle. Human-facing titles/branch use
    the bare artifact so they read cleanly (``Bump log4j-core to 2.25.4``).
    """
    package_name = (event.get("package") or "").strip()
    patched_version = (event.get("patched_version") or "").strip()
    cve_id = (event.get("cve_id") or "").strip()
    repo_name = (event.get("repo_name") or "").strip()
    if not (package_name and patched_version and cve_id and repo_name):
        raise RemediationError(
            "package, patched_version, cve_id and repo_name are all required."
        )

    coordinate = _to_colon_coord(package_name)
    artifact = coordinate.split(":")[-1]

    ctx = {
        "package_name": package_name,
        "coordinate": coordinate,
        "artifact": artifact,
        "patched_version": patched_version,
        "installed_version": (event.get("installed_version") or "").strip(),
        # direct / transitive / core_inherited / unknown, from the scan's origin
        # chain (see origin_classifier). Consulted only as a fallback when no
        # declaration is found: transitive -> force pin; core_inherited -> manual review.
        "declaration_class": (event.get("declaration_class") or "unknown").strip(),
        # Distinct build.gradle files the coordinate resolves in (distilled from the
        # scan origin by the Lambda; [] when absent/non-maven). Picks the force target.
        "origin_files": event.get("origin_files") or [],
        "cve_id": cve_id,
        "repo_name": repo_name,
        "write_owner": write_owner,
        "base_owner": base_owner,
        "base_branch": (event.get("base_branch") or "main").strip(),
        "branch_name": new_branch_name(cve_id, artifact),
        "bumped_sections": [],
    }
    ctx["commit_message"] = f"Bump {artifact} to {patched_version}"
    ctx["pr_title"] = ctx["commit_message"]
    installed = ctx["installed_version"] or "the affected version"
    ctx["pr_body"] = (
        f"Upgrades `{coordinate}` from {installed} to `{patched_version}`.\n\n"
        f"Addresses {cve_id}.\n\n"
        f"Opened automatically by the OSCAR CVE remediation flow."
    )
    return ctx


def apply_fix(work_dir, ctx):
    """Apply the version edit, branching on the repo's declaration style.

    A ``gradle/libs.versions.toml`` marks a core-style repo (version catalog): the
    fix bumps the catalog and ``regenerate`` rewrites the ``.jar.sha1`` checksums.
    Otherwise it's a plugin: edit the version in ``build.gradle`` and ``regenerate``
    is a no-op. ``ctx['is_core']`` records the branch so ``regenerate`` matches.
    """
    catalog = _catalog_path(work_dir)
    if catalog:
        ctx["is_core"] = True
        _apply_core_fix(work_dir, ctx, catalog)
        return
    ctx["is_core"] = False
    _apply_build_gradle_fix(work_dir, ctx)


def _apply_build_gradle_fix(work_dir, ctx):
    """Decide + apply the build.gradle edit (LLM-first, deterministic fallback).

    Used by BOTH repo styles — plugin repos (no catalog) and core repos for a
    coordinate that isn't in the version catalog (a submodule build.gradle dep).
    It only edits build.gradle; it does not depend on ``is_core`` and never
    changes it, so the caller's catalog/checksum decisions are unaffected.

    Asks the LLM planner to classify how the coordinate's version is declared, and
    applies verified edit plans (``edit_literal`` / ``edit_ext_var``) via the same
    primitives the deterministic scanner uses. Any other plan (``out_of_scope`` /
    ``none``), an unverifiable target, an invalid/absent plan, or a Bedrock failure
    all defer to ``_apply_fix_deterministic`` — the authoritative scanner — so the
    LLM can only cause a *verified* edit, never a wrong abstain or a wrong no-change.
    """
    plan = None
    sources = _gradle_sources(work_dir, ctx["coordinate"])
    # A coordinate the scan classified as transitive/core_inherited has no
    # declaration to locate, so skip the LLM planner (it would only return
    # out_of_scope) and let the deterministic scanner confirm there's no direct
    # declaration and then force (transitive) or defer to core (core_inherited).
    if sources and ctx.get("declaration_class") not in ("transitive", "core_inherited"):
        plan = llm_planner.plan_edit(ctx, sources)
    if plan is not None:
        logger.info("Applying LLM edit plan: %s", plan)
        if _apply_plan(work_dir, ctx, plan):
            return
        logger.info("LLM plan not applied (unverified/deferred); using scanner.")
    else:
        logger.info("No LLM plan; using deterministic scanner.")
    _apply_fix_deterministic(work_dir, ctx)


def _apply_plan(work_dir, ctx, plan):
    """Apply a verified LLM edit plan; return True if it fully handled the fix.

    Only ``edit_literal`` / ``edit_ext_var`` are acted on, and only when the named
    target is actually present (verified against the files). Everything else —
    ``out_of_scope``, ``none``, or a target that can't be confirmed — returns False
    so the deterministic scanner makes the authoritative decision.
    """
    action = plan["action"]
    patched = ctx["patched_version"]
    if action == "edit_ext_var":
        # target is either a plain ext var (``foo = '1.2.3'``) or a module-local
        # ``versions`` map key (``versions << ['foo': '1.2.3']`` used as
        # ${versions.foo}); try both, so the LLM's route holds for either form.
        target = plan["target"]
        result = _bump_variable(work_dir, target, patched)
        label = f"{target} (variable)"
        if result is None:
            result = _bump_versions_map(work_dir, target, patched)
            label = f"versions.{target} (variable)"
        if result is None:          # not defined in-repo -> let the scanner decide
            return False
        ctx["bumped_sections"] = [label] if result else []
        return True
    if action == "edit_literal":
        bumped = _edit_coordinate_literals(work_dir, ctx["coordinate"], patched)
        if bumped is None:          # no literal declaration found -> LLM mis-located
            return False
        ctx["bumped_sections"] = bumped   # [] => already patched (no_change)
        return True
    return False                    # out_of_scope / none -> deterministic decides


def _edit_coordinate_literals(work_dir, coord, patched):
    """Edit literal versions of ``coord`` across build.gradle(s), minimal-diff.

    Returns the list of bumped files ([] if only already-at/above-patched literals
    were found — a no-change), or None if no literal declaration of ``coord`` exists
    at all (so the caller falls back to the scanner). Shared by the LLM edit_literal
    path; the deterministic scanner has its own combined literal+var pass.
    """
    found_literal = False
    bumped = []
    for path in _find_files(work_dir, "**/build.gradle"):
        content = _read(path)
        edits = []
        for m, version_token in _declaration_matches(content, coord):
            if "$" in version_token:
                continue            # a variable reference, not a literal
            found_literal = True
            if at_or_above(version_token, patched):
                continue
            new_text = m.group(0).replace(version_token, patched, 1)
            edits.append((m.start(), m.end(), new_text))
            bumped.append(os.path.relpath(path, work_dir))
        for start, end, replacement in sorted(edits, reverse=True):
            content = content[:start] + replacement + content[end:]
        if edits:
            _write(path, content)
    return bumped if found_literal else None


def _gradle_sources(work_dir, coord, max_chars=20000):
    """build.gradle content to show the planner: prefer files that mention the
    artifact, else all build.gradle(s). Each block is ``# <relpath>\\n<content>``;
    capped so a huge multi-module repo can't blow the prompt."""
    artifact = coord.split(":")[-1] if ":" in coord else coord
    files = _find_files(work_dir, "**/build.gradle")
    contents = {path: _read(path) for path in files}  # read each file once
    blocks, total = [], 0
    # Files mentioning the artifact first (most likely to hold the declaration).
    ranked = sorted(files, key=lambda p: artifact not in contents[p])
    for path in ranked:
        block = f"# {os.path.relpath(path, work_dir)}\n{contents[path]}"
        if total + len(block) > max_chars and blocks:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------
# core (version catalog) path
# --------------------------------------------------------------------------

def _catalog_path(work_dir):
    """Absolute path to ``gradle/libs.versions.toml`` if this repo has one, else
    None. Its presence is what distinguishes a core-style repo from a plugin."""
    path = os.path.join(work_dir, _CATALOG_REL)
    return path if os.path.isfile(path) else None


def _apply_core_fix(work_dir, ctx, catalog):
    """Bump the coordinate's version key in the Gradle version catalog.

    LLM-first (mirrors the plugin path): the planner is shown the catalog and asked
    which ``[versions]`` key drives the coordinate (``catalog`` action). A verified
    key (confirmed present in ``[versions]``) is used; otherwise we fall back to a
    deterministic ``[libraries]`` lookup (match the coordinate's group+name, follow
    its ``version.ref``). If neither resolves a key the coordinate isn't in the
    catalog -> ``RemediationUnsupported``. The actual bump + the ``.jar.sha1``
    regen happen in ``_bump_catalog_version`` / ``regenerate``.
    """
    text = _read(catalog)
    coord = ctx["coordinate"]
    rel = os.path.relpath(catalog, work_dir)

    key = None
    plan = llm_planner.plan_edit(ctx, text, mode="catalog")
    if plan is not None:
        logger.info("Applying LLM catalog plan: %s", plan)
        if plan["action"] == "catalog" and _versions_key_present(text, plan["target"]):
            key = plan["target"]
        else:
            logger.info("LLM catalog plan not applied (unverified); using lookup.")
    if key is None:
        key = _version_ref_for_coordinate(text, coord)
    if key is None:
        # Not in the catalog: a core repo still declares some deps directly in a
        # submodule build.gradle (literal, ext var, or a module-local `versions <<
        # ['X': '...']` map used as ${versions.X}). Fall back to the same LLM-first
        # build.gradle path plugin repos use (deterministic scanner as authority).
        # is_core stays True, so regenerate still runs updateShas afterward.
        logger.info("%s not in %s; scanning build.gradle (submodule dep).",
                    coord, rel)
        _apply_build_gradle_fix(work_dir, ctx)
        return

    ctx["bumped_sections"] = _bump_catalog_version(catalog, rel, key,
                                                   ctx["patched_version"])
    if not ctx["bumped_sections"]:
        logger.info("catalog key %r already at/above %s; nothing to edit.",
                    key, ctx["patched_version"])


def _version_ref_for_coordinate(catalog_text, coord):
    """The ``[versions]`` key a coordinate maps to via its ``[libraries]`` entry.

    Catalog libraries read ``name = { group = "g", name = "a", version.ref = "key" }``;
    we match the entry whose group+name equal ``coord`` and return its ``version.ref``.
    Returns None if the coordinate has no library entry, or its entry pins an inline
    ``version = "..."`` (no ref) — that literal form isn't handled here.
    """
    group, _, artifact = coord.partition(":")
    entry = re.compile(
        r'''\{[^}]*?\bgroup\s*=\s*(["'])''' + re.escape(group) + r'''\1'''
        r'''[^}]*?\bname\s*=\s*(["'])''' + re.escape(artifact) + r'''\2'''
        r'''[^}]*?\bversion\.ref\s*=\s*(["'])([^"']+)\3[^}]*?\}''')
    m = entry.search(catalog_text)
    return m.group(4).strip() if m else None


def _versions_key_present(catalog_text, key):
    """True if ``key`` is defined in the catalog's ``[versions]`` table."""
    return bool(key) and _versions_assignment(key).search(catalog_text) is not None


def _http_get(url, timeout=_CORE_CATALOG_TIMEOUT):
    """GET ``url`` and return the body as text. Isolated so tests can stub it."""
    import urllib.request
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310 - https literal
        return resp.read().decode("utf-8", "replace")


@functools.lru_cache(maxsize=1)
def _core_catalog_text():
    """Core's version catalog, fetched once per process (memoized), or ``None`` on
    failure. Memoized so a batched run resolving many coordinates fetches it once
    rather than per coordinate.
    """
    try:
        return _http_get(_CORE_CATALOG_URL)
    except Exception as e:  # noqa: BLE001 - any fetch/network error -> unknown (None)
        logger.warning("core catalog fetch failed: %s", e)
        return None


def _core_managed_version(coord):
    """The version OpenSearch core manages for ``coord`` (via its catalog's
    ``[libraries]`` group+name -> ``version.ref`` -> ``[versions]``), or ``None`` when
    core doesn't manage it or the lookup fails. On None the caller falls back to a
    literal pin, never a wrong decline.
    """
    text = _core_catalog_text()
    if not text:
        return None
    ref = _version_ref_for_coordinate(text, coord)
    if not ref:
        return None
    m = _versions_assignment(ref).search(text)
    return m.group(2).strip() if m else None


def _core_inherited_unsupported(ctx, coord, fallback_msg):
    """``RemediationUnsupported`` for a core-inherited coordinate, naming core's
    managed version when core is confirmed below patched ("fix must come from core");
    else ``fallback_msg`` (lookup unavailable, core doesn't manage it, or core patched).
    """
    core_version = _core_managed_version(coord)
    if core_version is not None and not at_or_above(core_version, ctx["patched_version"]):
        return RemediationUnsupported(
            f"`{coord}` is inherited from OpenSearch core, which uses the vulnerable "
            f"version {core_version} (below the patched {ctx['patched_version']}). "
            f"Remediation must come from core, not {ctx['repo_name']}.")
    return RemediationUnsupported(fallback_msg)


def _versions_assignment(key):
    """Regex matching a ``key = "<version>"`` assignment (version group = 2)."""
    return re.compile(
        r'''(^\s*''' + re.escape(key) + r'''\s*=\s*")([^"]+)(")''', re.MULTILINE)


def _bump_catalog_version(catalog, rel, key, patched):
    """Edit ``key = "<version>"`` in the catalog to ``patched`` (minimal diff).

    Returns ``["<key> (catalog)"]`` if edited, ``[]`` if the key is already
    at/above ``patched`` (a no-change), and raises ``RemediationUnsupported`` if the
    key isn't in ``[versions]`` (a dangling ``version.ref`` — nothing safe to edit).
    """
    text = _read(catalog)
    m = _versions_assignment(key).search(text)
    if not m:
        raise RemediationUnsupported(
            f"catalog version key `{key}` is not defined in {rel}.")
    if at_or_above(m.group(2), patched):
        return []
    new_text = text[:m.start()] + f"{m.group(1)}{patched}{m.group(3)}" + text[m.end():]
    _write(catalog, new_text)
    logger.info("Bumped catalog %s: %s -> %s", key, m.group(2), patched)
    return [f"{key} (catalog)"]


def _apply_fix_deterministic(work_dir, ctx):
    """Edit the coordinate's version in build.gradle, in place (minimal diff).

    Scans every build.gradle for a ``"group:artifact:<version>"`` declaration.
    Literal versions are edited directly; a ``${var}`` reference is followed to an
    in-repo definition and that value edited. Records edited locations in
    ``ctx['bumped_sections']``. Raises ``RemediationUnsupported`` when the
    coordinate isn't declared here, or only via a core-inherited/indirect version
    we don't edit.
    """
    coord = ctx["coordinate"]
    patched = ctx["patched_version"]
    gradle_files = _find_files(work_dir, "**/build.gradle")
    if not gradle_files:
        raise RemediationUnsupported(
            f"{ctx['repo_name']} has no build.gradle to edit."
        )

    bumped = []
    unsupported_reasons = []
    vars_to_bump = set()
    versions_map_keys = set()
    # In-repo core-inherited version refs, as (reuse_token, catalog_key) pairs — the
    # transitive-force path can re-assert one instead of a literal.
    core_force_vars = []
    already_patched = False
    saw_declaration = False

    # Phase 1: apply LITERAL edits per file; collect referenced version vars.
    # Vars are bumped in phase 2 (which re-reads) so we never overwrite a literal
    # edit and a variable edit made to the same file.
    for path in gradle_files:
        content = _read(path)
        matches = list(_declaration_matches(content, coord))
        if not matches:
            continue
        saw_declaration = True
        edits = []  # (start, end, replacement) — applied in reverse so offsets hold
        for m, version_token in matches:
            if "$" in version_token:
                # A variable reference: resolve a simple in-repo ext var (braced
                # or bare); a core-inherited (${versions.X}) or otherwise indirect
                # one is out of scope.
                var = _var_name(version_token)
                map_key = _versions_map_key(version_token)
                if var is not None:
                    vars_to_bump.add(var)
                elif map_key is not None:
                    # ${versions.X}: resolvable only if X is set by a module-local
                    # `versions << ['X': '...']` map (else it's core-inherited).
                    versions_map_keys.add(map_key)
                else:
                    unsupported_reasons.append(
                        f"`{coord}` version is set indirectly "
                        f"(`{version_token}`), which isn't edited automatically.")
                continue
            # Literal version. Edit only this match's span (a shared literal like
            # 2.17.1 on a sibling artifact must not be cross-edited) by swapping
            # the version token inside the matched declaration text.
            if at_or_above(version_token, patched):
                already_patched = True
                continue
            new_text = m.group(0).replace(version_token, patched, 1)
            edits.append((m.start(), m.end(), new_text))
            bumped.append(os.path.relpath(path, work_dir))
        if edits:
            for start, end, replacement in sorted(edits, reverse=True):
                content = content[:start] + replacement + content[end:]
            _write(path, content)

    # Phase 2: bump in-repo version variables (reads files fresh, so a literal
    # edit from phase 1 in the same file is preserved).
    for var in sorted(vars_to_bump):
        result = _bump_variable(work_dir, var, patched)
        if result is None:
            unsupported_reasons.append(
                f"`{coord}` version comes from `${{{var}}}`, which isn't defined "
                f"in this repository (likely inherited from OpenSearch core).")
            core_force_vars.append((f"${{{var}}}", var))
        elif result:
            bumped.append(f"{var} (variable)")
        else:
            already_patched = True

    # Phase 2b: bump module-local `versions << ['key': '...']` map entries. A key
    # not defined in any such map is inherited from core (out of scope here).
    for key in sorted(versions_map_keys):
        result = _bump_versions_map(work_dir, key, patched)
        if result is None:
            unsupported_reasons.append(
                f"`{coord}` version comes from `${{versions.{key}}}`, which isn't "
                f"defined in this repository (likely inherited from OpenSearch core).")
            core_force_vars.append((f"${{versions.{key}}}", key))
        elif result:
            bumped.append(f"versions.{key} (variable)")
        else:
            already_patched = True

    ctx["bumped_sections"] = bumped
    if bumped:
        return

    dc = ctx.get("declaration_class")
    # A `transitive` coordinate (third-party parent) with nothing editable in-repo is
    # force-pinned in the resolving module — whether genuinely undeclared or only
    # "declared" via a core-managed `${versions.X}` a submodule BOM overrides (the
    # security#6550 pattern). So core-var refs don't block the force. `not
    # already_patched` keeps a stale transitive scan from forcing over an on-HEAD
    # declaration that's already >= patched (that stays no_change below).
    if dc == "transitive" and not already_patched:
        logger.info("%s transitive with nothing editable in-repo -> force in the "
                    "resolving module.", coord)
        # Offer any in-repo core-var ref to the force (re-assert the patched core
        # version, gated on it resolving >= patched; see _apply_force_resolution).
        ctx["force_var"] = core_force_vars[0] if core_force_vars else None
        _apply_force_resolution(work_dir, ctx)
        return
    if dc == "core_inherited":      # org.opensearch parent -> core owns the version
        raise _core_inherited_unsupported(
            ctx, coord,
            f"`{coord}` is inherited transitively from OpenSearch core. "
            f"It should be fixed in core, not {ctx['repo_name']}.")

    # Not transitive/core_inherited (direct/unknown). Prefer surfacing an
    # out-of-scope declaration for review over reporting no_change: another
    # declaration being already-patched does NOT prove the core-inherited/indirect
    # one is safe. When the blocker is a core-managed `${versions.X}` (core_force_vars
    # populated), enrich with core's actual version (see _core_inherited_unsupported).
    if unsupported_reasons:
        if core_force_vars:
            raise _core_inherited_unsupported(ctx, coord, unsupported_reasons[0])
        raise RemediationUnsupported(unsupported_reasons[0])
    if already_patched:
        # Declared but already >= patched (a fix landed since the scan). The
        # shared flow sees no changed files -> no_change.
        logger.info("%s already at/above %s; nothing to edit.", coord, patched)
        return
    if not saw_declaration:
        raise RemediationUnsupported(   # direct/unknown -> advisory package doesn't match
            f"`{coord}` is not declared in any build.gradle in {ctx['repo_name']} "
            f"(the advisory package may differ from what the plugin declares).")
    raise RemediationUnsupported(
        f"`{coord}` could not be remediated automatically.")


def _apply_force_resolution(work_dir, ctx):
    """Pin a transitive coordinate to the patched version in the resolving module.

    Reached only when the coordinate isn't declared directly. Origin names the
    resolving build.gradle(s): a single one is pinned there (submodule scope,
    matching security#6550); several distinct files, or no usable origin, fall back
    to a root ``allprojects`` force that cascades (precedented — alerting/sql). Raises
    ``RemediationUnsupported`` only when there's no root build.gradle. Per-owner
    multi-module pinning is deferred (root cascade is the current behavior).

    The pin is an LLM edit folded into the file's existing resolution block (verified);
    on any failure a fresh block is appended.
    """
    resolving = _resolving_build_files(work_dir, ctx.get("origin_files"))
    if len(resolving) == 1:
        target_rel = resolving[0]
    else:
        # No single resolving module (several, or no usable origin) -> root
        # build.gradle, whose allprojects force cascades to every subproject.
        target_rel = "build.gradle"
        if not os.path.isfile(os.path.join(work_dir, target_rel)):
            raise RemediationUnsupported(
                f"`{ctx['coordinate']}` is transitive but {ctx['repo_name']} has no "
                f"root build.gradle to pin it in.")
    target = os.path.join(work_dir, target_rel)
    original = _read(target)

    # Version to pin to: a core-managed ${versions.X} (reused when core >= patched)
    # or the literal patched version; may raise if core itself is vulnerable.
    force_token = _resolve_force_token(ctx)
    forced = f"{ctx['coordinate']}:{force_token}"

    # Let the LLM fold the pin into an existing resolution block (maintainer idiom:
    # one line into the module's configurations.all). It's told the exact token and to
    # double-quote a GString; _verify_force_edit confirms adds-only + right token +
    # double-quoting. On any failure, append a fresh block (correctly quoted).
    edit = llm_planner.write_force_edit(ctx, target_rel, original, version=force_token)
    if edit:
        old, new = edit["old_string"], edit["new_string"]
        if original.count(old) == 1:
            edited = original.replace(old, new, 1)
            if _verify_force_edit(original, edited, ctx["coordinate"],
                                  ctx["patched_version"], expected_token=force_token):
                _write(target, edited)
                logger.info("Applied verified LLM force edit for %s (%s) in %s",
                            ctx["coordinate"], force_token, target_rel)
                ctx["bumped_sections"] = [f"{target_rel} (force, llm)"]
                return
        logger.info("LLM force edit rejected (anchor not unique or unverified); "
                    "appending block to %s.", target_rel)

    _write(target, original.rstrip() + "\n\n" + _force_block(ctx, forced, target_rel) + "\n")
    logger.info("Appended resolutionStrategy.force for %s in %s", forced, target_rel)
    ctx["bumped_sections"] = [f"{target_rel} (force)"]


def _resolve_force_token(ctx):
    """The version token to pin a transitive coordinate to.

    Reuses an in-repo core-managed ``${versions.X}`` (``ctx['force_var']``) when core
    resolves it >= patched (maintainer idiom, auto-tracks core); raises
    ``RemediationUnsupported`` if core manages the coordinate but is itself below
    patched (fix belongs in core); else the literal patched version (always fixes).
    """
    coord = ctx["coordinate"]
    patched = ctx["patched_version"]
    core_version = _core_managed_version(coord)
    if core_version is not None and not at_or_above(core_version, patched):
        raise RemediationUnsupported(
            f"`{coord}` is managed by OpenSearch core, which uses the vulnerable "
            f"version {core_version} (below the patched {patched}). Remediation must "
            f"come from core, not {ctx['repo_name']}.")
    force_var = ctx.get("force_var")
    if force_var and core_version is not None and at_or_above(core_version, patched):
        return force_var[0]          # ${versions.X}: core is patched -> re-assert it
    return patched                   # literal


def _resolving_build_files(work_dir, origin_files):
    """The distinct ``origin_files`` (build.gradle relpaths, distilled from origin by
    the Lambda) that actually exist in the clone, sorted. Presence is confirmed so a
    stale/renamed module can't target a nonexistent file; empty when origin was
    absent/flat.
    """
    files = set()
    for rel in origin_files or []:
        if (isinstance(rel, str) and rel.endswith("build.gradle")
                and os.path.isfile(os.path.join(work_dir, rel))):
            files.add(rel)
    return sorted(files)


def _verify_force_edit(original, edited, coordinate, patched, expected_token=None):
    """True if ``edited`` adds ONLY a pin of ``coordinate`` to ``expected_token`` (the
    literal ``patched``, or a core-managed ``${versions.X}`` the caller re-asserts).

    Guards the LLM write so it can't pin a wrong version or touch another dependency:
      - additions only (every original line survives);
      - the added text references ``coordinate`` and ``expected_token``;
      - no literal version other than ``patched`` is introduced (a version token is a
        digit-led run after ':' / '@' / quote; a ``${...}`` var isn't one);
      - no maven ``group:artifact`` coordinate other than the target appears — blocks
        an extra ``coord:${var}`` pin the digit-led check can't see (e.g. the LLM
        "helpfully" pinning sibling family artifacts in var mode);
      - exactly ONE pin statement (``force``/``useVersion``) is added — a form-agnostic
        backstop for the above: an extra dep pinned via named-args or ``eachDependency``
        (which the coordinate regex above can't parse) still trips this;
      - a ``${...}`` GString pin must be DOUBLE-quoted (else it won't interpolate).
    Any violation -> False -> caller falls back to the deterministic append.
    """
    from collections import Counter
    expected = expected_token or patched
    removed = Counter(original.splitlines()) - Counter(edited.splitlines())
    if removed:                          # an existing line was changed or deleted
        return False
    added = "\n".join(
        (Counter(edited.splitlines()) - Counter(original.splitlines())).elements())
    if not added.strip():                # no-op edit
        return False
    artifact = coordinate.split(":")[-1]
    if expected not in added or (coordinate not in added and artifact not in added):
        return False
    # Every literal (digit-led) version token in the addition must be `patched`
    # (a ${...} var isn't digit-led, so it's exempt — quoting checked below).
    for token in re.findall(r"""[:@'"](\d[\w.\-]*)""", added):
        if token != patched:
            return False
    # Every maven coordinate (``"group:artifact:"``) in the addition must be the
    # target — rejects an extra dependency pinned via a var (literal extras are
    # already caught above).
    for m in re.finditer(r"""["']([\w.\-]+:[\w.\-]+):""", added):
        if m.group(1) != coordinate:
            return False
    # Exactly one pin statement — form-agnostic backstop for an extra dep added via
    # named-args / eachDependency (which the coordinate regex above can't parse).
    if len(re.findall(r"""\b(?:force|useVersion)\b\s*[("']""", added)) != 1:
        return False
    if "${" in expected and f'"{coordinate}:{expected}"' not in added:  # GString needs "..."
        return False
    return True


def _force_block(ctx, forced_coord, target_rel="build.gradle"):
    """The resolutionStrategy.force block text pinning ``forced_coord``.

    Root build.gradle wraps the pin in ``allprojects`` (cascades to subprojects); a
    submodule uses a bare ``configurations.all`` (already scoped; matches
    security#6550). Double-quoted when ``forced_coord`` embeds a ``${...}`` GString
    (only interpolates in double quotes), single-quoted for a literal.
    """
    q = '"' if "${" in forced_coord else "'"
    comment = (
        f"// Pin {ctx['coordinate']} to a patched version for {ctx['cve_id']} "
        f"(transitive dependency; not declared directly).\n"
    )
    if target_rel == "build.gradle":
        return (
            comment
            + "allprojects {\n"
            "    configurations.all {\n"
            "        resolutionStrategy {\n"
            f"            force {q}{forced_coord}{q}\n"
            "        }\n"
            "    }\n"
            "}"
        )
    return (
        comment
        + "configurations.all {\n"
        "    resolutionStrategy {\n"
        f"        force {q}{forced_coord}{q}\n"
        "    }\n"
        "}"
    )


def regenerate(work_dir, ctx):
    """Rewrite dependency-license checksums for core; no-op for plugins.

    Plugins have no lockfile/checksums, so the catalog/build.gradle edit is the
    whole fix. Core repos ship a ``<module>/licenses/<artifact>-<version>.jar.sha1``
    per dependency, guarded by the ``dependencyLicenses`` precommit; after a version
    bump those are stale, so we run ``./gradlew updateShas`` which downloads the new
    jars, writes the new ``.jar.sha1`` files, and deletes the orphaned old ones.

    Skips the run when the edit was a no-change (nothing bumped). A gradle failure
    is fatal (``RemediationError``): a catalog bump without matching checksums would
    fail ``dependencyLicenses``, so we must not open a PR with stale shas.
    """
    if not ctx.get("is_core") or not ctx.get("bumped_sections"):
        return
    wrapper = os.path.join(work_dir, "gradlew")
    if not os.path.isfile(wrapper):
        raise RemediationError(
            f"{ctx['repo_name']} has a version catalog but no gradlew wrapper; "
            f"cannot regenerate .jar.sha1 checksums.")
    logger.info("Running ./gradlew %s to regenerate .jar.sha1 checksums ...",
                _GRADLE_TASK)
    try:
        result = subprocess.run(
            ["./gradlew", _GRADLE_TASK, "--console=plain", "--no-daemon"],
            cwd=work_dir, capture_output=True, text=True, timeout=_GRADLE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RemediationError(
            f"./gradlew {_GRADLE_TASK} timed out after {_GRADLE_TIMEOUT}s.")
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-1500:]
        raise RemediationError(
            f"./gradlew {_GRADLE_TASK} failed (exit {result.returncode}): {tail}")
    logger.info("Checksum regeneration complete.")


def summary(ctx):
    where = ", ".join(ctx.get("bumped_sections")
                      or ["the version catalog" if ctx.get("is_core") else "build.gradle"])
    checksums = " and regenerated .jar.sha1 checksums" if ctx.get("is_core") else ""
    return (
        f"Bumped {ctx['coordinate']} to {ctx['patched_version']} in {where}"
        f"{checksums} and opened a pull request for {ctx['cve_id']}."
    )


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _declaration_matches(content, coord):
    """Yield ``(match, version_token)`` for each declaration of ``coord``.

    Handles both dependency syntaxes OpenSearch plugins use:
      - colon string:  ``"group:artifact:version"`` (force + shorthand deps)
      - named args:    ``group: 'group', name: 'artifact', version: 'version'``
        (the map form used by implementation/api/compileOnly)
    ``match.group(0)`` is the full declaration text (so the caller can swap the
    version within just that span); the yielded token is the version.
    """
    group, _, artifact = coord.partition(":")
    colon = re.compile(r'''(["'])''' + re.escape(coord) + r''':([^"']+)\1''')
    for m in colon.finditer(content):
        yield m, m.group(2).strip()
    # Named-arg / map form, standard group -> name -> version order (comma- and
    # whitespace/newline-separated). Other arg orders are rare in these repos.
    named = re.compile(
        r'''group:\s*(["'])''' + re.escape(group) + r'''\1\s*,\s*'''
        r'''name:\s*(["'])''' + re.escape(artifact) + r'''\2\s*,\s*'''
        r'''version:\s*(["'])([^"']+)\3''')
    for m in named.finditer(content):
        yield m, m.group(4).strip()


def _to_colon_coord(package_name):
    """Normalize ``group/artifact`` (cluster) or ``group:artifact`` to colon form.

    The group holds dots and the artifact holds no separator, so the single ``/``
    (if present) is the group/artifact boundary.
    """
    if "/" in package_name:
        group, _, artifact = package_name.partition("/")
        return f"{group}:{artifact}"
    return package_name


def _var_name(version_token):
    """Simple ext-var name from a ``${name}`` or bare ``$name`` token, else None.

    ``${foo_version}`` / ``$foo_version`` -> ``foo_version`` (a bare identifier we
    can resolve in the repo). ``${versions.httpcore5}`` / ``$versions.httpcore5``
    / ``${props.getProperty('x')}`` -> None (dotted / call = core-inherited or
    indirection, out of scope).
    """
    for pattern in (r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}",
                    r"\$([A-Za-z_][A-Za-z0-9_]*)"):
        m = re.fullmatch(pattern, version_token)
        if m:
            return m.group(1)
    return None


def _bump_variable(work_dir, var, patched):
    """Edit ``var = '<version>'`` assignments to ``patched`` across the repo.

    Searches every build.gradle + gradle.properties and edits EVERY assignment of
    the var — a version var can be set in more than one file AND more than once
    within a file (e.g. redeclared per configuration). Returns True if any
    assignment was edited, False if the var is defined but every occurrence is
    already at/above ``patched``, or None if it isn't defined anywhere in the repo.
    """
    assign = re.compile(
        r'''(\b''' + re.escape(var) + r'''\s*=\s*)(["']?)([^"'\s]+)(["']?)''')
    found = False
    edited = False
    for path in _find_files(work_dir, *_GRADLE_GLOBS):
        content = _read(path)
        # Collect all assignments in this file; apply in reverse so earlier edits
        # don't shift later spans. A var assigned several times is fully bumped.
        edits = []
        for m in assign.finditer(content):
            found = True
            current = m.group(3)
            if at_or_above(current, patched):
                continue
            edits.append((m.start(), m.end(),
                          f"{m.group(1)}{m.group(2)}{patched}{m.group(4)}"))
        if not edits:
            continue
        for start, end, replacement in sorted(edits, reverse=True):
            content = content[:start] + replacement + content[end:]
        _write(path, content)
        logger.info("Bumped %s -> %s (%d occurrence(s)) in %s", var, patched,
                    len(edits), os.path.relpath(path, work_dir))
        edited = True
    if not found:
        return None
    return edited


def _versions_map_key(version_token):
    """Map key ``X`` from a ``${versions.X}`` / ``$versions.X`` token, else None.

    OpenSearch core submodules extend a shared ``versions`` map (``versions <<
    ['X': '1.2.3']``) and reference it as ``${versions.X}``. Unlike a bare
    ``${foo}`` (handled by ``_var_name``), this dotted form is resolvable ONLY if
    ``X`` is set by such an in-repo map (checked by ``_bump_versions_map``); if not,
    ``versions.X`` is inherited from core's build-tools and out of scope.
    """
    for pattern in (r"\$\{versions\.([A-Za-z_][A-Za-z0-9_]*)\}",
                    r"\$versions\.([A-Za-z_][A-Za-z0-9_]*)"):
        m = re.fullmatch(pattern, version_token)
        if m:
            return m.group(1)
    return None


def _bump_versions_map(work_dir, key, patched):
    """Edit a module-local ``versions`` map entry for ``key`` to ``patched``.

    Handles the forms OpenSearch submodules use to set ``versions.<key>`` in-repo:
    a map-literal entry (``'key': '1.2.3'`` inside ``versions << [ ... ]``), a
    ``versions.key = '1.2.3'`` assignment, or ``versions['key'] = '1.2.3'``. Edits
    EVERY matching entry across all files (a key can be set more than once, in more
    than one file). Returns True if any was edited, False if all definitions are
    already at/above ``patched``, or None if ``key`` isn't set by any in-repo map
    (so it's inherited from core — out of scope).
    """
    k = re.escape(key)
    # Each pattern captures the (quote, version, quote) triple so we can swap the
    # version literal and keep the surrounding syntax (quotes / separator) untouched.
    patterns = (
        re.compile(r'''(["']''' + k + r'''["']\s*:\s*)(["'])([^"']+)(["'])'''),   # map entry
        re.compile(r'''(\bversions\.''' + k + r'''\s*=\s*)(["'])([^"']+)(["'])'''),  # versions.key =
        re.compile(r'''(\bversions\[\s*["']''' + k + r'''["']\s*\]\s*=\s*)(["'])([^"']+)(["'])'''),  # versions['key'] =
    )
    found = False
    edited = False
    for path in _find_files(work_dir, "**/build.gradle"):
        content = _read(path)
        # Collect every match of every pattern, then apply in reverse so earlier
        # edits don't shift later spans (the syntaxes don't overlap, so no dup spans).
        edits = []
        for pat in patterns:
            for m in pat.finditer(content):
                found = True
                if at_or_above(m.group(3), patched):
                    continue
                edits.append((m.start(), m.end(),
                              f"{m.group(1)}{m.group(2)}{patched}{m.group(4)}"))
        if not edits:
            continue
        for start, end, replacement in sorted(edits, reverse=True):
            content = content[:start] + replacement + content[end:]
        _write(path, content)
        logger.info("Bumped versions.%s -> %s (%d occurrence(s)) in %s", key, patched,
                    len(edits), os.path.relpath(path, work_dir))
        edited = True
    if not found:
        return None
    return edited


def _find_files(work_dir, *patterns):
    found = []
    for pat in patterns:
        found.extend(glob.glob(os.path.join(work_dir, pat), recursive=True))
    return sorted(set(found))


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
