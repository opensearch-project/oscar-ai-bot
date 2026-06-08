# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for QueryProcessor context sanitization and limited-tier override.

Covers:
- _sanitize_context_for_limited_user: redacts security advisory content from
  conversation history for non-privileged users.
- _apply_limited_tier_override: replaces LLM responses containing advisory
  data with the canonical limited-access message for non-privileged users.
"""

from unittest.mock import MagicMock

import pytest
from bedrock.query_processor import QueryProcessor
from constants import LIMITED_ACCESS_MESSAGE


@pytest.fixture
def processor():
    """Create a QueryProcessor with mocked dependencies."""
    mock_agent = MagicMock()
    mock_error_handler = MagicMock()
    return QueryProcessor(bedrock_agent=mock_agent, error_handler=mock_error_handler)


# ---------------------------------------------------------------------------
# _sanitize_context_for_limited_user
# ---------------------------------------------------------------------------


class TestSanitizeContextForLimitedUser:
    """Tests for context sanitization of security advisory data."""

    def test_empty_context_returns_unchanged(self, processor):
        """Empty string context is returned as-is."""
        assert processor._sanitize_context_for_limited_user('') == ''

    def test_none_context_returns_none(self, processor):
        """None context is returned as-is."""
        assert processor._sanitize_context_for_limited_user(None) is None

    def test_context_without_advisory_content_unchanged(self, processor):
        """Context with no security advisory content passes through unmodified."""
        context = (
            "User: What is OpenSearch?\n"
            "Assistant: OpenSearch is a search and analytics suite.\n"
            "User: How do I install it?"
        )
        result = processor._sanitize_context_for_limited_user(context)
        assert result == context

    def test_context_with_cve_id_is_redacted(self, processor):
        """Assistant turns containing CVE identifiers are sanitized."""
        context = (
            "User: Show me vulnerabilities\n"
            "Assistant: Found CVE-2024-12345 in lodash with CRITICAL severity.\n"
            "User: Tell me more"
        )
        result = processor._sanitize_context_for_limited_user(context)
        assert 'CVE-2024-12345' not in result
        assert LIMITED_ACCESS_MESSAGE in result
        # User turns remain intact
        assert 'User: Show me vulnerabilities' in result
        assert 'User: Tell me more' in result

    def test_context_with_ghsa_id_is_redacted(self, processor):
        """Assistant turns containing GHSA identifiers are sanitized."""
        context = (
            "User: Any advisories?\n"
            "Assistant: GHSA-abcd-efgh-ijkl affects version 2.19.6.\n"
            "User: Thanks"
        )
        result = processor._sanitize_context_for_limited_user(context)
        assert 'GHSA-abcd-efgh-ijkl' not in result
        assert LIMITED_ACCESS_MESSAGE in result

    def test_context_with_multiple_security_keywords_is_redacted(self, processor):
        """Assistant turns with >= 2 advisory indicators are sanitized."""
        context = (
            "User: Check vulnerabilities\n"
            "Assistant: Found 3 vulnerabilities with CRITICAL severity "
            "on advisories.opensearch.org.\n"
            "User: Next"
        )
        result = processor._sanitize_context_for_limited_user(context)
        assert 'Found 3 vulnerabilities' not in result
        assert LIMITED_ACCESS_MESSAGE in result

    def test_single_security_keyword_not_redacted(self, processor):
        """A single advisory keyword (below threshold) is not redacted."""
        context = (
            "User: What is a vulnerability?\n"
            "Assistant: A vulnerability is a weakness in software that can be exploited.\n"
            "User: Ok"
        )
        result = processor._sanitize_context_for_limited_user(context)
        # Only one indicator ('vulnerability') — should NOT trigger redaction
        assert 'A vulnerability is a weakness' in result

    def test_multiline_assistant_turn_redacted_fully(self, processor):
        """Multi-line assistant responses with advisory data are fully replaced."""
        context = (
            "User: Show CVEs\n"
            "Assistant: Here are the results:\n"
            "- CVE-2024-001 CRITICAL lodash\n"
            "- CVE-2024-002 HIGH express\n"
            "User: Filter by high"
        )
        result = processor._sanitize_context_for_limited_user(context)
        assert 'CVE-2024-001' not in result
        assert 'CVE-2024-002' not in result
        assert 'lodash' not in result
        assert LIMITED_ACCESS_MESSAGE in result
        assert 'User: Filter by high' in result

    def test_mixed_turns_only_advisory_turn_redacted(self, processor):
        """Only assistant turns with advisory content are redacted; others kept."""
        context = (
            "User: Hello\n"
            "Assistant: Hi! How can I help?\n"
            "User: Show me CVEs\n"
            "Assistant: Found CVE-2024-999 in package foo.\n"
            "User: What else can you do?\n"
            "Assistant: I can help with many things!"
        )
        result = processor._sanitize_context_for_limited_user(context)
        # First assistant turn — safe
        assert 'Hi! How can I help?' in result
        # Second assistant turn — contains CVE, should be redacted
        assert 'CVE-2024-999' not in result
        # Third assistant turn — safe
        assert 'I can help with many things!' in result


# ---------------------------------------------------------------------------
# _apply_limited_tier_override
# ---------------------------------------------------------------------------


class TestApplyLimitedTierOverride:
    """Tests for the limited-tier response override."""

    def test_privileged_user_response_unchanged(self, processor):
        """Privileged users always receive the original response."""
        response = "Found CVE-2024-001 in lodash with CRITICAL severity."
        result = processor._apply_limited_tier_override(response, privilege=True)
        assert result == response

    def test_limited_user_response_with_cve_replaced(self, processor):
        """Limited user response containing CVE IDs is replaced."""
        response = "Here are the results: CVE-2024-12345 is critical."
        result = processor._apply_limited_tier_override(response, privilege=False)
        assert result == LIMITED_ACCESS_MESSAGE

    def test_limited_user_response_with_dashboard_url_replaced(self, processor):
        """Limited user response containing advisory dashboard link is replaced."""
        response = "Visit advisories.opensearch.org for details on this issue."
        result = processor._apply_limited_tier_override(response, privilege=False)
        assert result == LIMITED_ACCESS_MESSAGE

    def test_limited_user_response_with_ghsa_replaced(self, processor):
        """Limited user response containing GHSA IDs is replaced."""
        response = "Advisory GHSA-wxyz-abcd-efgh affects your version."
        result = processor._apply_limited_tier_override(response, privilege=False)
        assert result == LIMITED_ACCESS_MESSAGE

    def test_limited_user_safe_response_unchanged(self, processor):
        """Limited user responses without advisory content pass through."""
        response = "OpenSearch is a search and analytics suite."
        result = processor._apply_limited_tier_override(response, privilege=False)
        assert result == response

    def test_limited_user_empty_response_unchanged(self, processor):
        """Empty responses are not replaced."""
        result = processor._apply_limited_tier_override('', privilege=False)
        assert result == ''

    def test_limited_user_none_response_unchanged(self, processor):
        """None responses are not replaced (returns None)."""
        result = processor._apply_limited_tier_override(None, privilege=False)
        assert result is None


# ---------------------------------------------------------------------------
# _contains_security_advisory_content
# ---------------------------------------------------------------------------


class TestContainsSecurityAdvisoryContent:
    """Tests for the advisory content detection helper."""

    def test_cve_id_detected(self, processor):
        """CVE identifiers are detected."""
        assert processor._contains_security_advisory_content("Found CVE-2024-12345") is True

    def test_ghsa_id_detected(self, processor):
        """GHSA identifiers are detected."""
        assert processor._contains_security_advisory_content("GHSA-abcd-efgh-ijkl found") is True

    def test_multiple_keywords_detected(self, processor):
        """Two or more advisory keywords trigger detection."""
        text = "CRITICAL vulnerabilities found on advisories.opensearch.org"
        assert processor._contains_security_advisory_content(text) is True

    def test_single_keyword_not_detected(self, processor):
        """A single advisory keyword does not trigger detection."""
        assert processor._contains_security_advisory_content("severity is low") is False

    def test_plain_text_not_detected(self, processor):
        """Plain non-advisory text is not flagged."""
        assert processor._contains_security_advisory_content("Hello world") is False
