# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""npm / yarn ecosystem strategy.

Fixes a CVE in a JavaScript project by bumping the vulnerable package, routed by
where it's declared in package.json:

  - direct dependency, no resolution -> ``yarn upgrade <pkg>@<version>``
  - in ``resolutions`` (alone or also a direct dep) -> edit the resolution value
    (and any direct-dep version), then ``yarn install``
  - undeclared transitive -> add a ``resolutions`` entry, then ``yarn install``

then regenerating ``yarn.lock``.

Toolchain is baked into the image (Node 22 / yarn 1.22, matching what
OpenSearch-Dashboards CI reads from its ``.nvmrc`` + ``engines.yarn`` on main).
Reading the toolchain per-repo dynamically is deferred.
"""

import json
import logging
import os
import re
import subprocess

from remediation import RemediationError, new_branch_name

logger = logging.getLogger()

name = "npm"

# package.json sections we will edit, in the order we report them.
_MANIFEST_SECTIONS = ("dependencies", "devDependencies", "resolutions")

# Timeout (seconds) for yarn install/upgrade — the long pole (a large repo like
# OpenSearch-Dashboards installs in ~2-3 min; this leaves headroom). Bounds a
# hung yarn since Fargate has no max task duration.
YARN_TIMEOUT = 600


def build_context(event, write_owner, base_owner):
    """Resolve the L2L event into a context dict for the shared flow.

    ``write_owner`` is the fork the fix branch is pushed to; ``base_owner`` is
    the repo cloned from and the PR is opened against (see remediation.py).
    """
    package_name = (event.get("package") or "").strip()
    patched_version = (event.get("patched_version") or "").strip()
    cve_id = (event.get("cve_id") or "").strip()
    repo_name = (event.get("repo_name") or "").strip()
    if not (package_name and patched_version and cve_id and repo_name):
        raise RemediationError(
            "package, patched_version, cve_id and repo_name are all required."
        )

    ctx = {
        "package_name": package_name,
        "patched_version": patched_version,
        "installed_version": (event.get("installed_version") or "").strip(),
        "cve_id": cve_id,
        "repo_name": repo_name,
        "write_owner": write_owner,
        "base_owner": base_owner,
        "base_branch": (event.get("base_branch") or "main").strip(),
        "branch_name": new_branch_name(cve_id, package_name),
    }
    # Generic title/commit (the CVE id is kept out of public-facing titles); the
    # CVE is recorded in the PR body and the branch name.
    ctx["commit_message"] = f"Bump {package_name} to {patched_version}"
    ctx["pr_title"] = ctx["commit_message"]
    installed = ctx["installed_version"] or "the affected version"
    ctx["pr_body"] = (
        f"Upgrades `{package_name}` from {installed} to `{patched_version}` and "
        f"regenerates the lockfile.\n\nAddresses {cve_id}.\n\n"
        f"Opened automatically by the OSCAR CVE remediation flow."
    )
    return ctx


def apply_fix(work_dir, ctx):
    """Make the package.json edit and set ``ctx['method']`` for regenerate, per
    the routing in the module docstring. The resolution and undeclared-transitive
    cases edit package.json here; the direct-dep case makes no edit and defers to
    ``yarn upgrade`` in regenerate. Edits use minimal-diff text replacement (never
    a JSON round-trip, which would reformat the whole file) and are validated as
    JSON before writing.
    """
    pkg_path = os.path.join(work_dir, "package.json")
    with open(pkg_path) as f:
        content = f.read()

    manifest = json.loads(content)
    package_name = ctx["package_name"]
    patched = ctx["patched_version"]

    declarations = _find_declarations(manifest, package_name)
    in_resolutions = any(sec == "resolutions" for sec, _ in declarations)
    dep_decl = next(
        ((sec, cur) for sec, cur in declarations
         if sec in ("dependencies", "devDependencies")), None,
    )

    if in_resolutions:
        # Edit every place it's declared (the resolution, plus any direct-dep
        # version for consistency), then yarn install.
        edited, bumped = _edit_versions(content, package_name, patched, declarations)
        _write_if_valid(pkg_path, content, edited)
        ctx["method"] = "install" if bumped else "none"
        ctx["bumped_sections"] = bumped
    elif dep_decl:
        # Direct dependency with no resolution -> targeted yarn upgrade.
        _section, current = dep_decl
        if _at_or_above(current, patched):
            ctx["method"] = "none"          # already patched; nothing to do
            ctx["bumped_sections"] = []
        else:
            ctx["method"] = "upgrade"       # regenerate runs yarn upgrade
            ctx["bumped_sections"] = [_section]
    else:
        # Undeclared: only pin it if it's genuinely a transitive dependency of
        # this repo (present in yarn.lock). Otherwise it isn't in the tree at all
        # (stale scan / wrong resolve / removed dep), and adding a resolution
        # would be a dead pin that fixes nothing.
        if not _in_lockfile(work_dir, package_name):
            raise RemediationError(
                f"{package_name} is not a dependency of this repository — it is "
                f"not declared in package.json and not present in yarn.lock, so "
                f"there is nothing to remediate."
            )
        # Undeclared transitive -> add a resolutions entry, then yarn install.
        edited = _add_resolution(content, manifest, package_name, patched)
        _write_if_valid(pkg_path, content, edited)
        ctx["method"] = "install"
        ctx["bumped_sections"] = ["resolutions (added)"]


def regenerate(work_dir, ctx):
    """Regenerate yarn.lock per ``ctx['method']`` (set by apply_fix):

      - ``upgrade``: ``yarn upgrade <pkg>@<version>`` (direct dep).
      - ``install``: ``yarn install`` (resolution / added resolution).
      - ``none``: already patched; no-op.
    """
    method = ctx.get("method", "install")
    if method == "none":
        logger.info("Already at/above the patched version; no regenerate needed.")
        return

    # Lambda only allows writes under /tmp — point HOME and caches there.
    # --ignore-scripts skips postinstall hooks (e.g. cypress) that fail in the
    # sandbox (we only need yarn.lock, not a usable node_modules).
    # --ignore-engines tolerates a Node/yarn engine mismatch between the baked
    # image and the target repo so the install/upgrade doesn't fail on it.
    env = {
        **os.environ,
        "HOME": "/tmp",
        "YARN_CACHE_FOLDER": "/tmp/.yarn-cache",
        "npm_config_cache": "/tmp/.npm",
    }
    common = ["--ignore-scripts", "--ignore-engines", "--non-interactive"]
    if method == "upgrade":
        spec = f"{ctx['package_name']}@{ctx['patched_version']}"
        cmd = ["yarn", "upgrade", spec, *common]
    else:
        cmd = ["yarn", "install", *common]

    logger.info("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True,
                                env=env, timeout=YARN_TIMEOUT)
    except subprocess.TimeoutExpired:
        # Fargate won't stop a hung task on its own, so bound the install/upgrade.
        raise RemediationError(f"yarn {cmd[1]} timed out after {YARN_TIMEOUT}s")
    if result.returncode != 0:
        logger.error("%s failed: %s", cmd[1], result.stderr[-500:])
        raise RemediationError(f"yarn {cmd[1]} failed: {result.stderr[-300:]}")


def summary(ctx):
    where = ", ".join(ctx.get("bumped_sections") or ["package.json"])
    return (
        f"Bumped {ctx['package_name']} to {ctx['patched_version']} in {where}, "
        f"regenerated yarn.lock, and opened a pull request for {ctx['cve_id']}."
    )


# --------------------------------------------------------------------------
# package.json helpers
# --------------------------------------------------------------------------

def _find_declarations(manifest, package_name):
    """``[(section, current_version), ...]`` for every section declaring the pkg."""
    found = []
    for section in _MANIFEST_SECTIONS:
        block = manifest.get(section)
        if isinstance(block, dict) and package_name in block:
            found.append((section, str(block[package_name])))
    return found


def _in_lockfile(work_dir, package_name):
    """True if ``package_name`` appears as a resolved entry in yarn.lock.

    Confirms an undeclared package is actually a transitive dependency of the
    repo (in the resolved tree) before we pin it via ``resolutions``. yarn.lock
    entry headers start at column 0 — ``pkg@range, ...:`` or ``"@scope/pkg@range":``
    — so a header line for this package proves it's in the tree.
    """
    lock_path = os.path.join(work_dir, "yarn.lock")
    if not os.path.exists(lock_path):
        return False
    header = re.compile(r'^"?' + re.escape(package_name) + r'@')
    with open(lock_path, encoding="utf-8", errors="replace") as f:
        return any(header.match(line) for line in f)


def _edit_versions(content, package_name, patched, declarations):
    """Bump the package version in each declared section (minimal-diff regex).

    Skips a section already at/above ``patched`` (avoids a downgrade if a fix
    landed since the scan). Returns ``(edited_content, bumped_sections)``.
    """
    edited = content
    bumped = []
    for section, current in declarations:
        if _at_or_above(current, patched):
            logger.info("%s in %s is already %s (>= %s); skipping",
                        package_name, section, current, patched)
            continue
        new_value = _version_prefix(current) + patched
        # re.subn is global, so if two sections pin the SAME value one call
        # already rewrote both — the section is still remediated, so record it
        # regardless of this call's substitution count.
        edited, _ = _replace_version(edited, package_name, current, new_value)
        logger.info("Bumped %s in %s: %s -> %s",
                    package_name, section, current, new_value)
        bumped.append(section)
    return edited, bumped


def _write_if_valid(pkg_path, original, edited):
    """Write ``edited`` to package.json only if it changed AND is valid JSON.

    Validating before writing means a bad text edit can never produce a
    malformed package.json that we'd commit and push.
    """
    if edited == original:
        return
    try:
        json.loads(edited)
    except ValueError as e:
        raise RemediationError(f"edited package.json is not valid JSON: {e}")
    with open(pkg_path, "w") as f:
        f.write(edited)


def _add_resolution(content, manifest, package_name, patched):
    """Insert a ``resolutions`` entry for an undeclared transitive (minimal-diff).

    Handles an existing non-empty block (insert as the first entry, matching its
    indentation), an empty ``{}`` block, and no block at all (add one before the
    final closing brace). The result is JSON-validated by the caller.
    """
    entry = f'"{package_name}": "{patched}"'
    res = manifest.get("resolutions")

    if isinstance(res, dict) and res:
        # Insert as the first entry, matching the existing entries' indentation.
        m = re.search(r'"resolutions"\s*:\s*\{\r?\n([ \t]+)', content)
        if not m:
            raise RemediationError("could not locate the resolutions block to extend")
        indent = m.group(1)
        return content[:m.end()] + f"{entry},\n{indent}" + content[m.end():]

    if isinstance(res, dict):  # empty {}
        return re.sub(r'"resolutions"\s*:\s*\{\s*\}',
                      '"resolutions": {\n    ' + entry + '\n  }', content, count=1)

    # No resolutions block — add one before the final top-level closing brace.
    m = re.search(r'\n([ \t]*)\}\s*$', content)
    if not m:
        raise RemediationError("could not add a resolutions block to package.json")
    indent = m.group(1)
    block = f',\n{indent}  "resolutions": {{\n{indent}    {entry}\n{indent}  }}'
    return content[:m.start()] + block + content[m.start():]


def _version_prefix(version_spec):
    """Leading range operator of a version spec (``^``, ``~``, ``>=`` …), or ''.

    Preserving it means ``^4.0.4`` bumps to ``^4.0.6`` and an exact ``4.0.4``
    bumps to ``4.0.6``.
    """
    m = re.match(r"^\s*([~^>=<]+)", version_spec)
    return m.group(1) if m else ""


def _replace_version(content, package_name, current, new_value):
    """Replace ``"pkg": "current"`` with ``"pkg": "new_value"`` in raw text.

    Tolerant of whitespace around the colon. Returns ``(new_content, n_subs)``.
    """
    pattern = (
        re.escape(f'"{package_name}"') + r"(\s*:\s*)" + re.escape(f'"{current}"')
    )
    replacement = f'"{package_name}"' + r"\1" + f'"{new_value}"'
    return re.subn(pattern, replacement, content)


def _at_or_above(version_spec, patched):
    """Best-effort: is the declared version already >= ``patched``?

    Compares numeric release components (ignoring range operators + suffixes).
    Returns False when it can't tell, so we default to bumping — this only guards
    against a downgrade if a fix landed between the scan and remediation.
    """
    cur = _release_tuple(version_spec)
    tgt = _release_tuple(patched)
    if cur is None or tgt is None:
        return False
    return cur >= tgt


def _release_tuple(version_spec):
    """``(major, minor, patch, ...)`` ints from a version spec, or None."""
    m = re.search(r"(\d+(?:\.\d+)*)", version_spec or "")
    if not m:
        return None
    try:
        return tuple(int(p) for p in m.group(1).split("."))
    except ValueError:
        return None
