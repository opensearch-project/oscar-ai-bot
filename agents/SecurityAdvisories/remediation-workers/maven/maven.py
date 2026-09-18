# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""maven / Gradle ecosystem strategy (OpenSearch plugins + core).

One worker, two declaration styles — it branches on how the repo declares
dependency versions:

  - **core** (``gradle/libs.versions.toml`` present) — OpenSearch core and any
    repo using a Gradle version catalog. The fix bumps the ``[versions]`` key the
    coordinate maps to (via its ``[libraries]`` ``version.ref``); ``regenerate``
    then runs ``./gradlew updateShas`` to rewrite the per-module ``.jar.sha1``
    dependency-license checksums so the ``dependencyLicenses`` precommit passes.
  - **plugin** (no catalog) — OpenSearch Gradle plugins. The fix edits the
    vulnerable dependency's version where it's declared in ``build.gradle``; there
    is no lockfile/checksum, so ``regenerate`` is a no-op — the text edit is the
    whole fix.

Plugin declaration forms handled (see cve-remediation-maven.md):
  - **force literal** — ``resolutionStrategy { force "group:artifact:1.2.3" }``
  - **direct-dep literal** — ``implementation "group:artifact:1.2.3"``
  - **in-repo ext var** — ``force "group:artifact:${foo_version}"`` where
    ``foo_version = '1.2.3'`` is defined in this repo (build.gradle / gradle.properties)

Out of scope (raised as ``RemediationUnsupported`` — a real CVE we can't
auto-fix here, not an error):
  - the coordinate isn't declared in any build.gradle / the catalog
  - (plugin) the version comes from a core-inherited map (``${versions.X}``) or
    other indirection (``System.getProperty(...)``) not defined in this repo
"""

import glob
import logging
import os
import re
import subprocess

import llm_planner
from remediation import (RemediationError, RemediationUnsupported, at_or_above,
                         new_branch_name)

logger = logging.getLogger()

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
    _apply_plugin_fix(work_dir, ctx)


def _apply_plugin_fix(work_dir, ctx):
    """Decide + apply the build.gradle edit (LLM-first, deterministic fallback).

    Asks the LLM planner to classify how the coordinate's version is declared, and
    applies verified edit plans (``edit_literal`` / ``edit_ext_var``) via the same
    primitives the deterministic scanner uses. Any other plan (``out_of_scope`` /
    ``none``), an unverifiable target, an invalid/absent plan, or a Bedrock failure
    all defer to ``_apply_fix_deterministic`` — the authoritative scanner — so the
    LLM can only cause a *verified* edit, never a wrong abstain or a wrong no-change.
    """
    plan = None
    sources = _gradle_sources(work_dir, ctx["coordinate"])
    if sources:
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
        result = _bump_variable(work_dir, plan["target"], patched)
        if result is None:          # var not defined in-repo -> let the scanner decide
            return False
        ctx["bumped_sections"] = [f"{plan['target']} (variable)"] if result else []
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
    blocks, total = [], 0
    # Files mentioning the artifact first (most likely to hold the declaration).
    ranked = sorted(files, key=lambda p: artifact not in _read(p))
    for path in ranked:
        block = f"# {os.path.relpath(path, work_dir)}\n{_read(path)}"
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
        raise RemediationUnsupported(
            f"`{coord}` has no [libraries] entry in {rel} "
            f"({ctx['repo_name']}), so its catalog version key can't be resolved.")

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
                if var is None:
                    unsupported_reasons.append(
                        f"`{coord}` version is set indirectly "
                        f"(`{version_token}`), which isn't edited automatically.")
                else:
                    vars_to_bump.add(var)
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
        elif result:
            bumped.append(f"{var} (variable)")
        else:
            already_patched = True

    ctx["bumped_sections"] = bumped
    if bumped:
        return
    # Prefer surfacing an out-of-scope declaration for review over reporting
    # no_change: another declaration being already-patched does NOT prove the
    # core-inherited/indirect one is safe.
    if unsupported_reasons:
        raise RemediationUnsupported(unsupported_reasons[0])
    if already_patched:
        # Declared but already >= patched (a fix landed since the scan). The
        # shared flow sees no changed files -> no_change.
        logger.info("%s already at/above %s; nothing to edit.", coord, patched)
        return
    if not saw_declaration:
        raise RemediationUnsupported(
            f"`{coord}` is not declared in any build.gradle in {ctx['repo_name']} "
            f"(the advisory package may differ from what the plugin declares).")
    raise RemediationUnsupported(
        f"`{coord}` could not be remediated automatically.")


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

    Searches every build.gradle + gradle.properties and edits the assignment in
    EACH file that defines the var (a version var can be set/redefined in more
    than one file). Returns True if any file was edited, False if the var is
    defined but every definition is already at/above ``patched``, or None if it
    isn't defined anywhere in the repo.
    """
    assign = re.compile(
        r'''(\b''' + re.escape(var) + r'''\s*=\s*)(["']?)([^"'\s]+)(["']?)''')
    found = False
    edited = False
    for path in _find_files(work_dir, *_GRADLE_GLOBS):
        content = _read(path)
        m = assign.search(content)
        if not m:
            continue
        found = True
        current = m.group(3)
        if at_or_above(current, patched):
            continue
        new_content = content[:m.start()] + \
            f"{m.group(1)}{m.group(2)}{patched}{m.group(4)}" + content[m.end():]
        _write(path, new_content)
        logger.info("Bumped %s: %s -> %s in %s", var, current, patched,
                    os.path.relpath(path, work_dir))
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
