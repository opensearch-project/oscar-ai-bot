# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""maven / Gradle ecosystem strategy (OpenSearch plugins).

Fixes a CVE in a Gradle plugin by editing the vulnerable dependency's version
where it's declared in ``build.gradle``. OpenSearch plugins have no version
catalog and no lockfile, so there is nothing to regenerate — editing the
declaration text IS the whole fix (``regenerate`` is a no-op).

Declaration forms this slice handles (see cve-remediation-maven.md):
  - **force literal** — ``resolutionStrategy { force "group:artifact:1.2.3" }``
  - **direct-dep literal** — ``implementation "group:artifact:1.2.3"``
  - **in-repo ext var** — ``force "group:artifact:${foo_version}"`` where
    ``foo_version = '1.2.3'`` is defined in this repo (build.gradle / gradle.properties)

Out of scope (raised as ``RemediationUnsupported`` — a real CVE we can't
auto-fix here, not an error):
  - the coordinate isn't declared in any build.gradle (e.g. the advisory names a
    sub-artifact the plugin doesn't declare)
  - the version comes from a core-inherited map (``${versions.X}``) or other
    indirection (``System.getProperty(...)``) not defined in this repo
"""

import glob
import logging
import os
import re

import llm_planner
from remediation import (RemediationError, RemediationUnsupported, at_or_above,
                         new_branch_name)

logger = logging.getLogger()

name = "maven"

# Files we scan for declarations and for resolving in-repo version variables.
_GRADLE_GLOBS = ("**/build.gradle", "**/gradle.properties")


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
    """No-op: Gradle plugins have no lockfile/checksums; the edit is the fix."""
    return


def summary(ctx):
    where = ", ".join(ctx.get("bumped_sections") or ["build.gradle"])
    return (
        f"Bumped {ctx['coordinate']} to {ctx['patched_version']} in {where} "
        f"and opened a pull request for {ctx['cve_id']}."
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
