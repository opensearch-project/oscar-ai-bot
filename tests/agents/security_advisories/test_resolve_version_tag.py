# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for resolve_version_tag and enhanced enhance_query with resolved_tag.

Covers:
- resolve_version_tag: maps user-provided versions to the canonical
  origin/{major}.{minor} tag format used in the scans index.
- enhance_query: replaces the version in query text when a resolved_tag differs.
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)


def _load_agentic_search():
    """Import agentic_search with mocked aws_utils."""
    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)

    mock_aws_utils = MagicMock()
    mock_aws_utils.get_latest_scans_index.return_value = 'scans-000164'
    mock_aws_utils.opensearch_request.return_value = {'hits': {'hits': []}}

    with patch.dict('sys.modules', {'aws_utils': mock_aws_utils}):
        spec = importlib.util.spec_from_file_location(
            'sa_agentic_search_resolve', os.path.join(_LAMBDA_PATH, 'agentic_search.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


# ---------------------------------------------------------------------------
# resolve_version_tag — semver to origin/ mapping
# ---------------------------------------------------------------------------


class TestResolveVersionTagSemver:
    """Semver versions are mapped to origin/{major}.{minor}."""

    def test_three_part_version(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('3.7.0') == 'origin/3.7'

    def test_three_part_version_with_patch(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('2.19.6') == 'origin/2.19'

    def test_four_part_version(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('1.2.0.1') == 'origin/1.2'

    def test_two_part_version(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('3.7') == 'origin/3.7'

    def test_major_zero(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('0.9.0') == 'origin/0.9'


# ---------------------------------------------------------------------------
# resolve_version_tag — main/latest
# ---------------------------------------------------------------------------


class TestResolveVersionTagMainLatest:
    """'main' and 'latest' map to origin/main."""

    def test_main(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('main') == 'origin/main'

    def test_latest(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('latest') == 'origin/main'

    def test_main_case_insensitive(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('Main') == 'origin/main'

    def test_latest_case_insensitive(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('LATEST') == 'origin/main'


# ---------------------------------------------------------------------------
# resolve_version_tag — origin/ prefix passthrough
# ---------------------------------------------------------------------------


class TestResolveVersionTagOriginPassthrough:
    """Versions already prefixed with origin/ are returned as-is."""

    def test_origin_main(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('origin/main') == 'origin/main'

    def test_origin_branch(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('origin/3.7') == 'origin/3.7'

    def test_origin_with_suffix(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('origin/2.x') == 'origin/2.x'


# ---------------------------------------------------------------------------
# resolve_version_tag — non-parseable passthrough
# ---------------------------------------------------------------------------


class TestResolveVersionTagPassthrough:
    """Non-parseable strings are returned as-is for exact tag lookups."""

    def test_single_number(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('3') == '3'

    def test_branch_name(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('feature-branch') == 'feature-branch'

    def test_empty_string(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('') == ''

    def test_v_prefix(self):
        mod = _load_agentic_search()
        assert mod.resolve_version_tag('v2.19.6') == 'v2.19.6'


# ---------------------------------------------------------------------------
# enhance_query with resolved_tag
# ---------------------------------------------------------------------------


class TestEnhanceQueryWithResolvedTag:
    """Test that enhance_query replaces version with resolved_tag in query text."""

    def test_replaces_version_in_query_with_resolved_tag(self):
        mod = _load_agentic_search()
        result = mod.enhance_query(
            'Show me CVEs for 3.7.0 release components',
            version='3.7.0',
            resolved_tag='origin/3.7',
        )
        assert 'origin/3.7' in result
        assert '3.7.0' not in result

    def test_no_replacement_when_resolved_tag_same_as_version(self):
        mod = _load_agentic_search()
        result = mod.enhance_query(
            'Show me CVEs for origin/3.7',
            version='origin/3.7',
            resolved_tag='origin/3.7',
        )
        assert 'origin/3.7' in result
        assert result.count('origin/3.7') == 1

    def test_appends_resolved_tag_when_not_in_query(self):
        mod = _load_agentic_search()
        result = mod.enhance_query(
            'Show me critical CVEs',
            version='3.7.0',
            resolved_tag='origin/3.7',
        )
        assert 'origin/3.7' in result

    def test_falls_back_to_version_when_resolved_tag_none(self):
        mod = _load_agentic_search()
        result = mod.enhance_query(
            'Show me CVEs',
            version='2.19.6',
            resolved_tag=None,
        )
        assert '2.19.6' in result

    def test_project_name_still_appended(self):
        mod = _load_agentic_search()
        result = mod.enhance_query(
            'Show me CVEs for 3.7.0',
            version='3.7.0',
            resolved_tag='origin/3.7',
            project_name='OpenSearch',
        )
        assert 'origin/3.7' in result
        assert 'OpenSearch' in result
        assert '3.7.0' not in result

    def test_no_version_no_resolved_tag(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('Show me CVEs')
        assert result == 'Show me CVEs'
