# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for resolve_version_tag in dsl_query_builder.

Covers:
- resolve_version_tag: maps user-provided versions to the canonical
  origin/{major}.{minor} tag format used in the scans index.
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)


def _load_dsl_query_builder():
    """Import dsl_query_builder with mocked aws_utils."""
    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)

    mock_aws_utils = MagicMock()
    mock_aws_utils.get_latest_scans_index.return_value = 'scans-000164'
    mock_aws_utils.opensearch_request.return_value = {'hits': {'hits': []}}

    mock_config_module = MagicMock()
    mock_config_module.config.opensearch_query_size = 100

    with patch.dict('sys.modules', {
        'aws_utils': mock_aws_utils,
        'config': mock_config_module,
    }):
        spec = importlib.util.spec_from_file_location(
            'sa_dsl_query_builder_resolve', os.path.join(_LAMBDA_PATH, 'dsl_query_builder.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


# ---------------------------------------------------------------------------
# resolve_version_tag — numeric versions returned as-is
# ---------------------------------------------------------------------------


class TestResolveVersionTagSemver:
    """Numeric versions are returned as-is for exact release tag lookups."""

    def test_three_part_version(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('3.7.0') == '3.7.0'

    def test_three_part_version_with_patch(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('2.19.6') == '2.19.6'

    def test_four_part_version(self):
        """Four-part versions are not a valid user input — treated as non-parseable."""
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('1.2.0.1') == '1.2.0.1'

    def test_two_part_version(self):
        """Two-part versions map to origin/ branch since they don't exist as release tags."""
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('3.7') == 'origin/3.7'

    def test_major_zero(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('0.9.0') == '0.9.0'


# ---------------------------------------------------------------------------
# resolve_version_tag — main/latest
# ---------------------------------------------------------------------------


class TestResolveVersionTagMainLatest:
    """'main' and 'latest' map to origin/main."""

    def test_main(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('main') == 'origin/main'

    def test_latest(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('latest') == 'origin/main'

    def test_main_case_insensitive(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('Main') == 'origin/main'

    def test_latest_case_insensitive(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('LATEST') == 'origin/main'


# ---------------------------------------------------------------------------
# resolve_version_tag — origin/ prefix passthrough
# ---------------------------------------------------------------------------


class TestResolveVersionTagOriginPassthrough:
    """Versions already prefixed with origin/ are returned as-is."""

    def test_origin_main(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('origin/main') == 'origin/main'

    def test_origin_branch(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('origin/3.7') == 'origin/3.7'

    def test_origin_with_suffix(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('origin/2.x') == 'origin/2.x'


# ---------------------------------------------------------------------------
# resolve_version_tag — non-parseable passthrough
# ---------------------------------------------------------------------------


class TestResolveVersionTagPassthrough:
    """Non-parseable strings are returned as-is for exact tag lookups."""

    def test_single_number(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('3') == '3'

    def test_branch_name(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('feature-branch') == 'feature-branch'

    def test_empty_string(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('') == ''

    def test_v_prefix(self):
        mod = _load_dsl_query_builder()
        assert mod.resolve_version_tag('v2.19.6') == 'v2.19.6'
