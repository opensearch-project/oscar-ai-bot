# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for security advisories remediation_handler.py.

These tests verify the remediate_cve pre-flight logic:
  - input validation,
  - repo resolution from the scans index (main branch) incl. not-affected and
    multi-repo disambiguation,
  - ecosystem read from the cluster (cluster vocabulary),
  - patched-version derivation via the GitHub Advisory API,
  - the unsupported-ecosystem and no-patched-version gates,
  - the existing-PR dedup check (match by CVE id or package+version).

Both OpenSearch (scans) and GitHub network calls are mocked — no live HTTP.
"""

import importlib.util
import os
from unittest.mock import MagicMock, patch

# Path to the real remediation_handler module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'SecurityAdvisories', 'lambda',
)


class _FakeResp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')

    def json(self):
        return self._payload


# --- scans-index (OpenSearch) fakes ----------------------------------------

def _scans_hit(repo='https://github.com/opensearch-project/OpenSearch-Dashboards.git',
               name='OpenSearch Dashboards', ecosystem='npm',
               cve='CVE-2023-45857', pkg='axios'):
    """A scans hit shaped like the real response: project in _source, and the
    matched vulnerability delivered via nested inner_hits."""
    return {
        '_source': {'project': {'repo': repo, 'name': name, 'tag': 'origin/main'}},
        'inner_hits': {
            'vulnerabilities': {
                'hits': {
                    'hits': [
                        {'_source': {'id': cve,
                                     'package': {'ecosystem': ecosystem, 'name': pkg}}},
                    ],
                },
            },
        },
    }


def _scans_response(hits):
    return {'hits': {'hits': hits}}


def _make_mock_aws(hits=None):
    """Mock aws_utils with get_latest_scans_index + opensearch_request.

    Default: one main-branch hit resolving to opensearch-project/OpenSearch-Dashboards.
    """
    if hits is None:
        hits = [_scans_hit()]
    m = MagicMock()
    m.get_latest_scans_index.return_value = 'scans-000181'
    m.opensearch_request.return_value = _scans_response(hits)
    return m


def _load_remediation_handler(mock_aws=None):
    """Import a fresh remediation_handler with aws_utils mocked."""
    if mock_aws is None:
        mock_aws = _make_mock_aws()

    # Load the real query_utils module so error_response/connection_error work
    query_utils_spec = importlib.util.spec_from_file_location(
        'query_utils',
        os.path.join(_LAMBDA_PATH, 'query_utils.py'),
    )
    query_utils_mod = importlib.util.module_from_spec(query_utils_spec)
    query_utils_spec.loader.exec_module(query_utils_mod)

    with patch.dict('sys.modules', {
        'aws_utils': mock_aws,
        'config': MagicMock(),
        'query_utils': query_utils_mod,
    }):
        spec = importlib.util.spec_from_file_location(
            'sa_remediation_handler',
            os.path.join(_LAMBDA_PATH, 'remediation_handler.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod, mock_aws


# --- GitHub (requests) fakes -----------------------------------------------

def _install_fake_github(
    mod,
    advisories=None,
    cve_pr_items=None,
    pkg_pr_items=None,
    advisory_error=None,
    search_error=None,
):
    """Replace the module's ``requests`` with a fake routed by URL/query."""
    advisories = advisories if advisories is not None else []
    cve_pr_items = cve_pr_items or []
    pkg_pr_items = pkg_pr_items or []

    def _get(url, params=None, headers=None, timeout=None):
        if url.endswith('/advisories'):
            if advisory_error:
                raise advisory_error
            return _FakeResp(advisories)
        if url.endswith('/search/issues'):
            if search_error:
                raise search_error
            q = (params or {}).get('q', '')
            items = cve_pr_items if 'CVE-' in q else pkg_pr_items
            return _FakeResp({'items': items})
        return _FakeResp({})

    fake_requests = MagicMock()
    fake_requests.get = MagicMock(side_effect=_get)
    mod.requests = fake_requests
    return fake_requests


def _advisory(ecosystem='npm', name='axios', patched='1.6.0'):
    return [{
        'ghsa_id': 'GHSA-test',
        'cve_id': 'CVE-2023-45857',
        'vulnerabilities': [{
            'package': {'ecosystem': ecosystem, 'name': name},
            'vulnerable_version_range': '< ' + patched,
            'first_patched_version': patched,
        }],
    }]


def _pr(number=42, title='Bump axios', url=None):
    return {
        'number': number,
        'title': title,
        'html_url': url or f'https://github.com/opensearch-project/repo/pull/{number}',
    }


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_missing_project_returns_error(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(mod)
        result = mod.handle_remediate_cve({'cve_id': 'CVE-2023-45857'}, 't1')
        assert result['status'] == 'error'
        assert 'required' in result['message'].lower()

    def test_missing_cve_returns_error(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(mod)
        result = mod.handle_remediate_cve({'project': 'OpenSearch'}, 't2')
        assert result['status'] == 'error'

    def test_missing_params_do_no_lookups(self):
        mod, mock_aws = _load_remediation_handler()
        fake = _install_fake_github(mod)
        mod.handle_remediate_cve({'cve_id': 'CVE-2023-45857'}, 't3')
        mock_aws.opensearch_request.assert_not_called()
        fake.get.assert_not_called()


# ---------------------------------------------------------------------------
# Repo resolution (scans index, main branch)
# ---------------------------------------------------------------------------


class TestResolveRepo:
    def test_resolves_owner_and_repo_from_cluster_url(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.6.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't4',
        )
        assert result['status'] == 'no_existing_pr'
        assert result['repository'] == 'opensearch-project/OpenSearch-Dashboards'

    def test_query_scopes_to_main_and_bundle_release_types(self):
        mod, mock_aws = _load_remediation_handler()
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.6.0'))
        mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 'trt',
        )
        # scoped to main + BOTH bundle release types
        _method, _path, body = mock_aws.opensearch_request.call_args[0]
        assert 'release_type.keyword' in body
        assert 'bundle_opensearch' in body
        assert 'bundle_opensearch_dashboards' in body
        assert 'origin/main' in body

    def test_not_affected_when_no_main_scan(self):
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[]))
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.6.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch'}, 't5',
        )
        assert result['status'] == 'not_affected'

    def test_not_affected_short_circuits_before_github(self):
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[]))
        fake = _install_fake_github(mod, advisories=_advisory())
        mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch'}, 't6',
        )
        fake.get.assert_not_called()  # no advisory lookup, no PR search

    def test_project_mismatch_single_repo(self):
        # CVE affects ONLY OpenSearch; user named 'alerting' -> must NOT silently
        # remediate OpenSearch
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[
                _scans_hit('https://github.com/opensearch-project/OpenSearch.git', 'OpenSearch'),
            ]),
        )
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'alerting'}, 'tpm1',
        )
        assert result['status'] == 'project_mismatch'
        assert result['requested_project'] == 'alerting'
        assert result['affected_repositories'] == ['opensearch-project/OpenSearch']

    def test_project_mismatch_when_named_repo_not_among_affected(self):
        # CVE affects sql + alerting; user named 'zzz' (neither) -> mismatch,
        # not an ambiguous "pick one" prompt
        hits = [
            _scans_hit('https://github.com/opensearch-project/sql.git', 'SQL: OpenSearch Plugin'),
            _scans_hit('https://github.com/opensearch-project/alerting.git', 'Alerting: OpenSearch Plugin'),
        ]
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=hits))
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'zzz'}, 't7',
        )
        assert result['status'] == 'project_mismatch'
        assert set(result['affected_repositories']) == {
            'opensearch-project/sql', 'opensearch-project/alerting',
        }

    def test_project_disambiguates_multiple_repos(self):
        hits = [
            _scans_hit('https://github.com/opensearch-project/sql.git', 'SQL: OpenSearch Plugin'),
            _scans_hit('https://github.com/opensearch-project/alerting.git', 'Alerting: OpenSearch Plugin'),
        ]
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=hits))
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'alerting'}, 't8',
        )
        assert result['status'] == 'no_existing_pr'
        assert result['repository'] == 'opensearch-project/alerting'

    def test_disambiguates_by_display_name(self):
        # user text matches the DISPLAY name only (not the repo slug)
        hits = [
            _scans_hit('https://github.com/opensearch-project/sql.git', 'SQL: OpenSearch Plugin'),
            _scans_hit('https://github.com/opensearch-project/alerting.git', 'Alerting: OpenSearch Plugin'),
        ]
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=hits))
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'SQL: OpenSearch'}, 't8b',
        )
        assert result['status'] == 'no_existing_pr'
        assert result['repository'] == 'opensearch-project/sql'

    def test_ambiguous_after_narrowing_returns_multiple(self):
        # 'dashboards' matches BOTH repo slugs -> narrowing leaves >1 -> ambiguous
        hits = [
            _scans_hit('https://github.com/opensearch-project/dashboards-observability.git',
                       'Observability Dashboards'),
            _scans_hit('https://github.com/opensearch-project/dashboards-reporting.git',
                       'Reporting Dashboards'),
        ]
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=hits))
        _install_fake_github(mod, advisories=_advisory('npm', 'x', '1.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'dashboards'}, 't8c',
        )
        assert result['status'] == 'multiple_repos'
        assert set(result['candidates']) == {
            'opensearch-project/dashboards-observability',
            'opensearch-project/dashboards-reporting',
        }

    def test_unparseable_repo_url_is_skipped(self):
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_scans_hit('not-a-url', 'Weird')]),
        )
        _install_fake_github(mod, advisories=_advisory())
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'Weird'}, 't9',
        )
        # only candidate was unparseable -> treated as not affected
        assert result['status'] == 'not_affected'

    def test_multiple_packages_in_one_repo(self):
        # one CVE affects two packages in the same repo (netty epoll + kqueue)
        # -> surface multiple_packages instead of silently remediating the first
        hit = {
            '_source': {'project': {
                'repo': 'https://github.com/opensearch-project/OpenSearch.git',
                'name': 'OpenSearch', 'tag': 'origin/main'}},
            'inner_hits': {'vulnerabilities': {'hits': {'hits': [
                {'_source': {'id': 'CVE-2026-45536', 'package': {
                    'ecosystem': 'maven', 'name': 'io.netty/netty-transport-native-epoll'}}},
                {'_source': {'id': 'CVE-2026-45536', 'package': {
                    'ecosystem': 'maven', 'name': 'io.netty/netty-transport-native-kqueue'}}},
            ]}}},
        }
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[hit]))
        _install_fake_github(mod, advisories=_advisory('maven', 'x', '1.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2026-45536', 'project': 'OpenSearch'}, 'tmpk',
        )
        assert result['status'] == 'multiple_packages'
        assert result['repository'] == 'opensearch-project/OpenSearch'
        assert set(result['packages']) == {
            'io.netty/netty-transport-native-epoll',
            'io.netty/netty-transport-native-kqueue',
        }

    def test_resolve_network_error(self):
        mock_aws = _make_mock_aws()
        mock_aws.opensearch_request.side_effect = RuntimeError('cluster down')
        mod, _ = _load_remediation_handler(mock_aws=mock_aws)
        _install_fake_github(mod, advisories=_advisory())
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch'}, 't10',
        )
        assert result['status'] == 'error'
        assert result['type'] == 'connection_error'   # routed through query_utils
        assert result['retryable'] is False


# ---------------------------------------------------------------------------
# Derivation via the GitHub Advisory API
# ---------------------------------------------------------------------------


class TestDerive:
    def test_derives_ecosystem_package_version(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.6.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't11',
        )
        assert result['status'] == 'no_existing_pr'
        assert result['ecosystem'] == 'npm'
        assert result['package'] == 'axios'
        assert result['patched_version'] == '1.6.0'

    def test_no_advisory_found_returns_no_patched_version(self):
        # cluster resolved the CVE (it's real), but GitHub has no advisory ->
        # not an error; we just can't determine a patched version
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_scans_hit(cve='CVE-0000-00000')]),
        )
        _install_fake_github(mod, advisories=[])
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-0000-00000', 'project': 'OpenSearch-Dashboards'}, 't12',
        )
        assert result['status'] == 'no_patched_version'

    def test_first_patched_version_as_object(self):
        mod, _ = _load_remediation_handler()
        adv = _advisory('npm', 'axios', '1.6.0')
        adv[0]['vulnerabilities'][0]['first_patched_version'] = {'identifier': '1.6.0'}
        _install_fake_github(mod, advisories=adv)
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't14',
        )
        assert result['patched_version'] == '1.6.0'

    def test_matches_github_entry_by_cluster_package(self):
        # cluster says the repo uses 'axios'; the advisory lists TWO packages.
        # Must pick axios's version, not the other/first entry.
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_scans_hit(ecosystem='npm', pkg='axios')]),
        )
        adv = [{'vulnerabilities': [
            {'package': {'ecosystem': 'npm', 'name': 'other-lib'}, 'first_patched_version': '9.9.9'},
            {'package': {'ecosystem': 'npm', 'name': 'axios'}, 'first_patched_version': '1.6.0'},
        ]}]
        _install_fake_github(mod, advisories=adv)
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't16a',
        )
        assert result['package'] == 'axios'          # from the cluster
        assert result['patched_version'] == '1.6.0'  # matched entry, not 9.9.9

    def test_matches_maven_coordinate_by_containment(self):
        # cluster package 'bc-fips'; GitHub names it 'org.bouncycastle:bc-fips'
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_scans_hit(ecosystem='maven', pkg='bc-fips')]),
        )
        adv = [{'vulnerabilities': [
            {'package': {'ecosystem': 'maven', 'name': 'org.bouncycastle:bc-fips'},
             'first_patched_version': '2.1.3'},
        ]}]
        _install_fake_github(mod, advisories=adv)
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch'}, 't16b',
        )
        assert result['package'] == 'bc-fips'
        assert result['patched_version'] == '2.1.3'

    def test_matches_maven_slash_vs_colon_separator(self):
        # cluster writes maven as group/artifact; GitHub writes group:artifact
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[
                _scans_hit(ecosystem='maven', pkg='io.netty/netty-transport-native-epoll'),
            ]),
        )
        adv = [{'vulnerabilities': [
            {'package': {'ecosystem': 'maven', 'name': 'io.netty:netty-transport-native-epoll'},
             'first_patched_version': '4.1.118.Final'},
        ]}]
        _install_fake_github(mod, advisories=adv)
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2026-45536', 'project': 'OpenSearch'}, 't16d',
        )
        assert result['package'] == 'io.netty/netty-transport-native-epoll'  # cluster format kept
        assert result['patched_version'] == '4.1.118.Final'

    def test_no_patched_version_when_package_not_in_advisory(self):
        # the repo's package isn't among the advisory's packages -> no known fix
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_scans_hit(ecosystem='npm', pkg='some-unlisted-pkg')]),
        )
        adv = [{'vulnerabilities': [
            {'package': {'ecosystem': 'npm', 'name': 'axios'}, 'first_patched_version': '1.6.0'},
        ]}]
        _install_fake_github(mod, advisories=adv)
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't16c',
        )
        assert result['status'] == 'no_patched_version'


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


class TestGates:
    def test_unsupported_ecosystem(self):
        # ecosystem comes from the cluster
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_scans_hit(ecosystem='go')]),
        )
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.6.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't17',
        )
        assert result['status'] == 'unsupported_ecosystem'
        assert result['ecosystem'] == 'go'

    def test_no_patched_version(self):
        mod, _ = _load_remediation_handler()  # cluster resolves npm (supported)
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', ''))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't18',
        )
        assert result['status'] == 'no_patched_version'

    def test_unsupported_ecosystem_short_circuits_before_github(self):
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_scans_hit(ecosystem='go')]),
        )
        fake = _install_fake_github(mod, advisories=_advisory('go', 'some/mod', '2.0.0'))
        mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't19',
        )
        # the ecosystem gate (from the cluster) fires before any GitHub call
        fake.get.assert_not_called()


# ---------------------------------------------------------------------------
# Dedup check
# ---------------------------------------------------------------------------


class TestDedup:
    def test_open_pr_matched_by_cve_id(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(
            mod,
            advisories=_advisory('npm', 'axios', '1.6.0'),
            cve_pr_items=[_pr(101, 'Fix CVE-2023-45857')],
        )
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't20',
        )
        assert result['status'] == 'pr_exists'
        assert result['pr_url'].endswith('/101')
        assert 'CVE id' in result['matched_by']

    def test_open_pr_matched_by_package_version(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(
            mod,
            advisories=_advisory('npm', 'axios', '1.6.0'),
            cve_pr_items=[],
            pkg_pr_items=[_pr(202, 'Bump axios from 1.5.0 to 1.6.0')],
        )
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't21',
        )
        assert result['status'] == 'pr_exists'
        assert result['pr_url'].endswith('/202')
        assert 'package/version' in result['matched_by']

    def test_no_open_pr_returns_no_existing_pr(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(
            mod,
            advisories=_advisory('npm', 'axios', '1.6.0'),
            cve_pr_items=[],
            pkg_pr_items=[],
        )
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't22',
        )
        assert result['status'] == 'no_existing_pr'
        assert result['repository'] == 'opensearch-project/OpenSearch-Dashboards'

    def test_package_search_uses_quoted_github_coordinate(self):
        # cluster stores maven as group/artifact; GitHub (and PR titles) use
        # group:artifact. Dedup should search the quoted GitHub coordinate +
        # quoted version — not the cluster's slash form.
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[
                _scans_hit(ecosystem='maven', pkg='io.netty/netty-transport-native-epoll'),
            ]),
        )
        fake = _install_fake_github(
            mod,
            advisories=[{'vulnerabilities': [
                {'package': {'ecosystem': 'maven',
                             'name': 'io.netty:netty-transport-native-epoll'},
                 'first_patched_version': '4.2.15.Final'},
            ]}],
            cve_pr_items=[], pkg_pr_items=[],
        )
        mod.handle_remediate_cve(
            {'cve_id': 'CVE-2026-45536', 'project': 'OpenSearch'}, 'tqm',
        )
        pkg_q = next(
            c.kwargs['params']['q'] for c in fake.get.call_args_list
            if c.args and c.args[0].endswith('/search/issues')
            and 'netty' in c.kwargs['params']['q']
            and 'CVE-' not in c.kwargs['params']['q']
        )
        assert '"io.netty:netty-transport-native-epoll"' in pkg_q  # GitHub colon form, quoted
        assert '"4.2.15.Final"' in pkg_q                           # version quoted
        assert 'io.netty/netty-transport-native-epoll' not in pkg_q  # not the slash form


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_advisory_lookup_network_error(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(mod, advisory_error=RuntimeError('boom'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't23',
        )
        assert result['status'] == 'error'
        assert result['type'] == 'github_error'
        assert 'advisory' in result['message'].lower()

    def test_pr_search_network_error(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(
            mod,
            advisories=_advisory('npm', 'axios', '1.6.0'),
            search_error=RuntimeError('search 422'),
        )
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 't24',
        )
        assert result['status'] == 'error'
        assert result['type'] == 'github_error'
        assert 'pull request' in result['message'].lower()


# ---------------------------------------------------------------------------
# Ecosystem source: the cluster, not GitHub (cluster vocabulary)
# ---------------------------------------------------------------------------


class TestEcosystemSource:
    def test_ecosystem_comes_from_cluster_not_github(self):
        # cluster says maven; the GitHub advisory says npm — result must be maven
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_scans_hit(ecosystem='maven')]),
        )
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.6.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'project': 'OpenSearch-Dashboards'}, 'te1',
        )
        assert result['status'] == 'no_existing_pr'
        assert result['ecosystem'] == 'maven'

    def test_vuln_ecosystem_handles_dict_and_list_and_missing(self):
        mod, _ = _load_remediation_handler()
        # package as a dict, lower-cased
        assert mod._vuln_ecosystem({'package': {'ecosystem': 'MAVEN'}}) == 'maven'
        # package as a list (nested field can come back as an array) -> first
        assert mod._vuln_ecosystem({'package': [{'ecosystem': 'npm'}]}) == 'npm'
        # missing package / ecosystem -> ''
        assert mod._vuln_ecosystem({}) == ''
        assert mod._vuln_ecosystem({'package': {}}) == ''


# ---------------------------------------------------------------------------
# Repo URL parsing
# ---------------------------------------------------------------------------


class TestParseRepoUrl:
    def test_https_with_git_suffix(self):
        mod, _ = _load_remediation_handler()
        assert mod._parse_repo_url(
            'https://github.com/opensearch-project/sql.git'
        ) == ('opensearch-project', 'sql')

    def test_https_without_git_suffix(self):
        mod, _ = _load_remediation_handler()
        assert mod._parse_repo_url(
            'https://github.com/opensearch-project/sql'
        ) == ('opensearch-project', 'sql')

    def test_ssh_form(self):
        mod, _ = _load_remediation_handler()
        assert mod._parse_repo_url(
            'git@github.com:opensearch-project/cross-cluster-replication.git'
        ) == ('opensearch-project', 'cross-cluster-replication')

    def test_unparseable_returns_empty(self):
        mod, _ = _load_remediation_handler()
        assert mod._parse_repo_url('not-a-url') == ('', '')
        assert mod._parse_repo_url('') == ('', '')
        assert mod._parse_repo_url('https://github.com/only-owner') == ('', '')
