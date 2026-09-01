#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Remediation Handler for Security Advisories Lambda Functions.

Backs the ``remediate_cve`` action group. For a chosen repo it runs the
pre-flight — confirm the repo is affected, gate on ecosystem, derive the patched
version, and check for an existing open PR that already fixes this CVE (from
Dependabot, Mend, or a human maintainer) so we never open a duplicate — then
dispatches the actual fix to the ecosystem's remediation worker.

Important repo detail: the existing-PR check reads the **upstream org
repository** (``opensearch-project/<repo>``), NOT a bot fork — the PRs we must
not duplicate live upstream, not on a fork. Reading open PRs on a public repo
needs no credentials, so this check runs unauthenticated (a token is used only
if one happens to be present in the environment, purely to raise the rate limit).

The actual remediation (clone -> edit -> regenerate -> push -> open PR) runs on a
per-ecosystem Fargate worker, dispatched here via ``ecs.run_task`` (see
``_dispatch_remediation``). If no worker is wired for the ecosystem yet, a
``remediation_unavailable`` result reports the resolved fix without remediating.

Repository selection is split across two action-group functions, mirroring the
list_projects -> query_vulnerabilities pattern the rest of this agent uses:
``list_affected_repositories`` returns the repos a CVE affects (the agent, with
full conversational context, resolves the user's phrasing to one), and
``remediate_cve`` takes that exact repo and runs the pre-flight + remediation.
This handler does NO name matching itself — it only confirms the chosen repo is
genuinely in the affected set.

Functions:
    handle_list_affected_repositories: List repos a CVE affects on main.
    handle_remediate_cve: Remediate a CVE on a chosen repo (dedup + dispatch).
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import boto3
import requests
import semver
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


def handle_remediate_cve(
    params: Dict[str, str],
    request_id: str,
    session_attributes: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Handle a remediate_cve request for one chosen repository.

    The caller (agent) has already picked which repository to remediate — via
    ``list_affected_repositories`` — so this takes the exact ``repo_name`` and:
    confirms it is genuinely in the CVE's affected set (a membership guard, not
    name matching), gates on ecosystem, derives the patched version, checks for
    an existing PR, and dispatches to the per-ecosystem Fargate worker.

    Dispatch is ASYNCHRONOUS: the worker's clone + install can exceed Bedrock's
    ~120s action-group timeout, so we launch the task and return immediately
    with ``remediation_started``. The worker posts the resulting PR link back to
    the Slack thread when it finishes (using the thread context carried in
    ``session_attributes``). All the pre-flight outcomes (already_patched,
    pr_exists, no_patched_version, not_affected, unsupported_ecosystem,
    multiple_packages) are fast and still return synchronously.

    Args:
        params: Flat parameter dict from the Bedrock event. Recognized keys:
            cve_id (required)    — the CVE identifier, e.g. "CVE-2026-1225".
            repo_name (required) — the exact repository to remediate, as returned
                                   by list_affected_repositories (e.g.
                                   "alerting-dashboards-plugin").
        request_id: Short request ID for log correlation.
        session_attributes: Out-of-band attributes carried from the Slack event
            via Bedrock (e.g. ``slack_channel``, ``slack_thread_ts``), forwarded
            to the worker so it can reply in the originating thread.

    Returns:
        Structured result dict (wrapped in the Bedrock envelope by the caller).
    """
    session_attributes = session_attributes or {}
    cve_id = (params.get('cve_id') or '').strip()
    repo_name_in = (params.get('repo_name') or '').strip()

    if not cve_id or not repo_name_in:
        logger.warning(
            f"[{request_id}] REMEDIATE_CVE: missing required params "
            f"(cve_id={cve_id!r}, repo_name={repo_name_in!r})"
        )
        return error_response(
            'invalid_request',
            'Both cve_id and repo_name are required. Call '
            'list_affected_repositories first to get the exact repository name.',
        )

    logger.info(
        f"[{request_id}] REMEDIATE_CVE: cve_id={cve_id!r} repo_name={repo_name_in!r}"
    )

    # --- resolve the chosen repo from the scans cluster (main branch) --------
    # Membership guard, NOT intent-matching: re-run the affected-repos query and
    # confirm the caller's chosen repo is in the set (also derives the GitHub
    # owner, ecosystem, and repo-specific package).
    try:
        candidates, not_affected = _affected_candidates(cve_id, request_id)
    except Exception as e:  # OpenSearch query failed
        logger.error(f"[{request_id}] REMEDIATE_CVE_RESOLVE_FAILED: {e}")
        return connection_error(e)
    if not_affected:
        return not_affected

    match = _select_candidate(candidates, repo_name_in)
    if match is None:
        affected = sorted(f"{c['repo_owner']}/{c['repo_name']}" for c in candidates)
        logger.info(
            f"[{request_id}] REMEDIATE_CVE_NOT_IN_SET: {repo_name_in!r} not among "
            f"affected repos for {cve_id} ({affected})"
        )
        return {
            'status': 'not_affected',
            'cve_id': cve_id,
            'requested_repository': repo_name_in,
            'affected_repositories': affected,
            'message': (
                f"{cve_id} does not affect '{repo_name_in}' on the main branch of "
                f"a supported release-bundle component. It affects: "
                f"{', '.join(affected)}."
            ),
        }

    # One repo, multiple affected packages — surface it rather than silently
    # remediating only the first.
    pkgs = match['packages']
    if len(pkgs) > 1:
        names = sorted(p['package'] for p in pkgs)
        return {
            'status': 'multiple_packages',
            'cve_id': cve_id,
            'repository': f"{match['repo_owner']}/{match['repo_name']}",
            'packages': names,
            'message': (
                f"{cve_id} affects multiple packages in "
                f"{match['repo_owner']}/{match['repo_name']}: {', '.join(names)}. "
                f"Remediating multiple packages for a single CVE is not yet "
                f"supported."
            ),
        }

    one = pkgs[0] if pkgs else {'ecosystem': '', 'package': '', 'version': ''}
    resolved = {
        'repo_owner': match['repo_owner'],
        'repo_name': match['repo_name'],
        'project_name': match['project_name'],
        'ecosystem': one['ecosystem'],
        'package': one['package'],
        'installed_version': one.get('version', ''),
    }

    repo_owner = resolved['repo_owner']
    repo_name = resolved['repo_name']
    ecosystem = resolved['ecosystem']
    package = resolved['package']
    installed_version = resolved.get('installed_version', '')
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
    # version for the package this repo actually uses (not an arbitrary one), and
    # to OUR installed version, so a multi-range advisory resolves to the fix for
    # the version line this repo is on.
    try:
        gh_package, patched_version = _derive_patched_version(
            cve_id, ecosystem, package, installed_version, request_id,
        )
    except Exception as e:  # advisory lookup failed (network / API error)
        logger.error(f"[{request_id}] REMEDIATE_CVE_DERIVE_FAILED: {e}")
        return error_response(
            'github_error', 'Failed to look up advisory details from GitHub.',
        )

    logger.info(
        f"[{request_id}] REMEDIATE_CVE_DERIVED: package={package!r} "
        f"github_package={gh_package!r} patched_version={patched_version!r}"
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

    # gate 3: cross-check GitHub's patched version against the cluster's installed
    # version to avoid false positives — skip if installed >= patched. Semver
    # only; unparseable versions (e.g. maven) proceed, since we can't prove safe.
    if installed_version and _at_or_above_version(installed_version, patched_version):
        logger.info(
            f"[{request_id}] REMEDIATE_CVE_NOT_AFFECTED: {repo_owner}/{repo_name} "
            f"has {package} {installed_version} >= patched {patched_version} for {cve_id}"
        )
        return {
            'status': 'already_patched',
            'cve_id': cve_id,
            'repository': f'{repo_owner}/{repo_name}',
            'package': package,
            'installed_version': installed_version,
            'patched_version': patched_version,
            'message': (
                f"{repo_owner}/{repo_name} already has {package} {installed_version}, "
                f"which is at or above the patched version {patched_version} for "
                f"{cve_id} in the {ecosystem} ecosystem — it is not affected, so no "
                f"remediation is needed."
            ),
        }

    # --- pre-flight: is there already an OPEN PR fixing this CVE? -----------
    # Look for an open PR already fixing this CVE; if found, surface it and stop
    # (dedup — don't open a duplicate).
    try:
        existing = _find_existing_pr(
            repo_owner, repo_name, cve_id, gh_package or package, patched_version, request_id,
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

    # --- no existing PR: hand the fix to the ecosystem's Fargate worker -----
    # Slack thread context rides along in the payload so the worker can post the
    # PR link back when it finishes. If no worker is wired for this ecosystem yet,
    # we fall back to remediation_unavailable below.
    payload = {
        'repo_name': repo_name,
        'cve_id': cve_id,
        'package': package,
        'patched_version': patched_version,
        'installed_version': installed_version,
        # We remediate main only; the worker pushes to the fork's main.
        'base_branch': SCANS_MAIN_TAG.split('/')[-1],
        # Slack thread context so the worker replies in the originating thread
        # (empty when invoked outside Slack — the worker then just logs).
        'slack_channel': (session_attributes.get('slack_channel') or '').strip(),
        'slack_thread_ts': (session_attributes.get('slack_thread_ts') or '').strip(),
    }
    try:
        dispatched = _dispatch_remediation(ecosystem, payload, request_id)
    except Exception as e:  # run_task launch failure
        logger.error(f"[{request_id}] REMEDIATE_CVE_DISPATCH_FAILED: {e}")
        return error_response(
            'remediation_error', 'Failed to start automated remediation.',
        )

    if dispatched:
        logger.info(
            f"[{request_id}] REMEDIATE_CVE_STARTED: async remediation dispatched "
            f"for {cve_id} on {repo_owner}/{repo_name} ({ecosystem})"
        )
        return {
            'status': 'remediation_started',
            'cve_id': cve_id,
            'repository': f'{repo_owner}/{repo_name}',
            'ecosystem': ecosystem,
            'package': package,
            'patched_version': patched_version,
            'message': (
                f"Started remediation for {cve_id} on {repo_owner}/{repo_name} "
                f"(bumping {package} to {patched_version}). This runs in the "
                f"background; the pull request link will be posted here shortly."
            ),
        }

    # No Fargate worker for this ecosystem yet: a real CVE with a known fix we
    # just can't auto-remediate here → report the fix as remediation_unavailable.
    logger.info(
        f"[{request_id}] REMEDIATE_CVE: no existing PR for {cve_id} on "
        f"{repo_owner}/{repo_name}; no {ecosystem} Fargate worker wired"
    )
    return {
        'status': 'remediation_unavailable',
        'cve_id': cve_id,
        'repository': f'{repo_owner}/{repo_name}',
        'ecosystem': ecosystem,
        'package': package,
        'patched_version': patched_version,
        'message': (
            f"No open PR was found for {cve_id} on {repo_owner}/{repo_name}. "
            f"Resolved fix: bump {package} to {patched_version} ({ecosystem}). "
            f"Automated remediation for the {ecosystem} ecosystem is not yet enabled."
        ),
    }


def handle_list_affected_repositories(
    params: Dict[str, str], request_id: str,
) -> Dict[str, Any]:
    """Handle a list_affected_repositories request.

    Returns the repositories a CVE affects on the main branch of the supported
    release-bundle components. The release_type scoping already limits these to
    the OpenSearch and OpenSearch-Dashboards bundles, which are structurally
    maven and npm only — so every repo listed is remediable; remediate_cve's
    ecosystem gate is the per-repo backstop if a stray ecosystem ever slips
    through the scan data. Each repo is annotated with its ecosystem for context.
    The agent uses this list (with full conversational context) to resolve the
    user's phrasing to one exact repo before calling ``remediate_cve`` —
    mirroring how ``list_projects`` precedes ``query_vulnerabilities``. This
    function does NO name matching itself.

    Args:
        params: Flat parameter dict; recognized key: cve_id (required).
        request_id: Short request ID for log correlation.

    Returns:
        Structured result dict (wrapped in the Bedrock envelope by the caller):
        ``affected_repositories`` (with the repo list) or ``not_affected``.
    """
    cve_id = (params.get('cve_id') or '').strip()
    if not cve_id:
        logger.warning(f"[{request_id}] LIST_AFFECTED_REPOS: missing cve_id")
        return error_response('invalid_request', 'cve_id is required.')

    logger.info(f"[{request_id}] LIST_AFFECTED_REPOS: cve_id={cve_id!r}")
    try:
        candidates, not_affected = _affected_candidates(cve_id, request_id)
    except Exception as e:  # OpenSearch query failed
        logger.error(f"[{request_id}] LIST_AFFECTED_REPOS_FAILED: {e}")
        return connection_error(e)
    if not_affected:
        return not_affected

    repositories = []
    for c in candidates:
        ecos = sorted({p['ecosystem'] for p in c['packages'] if p['ecosystem']})
        repositories.append({
            'repository': f"{c['repo_owner']}/{c['repo_name']}",
            'repo_name': c['repo_name'],
            'project_name': c['project_name'],
            'ecosystem': '/'.join(ecos),
        })
    repositories.sort(key=lambda r: r['repository'])

    logger.info(
        f"[{request_id}] LIST_AFFECTED_REPOS_RESULT: {cve_id} -> "
        f"{[r['repository'] for r in repositories]}"
    )
    return {
        'status': 'affected_repositories',
        'cve_id': cve_id,
        'repositories': repositories,
        'message': (
            f"{cve_id} affects {len(repositories)} repository(ies) on the main "
            f"branch of the supported release-bundle components."
        ),
    }


# Env var holding the per-ecosystem remediation Fargate task definition ARN. The
# CDK stack injects the value when it wires the ECS task to this handler.
_REMEDIATION_TASKDEF_ENV = {
    'npm': 'NPM_REMEDIATION_TASKDEF',
    # 'maven': 'MAVEN_REMEDIATION_TASKDEF',  # added with the maven ecosystem
}

# The container in the task definition to override (see the CDK task def).
_REMEDIATION_CONTAINER = 'worker'

# Remediation payload key -> container environment variable name. The worker's
# ECS entrypoint (main.py) reads these env vars back into the same event keys.
_PAYLOAD_TO_ENV = {
    'repo_name': 'REPO_NAME',
    'cve_id': 'CVE_ID',
    'package': 'PACKAGE',
    'patched_version': 'PATCHED_VERSION',
    'installed_version': 'INSTALLED_VERSION',
    'base_branch': 'BASE_BRANCH',
    'slack_channel': 'SLACK_CHANNEL',
    'slack_thread_ts': 'SLACK_THREAD_TS',
}


def _dispatch_remediation(ecosystem: str, payload: Dict[str, Any], request_id: str) -> bool:
    """Launch the per-ecosystem remediation worker as a Fargate task (async).

    The worker (clone + install + PR) far exceeds Bedrock's ~120s action-group
    timeout and, for large repos, Lambda's own limits — so it runs as an ECS
    Fargate task, dispatched fire-and-forget: ``run_task`` returns as soon as the
    task is accepted and we do NOT wait. The worker posts its outcome (PR link)
    back to the Slack thread when it finishes (thread context is in the payload,
    passed as container env overrides). Returns True when the task was accepted,
    or False when no task definition is configured for this ecosystem (the caller
    then reports the resolved fix without opening a PR). Raises on a launch
    failure (the caller surfaces an error).
    """
    env_key = _REMEDIATION_TASKDEF_ENV.get(ecosystem)
    task_definition = os.environ.get(env_key) if env_key else None
    if not task_definition:
        return False

    cluster = os.environ.get('REMEDIATION_ECS_CLUSTER')
    subnets = [s for s in os.environ.get('REMEDIATION_ECS_SUBNETS', '').split(',') if s]
    security_group = os.environ.get('REMEDIATION_ECS_SECURITY_GROUP')
    if not (cluster and subnets and security_group):
        # A task definition is wired but the network config is missing — a
        # deployment/config error, not an unsupported ecosystem. Fail loudly.
        raise RuntimeError(
            'remediation ECS network configuration is incomplete '
            '(REMEDIATION_ECS_CLUSTER / _SUBNETS / _SECURITY_GROUP)'
        )

    environment = [
        {'name': env, 'value': str(payload.get(key, ''))}
        for key, env in _PAYLOAD_TO_ENV.items()
    ]
    logger.info(
        f"[{request_id}] REMEDIATE_CVE_DISPATCH: running Fargate task "
        f"{task_definition} on {cluster} payload={payload}"
    )
    client = boto3.client('ecs')
    response = client.run_task(
        cluster=cluster,
        taskDefinition=task_definition,
        launchType='FARGATE',
        count=1,
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': subnets,
                'securityGroups': [security_group],
                # Public subnets with a public IP so the task can reach GitHub,
                # Slack, and package registries without a NAT gateway.
                'assignPublicIp': 'ENABLED',
            }
        },
        overrides={
            'containerOverrides': [
                {'name': _REMEDIATION_CONTAINER, 'environment': environment}
            ]
        },
    )
    failures = response.get('failures') or []
    tasks = response.get('tasks') or []
    if failures or not tasks:
        raise RuntimeError(
            f"run_task for {task_definition} failed: {failures or 'no task returned'}"
        )
    task_arn = tasks[0].get('taskArn', '')
    logger.info(
        f"[{request_id}] REMEDIATE_CVE_DISPATCH_ACCEPTED: {task_definition} "
        f"task={task_arn.rsplit('/', 1)[-1]}"
    )
    return True


def _affected_candidates(cve_id: str, request_id: str):
    """Repositories a CVE affects on the main branch, from the scans index.

    Queries the latest scans index for main-branch (``origin/main``) scans in the
    supported release-bundle components whose vulnerabilities include ``cve_id``
    (by ``id`` or ``aliases``) and are not ``excluded``, then parses each
    project's authoritative ``project.repo`` URL into owner/repo.

    Returns ``(candidates, response)``:
      - ``candidates`` = a list of ``{'repo_owner', 'repo_name', 'project_name',
        'packages'}`` dicts, one per distinct affected repo, where ``packages``
        is the distinct ``{'ecosystem', 'package', 'version'}`` set the CVE hits
        in that repo (usually one). ``response`` is None.
      - ``response`` = a ``not_affected`` status dict (with ``candidates`` == [])
        when the CVE affects no supported main-branch repo.

    Does NO name matching — selecting among candidates is the caller's job (the
    agent, which has full conversational context, mirroring list_projects).
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
                                # installed version — used to pick the right
                                # patched version when an advisory lists several
                                # affected ranges for the same package.
                                'vulnerabilities.package.version',
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

    # Log the affected repos + matched package(s) with the installed version —
    # the inputs that drive ecosystem/package/patched-version selection.
    logger.info(
        f"[{request_id}] REMEDIATE_CVE_SCANS: {len(hits)} hit(s); candidates="
        + str([
            {
                'repo': repo,
                'packages': [
                    f"{p.get('ecosystem', '')}:{p.get('package', '')}@{p.get('version', '')}"
                    for p in c['packages']
                ],
            }
            for repo, c in candidates.items()
        ])
    )

    if not candidates:
        return [], {
            'status': 'not_affected',
            'cve_id': cve_id,
            'message': (
                f"{cve_id} was not found on the main branch of any supported "
                f"component. Remediation currently only covers the OpenSearch and "
                f"OpenSearch-Dashboards release-bundle components — so either the CVE "
                f"does not affect them / is already fixed on main, or the target is a "
                f"non-release component that is not supported yet."
            ),
        }

    return list(candidates.values()), None


def _select_candidate(
    candidates: List[Dict[str, Any]], repo_name: str,
) -> Optional[Dict[str, Any]]:
    """Return the candidate whose repo matches ``repo_name`` exactly, or None.

    An exact membership guard, NOT intent-matching: the agent has already chosen
    which repository to remediate (from list_affected_repositories), so we only
    confirm that choice is genuinely in the CVE's affected set. Accepts a bare
    repo slug ("alerting-dashboards-plugin") or an "owner/repo" form, compared
    case-insensitively against the authoritative slug parsed from the cluster.
    """
    wanted = (repo_name or '').strip().lower().rsplit('/', 1)[-1]
    if not wanted:
        return None
    for c in candidates:
        if c['repo_name'].lower() == wanted:
            return c
    return None


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
            packages.append({
                'ecosystem': _vuln_ecosystem(src),
                'package': name,
                'version': _vuln_version(src),
            })
    return packages


def _vuln_package_obj(vuln: Dict[str, Any]) -> Dict[str, Any]:
    """The package object of a scan vulnerability (nested field may be a list)."""
    pkg = vuln.get('package') or {}
    if isinstance(pkg, list):
        pkg = pkg[0] if pkg else {}
    return pkg or {}


def _vuln_ecosystem(vuln: Dict[str, Any]) -> str:
    """Ecosystem (scans-cluster vocabulary) of a scan vulnerability entry."""
    return (_vuln_package_obj(vuln).get('ecosystem') or '').strip().lower()


def _vuln_package(vuln: Dict[str, Any]) -> str:
    """Repo-specific package name of a scan vulnerability entry."""
    return (_vuln_package_obj(vuln).get('name') or '').strip()


def _vuln_version(vuln: Dict[str, Any]) -> str:
    """Installed version of a scan vulnerability entry (the version in the repo)."""
    return (_vuln_package_obj(vuln).get('version') or '').strip()


# Resolved GitHub token, cached per container (None = not resolved yet, '' =
# resolved to none → run unauthenticated). Avoids a Secrets Manager fetch on
# every API call (each remediate_cve makes up to 3).
_GH_TOKEN_CACHE: Optional[str] = None


def _resolve_github_token() -> str:
    """GitHub token for the read-side API calls (advisory + PR-dedup search).

    Env ``GH_TOKEN`` (dev PAT) first, else Secrets Manager named by
    ``GH_TOKEN_SECRET_NAME``. These calls only read PUBLIC data, so a scopeless
    token suffices — it's used purely to raise the API rate limit above the
    unauthenticated per-IP ceiling. Returns '' when none is configured (calls
    then run unauthenticated). Cached per container.
    """
    global _GH_TOKEN_CACHE
    if _GH_TOKEN_CACHE is not None:
        return _GH_TOKEN_CACHE

    token = os.environ.get('GH_TOKEN') or ''
    secret_name = os.environ.get('GH_TOKEN_SECRET_NAME')
    if not token and secret_name:
        try:
            value = boto3.client('secretsmanager').get_secret_value(
                SecretId=secret_name)['SecretString'].strip()
            # The secret may be the raw token or a JSON blob with a "token" field.
            token = (json.loads(value).get('token', '') if value.startswith('{')
                     else value).strip()
        except Exception as e:  # never leak the underlying error
            logger.error(f"Failed to read GitHub token from Secrets Manager: {e}")
            token = ''

    _GH_TOKEN_CACHE = token
    return token


def _github_headers() -> Dict[str, str]:
    """Headers for GitHub API calls; authenticated if a token is configured."""
    headers = {'Accept': 'application/vnd.github+json'}
    token = _resolve_github_token()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


def _derive_patched_version(
    cve_id: str, ecosystem: str, package: str, installed_version: str, request_id: str,
) -> str:
    """Resolve (github_package_name, patched_version) for ``package`` from the
    GitHub Advisory API.

    ``ecosystem`` (cluster vocabulary, e.g. ``npm``/``maven``) scopes the advisory
    entries to OUR ecosystem FIRST: a single CVE can list the same package name
    under several ecosystems (e.g. langsmith under both pip ``< 0.8.0`` and npm
    ``< 0.6.0``) with different ranges and patched versions, so matching by name
    alone can return the wrong ecosystem's fix. ``package`` is the repo-specific
    package resolved from the scans cluster, used to match the advisory's
    ``vulnerabilities[]`` entry (so a multi-package CVE resolves to the package
    this repo uses). ``installed_version`` (also from the cluster) disambiguates a
    multi-RANGE advisory — the same package listed
    once per affected line, each with its own patched version — to the fix for
    the line this repo is actually on. We return the matched entry's OWN package
    name — GitHub's canonical form (maven ``group:artifact``, npm ``@scope/name``),
    which is what PR titles use — for the dedup search, plus that entry's patched
    version. Returns ``('', '')`` when nothing can be determined (no advisory for
    the CVE — the CVE is still real, the cluster resolved it; no entry for our
    package; or no fix version); the caller then reports ``no_patched_version``.
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
        return '', ''

    entry = _select_vulnerability(
        advisories[0].get('vulnerabilities') or [], ecosystem, package, installed_version,
    )
    if not entry:
        # advisory exists but has no entry for our package -> no known fix version
        return '', ''

    gh_package = ((entry.get('package') or {}).get('name') or '').strip()
    # first_patched_version is a string in the current API; historically an
    # object with an "identifier" key — handle both.
    fpv = entry.get('first_patched_version')
    if isinstance(fpv, dict):
        fpv = fpv.get('identifier')
    patched_version = (fpv or '').strip()
    # Log which advisory line we matched: the ecosystem it was scoped to and the
    # affected range the installed version fell in. This is the signal for
    # multi-range / multi-ecosystem mis-selection (e.g. langsmith npm vs pip).
    logger.info(
        f"[{request_id}] REMEDIATE_CVE_ADVISORY_MATCH: ecosystem={ecosystem!r} "
        f"gh_package={gh_package!r} "
        f"range={(entry.get('vulnerable_version_range') or '')!r} "
        f"patched_version={patched_version!r}"
    )
    return gh_package, patched_version


def _select_vulnerability(
    vulnerabilities: List[Dict[str, Any]],
    ecosystem: str,
    package: str,
    installed_version: str = '',
) -> Optional[Dict[str, Any]]:
    """Pick the advisory vulnerability entry for our ``ecosystem`` + ``package``.

    Matches the repo-specific package (from the cluster) against the advisory's
    listed packages so a multi-package CVE resolves to the right one:
      0. FIRST scope the entries to OUR ecosystem. A CVE can list the same
         package name under several ecosystems with different ranges/patched
         versions (e.g. langsmith: pip ``< 0.8.0`` vs npm ``< 0.6.0``), so a
         name-only match can return another ecosystem's fix. If the advisory has
         no entry for our ecosystem at all -> None (no known fix for us).
      1. exact package-name match, else loose containment (handles maven
         ``group:artifact`` vs bare ``artifact``, npm scopes, etc.),
      2. among the name-matched entries, when ``installed_version`` is known,
         prefer the one whose ``vulnerable_version_range`` CONTAINS it. An
         advisory can list the SAME package once per affected line, each with a
         different patched version (e.g. form-data: ``< 2.5.6``,
         ``>= 3.0.0, < 3.0.5``, ``>= 4.0.0, < 4.0.6``); matching the installed
         version selects the fix for the line the repo is actually on rather
         than the first-listed one. Falls back to the first name match when the
         version/ranges can't be compared (e.g. non-semver maven versions).
      3. if ``package`` is known but not listed in the advisory -> None (we don't
         have a reliable fix version for it → no_patched_version),
      4. if no package is known at all -> best effort: first entry with a patched
         version, else the first entry.
    """
    if not vulnerabilities:
        return None

    # 0. scope to our ecosystem (cluster vocab == GitHub vocab for npm/maven).
    eco = (ecosystem or '').strip().lower()
    if eco:
        scoped = [
            v for v in vulnerabilities
            if ((v.get('package') or {}).get('ecosystem') or '').strip().lower() == eco
        ]
        # If the advisory lists nothing for our ecosystem, we have no fix for it.
        if not scoped:
            return None
        vulnerabilities = scoped

    pkg = _normalize_pkg_name(package)
    if pkg:
        def _entry_name(v):
            return _normalize_pkg_name((v.get('package') or {}).get('name'))

        matched = [v for v in vulnerabilities if _entry_name(v) == pkg]
        if not matched:
            matched = [
                v for v in vulnerabilities
                if _entry_name(v) and (pkg in _entry_name(v) or _entry_name(v) in pkg)
            ]
        if not matched:
            return None
        return _entry_for_installed_version(matched, installed_version)

    for v in vulnerabilities:
        if v.get('first_patched_version'):
            return v
    return vulnerabilities[0]


def _entry_for_installed_version(
    entries: List[Dict[str, Any]],
    installed_version: str,
) -> Dict[str, Any]:
    """Among same-package advisory entries, prefer the one whose affected range
    contains ``installed_version``; else the first entry.

    A single entry, an unknown installed version, or ranges we can't compare all
    fall back to the first entry (the pre-existing behavior).
    """
    if len(entries) == 1 or not installed_version:
        return entries[0]
    for v in entries:
        rng = v.get('vulnerable_version_range') or ''
        if rng and _version_in_range(installed_version, rng):
            return v
    return entries[0]


def _version_in_range(version: str, version_range: str) -> bool:
    """True if ``version`` satisfies a GitHub advisory ``vulnerable_version_range``.

    GitHub ranges are a comma-separated AND of comparators, e.g. ``< 2.5.6`` or
    ``>= 4.0.0, < 4.0.6`` (and ``= 1.2.3`` for a single version). Evaluated with
    semver; any parse failure — e.g. non-semver maven versions like
    ``4.1.134.Final`` — returns False, so the caller falls back to first-match
    rather than guessing a version.
    """
    try:
        v = semver.Version.parse(version)
        for comp in version_range.split(','):
            c = comp.strip().replace(' ', '')
            if not c:
                continue
            # GitHub writes an exact single version as "= X"; semver wants "==".
            if c.startswith('=') and not c.startswith('=='):
                c = '=' + c
            if not v.match(c):
                return False
        return True
    except (ValueError, TypeError):
        return False


def _at_or_above_version(installed: str, patched: str) -> bool:
    """True if ``installed`` >= ``patched`` (both parsed as semver).

    Used to decide the repo is already fixed (not affected). Returns False when
    either version can't be parsed as semver (e.g. non-semver maven versions) —
    we then do NOT gate and proceed, since we can't prove the repo is safe. So
    the affected-check is conservative: it only skips remediation when it can
    positively confirm the installed version is at/above the patched one.
    """
    try:
        return semver.Version.parse(installed) >= semver.Version.parse(patched)
    except (ValueError, TypeError):
        return False


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

    ``package`` is GitHub's canonical package name (the matched advisory entry's
    own name — maven ``group:artifact``, npm ``@scope/name``), i.e. the form PR
    titles use.

    Runs up to two searches against the target repo's OPEN pull requests:
      1. By CVE id — catches PRs that reference the CVE in the title or body
         (and our own bot PRs, which carry the CVE in the description/branch).
      2. By quoted package + version — catches Dependabot / Mend / human "Bump
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

    # 2) package (+ version), quoted for exact matching. Unquoted, GitHub
    # tokenizes punctuated terms (e.g. "1.6.0" -> 1/6/0) and matches spuriously.
    # ``package`` here is GitHub's canonical name (maven group:artifact, npm
    # @scope/name) — the form PR titles use — so quoting it exact-matches those
    # PRs without any separator conversion.
    if package:
        terms = [f'"{package}"']
        if patched_version:
            terms.append(f'"{patched_version}"')
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
    logger.info(f"[{request_id}] REMEDIATE_CVE_PR_SEARCH_RESULT: {len(items)} open PR(s)")
    if not items:
        return None

    top = items[0]
    return {
        'url': top.get('html_url', ''),
        'title': top.get('title', ''),
        'number': str(top.get('number', '')),
    }
