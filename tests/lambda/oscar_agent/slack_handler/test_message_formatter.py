# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for MessageFormatter."""

from slack_handler.message_formatter import MessageFormatter


class TestFormatMarkdownToSlackMrkdwn:
    """Tests for format_markdown_to_slack_mrkdwn."""

    def test_bold_conversion(self):
        assert "*bold*" in MessageFormatter.format_markdown_to_slack_mrkdwn("**bold**")

    def test_double_underscore_bold(self):
        assert "*bold*" in MessageFormatter.format_markdown_to_slack_mrkdwn("__bold__")

    def test_heading_h1(self):
        result = MessageFormatter.format_markdown_to_slack_mrkdwn("# Heading")
        assert "*Heading*" in result

    def test_heading_h3(self):
        result = MessageFormatter.format_markdown_to_slack_mrkdwn("### Sub Heading")
        assert "*Sub Heading*" in result

    def test_link_conversion(self):
        result = MessageFormatter.format_markdown_to_slack_mrkdwn("[click here](https://example.com)")
        assert "<https://example.com|click here>" in result

    def test_bullet_asterisk(self):
        result = MessageFormatter.format_markdown_to_slack_mrkdwn("* item one")
        assert result.startswith("•")

    def test_bullet_dash(self):
        result = MessageFormatter.format_markdown_to_slack_mrkdwn("- item one")
        assert result.startswith("•")

    def test_channel_mention(self):
        result = MessageFormatter.format_markdown_to_slack_mrkdwn("see #general for details")
        assert "<#general>" in result

    def test_preserves_already_formatted_channel(self):
        result = MessageFormatter.format_markdown_to_slack_mrkdwn("see <#C123|general> for details")
        assert "<#C123|general>" in result
        assert "<<#" not in result

    def test_xml_tag_stripping_answer(self):
        result = MessageFormatter.format_markdown_to_slack_mrkdwn("<answer>hello world</answer>")
        assert "hello world" in result
        assert "<answer>" not in result

    def test_xml_tag_stripping_sources(self):
        result = MessageFormatter.format_markdown_to_slack_mrkdwn(
            "response text<sources>source1\nsource2</sources>"
        )
        assert "response text" in result
        assert "<sources>" not in result
        assert "source1" not in result

    def test_empty_string(self):
        assert MessageFormatter.format_markdown_to_slack_mrkdwn("") == ""

    def test_plain_text_passthrough(self):
        text = "Just plain text with no formatting"
        assert MessageFormatter.format_markdown_to_slack_mrkdwn(text) == text

    def test_complex_mixed_message(self):
        msg = "# Release Notes\n**Version 2.12.0** is ready.\n- Fix [bug](https://gh.com/1)\n- Update #release-channel"
        result = MessageFormatter.format_markdown_to_slack_mrkdwn(msg)
        assert "*Release Notes*" in result
        assert "*Version 2.12.0*" in result
        assert "<https://gh.com/1|bug>" in result
        assert "<#release-channel>" in result
        assert "•" in result


class TestConvertAtSymbolsToSlackPings:
    """Tests for convert_at_symbols_to_slack_pings."""

    def test_single_mention(self):
        result = MessageFormatter.convert_at_symbols_to_slack_pings("hello @username")
        assert "<@username>" in result

    def test_multiple_mentions(self):
        result = MessageFormatter.convert_at_symbols_to_slack_pings("@alice and @bob")
        assert "<@alice>" in result
        assert "<@bob>" in result

    def test_no_mentions(self):
        text = "no mentions here"
        assert MessageFormatter.convert_at_symbols_to_slack_pings(text) == text
