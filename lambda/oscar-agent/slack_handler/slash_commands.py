#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Slash command handlers for Slack Handler.
"""

import json
import logging
import os
import time

import boto3
from config import config

logger = logging.getLogger(__name__)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "")


def _get_identity_table(workspace_id):
    """Get the identity DynamoDB table for a workspace."""
    if not ENVIRONMENT:
        return None
    table_name = f"oscar-identity-{workspace_id}-{ENVIRONMENT}"
    _dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    return _dynamodb.Table(table_name)


class SlashCommandHandlers:
    """Handles Slack slash commands."""

    def __init__(self, message_processor, storage) -> None:
        """Initialize with message processor and storage.

        Args:
            message_processor: MessageProcessor instance
            storage: Storage instance
        """
        self.message_processor = message_processor
        self.storage = storage

    def handle_announce_command(self, ack, command, say) -> None:
        """Handle /announce slash command."""
        self._handle_slash_command(ack, command, say, "announce")

    def handle_assign_owner_command(self, ack, command, say) -> None:
        """Handle /assign-owner slash command."""
        self._handle_slash_command(ack, command, say, "assign_owner")

    def handle_request_owner_command(self, ack, command, say) -> None:
        """Handle /request-owner slash command."""
        self._handle_slash_command(ack, command, say, "request_owner")

    def handle_rc_details_command(self, ack, command, say) -> None:
        """Handle /rc-details slash command."""
        self._handle_slash_command(ack, command, say, "rc_details")

    def handle_missing_notes_command(self, ack, command, say) -> None:
        """Handle /missing-notes slash command."""
        self._handle_slash_command(ack, command, say, "missing_notes")

    def handle_integration_test_command(self, ack, command, say) -> None:
        """Handle /integration-test slash command."""
        self._handle_slash_command(ack, command, say, "integration_test")

    def handle_broadcast_command(self, ack, command, say) -> None:
        """Handle /broadcast slash command."""
        self._handle_broadcast_command(ack, command, say)

    def _handle_slash_command(self, ack, command, say, slash_command_type: str) -> None:
        """Handle slash commands by delegating to message processor."""
        ack()

        user_id = command.get('user_id')
        params = command.get('text', '').strip().split()

        # Require channel and version, RC is optional
        if len(params) < 2 or len(params) > 3:
            say(text=f"❌ Usage: `/{slash_command_type.replace('_', '-')} <channel_id_or_name> <version> [rc_number]`", response_type="ephemeral")
            return

        channel_param = params[0]
        version_param = params[1]
        rc_param = f" and RC{params[2]}" if len(params) == 3 else ""

        # Create synthetic parameters
        channel_id = command.get('channel_id')
        thread_ts = str(int(time.time()))

        # Generate query with RC parameter
        query_template = config.agent_queries.get(slash_command_type)
        if not query_template:
            say(text="❌ Unknown slash command type", response_type="ephemeral")
            return

        query = query_template.format(channel=channel_param, version=version_param, rc_param=rc_param)

        # Create a wrapper for say that captures the response and stores context efficiently
        def say_with_context_storage(text, **kwargs):
            response = say(text=text, **kwargs)
            if response and 'ts' in response:
                actual_thread_ts = response['ts']
                original_query = f"/{slash_command_type.replace('_', '-')} {channel_param} {version_param} {params[2] if len(params) == 3 else ''}".strip()
                self.storage.store_bot_message_context(channel_id, actual_thread_ts, text, None, original_query)
            return response

        # Process directly with context storage skipped (handled by say_with_context_storage)
        self.message_processor.process_message(channel_id, thread_ts, user_id, query, say_with_context_storage, thread_ts, skip_context_storage=True)

    def _handle_broadcast_command(self, ack, command, say) -> None:
        """Handle broadcast slash command for general queries."""
        ack()

        user_id = command.get('user_id')
        text = command.get('text', '').strip()

        # Parse channel and query
        parts = text.split(' ', 1)
        if len(parts) < 2:
            say(text="❌ Usage: `/oscar-broadcast <channel_id_or_name> <your_query>`", response_type="ephemeral")
            return

        channel_param = parts[0]
        user_query = parts[1]

        # Create synthetic parameters
        channel_id = command.get('channel_id')
        thread_ts = str(int(time.time()))

        # Generate query for processing
        query_template = config.agent_queries.get("broadcast")
        query = query_template.format(channel=channel_param, user_query=user_query)

        # Create a wrapper for say that captures the response and stores context efficiently
        def say_with_context_storage(text, **kwargs):
            response = say(text=text, **kwargs)
            if response and 'ts' in response:
                actual_thread_ts = response['ts']
                original_query = f"/oscar-broadcast {channel_param} {user_query}"
                self.storage.store_bot_message_context(channel_id, actual_thread_ts, text, None, original_query)
            return response

        # Process directly with context storage skipped (handled by say_with_context_storage)
        self.message_processor.process_message(channel_id, thread_ts, user_id, query, say_with_context_storage, thread_ts, skip_context_storage=True)

    # ---- Identity linking commands ----

    def handle_link_github(self, ack, command, say) -> None:
        """Handle /oscar-link-github — initiate OAuth flow."""
        ack()

        workspace_id = command.get("team_id", "")
        table = _get_identity_table(workspace_id)
        if not table:
            say(text="❌ Identity linking is not configured for this workspace.", response_type="ephemeral")
            return

        user_id = command.get("user_id")

        # Check existing active mapping via GSI
        resp = table.query(
            IndexName="slack-user-index",
            KeyConditionExpression="slack_user_id = :uid",
            ExpressionAttributeValues={":uid": user_id},
        )
        items = resp.get("Items", [])
        active = next((i for i in items if i.get("status") == "active"), None)
        if active:
            handle = active.get("github_handle", "unknown")
            say(text=f"✅ Already linked to *@{handle}*. Use `/oscar-unlink-github` to unlink.", response_type="ephemeral")
            return

        # Build OAuth URL with HMAC-signed state
        from oauth_state import generate_state

        client_id = config.github_oauth_client_id
        callback_url = config.oauth_callback_url
        state = generate_state(user_id, workspace_id, config.oauth_state_secret)
        oauth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={client_id}"
            f"&redirect_uri={callback_url}"
            f"&state={state}"
            f"&scope=read:user"
        )

        say(text=f"<{oauth_url}|Click here to link your GitHub account>", response_type="ephemeral")

    def handle_unlink_github(self, ack, command, say) -> None:
        """Handle /oscar-unlink-github — revoke mapping."""
        ack()

        workspace_id = command.get("team_id", "")
        table = _get_identity_table(workspace_id)
        if not table:
            say(text="❌ Identity linking is not configured for this workspace.", response_type="ephemeral")
            return

        user_id = command.get("user_id")

        # Find active mapping via GSI
        resp = table.query(
            IndexName="slack-user-index",
            KeyConditionExpression="slack_user_id = :uid",
            ExpressionAttributeValues={":uid": user_id},
        )
        items = resp.get("Items", [])
        active = next((i for i in items if i.get("status") == "active"), None)
        if not active:
            say(text="No GitHub account linked.", response_type="ephemeral")
            return

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        handle = active.get("github_handle", "unknown")

        table.update_item(
            Key={"github_id": active["github_id"]},
            UpdateExpression="SET #s = :revoked, last_validated = :now",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":revoked": "revoked", ":now": now},
        )

        logger.info(f"IDENTITY_UNLINKED: slack_user={user_id} workspace={workspace_id} github={handle} github_id={active.get('github_id')}")
        say(text=f"✅ GitHub account *@{handle}* unlinked.", response_type="ephemeral")

    def handle_identity_status(self, ack, command, say) -> None:
        """Handle /oscar-identity-status — show current mapping."""
        ack()

        workspace_id = command.get("team_id", "")
        table = _get_identity_table(workspace_id)
        if not table:
            say(text="❌ Identity linking is not configured for this workspace.", response_type="ephemeral")
            return

        user_id = command.get("user_id")

        # Find mapping via GSI
        resp = table.query(
            IndexName="slack-user-index",
            KeyConditionExpression="slack_user_id = :uid",
            ExpressionAttributeValues={":uid": user_id},
        )
        items = resp.get("Items", [])
        if not items:
            say(text="No GitHub account linked. Run `/oscar-link-github` to connect.", response_type="ephemeral")
            return

        item = items[0]
        lines = [
            f"*GitHub:* @{item.get('github_handle', 'unknown')}",
            f"*GitHub ID:* {item.get('github_id', 'unknown')}",
            f"*Status:* {item.get('status', 'unknown')}",
            f"*Affiliation:* {item.get('affiliation', 'unknown')}",
            f"*Last validated:* {item.get('last_validated', 'unknown')}",
        ]
        say(text="\n".join(lines), response_type="ephemeral")
