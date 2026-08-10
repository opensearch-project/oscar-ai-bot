# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests verifying CVE IDs become clickable links in Slack responses.

The approach: bare CVE/GHSA identifiers in the Bedrock agent's plain-text
response are converted to Markdown links by linkify_cve_ids(), then the
existing Slack mrkdwn formatter converts [text](url) → <url|text>.

Validates:
1. linkify_cve_ids converts bare CVE/GHSA IDs to Markdown links
2. Already-linked IDs are not double-wrapped
3. The full format_markdown_to_slack_mrkdwn pipeline produces Slack links
4. Both formatters (oscar-agent and communication-handler) work correctly
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Paths to the formatter modules
# ---------------------------------------------------------------------------

_OSCAR_AGENT_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'lambda', 'oscar-agent', 'slack_handler',
)

_COMM_HANDLER_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'lambda', 'oscar-communication-handler',
)


def _load_slack_message_formatter(source_path):
    """Load a MessageFormatter from the given lambda directory."""
    if source_path not in sys.path:
        sys.path.insert(0, source_path)

    mock_config = MagicMock()
    mock_config.config = MagicMock()
    mock_config.config.patterns = {'at_symbol': r'@(\w+)'}

    with patch.dict('sys.modules', {
        'config': mock_config,
    }):
        spec = importlib.util.spec_from_file_location(
            f'msg_formatter_{os.path.basename(source_path)}',
            os.path.join(source_path, 'message_formatter.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.MessageFormatter()


# ---------------------------------------------------------------------------
# 1. linkify_cve_ids — unit tests
# ---------------------------------------------------------------------------


class TestLinkifyCveIds:
    """Test the linkify_cve_ids static method."""

    @pytest.fixture
    def formatter(self):
        return _load_slack_message_formatter(_OSCAR_AGENT_PATH)

    def test_bare_cve_id_is_linked(self, formatter):
        text = "Found CVE-2024-12345 in lodash"
        result = formatter.linkify_cve_ids(text)

        assert result == "Found [CVE-2024-12345](https://advisories.opensearch.org/advisory/CVE-2024-12345) in lodash"

    def test_bare_ghsa_id_is_linked(self, formatter):
        text = "Found GHSA-abcd-1234-efgh in express"
        result = formatter.linkify_cve_ids(text)

        assert result == "Found [GHSA-abcd-1234-efgh](https://advisories.opensearch.org/advisory/GHSA-abcd-1234-efgh) in express"

    def test_multiple_cve_ids_are_linked(self, formatter):
        text = "CVE-2024-001 and CVE-2024-002 are critical"
        result = formatter.linkify_cve_ids(text)

        assert "[CVE-2024-001](https://advisories.opensearch.org/advisory/CVE-2024-001)" in result
        assert "[CVE-2024-002](https://advisories.opensearch.org/advisory/CVE-2024-002)" in result

    def test_already_linked_cve_is_not_double_wrapped(self, formatter):
        text = "[CVE-2024-12345](https://advisories.opensearch.org/advisory/CVE-2024-12345)"
        result = formatter.linkify_cve_ids(text)

        # Should not produce [[CVE-...]]
        assert "[[" not in result
        assert result == text

    def test_mixed_bare_and_linked_cves(self, formatter):
        text = (
            "[CVE-2024-001](https://advisories.opensearch.org/advisory/CVE-2024-001) "
            "and CVE-2024-002 are found"
        )
        result = formatter.linkify_cve_ids(text)

        # First one should stay as-is, second should be linked
        assert "[CVE-2024-001](https://advisories.opensearch.org/advisory/CVE-2024-001)" in result
        assert "[CVE-2024-002](https://advisories.opensearch.org/advisory/CVE-2024-002)" in result
        assert "[[" not in result

    def test_no_cve_ids_unchanged(self, formatter):
        text = "No vulnerabilities found for this version."
        result = formatter.linkify_cve_ids(text)

        assert result == text

    def test_cve_with_long_number(self, formatter):
        text = "CVE-2024-1234567 is severe"
        result = formatter.linkify_cve_ids(text)

        assert "[CVE-2024-1234567]" in result

    def test_cve_at_start_of_line(self, formatter):
        text = "CVE-2024-50379 — tomcat-embed-core 10.1.33"
        result = formatter.linkify_cve_ids(text)

        assert result.startswith("[CVE-2024-50379](")

    def test_cve_at_end_of_line(self, formatter):
        text = "Critical vulnerability: CVE-2024-50379"
        result = formatter.linkify_cve_ids(text)

        assert result.endswith("[CVE-2024-50379](https://advisories.opensearch.org/advisory/CVE-2024-50379)")

    def test_cve_in_bullet_list(self, formatter):
        text = (
            "- CRITICAL — CVE-2024-50379 — tomcat 10.1.33\n"
            "- HIGH — CVE-2024-47535 — netty 4.1.114\n"
        )
        result = formatter.linkify_cve_ids(text)

        assert "[CVE-2024-50379](" in result
        assert "[CVE-2024-47535](" in result


# ---------------------------------------------------------------------------
# 2. End-to-end: format_markdown_to_slack_mrkdwn produces Slack links
# ---------------------------------------------------------------------------


class TestEndToEndSlackLinkFormatting:
    """Test that bare CVE IDs in agent output become clickable Slack links."""

    def test_oscar_agent_formatter_produces_slack_links(self):
        formatter = _load_slack_message_formatter(_OSCAR_AGENT_PATH)
        agent_response = "Found CVE-2024-12345 (CRITICAL) in lodash 4.17.20"
        result = formatter.format_markdown_to_slack_mrkdwn(agent_response)

        assert '<https://advisories.opensearch.org/advisory/CVE-2024-12345|CVE-2024-12345>' in result

    def test_communication_handler_formatter_converts_existing_markdown_links(self):
        """The communication handler should still convert pre-existing Markdown links."""
        formatter = _load_slack_message_formatter(_COMM_HANDLER_PATH)
        # If a message already has Markdown links (e.g. from a different source), they should convert
        agent_response = "[CVE-2024-12345](https://advisories.opensearch.org/advisory/CVE-2024-12345) is critical"
        result = formatter.format_markdown_to_slack_mrkdwn(agent_response)

        assert '<https://advisories.opensearch.org/advisory/CVE-2024-12345|CVE-2024-12345>' in result

    def test_typical_cve_list_response(self):
        """Simulate a typical agent response listing CVEs."""
        formatter = _load_slack_message_formatter(_OSCAR_AGENT_PATH)
        agent_response = (
            "**OpenSearch 2.19.6** — 3 vulnerabilities found:\n\n"
            "- **CRITICAL** — CVE-2024-50379 — tomcat-embed-core 10.1.33\n"
            "- **HIGH** — CVE-2024-47535 — netty-common 4.1.114.Final\n"
            "- **MEDIUM** — GHSA-abcd-1234-efgh — json-path 2.9.0\n"
        )
        result = formatter.format_markdown_to_slack_mrkdwn(agent_response)

        assert '<https://advisories.opensearch.org/advisory/CVE-2024-50379|CVE-2024-50379>' in result
        assert '<https://advisories.opensearch.org/advisory/CVE-2024-47535|CVE-2024-47535>' in result
        assert '<https://advisories.opensearch.org/advisory/GHSA-abcd-1234-efgh|GHSA-abcd-1234-efgh>' in result

    def test_response_without_cves_has_no_links(self):
        formatter = _load_slack_message_formatter(_OSCAR_AGENT_PATH)
        agent_response = "No vulnerabilities found for OpenSearch 2.19.6."
        result = formatter.format_markdown_to_slack_mrkdwn(agent_response)

        assert '<https://' not in result

    def test_already_linked_cves_not_broken(self):
        """If the agent somehow includes Markdown links, they should still work."""
        formatter = _load_slack_message_formatter(_OSCAR_AGENT_PATH)
        agent_response = "[CVE-2024-12345](https://advisories.opensearch.org/advisory/CVE-2024-12345) is critical"
        result = formatter.format_markdown_to_slack_mrkdwn(agent_response)

        assert '<https://advisories.opensearch.org/advisory/CVE-2024-12345|CVE-2024-12345>' in result
        # Should not have double-nested links
        assert '<<' not in result
