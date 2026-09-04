# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for security advisories remediation_handler.py.

Repository selection is split across two action-group functions:
  - list_affected_repositories(cve_id) — returns the repos a CVE affects on main
    (the agent resolves the user's phrasing to one; the handler does NO matching),
  - remediate_cve(cve_id, repo_name) — verifies the chosen repo is in the
    affected set (exact membership guard), then runs the pre-flight.

These tests verify:
  - input validation,
  - listing affected repos from the scans index (main branch, bundle scoped),
  - the exact-membership guard in remediate_cve (in-set resolves; out-of-set
    returns not_affected),
  - ecosystem read from the cluster (cluster vocabulary),
  - patched-version derivation via the GitHub Advisory API,
  - the unsupported-ecosystem and no-patched-version gates,
  - the existing-PR dedup check (match by CVE id or package+version),
  - dispatch to the ecosystem remediation container Lambda.

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
               cve='CVE-2023-45857', pkg='axios', version=''):
    """A scans hit shaped like the real response: project in _source, and the
    matched vulnerability delivered via nested inner_hits."""
    return {
        '_source': {'project': {'repo': repo, 'name': name, 'tag': 'origin/main'}},
        'inner_hits': {
            'vulnerabilities': {
                'hits': {
                    'hits': [
                        {'_source': {'id': cve, 'package': {
                            'ecosystem': ecosystem, 'name': pkg, 'version': version}}},
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


def _advisory_multi(name, entries, ecosystem='npm'):
    """Advisory listing the same package once per affected line.

    ``entries`` = list of ``(vulnerable_version_range, first_patched_version)``.
    """
    return [{
        'ghsa_id': 'GHSA-multi',
        'cve_id': 'CVE-2026-12143',
        'vulnerabilities': [
            {'package': {'ecosystem': ecosystem, 'name': name},
             'vulnerable_version_range': rng,
             'first_patched_version': patched}
            for rng, patched in entries
        ],
    }]


# The real form-data advisory (CVE-2026-12143): three affected lines.
_FORM_DATA_RANGES = [
    ('< 2.5.6', '2.5.6'),
    ('>= 3.0.0, < 3.0.5', '3.0.5'),
    ('>= 4.0.0, < 4.0.6', '4.0.6'),
]


def _pr(number=42, title='Bump axios', url=None):
    return {
        'number': number,
        'title': title,
        'html_url': url or f'https://github.com/opensearch-project/repo/pull/{number}',
    }


def _two_netty_packages_hit():
    """One CVE hitting two packages (netty epoll + kqueue) in OpenSearch."""
    return {
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


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_missing_repo_name_returns_error(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(mod)
        result = mod.handle_remediate_cve({'cve_id': 'CVE-2023-45857'}, 't1')
        assert result['status'] == 'error'
        assert 'required' in result['message'].lower()

    def test_missing_cve_returns_error(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(mod)
        result = mod.handle_remediate_cve({'repo_name': 'OpenSearch'}, 't2')
        assert result['status'] == 'error'

    def test_missing_params_do_no_lookups(self):
        mod, mock_aws = _load_remediation_handler()
        fake = _install_fake_github(mod)
        mod.handle_remediate_cve({'cve_id': 'CVE-2023-45857'}, 't3')
        mock_aws.opensearch_request.assert_not_called()
        fake.get.assert_not_called()

    def test_list_affected_missing_cve_returns_error(self):
        mod, mock_aws = _load_remediation_handler()
        result = mod.handle_list_affected_repositories({}, 'la0')
        assert result['status'] == 'error'
        mock_aws.opensearch_request.assert_not_called()


# ---------------------------------------------------------------------------
# list_affected_repositories (scans index, main branch, bundle scoped)
# ---------------------------------------------------------------------------


class TestListAffectedRepositories:
    def test_lists_single_affected_repo_with_ecosystem(self):
        mod, _ = _load_remediation_handler()  # default: OpenSearch-Dashboards, npm/axios
        result = mod.handle_list_affected_repositories(
            {'cve_id': 'CVE-2023-45857'}, 'la1',
        )
        assert result['status'] == 'affected_repositories'
        repos = result['repositories']
        assert len(repos) == 1
        assert repos[0]['repository'] == 'opensearch-project/OpenSearch-Dashboards'
        assert repos[0]['repo_name'] == 'OpenSearch-Dashboards'
        assert repos[0]['ecosystem'] == 'npm'

    def test_lists_all_affected_repos_sorted(self):
        hits = [
            _scans_hit('https://github.com/opensearch-project/sql.git', 'SQL: OpenSearch Plugin'),
            _scans_hit('https://github.com/opensearch-project/alerting.git', 'Alerting: OpenSearch Plugin'),
        ]
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=hits))
        result = mod.handle_list_affected_repositories(
            {'cve_id': 'CVE-2023-45857'}, 'la2',
        )
        names = [r['repository'] for r in result['repositories']]
        assert names == ['opensearch-project/alerting', 'opensearch-project/sql']

    def test_not_affected_when_no_main_scan(self):
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[]))
        result = mod.handle_list_affected_repositories(
            {'cve_id': 'CVE-2023-45857'}, 'la3',
        )
        assert result['status'] == 'not_affected'

    def test_query_scopes_to_main_and_bundle_release_types(self):
        mod, mock_aws = _load_remediation_handler()
        mod.handle_list_affected_repositories({'cve_id': 'CVE-2023-45857'}, 'la4')
        _method, _path, body = mock_aws.opensearch_request.call_args[0]
        assert 'release_type.keyword' in body
        assert 'bundle_opensearch' in body
        assert 'bundle_opensearch_dashboards' in body
        assert 'origin/main' in body

    def test_does_no_github_calls(self):
        mod, _ = _load_remediation_handler()
        fake = _install_fake_github(mod)
        mod.handle_list_affected_repositories({'cve_id': 'CVE-2023-45857'}, 'la5')
        fake.get.assert_not_called()

    def test_unparseable_repo_url_is_skipped(self):
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_scans_hit('not-a-url', 'Weird')]),
        )
        result = mod.handle_list_affected_repositories(
            {'cve_id': 'CVE-2023-45857'}, 'la6',
        )
        # only candidate was unparseable -> treated as not affected
        assert result['status'] == 'not_affected'

    def test_resolve_network_error(self):
        mock_aws = _make_mock_aws()
        mock_aws.opensearch_request.side_effect = RuntimeError('cluster down')
        mod, _ = _load_remediation_handler(mock_aws=mock_aws)
        result = mod.handle_list_affected_repositories(
            {'cve_id': 'CVE-2023-45857'}, 'la7',
        )
        assert result['status'] == 'error'
        assert result['type'] == 'connection_error'
        assert result['retryable'] is False


# ---------------------------------------------------------------------------
# remediate_cve: exact-membership guard (the chosen repo must be affected)
# ---------------------------------------------------------------------------


class TestRepoMembership:
    def test_resolves_when_repo_name_matches(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.6.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't4',
        )
        assert result['status'] == 'remediation_unavailable'
        assert result['repository'] == 'opensearch-project/OpenSearch-Dashboards'

    def test_accepts_owner_slash_repo_form(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.6.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857',
             'repo_name': 'opensearch-project/OpenSearch-Dashboards'}, 't4b',
        )
        assert result['status'] == 'remediation_unavailable'
        assert result['repository'] == 'opensearch-project/OpenSearch-Dashboards'

    def test_repo_name_match_is_case_insensitive(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.6.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'opensearch-dashboards'}, 't4c',
        )
        assert result['status'] == 'remediation_unavailable'

    def test_not_affected_when_no_main_scan(self):
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[]))
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.6.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch'}, 't5',
        )
        assert result['status'] == 'not_affected'

    def test_not_affected_short_circuits_before_github(self):
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[]))
        fake = _install_fake_github(mod, advisories=_advisory())
        mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch'}, 't6',
        )
        fake.get.assert_not_called()  # no advisory lookup, no PR search

    def test_repo_not_in_affected_set_returns_not_affected(self):
        # CVE affects ONLY OpenSearch; caller passes 'alerting' -> not_affected,
        # with the real affected repos listed (membership guard, not matching).
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[
                _scans_hit('https://github.com/opensearch-project/OpenSearch.git', 'OpenSearch'),
            ]),
        )
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'alerting'}, 'tpm1',
        )
        assert result['status'] == 'not_affected'
        assert result['requested_repository'] == 'alerting'
        assert result['affected_repositories'] == ['opensearch-project/OpenSearch']

    def test_repo_not_in_multi_repo_affected_set(self):
        hits = [
            _scans_hit('https://github.com/opensearch-project/sql.git', 'SQL: OpenSearch Plugin'),
            _scans_hit('https://github.com/opensearch-project/alerting.git', 'Alerting: OpenSearch Plugin'),
        ]
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=hits))
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'zzz'}, 't7',
        )
        assert result['status'] == 'not_affected'
        assert set(result['affected_repositories']) == {
            'opensearch-project/sql', 'opensearch-project/alerting',
        }

    def test_selects_named_repo_from_multiple(self):
        hits = [
            _scans_hit('https://github.com/opensearch-project/sql.git', 'SQL: OpenSearch Plugin'),
            _scans_hit('https://github.com/opensearch-project/alerting.git', 'Alerting: OpenSearch Plugin'),
        ]
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=hits))
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'alerting'}, 't8',
        )
        assert result['status'] == 'remediation_unavailable'
        assert result['repository'] == 'opensearch-project/alerting'

    def test_selects_exact_repo_among_siblings(self):
        # exact membership picks core 'OpenSearch' — no substring confusion with
        # sibling repos/display names (the resolution the agent does upstream).
        hits = [
            _scans_hit('https://github.com/opensearch-project/OpenSearch.git', 'OpenSearch'),
            _scans_hit('https://github.com/opensearch-project/sql.git', 'SQL: OpenSearch Plugin'),
            _scans_hit('https://github.com/opensearch-project/alerting.git', 'Alerting: OpenSearch Plugin'),
        ]
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=hits))
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch'}, 't8d',
        )
        assert result['status'] == 'remediation_unavailable'
        assert result['repository'] == 'opensearch-project/OpenSearch'

    def test_unparseable_repo_url_is_skipped(self):
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_scans_hit('not-a-url', 'Weird')]),
        )
        _install_fake_github(mod, advisories=_advisory())
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'Weird'}, 't9',
        )
        # only candidate was unparseable -> nothing affected -> not_affected
        assert result['status'] == 'not_affected'

    def test_multiple_packages_in_one_repo(self):
        # one CVE affects two packages in the same repo (netty epoll + kqueue)
        # -> surface multiple_packages instead of silently remediating the first
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_two_netty_packages_hit()]),
        )
        _install_fake_github(mod, advisories=_advisory('maven', 'x', '1.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2026-45536', 'repo_name': 'OpenSearch'}, 'tmpk',
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
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch'}, 't10',
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
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't11',
        )
        assert result['status'] == 'remediation_unavailable'
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
            {'cve_id': 'CVE-0000-00000', 'repo_name': 'OpenSearch-Dashboards'}, 't12',
        )
        assert result['status'] == 'no_patched_version'

    def test_first_patched_version_as_object(self):
        mod, _ = _load_remediation_handler()
        adv = _advisory('npm', 'axios', '1.6.0')
        adv[0]['vulnerabilities'][0]['first_patched_version'] = {'identifier': '1.6.0'}
        _install_fake_github(mod, advisories=adv)
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't14',
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
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't16a',
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
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't16b',
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
            {'cve_id': 'CVE-2026-45536', 'repo_name': 'OpenSearch-Dashboards'}, 't16d',
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
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't16c',
        )
        assert result['status'] == 'no_patched_version'

    def test_multirange_selects_patch_for_installed_line(self):
        # form-data advisory has 3 affected lines; repo is on 4.0.4 -> must pick
        # 4.0.6, NOT the first-listed 2.5.6.
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[_scans_hit(
            'https://github.com/opensearch-project/alerting-dashboards-plugin.git',
            'Alerting: OpenSearch Dashboards Plugin',
            ecosystem='npm', pkg='form-data', version='4.0.4')]))
        _install_fake_github(mod, advisories=_advisory_multi('form-data', _FORM_DATA_RANGES))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2026-12143', 'repo_name': 'alerting-dashboards-plugin'}, 'tmr1',
        )
        assert result['status'] == 'remediation_unavailable'
        assert result['patched_version'] == '4.0.6'

    def test_multirange_older_install_selects_lower_patch(self):
        # same advisory, repo on 2.0.0 -> the < 2.5.6 line -> 2.5.6
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[_scans_hit(
            ecosystem='npm', pkg='form-data', version='2.0.0')]))
        _install_fake_github(mod, advisories=_advisory_multi('form-data', _FORM_DATA_RANGES))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2026-12143', 'repo_name': 'OpenSearch-Dashboards'}, 'tmr2',
        )
        assert result['patched_version'] == '2.5.6'

    def test_multirange_no_installed_version_falls_back_to_first(self):
        # no installed version in the cluster hit -> first entry (2.5.6)
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[_scans_hit(
            ecosystem='npm', pkg='form-data', version='')]))
        _install_fake_github(mod, advisories=_advisory_multi('form-data', _FORM_DATA_RANGES))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2026-12143', 'repo_name': 'OpenSearch-Dashboards'}, 'tmr3',
        )
        assert result['patched_version'] == '2.5.6'

    def test_multirange_non_semver_version_falls_back_to_first(self):
        # a maven-style installed version can't be semver-parsed -> first entry,
        # never a wrong guess (range logic degrades gracefully for maven).
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[_scans_hit(
            'https://github.com/opensearch-project/OpenSearch.git', 'OpenSearch',
            ecosystem='maven', pkg='io.netty/netty', version='4.1.134.Final')]))
        _install_fake_github(mod, advisories=_advisory_multi('io.netty:netty', [
            ('< 4.1.135', '4.1.135'),
            ('>= 4.2.0, < 4.2.15', '4.2.15'),
        ], ecosystem='maven'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2026-12143', 'repo_name': 'OpenSearch'}, 'tmr4',
        )
        assert result['patched_version'] == '4.1.135'


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
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't17',
        )
        assert result['status'] == 'unsupported_ecosystem'
        assert result['ecosystem'] == 'go'

    def test_no_patched_version(self):
        mod, _ = _load_remediation_handler()  # cluster resolves npm (supported)
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', ''))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't18',
        )
        assert result['status'] == 'no_patched_version'

    def test_unsupported_ecosystem_short_circuits_before_github(self):
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_scans_hit(ecosystem='go')]),
        )
        fake = _install_fake_github(mod, advisories=_advisory('go', 'some/mod', '2.0.0'))
        mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't19',
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
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't20',
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
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't21',
        )
        assert result['status'] == 'pr_exists'
        assert result['pr_url'].endswith('/202')
        assert 'package/version' in result['matched_by']

    def test_no_open_pr_returns_remediation_unavailable(self):
        mod, _ = _load_remediation_handler()
        _install_fake_github(
            mod,
            advisories=_advisory('npm', 'axios', '1.6.0'),
            cve_pr_items=[],
            pkg_pr_items=[],
        )
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't22',
        )
        assert result['status'] == 'remediation_unavailable'
        assert result['repository'] == 'opensearch-project/OpenSearch-Dashboards'

    def test_package_search_uses_quoted_github_coordinate(self):
        # cluster stores maven as group/artifact; GitHub (and PR titles) use
        # group:artifact. Dedup should search the quoted GitHub coordinate +
        # quoted version — not the cluster's slash form.
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[
                _scans_hit('https://github.com/opensearch-project/OpenSearch.git', 'OpenSearch',
                           ecosystem='maven', pkg='io.netty/netty-transport-native-epoll'),
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
            {'cve_id': 'CVE-2026-45536', 'repo_name': 'OpenSearch'}, 'tqm',
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
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't23',
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
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 't24',
        )
        assert result['status'] == 'error'
        assert result['type'] == 'github_error'
        assert 'pull request' in result['message'].lower()


# ---------------------------------------------------------------------------
# Ecosystem source: the cluster, not GitHub (cluster vocabulary)
# ---------------------------------------------------------------------------


class TestEcosystemSource:
    def test_ecosystem_comes_from_cluster_not_github(self):
        # cluster says maven; the advisory lists the package under BOTH npm and
        # maven — the result ecosystem is the cluster's (maven), and the maven
        # advisory entry (not npm's) supplies the patched version.
        mod, _ = _load_remediation_handler(
            mock_aws=_make_mock_aws(hits=[_scans_hit(ecosystem='maven', pkg='axios')]),
        )
        adv = [{'vulnerabilities': [
            {'package': {'ecosystem': 'npm', 'name': 'axios'}, 'first_patched_version': '1.6.0'},
            {'package': {'ecosystem': 'maven', 'name': 'axios'}, 'first_patched_version': '9.9.9'},
        ]}]
        _install_fake_github(mod, advisories=adv)
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 'te1',
        )
        assert result['status'] == 'remediation_unavailable'
        assert result['ecosystem'] == 'maven'
        assert result['patched_version'] == '9.9.9'   # maven entry, not npm's 1.6.0

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
# Ecosystem-scoped advisory selection + the "already patched" affected-gate
# ---------------------------------------------------------------------------


class TestEcosystemFilterAndAffectedGate:
    def _multi_eco_langsmith_advisory(self):
        # The real CVE-2026-45134 shape: langsmith under pip (< 0.8.0) AND npm
        # (< 0.6.0), with DIFFERENT patched versions, plus unrelated packages.
        return [{'vulnerabilities': [
            {'package': {'ecosystem': 'pip', 'name': 'langsmith'},
             'vulnerable_version_range': '< 0.8.0', 'first_patched_version': '0.8.0'},
            {'package': {'ecosystem': 'npm', 'name': 'langsmith'},
             'vulnerable_version_range': '< 0.6.0', 'first_patched_version': '0.6.0'},
            {'package': {'ecosystem': 'pip', 'name': 'langchain'},
             'vulnerable_version_range': '< 0.3.30', 'first_patched_version': '0.3.30'},
        ]}]

    def test_picks_our_ecosystem_entry_not_another(self):
        # cluster = npm langsmith; the advisory lists langsmith under pip (0.8.0)
        # and npm (0.6.0). Must derive the NPM patched version, not pip's.
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[
            _scans_hit(ecosystem='npm', pkg='langsmith', version='0.4.0')]))
        _install_fake_github(mod, advisories=self._multi_eco_langsmith_advisory(),
                             cve_pr_items=[], pkg_pr_items=[])
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2026-45134', 'repo_name': 'OpenSearch-Dashboards'}, 'tee1',
        )
        # installed 0.4.0 < npm patched 0.6.0 -> genuinely affected, proceeds
        assert result['status'] == 'remediation_unavailable'
        assert result['patched_version'] == '0.6.0'   # npm entry, NOT pip's 0.8.0

    def test_already_patched_installed_at_or_above_npm_patch(self):
        # The exact OSD bug: installed 0.6.3 is >= the NPM patched 0.6.0, so the
        # repo is NOT affected -> already_patched, and NO dispatch/PR. (Without
        # the ecosystem filter it would wrongly pick pip's 0.8.0 and remediate.)
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[
            _scans_hit(ecosystem='npm', pkg='langsmith', version='0.6.3')]))
        fake = _install_fake_github(mod, advisories=self._multi_eco_langsmith_advisory())
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2026-45134', 'repo_name': 'OpenSearch-Dashboards'}, 'tee2',
        )
        assert result['status'] == 'already_patched'
        assert result['installed_version'] == '0.6.3'
        assert result['patched_version'] == '0.6.0'
        # No PR search happens once we know it's not affected (advisory lookup is
        # the only GitHub call before the gate).
        search_calls = [c for c in fake.get.call_args_list
                        if c.args and c.args[0].endswith('/search/issues')]
        assert search_calls == []

    def test_advisory_missing_our_ecosystem_returns_no_patched(self):
        # cluster = maven, but the advisory only lists the package under npm ->
        # no fix for our ecosystem -> no_patched_version (not another eco's fix).
        mod, _ = _load_remediation_handler(mock_aws=_make_mock_aws(hits=[
            _scans_hit(ecosystem='maven', pkg='axios')]))
        _install_fake_github(mod, advisories=_advisory('npm', 'axios', '1.6.0'))
        result = mod.handle_remediate_cve(
            {'cve_id': 'CVE-2023-45857', 'repo_name': 'OpenSearch-Dashboards'}, 'tee3',
        )
        assert result['status'] == 'no_patched_version'

    def test_at_or_above_version_non_semver_does_not_gate(self):
        # A non-semver (maven) installed version can't be compared -> the gate
        # does NOT fire (we can't prove it's safe), so remediation proceeds.
        mod, _ = _load_remediation_handler()
        assert mod._at_or_above_version('2.0.0', '1.6.0') is True
        assert mod._at_or_above_version('1.0.0', '1.6.0') is False
        assert mod._at_or_above_version('4.1.134.Final', '4.1.135') is False
        assert mod._at_or_above_version('', '1.6.0') is False


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


# ---------------------------------------------------------------------------
# _select_candidate: the exact-membership guard
# ---------------------------------------------------------------------------


class TestSelectCandidate:
    _CANDIDATES = [
        {'repo_owner': 'opensearch-project', 'repo_name': 'OpenSearch', 'packages': []},
        {'repo_owner': 'opensearch-project', 'repo_name': 'alerting-dashboards-plugin',
         'packages': []},
    ]

    def test_exact_slug(self):
        mod, _ = _load_remediation_handler()
        m = mod._select_candidate(self._CANDIDATES, 'alerting-dashboards-plugin')
        assert m['repo_name'] == 'alerting-dashboards-plugin'

    def test_owner_slash_repo_form(self):
        mod, _ = _load_remediation_handler()
        m = mod._select_candidate(self._CANDIDATES, 'opensearch-project/OpenSearch')
        assert m['repo_name'] == 'OpenSearch'

    def test_case_insensitive(self):
        mod, _ = _load_remediation_handler()
        assert mod._select_candidate(self._CANDIDATES, 'opensearch')['repo_name'] == 'OpenSearch'

    def test_no_match_returns_none(self):
        mod, _ = _load_remediation_handler()
        assert mod._select_candidate(self._CANDIDATES, 'nonexistent') is None

    def test_empty_repo_name_returns_none(self):
        mod, _ = _load_remediation_handler()
        assert mod._select_candidate(self._CANDIDATES, '') is None
        assert mod._select_candidate(self._CANDIDATES, '   ') is None


class TestGithubToken:
    """Read-side GitHub token resolution for _github_headers (env -> Secrets
    Manager, cached; used only to raise the API rate limit)."""

    def _fake_secrets_boto3(self, secret_string):
        client = MagicMock()
        client.get_secret_value.return_value = {'SecretString': secret_string}
        fake_boto3 = MagicMock()
        fake_boto3.client.return_value = client
        return fake_boto3, client

    def test_unauthenticated_when_no_token(self):
        mod, _ = _load_remediation_handler()
        with patch.dict(os.environ, {}, clear=True):
            headers = mod._github_headers()
        assert 'Authorization' not in headers
        assert headers['Accept'] == 'application/vnd.github+json'

    def test_raw_env_token_is_ignored(self):
        # A raw GH_TOKEN env var is NOT used (Secrets Manager only) — so with no
        # secret configured, the calls run unauthenticated even if GH_TOKEN is set.
        mod, _ = _load_remediation_handler()
        with patch.dict(os.environ, {'GH_TOKEN': 'ghp_env'}, clear=True):
            headers = mod._github_headers()
        assert 'Authorization' not in headers

    def test_secrets_manager_raw_token(self):
        mod, _ = _load_remediation_handler()
        mod.boto3, _ = self._fake_secrets_boto3('ghp_secret')
        with patch.dict(os.environ, {'GH_TOKEN_SECRET_NAME': 'sa-tok'}, clear=True):
            headers = mod._github_headers()
        assert headers['Authorization'] == 'Bearer ghp_secret'

    def test_secrets_manager_json_token(self):
        mod, _ = _load_remediation_handler()
        mod.boto3, _ = self._fake_secrets_boto3('{"token": "ghp_json"}')
        with patch.dict(os.environ, {'GH_TOKEN_SECRET_NAME': 'sa-tok'}, clear=True):
            headers = mod._github_headers()
        assert headers['Authorization'] == 'Bearer ghp_json'

    def test_token_cached_one_fetch(self):
        mod, _ = _load_remediation_handler()
        mod.boto3, client = self._fake_secrets_boto3('ghp_secret')
        with patch.dict(os.environ, {'GH_TOKEN_SECRET_NAME': 'sa-tok'}, clear=True):
            mod._github_headers()
            mod._github_headers()
        # cached per container -> Secrets Manager hit only once
        assert client.get_secret_value.call_count == 1

    def test_secrets_manager_failure_runs_unauthenticated(self):
        mod, _ = _load_remediation_handler()
        fake_boto3 = MagicMock()
        fake_boto3.client.return_value.get_secret_value.side_effect = RuntimeError('boom')
        mod.boto3 = fake_boto3
        with patch.dict(os.environ, {'GH_TOKEN_SECRET_NAME': 'sa-tok'}, clear=True):
            headers = mod._github_headers()
        assert 'Authorization' not in headers
