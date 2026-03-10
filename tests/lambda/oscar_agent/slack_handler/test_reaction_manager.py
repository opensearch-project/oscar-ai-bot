# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for ReactionManager."""

from unittest.mock import Mock

from slack_handler.reaction_manager import ReactionManager
from slack_sdk.errors import SlackApiError


def _make_slack_error(message):
    """Create a SlackApiError with the given message."""
    return SlackApiError(message=message, response=Mock(data={"error": message}))


class TestReactionManager:

    def test_add_reaction_calls_api(self):
        client = Mock()
        rm = ReactionManager(client)
        rm.manage_reactions("C123", "ts123", add_reaction="thumbsup")
        client.reactions_add.assert_called_once_with(
            channel="C123", timestamp="ts123", name="thumbsup",
        )

    def test_remove_single_reaction(self):
        client = Mock()
        rm = ReactionManager(client)
        rm.manage_reactions("C123", "ts123", remove_reaction="thinking_face")
        client.reactions_remove.assert_called_once_with(
            channel="C123", timestamp="ts123", name="thinking_face",
        )

    def test_remove_list_of_reactions(self):
        client = Mock()
        rm = ReactionManager(client)
        rm.manage_reactions("C123", "ts123", remove_reaction=["thinking_face", "hourglass"])
        assert client.reactions_remove.call_count == 2

    def test_remove_then_add_order(self):
        """Removal should happen before addition."""
        call_order = []
        client = Mock()
        client.reactions_remove.side_effect = lambda **_: call_order.append("remove")
        client.reactions_add.side_effect = lambda **_: call_order.append("add")

        rm = ReactionManager(client)
        rm.manage_reactions("C123", "ts123", add_reaction="check", remove_reaction="thinking")
        assert call_order == ["remove", "add"]

    def test_already_reacted_suppressed(self):
        client = Mock()
        client.reactions_add.side_effect = _make_slack_error("already_reacted")
        rm = ReactionManager(client)
        # Should not raise
        rm.manage_reactions("C123", "ts123", add_reaction="thumbsup")

    def test_no_reaction_suppressed(self):
        client = Mock()
        client.reactions_remove.side_effect = _make_slack_error("no_reaction")
        rm = ReactionManager(client)
        # Should not raise
        rm.manage_reactions("C123", "ts123", remove_reaction="thinking")

    def test_none_params_no_calls(self):
        client = Mock()
        rm = ReactionManager(client)
        rm.manage_reactions("C123", "ts123")
        client.reactions_add.assert_not_called()
        client.reactions_remove.assert_not_called()
