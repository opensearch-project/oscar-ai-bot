#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Remediation Handler for Security Advisories Lambda Functions.

Backs the ``remediate_cve`` action group. Today this handler performs only the
**pre-flight existing-PR check** — before any remediation work is attempted, it
asks GitHub whether the target repository already has an open pull request that
fixes this CVE (from Dependabot, Mend, or a human maintainer). If one exists,
remediation is skipped and the existing PR is surfaced; this both avoids
duplicate PRs and is cheap enough to run before spinning up any heavier work.

Important repo detail: the check reads the **upstream org repository**
(``opensearch-project/<repo>``), NOT a bot fork — the PRs we must not duplicate
live upstream, not on a fork. Reading open PRs on a public repo needs no
credentials, so this check runs unauthenticated (a token is used only if one
happens to be present in the environment, purely to raise the rate limit).

The actual remediation (clone -> edit -> regenerate -> push -> open PR) is done
by per-ecosystem container-image Lambdas, invoked from here once they exist.
Until then, a "no existing PR" result returns a placeholder indicating that
remediation execution is not yet wired.

Functions:
    handle_remediate_cve: Handle remediate_cve requests (existing-PR check).
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests
from aws_utils import get_latest_scans_index, opensearch_request
from query_utils import connection_error, error_response

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

GITHUB_API = 'https://api.github.com'


def _int_env(name: str, default: int) -> int:
    """Read an int env var, falling back to ``default`` on a missing/bad value.

    Parsed at import; a bad value must not raise (this module is imported by the
    Lambda entrypoint, so a raise here would break every function, not just
    remediate_cve).
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r; using default %d", name, raw, default)
        return default


# The repository owner is not configured here — it is parsed from the
# authoritative repo URL in the scans cluster (always the OpenSearch org). The
# dedup read targets that org repo, where the PRs we must not duplicate
# (Dependabot / Mend / maintainers) live. The fork that fixes are pushed to is a
# separate, write-side concern handled by the ecosystem Lambda.

# Read timeout for GitHub API calls, in seconds.
GITHUB_TIMEOUT = _int_env('GITHUB_API_TIMEOUT', 15)

# Ecosystems this feature can remediate, in SCANS-CLUSTER vocabulary (the
# ecosystem is read from the cluster's matched vulnerability). The bundle release
# components are structurally maven (OpenSearch core + Gradle plugins) and npm
# (OpenSearch-Dashboards + JS plugins); pypi (e.g. opensearch-build's Pipfile) is
# build tooling, not a bundle release component, so it's out of scope here.
SUPPORTED_ECOSYSTEMS = {'npm', 'maven'}

# We remediate the main branch only; release-branch propagation is handled by the
# repos' existing backport workflow. So repo resolution is scoped to main scans.
SCANS_MAIN_TAG = 'origin/main'

# Scope resolution to the OpenSearch bundle release components — the OpenSearch
# and OpenSearch-Dashboards bundles — via the scans cluster's top-level
# release_type field.
SCANS_RELEASE_TYPES = ['bundle_opensearch', 'bundle_opensearch_dashboards']


def handle_remediate_cve(params: Dict[str, str], request_id: str) -> Dict[str, Any]:
    """Handle a remediate_cve request.

    Currently performs the existing-PR dedup check against the upstream org
    repository and returns the result. Remediation execution (via the
    per-ecosystem container Lambdas) is not yet wired — a "no existing PR"
    result returns a placeholder.

    Args:
        params: Flat parameter dict from the Bedrock event. Recognized keys:
            cve_id (required)        — the CVE identifier, e.g. "CVE-2026-1225".
            project (required)       — the affected project/repo, used to pick which
                                       repository when a CVE affects more than one.
        request_id: Short request ID for log correlation.

    Returns:
        Structured result dict (wrapped in the Bedrock envelope by the caller).
    """
    cve_id = (params.get('cve_id') or '').strip()
    project = (params.get('project') or '').strip()

    if not cve_id or not project:
        logger.warning(
            f"[{request_id}] REMEDIATE_CVE: missing required params "
            f"(cve_id={cve_id!r}, project={project!r})"
        )
        return error_response(
            'invalid_request',
            'Both cve_id and project (repository name) are required.',
        )

    logger.info(
        f"[{request_id}] REMEDIATE_CVE: cve_id={cve_id!r} project={project!r}"
    )

    # --- resolve the target repo from the scans cluster (main branch) --------
    # This both derives the real GitHub owner/repo (no display-name guessing) and
    # validates that the CVE actually affects a tracked repo on main — if it
    # doesn't, there is nothing to remediate.
    try:
        resolved, resolve_resp = _resolve_repo(cve_id, project, request_id)
    except Exception as e:  # OpenSearch query failed
        logger.error(f"[{request_id}] REMEDIATE_CVE_RESOLVE_FAILED: {e}")
        return connection_error(e)
    if resolve_resp:
        return resolve_resp

    repo_owner = resolved['repo_owner']
    repo_name = resolved['repo_name']
    ecosystem = resolved['ecosystem']
    package = resolved['package']
    logger.info(
        f"[{request_id}] REMEDIATE_CVE_REPO_RESOLVED: {repo_owner}/{repo_name} "
        f"ecosystem={ecosystem!r} package={package!r} "
        f"(project={resolved['project_name']!r})"
    )

    # gate 1: is this an ecosystem we can remediate at all? The ecosystem comes
    # from the scans cluster (repo-specific, cluster vocabulary), so this gate
    # runs without any GitHub call — unsupported ecosystems short-circuit here.
    if ecosystem not in SUPPORTED_ECOSYSTEMS:
        logger.info(
            f"[{request_id}] REMEDIATE_CVE_UNSUPPORTED: ecosystem={ecosystem!r} "
            f"for {cve_id} is not in scope"
        )
        return {
            'status': 'unsupported_ecosystem',
            'cve_id': cve_id,
            'ecosystem': ecosystem,
            'message': (
                f"{cve_id} affects the '{ecosystem or 'unknown'}' ecosystem, "
                f"which is not supported for automated remediation. "
                f"Supported ecosystems: {', '.join(sorted(SUPPORTED_ECOSYSTEMS))}."
            ),
        }

    # --- derive the patched version from the GitHub Advisory API --------------
    # Ecosystem AND the repo-specific package both come from the cluster (above);
    # GitHub only supplies the fix version the cluster doesn't carry. We match the
    # GitHub advisory entry to OUR package, so a multi-package CVE resolves to the
    # version for the package this repo actually uses (not an arbitrary one).
    try:
        patched_version = _derive_patched_version(cve_id, package, request_id)
    except Exception as e:  # advisory lookup failed (network / API error)
        logger.error(f"[{request_id}] REMEDIATE_CVE_DERIVE_FAILED: {e}")
        return error_response(
            'github_error', 'Failed to look up advisory details from GitHub.',
        )

    logger.info(
        f"[{request_id}] REMEDIATE_CVE_DERIVED: package={package!r} "
        f"patched_version={patched_version!r}"
    )

    # gate 2: do we have a version to upgrade to?
    if not patched_version:
        logger.info(
            f"[{request_id}] REMEDIATE_CVE_NO_PATCH: no patched version for {cve_id}"
        )
        return {
            'status': 'no_patched_version',
            'cve_id': cve_id,
            'message': (
                f"No patched version is available for {cve_id}, so it cannot be "
                f"remediated by a version bump."
            ),
        }

    # --- pre-flight: is there already an OPEN PR fixing this CVE? -----------
    # We check open PRs only. An already-MERGED fix means the target branch is
    # already updated, which the ecosystem Lambda detects authoritatively at
    # clone time ("no files changed"), with no branch-ambiguity — so a merged-PR
    # heuristic here would add false positives (e.g. a PR merged to a release
    # branch but not main) for no correctness gain. An open PR, by contrast, is
    # NOT yet merged, so nothing downstream would catch the duplicate.
    try:
        existing = _find_existing_pr(
            repo_owner, repo_name, cve_id, package, patched_version, request_id,
        )
    except Exception as e:  # network / API errors — surface, don't crash
        logger.error(f"[{request_id}] REMEDIATE_CVE_PR_CHECK_FAILED: {e}")
        return error_response(
            'github_error', 'Failed to check for existing pull requests on GitHub.',
        )

    if existing:
        logger.info(
            f"[{request_id}] REMEDIATE_CVE_SKIPPED: open PR already exists for "
            f"{cve_id} on {repo_owner}/{repo_name} -> {existing['url']} "
            f"(matched by {existing['matched_by']})"
        )
        return {
            'status': 'pr_exists',
            'cve_id': cve_id,
            'repository': f'{repo_owner}/{repo_name}',
            'pr_url': existing['url'],
            'pr_title': existing['title'],
            'matched_by': existing['matched_by'],
            'message': (
                f"An open pull request already addresses {cve_id} on "
                f"{repo_owner}/{repo_name}: {existing['url']}. "
                f"Skipping remediation to avoid a duplicate."
            ),
        }

    # --- no existing PR: hand off to the ecosystem remediation Lambda -------
    # This is where dispatch(ctx) will invoke the per-ecosystem container Lambda
    # with the derived details below. Until those Lambdas exist, return a
    # placeholder that carries the full resolved context.
    logger.info(
        f"[{request_id}] REMEDIATE_CVE: no existing PR found for {cve_id} on "
        f"{repo_owner}/{repo_name}; ecosystem={ecosystem} remediation not yet wired"
    )
    return {
        'status': 'no_existing_pr',
        'cve_id': cve_id,
        'repository': f'{repo_owner}/{repo_name}',
        'ecosystem': ecosystem,
        'package': package,
        'patched_version': patched_version,
        'message': (
            f"No open PR was found for {cve_id} on {repo_owner}/{repo_name}. "
            f"Resolved fix: bump {package} to {patched_version} ({ecosystem}). "
            f"Remediation execution is not yet implemented."
        ),
    }


def _resolve_repo(cve_id: str, project: str, request_id: str):
    """Resolve the target GitHub repo for a CVE from the scans index (main only).

    Queries the latest scans index for main-branch (``origin/main``) scans whose
    vulnerabilities include ``cve_id`` (by ``id`` or ``aliases``) and are not
    ``excluded``, then parses each project's authoritative ``project.repo`` URL
    into owner/repo.

    Returns ``(resolved, response)``:
      - ``resolved`` = ``{'repo_owner', 'repo_name', 'project_name', 'ecosystem',
        'package'}`` when exactly one repo and one affected package are
        identified (after reconciling with ``project``), with ``response`` None.
      - ``response`` = an early-return status dict, with ``resolved`` None, for:
        ``not_affected`` (CVE on no main-branch repo), ``project_mismatch``
        (affected repos don't include the one the user named), ``multiple_repos``
        (ambiguous across repos), or ``multiple_packages`` (one repo, several
        affected packages).
    """
    body = json.dumps({
        'size': 50,
        '_source': ['project.name', 'project.repo', 'project.tag'],
        # Sort newest scan first so collapse keeps the LATEST scan per project
        # (without a sort, collapse's representative doc is non-deterministic when
        # a project has several main-branch scans).
        'sort': [{'timestamp.scan': {'order': 'desc'}}],
        'collapse': {'field': 'project.name'},
        'query': {
            'bool': {
                'filter': [
                    {'term': {'project.tag': SCANS_MAIN_TAG}},
                    # release_type is a text field with a keyword sub-field; use
                    # the keyword for exact matching. `terms` matches either bundle.
                    {'terms': {'release_type.keyword': SCANS_RELEASE_TYPES}},
                    {'nested': {
                        'path': 'vulnerabilities',
                        # inner_hits returns ONLY the matched (non-excluded)
                        # vulnerability + its ecosystem, so the project's full
                        # vulnerabilities array is never shipped to the Lambda.
                        'inner_hits': {
                            # a CVE can hit several artifacts of one package
                            # family in a repo (e.g. netty epoll+kqueue, the
                            # log4j family) — pull enough to detect them all.
                            'size': 10,
                            '_source': [
                                'vulnerabilities.id',
                                'vulnerabilities.package.ecosystem',
                                'vulnerabilities.package.name',
                            ],
                        },
                        'query': {'bool': {
                            'should': [
                                {'term': {'vulnerabilities.id': cve_id}},
                                {'term': {'vulnerabilities.aliases': cve_id}},
                            ],
                            'minimum_should_match': 1,
                            # ignore CVEs suppressed AT_PROJECT / AT_RULE
                            'must_not': [
                                {'exists': {'field': 'vulnerabilities.excluded'}},
                            ],
                        }},
                    }},
                ],
            },
        },
    })

    response = opensearch_request(
        'POST', f'/{get_latest_scans_index()}/_search', body,
    )
    hits = response.get('hits', {}).get('hits', [])

    # distinct owner/repo (parsed from the cluster's repo URL), with display name
    # and the ecosystem read from this repo's matching (non-excluded) vulnerability.
    candidates: Dict[str, Dict[str, str]] = {}
    for hit in hits:
        proj = hit.get('_source', {}).get('project', {})
        owner, name = _parse_repo_url(proj.get('repo') or '')
        if not owner or not name:
            # can't fully identify the repo from the cluster record — skip it
            logger.warning(
                f"[{request_id}] REMEDIATE_CVE_RESOLVE: unparseable repo url "
                f"{proj.get('repo')!r} for project {proj.get('name')!r}"
            )
            continue
        candidates[f'{owner}/{name}'] = {
            'repo_owner': owner,
            'repo_name': name,
            'project_name': proj.get('name', ''),
            # all distinct packages this CVE hits in this repo (usually one)
            'packages': _matched_packages(hit),
        }

    if not candidates:
        return None, {
            'status': 'not_affected',
            'cve_id': cve_id,
            'message': (
                f"{cve_id} was not found on the main branch of any tracked "
                f"OpenSearch project. It may not affect them, or may already be "
                f"fixed on main — no remediation needed."
            ),
        }

    matches = list(candidates.values())

    # Reconcile against the user-supplied project (a required input). This runs
    # even when a single repo matched, so we never silently remediate a repo the
    # user did not name. Match the project string against the display name or the
    # repo slug.
    if project:
        p = project.strip().lower()
        narrowed = [
            m for m in matches
            if p in m['project_name'].lower() or p in m['repo_name'].lower()
        ]
        if not narrowed:
            affected = sorted(f"{m['repo_owner']}/{m['repo_name']}" for m in matches)
            return None, {
                'status': 'project_mismatch',
                'cve_id': cve_id,
                'requested_project': project,
                'affected_repositories': affected,
                'message': (
                    f"{cve_id} does not affect '{project}' on the main branch. "
                    f"It affects: {', '.join(affected)}."
                ),
            }
        matches = narrowed

    if len(matches) == 1:
        m = matches[0]
        pkgs = m['packages']
        if len(pkgs) > 1:
            # one CVE, multiple affected packages in this repo — surface it
            # rather than silently remediating only the first.
            names = sorted(p['package'] for p in pkgs)
            return None, {
                'status': 'multiple_packages',
                'cve_id': cve_id,
                'repository': f"{m['repo_owner']}/{m['repo_name']}",
                'packages': names,
                'message': (
                    f"{cve_id} affects multiple packages in "
                    f"{m['repo_owner']}/{m['repo_name']}: {', '.join(names)}. "
                    f"Remediating multiple packages for a single CVE is not yet "
                    f"supported."
                ),
            }
        one = pkgs[0] if pkgs else {'ecosystem': '', 'package': ''}
        return {
            'repo_owner': m['repo_owner'],
            'repo_name': m['repo_name'],
            'project_name': m['project_name'],
            'ecosystem': one['ecosystem'],
            'package': one['package'],
        }, None

    listing = sorted(f"{m['repo_owner']}/{m['repo_name']}" for m in matches)
    return None, {
        'status': 'multiple_repos',
        'cve_id': cve_id,
        'candidates': listing,
        'message': (
            f"{cve_id} affects multiple repositories on main: "
            f"{', '.join(listing)}. Please specify which one to remediate."
        ),
    }


def _parse_repo_url(repo_url: str):
    """Parse a GitHub repo URL into ``(owner, name)``; ``('', '')`` if not parseable.

    Handles the cluster's ``https://github.com/<owner>/<repo>.git`` form (and the
    ssh ``git@github.com:<owner>/<repo>.git`` form). Both owner and name must be
    present, otherwise the repo can't be reliably identified.
    """
    s = (repo_url or '').strip()
    if not s:
        return '', ''
    for prefix in ('https://github.com/', 'http://github.com/', 'git@github.com:'):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    if s.endswith('.git'):
        s = s[:-len('.git')]
    parts = [p for p in s.strip('/').split('/') if p]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return '', ''


def _matched_packages(hit: Dict[str, Any]) -> List[Dict[str, str]]:
    """Distinct ``{ecosystem, package}`` pairs the CVE hits in this repo.

    The scans query attaches ``inner_hits`` with the matched (non-excluded)
    vulnerabilities for this CVE — normally one, but a CVE can affect several
    packages of a family in one repo (e.g. netty epoll + kqueue, the log4j
    family), which show up as multiple inner hits. Deduped by package name.
    """
    inner = (
        ((hit.get('inner_hits') or {}).get('vulnerabilities') or {})
        .get('hits', {}).get('hits', [])
    )
    packages: List[Dict[str, str]] = []
    seen = set()
    for h in inner:
        src = h.get('_source') or {}
        name = _vuln_package(src)
        if name and name not in seen:
            seen.add(name)
            packages.append({'ecosystem': _vuln_ecosystem(src), 'package': name})
    return packages


def _vuln_pkg(vuln: Dict[str, Any]) -> Dict[str, Any]:
    """The package object of a scan vulnerability (nested field may be a list)."""
    pkg = vuln.get('package') or {}
    if isinstance(pkg, list):
        pkg = pkg[0] if pkg else {}
    return pkg or {}


def _vuln_ecosystem(vuln: Dict[str, Any]) -> str:
    """Ecosystem (scans-cluster vocabulary) of a scan vulnerability entry."""
    return (_vuln_pkg(vuln).get('ecosystem') or '').strip().lower()


def _vuln_package(vuln: Dict[str, Any]) -> str:
    """Repo-specific package name of a scan vulnerability entry."""
    return (_vuln_pkg(vuln).get('name') or '').strip()


def _github_headers() -> Dict[str, str]:
    """Headers for GitHub API calls.

    Uses a token if one is in the environment (raising rate limits); runs
    unauthenticated otherwise — which is the current mode. A token is added with
    the remediation-execution / ecosystem work, at which point these calls pick
    it up automatically with no change here.
    """
    headers = {'Accept': 'application/vnd.github+json'}
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


def _derive_patched_version(cve_id: str, package: str, request_id: str) -> str:
    """Fetch the first patched version for ``package`` from the GitHub Advisory API.

    ``package`` is the repo-specific package resolved from the scans cluster. For
    a multi-package CVE, we match the advisory's ``vulnerabilities[]`` entry to
    THAT package, so the version corresponds to the package this repo actually
    uses. Returns the patched version string, or '' when it can't be determined —
    GitHub has no advisory for the CVE (the CVE is still real; the cluster
    resolved it), the advisory has no entry for our package, or the entry has no
    fix version. In all those cases the caller reports ``no_patched_version``.
    Network / API errors propagate to the caller.
    """
    headers = _github_headers()

    logger.info(
        f"[{request_id}] REMEDIATE_CVE_ADVISORY_LOOKUP: cve_id={cve_id!r} "
        f"package={package!r}"
    )
    response = requests.get(
        f'{GITHUB_API}/advisories',
        params={'cve_id': cve_id, 'per_page': 5},
        headers=headers,
        timeout=GITHUB_TIMEOUT,
    )
    response.raise_for_status()
    advisories = response.json()
    if not advisories:
        # Not an error: the CVE is real (resolved from the cluster); GitHub just
        # has no advisory, so we can't determine a fix version → no_patched_version.
        logger.info(f"[{request_id}] REMEDIATE_CVE_NO_ADVISORY: {cve_id}")
        return ''

    entry = _select_vulnerability(advisories[0].get('vulnerabilities') or [], package)
    if not entry:
        # advisory exists but has no entry for our package -> no known fix version
        return ''

    # first_patched_version is a string in the current API; historically an
    # object with an "identifier" key — handle both.
    fpv = entry.get('first_patched_version')
    if isinstance(fpv, dict):
        fpv = fpv.get('identifier')
    return (fpv or '').strip()


def _select_vulnerability(
    vulnerabilities: List[Dict[str, Any]],
    package: str,
) -> Optional[Dict[str, Any]]:
    """Pick the advisory vulnerability entry for ``package``.

    Matches the repo-specific package (from the cluster) against the advisory's
    listed packages so a multi-package CVE resolves to the right one:
      1. exact package-name match,
      2. loose containment (handles maven ``group:artifact`` vs bare ``artifact``,
         npm scopes, etc.),
      3. if ``package`` is known but not listed in the advisory -> None (we don't
         have a reliable fix version for it → no_patched_version),
      4. if no package is known at all -> best effort: first entry with a patched
         version, else the first entry.
    """
    if not vulnerabilities:
        return None

    pkg = _normalize_pkg_name(package)
    if pkg:
        for v in vulnerabilities:
            name = _normalize_pkg_name((v.get('package') or {}).get('name'))
            if name and name == pkg:
                return v
        for v in vulnerabilities:
            name = _normalize_pkg_name((v.get('package') or {}).get('name'))
            if name and (pkg in name or name in pkg):
                return v
        return None

    for v in vulnerabilities:
        if v.get('first_patched_version'):
            return v
    return vulnerabilities[0]


def _normalize_pkg_name(name: str) -> str:
    """Normalize a package name for cross-source comparison.

    The scans cluster writes maven packages as ``group/artifact`` while the
    GitHub Advisory API writes them as ``group:artifact``. Unifying ``:`` to
    ``/`` (and lower-casing) lets the two match. npm/pypi names have no ``:`` so
    this is a no-op for them (npm scopes like ``@scope/name`` are preserved).
    """
    return (name or '').strip().lower().replace(':', '/')


def _find_existing_pr(
    owner: str,
    repo: str,
    cve_id: str,
    package: str,
    patched_version: str,
    request_id: str,
) -> Optional[Dict[str, str]]:
    """Return an open PR that appears to fix this CVE, or None.

    Runs up to two searches against the target repo's OPEN pull requests:
      1. By CVE id — catches PRs that reference the CVE in the title or body
         (and our own bot PRs, which carry the CVE in the description/branch).
      2. By package + version — catches Dependabot / Mend / human "Bump
         <package> to/from <version>" PRs, whose titles deliberately do NOT
         contain the CVE id.

    The first match wins. Each result records which search matched it.

    KNOWN LIMITATION: (2) is a GitHub free-text match (title + body), so it can
    false-positive on an unrelated PR that merely mentions the package + version
    — which would skip a real fix — and we do NOT verify the matched PR actually
    changes the dependency (that needs the PR diff, deferred). Searching the body
    (not just the title) favors recall: it also catches human "batch" PRs that
    list bumped packages in a body table, at the cost of possible false
    positives.
    """
    # 1) CVE id
    hit = _search_open_prs(owner, repo, [cve_id], request_id)
    if hit:
        hit['matched_by'] = f'CVE id ({cve_id})'
        return hit

    # 2) package (+ version)
    if package:
        terms = [package] + ([patched_version] if patched_version else [])
        hit = _search_open_prs(owner, repo, terms, request_id)
        if hit:
            label = package + (f' {patched_version}' if patched_version else '')
            hit['matched_by'] = f'package/version ({label})'
            return hit

    return None


def _search_open_prs(
    owner: str,
    repo: str,
    terms: List[str],
    request_id: str,
) -> Optional[Dict[str, str]]:
    """Search a repo's open PRs for the given terms; return the first, or None.

    Uses GitHub's issue-search API scoped to open PRs in one repo (matching the
    terms in the title or body). Reading a public repo needs no auth; a token
    from the environment is used only to raise the rate limit, if present.
    """
    query = ' '.join([f'repo:{owner}/{repo}', 'is:pr', 'is:open', *terms])
    logger.info(f"[{request_id}] REMEDIATE_CVE_PR_SEARCH: q={query!r}")

    headers = _github_headers()

    response = requests.get(
        f'{GITHUB_API}/search/issues',
        params={'q': query, 'per_page': 5},
        headers=headers,
        timeout=GITHUB_TIMEOUT,
    )
    response.raise_for_status()
    items = response.json().get('items', [])
    if not items:
        return None

    top = items[0]
    return {
        'url': top.get('html_url', ''),
        'title': top.get('title', ''),
        'number': str(top.get('number', '')),
    }
