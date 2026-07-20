# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Property-based tests for dsl_query_builder.py using Hypothesis.

These tests verify universal correctness properties of the DSL query builder
module across many randomly generated inputs.
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import semver
from hypothesis import given, settings
from hypothesis import strategies as st

# Path to the real lambda module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'agents', 'security-advisories', 'lambda',
)


def _load_dsl_query_builder():
    """Import dsl_query_builder with mocked aws_utils and config."""
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
            'sa_dsl_query_builder', os.path.join(_LAMBDA_PATH, 'dsl_query_builder.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


# Load the module once for all tests
_mod = _load_dsl_query_builder()
resolve_version_tag = _mod.resolve_version_tag


# ---------------------------------------------------------------------------
# Hypothesis Strategies for version string categories
# ---------------------------------------------------------------------------

# Two-part numeric versions (e.g., "3.7", "0.1", "123.456")
two_part_versions = st.from_regex(r'[0-9]{1,3}\.[0-9]{1,3}', fullmatch=True)

# Three-part semver versions (e.g., "3.7.0", "2.19.6")
three_part_versions = st.from_regex(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', fullmatch=True)

# main/latest variants (case-insensitive)
main_latest_variants = st.sampled_from([
    'main', 'latest', 'MAIN', 'LATEST', 'Main', 'Latest', 'mAiN', 'lAtEsT',
])

# origin/-prefixed strings
origin_prefixed = st.text(min_size=1, max_size=50).map(lambda s: f'origin/{s}')

# Arbitrary non-empty text strings (for non-parseable passthrough)
arbitrary_text = st.text(min_size=1, max_size=50)


# ---------------------------------------------------------------------------
# Feature: dsl-query-replacement, Property 1: Version tag resolution correctness
# ---------------------------------------------------------------------------


class TestVersionTagResolutionCorrectness:
    """Property 1: Version tag resolution correctness.

    For any version string, resolve_version_tag SHALL produce the correct
    canonical output based on the input's classification.

    **Validates: Requirements 5.2, 5.3, 5.4, 5.5, 5.6**
    """

    @given(version=two_part_versions)
    @settings(max_examples=100)
    def test_two_part_versions_map_to_origin_prefix(self, version):
        """Two-part numeric versions map to origin/{version}.

        A two-part version is defined as a string that forms valid semver
        when ".0" is appended.

        **Validates: Requirements 5.2**
        """
        # Verify it is actually a valid two-part version (appending .0 gives valid semver)
        try:
            semver.Version.parse(f'{version}.0')
        except ValueError:
            # If appending .0 doesn't produce valid semver, it's not a true two-part version
            return

        # Also verify it's NOT already valid three-part semver
        try:
            semver.Version.parse(version)
            # If it IS valid three-part semver, it should pass through unchanged
            return
        except ValueError:
            pass

        result = resolve_version_tag(version)
        assert result == f'origin/{version}', (
            f'Two-part version "{version}" should map to "origin/{version}", got "{result}"'
        )

    @given(version=three_part_versions)
    @settings(max_examples=100)
    def test_three_part_semver_maps_to_origin_major_minor(self, version):
        """Three-part valid semver versions map to origin/{major}.{minor}.

        **Validates: Requirements 5.3**
        """
        # Only test versions that are actually valid semver
        try:
            parsed = semver.Version.parse(version)
        except ValueError:
            return

        result = resolve_version_tag(version)
        expected = f'origin/{parsed.major}.{parsed.minor}'
        assert result == expected, (
            f'Three-part semver "{version}" should map to "{expected}", got "{result}"'
        )

    @given(version=main_latest_variants)
    @settings(max_examples=100)
    def test_main_latest_maps_to_origin_main(self, version):
        """Case-insensitive "main" or "latest" maps to "origin/main".

        **Validates: Requirements 5.4**
        """
        result = resolve_version_tag(version)
        assert result == 'origin/main', (
            f'"{version}" should map to "origin/main", got "{result}"'
        )

    @given(version=origin_prefixed)
    @settings(max_examples=100)
    def test_origin_prefixed_passes_through_unchanged(self, version):
        """Strings already prefixed with origin/ pass through unchanged.

        **Validates: Requirements 5.5**
        """
        result = resolve_version_tag(version)
        assert result == version, (
            f'origin/-prefixed "{version}" should pass through unchanged, got "{result}"'
        )

    @given(version=arbitrary_text)
    @settings(max_examples=100)
    def test_non_parseable_passes_through_unchanged(self, version):
        """Non-parseable strings pass through unchanged.

        A string is non-parseable if it is NOT:
        - A two-part numeric version (appending .0 gives valid semver)
        - A three-part valid semver
        - "main" or "latest" (case-insensitive)
        - Already prefixed with "origin/"

        **Validates: Requirements 5.6**
        """
        # Skip strings that fall into other categories
        if version.startswith('origin/'):
            return
        if version.lower() in ('main', 'latest'):
            return

        # Skip if it's valid three-part semver
        try:
            semver.Version.parse(version)
            return
        except ValueError:
            pass

        # Skip if it's a valid two-part version
        try:
            semver.Version.parse(f'{version}.0')
            return
        except ValueError:
            pass

        result = resolve_version_tag(version)
        assert result == version, (
            f'Non-parseable "{version}" should pass through unchanged, got "{result}"'
        )

    @settings(max_examples=100)
    @given(version=st.just(''))
    def test_empty_string_returns_as_is(self, version):
        """Empty string returns as-is (falsy check at start of function).

        **Validates: Requirements 5.6**
        """
        result = resolve_version_tag(version)
        assert result == '', (
            f'Empty string should return as-is, got "{result}"'
        )
