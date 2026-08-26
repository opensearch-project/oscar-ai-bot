# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""OAuth callback Lambda for Slack-GitHub identity linking."""

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import boto3
import requests
from oscar_shared.oauth_state import verify_state

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
secrets_client = boto3.client("secretsmanager")

_oauth_creds = None

IDENTITY_TABLE_NAME = os.environ.get("IDENTITY_TABLE_NAME", "")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "")
CENTRAL_SECRET_NAME = os.environ.get("CENTRAL_SECRET_NAME", "")

if not ENVIRONMENT:
    raise ValueError("ENVIRONMENT environment variable is required")
if not CENTRAL_SECRET_NAME:
    raise ValueError("CENTRAL_SECRET_NAME environment variable is required")


@dataclass
class IdentityRecord:
    github_id: int
    github_handle: str
    slack_user_id: str
    status: str
    affiliation: str
    last_validated: str

    def to_dynamo_item(self) -> dict:
        return {
            "github_id": self.github_id,
            "github_handle": self.github_handle,
            "slack_user_id": self.slack_user_id,
            "status": self.status,
            "affiliation": self.affiliation,
            "last_validated": self.last_validated,
        }


def _get_oauth_creds():
    global _oauth_creds
    if _oauth_creds is None:
        raw = secrets_client.get_secret_value(SecretId=CENTRAL_SECRET_NAME)
        _oauth_creds = json.loads(raw["SecretString"])
    return _oauth_creds


def _get_table() -> Optional[object]:
    if not IDENTITY_TABLE_NAME:
        return None
    return dynamodb.Table(IDENTITY_TABLE_NAME)


def lambda_handler(event, context):
    # Route: EventBridge scheduled event → run validation
    if event.get("source") == "aws.events":
        return _handle_validation()

    # Route: API Gateway OAuth callback
    params = event.get("queryStringParameters") or {}
    # code: the temporary OAuth authorization code returned by GitHub after user consent
    code = params.get("code")
    # state: HMAC-signed, base64url-encoded token containing slack_user_id, workspace_id, and timestamp
    state = params.get("state")

    if not code or not state:
        return _html(400, "Missing code or state parameter.")

    creds = _get_oauth_creds()
    try:
        slack_user_id, workspace_id = verify_state(state, creds["OAUTH_STATE_SECRET"])
    except ValueError as e:
        logger.warning(f"IDENTITY_STATE_INVALID: reason={e}")
        return _html(400, "Invalid or expired link. Please run /oscar-link-github again.")

    table = _get_table()
    if not table:
        return _html(400, "Identity table not configured.")

    try:
        token_resp = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": creds["GITHUB_OAUTH_CLIENT_ID"],
                "client_secret": creds["GITHUB_OAUTH_CLIENT_SECRET"],
                "code": code,
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
    except requests.RequestException as e:
        logger.warning(f"IDENTITY_AUTH_FAILED: slack_user={slack_user_id} workspace={workspace_id} reason=token_exchange_error error={e}")
        return _html(400, "GitHub authorization failed. Run /oscar-link-github again.")

    if not access_token:
        logger.warning(f"IDENTITY_AUTH_FAILED: slack_user={slack_user_id} workspace={workspace_id} reason=token_exchange_failed")
        return _html(400, "GitHub authorization failed. Run /oscar-link-github again.")

    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}

    try:
        user_resp = requests.get("https://api.github.com/user", headers=headers, timeout=10)
        user_resp.raise_for_status()
        user = user_resp.json()
    except requests.RequestException as e:
        logger.warning(f"IDENTITY_AUTH_FAILED: slack_user={slack_user_id} workspace={workspace_id} reason=user_fetch_error error={e}")
        return _html(400, "Could not retrieve GitHub profile. Please try again.")

    github_handle = user.get("login")
    github_id = user.get("id")

    if not github_handle or not github_id:
        return _html(400, "Could not retrieve GitHub profile.")

    affiliation = user.get("company") or ""

    existing = table.get_item(Key={"github_id": github_id}).get("Item")
    if existing and existing.get("slack_user_id") != slack_user_id and existing.get("status") == "active":
        logger.warning(f"IDENTITY_DUPLICATE_REJECTED: slack_user={slack_user_id} workspace={workspace_id} github={github_handle} github_id={github_id} existing_slack_user={existing['slack_user_id']}")
        return _html(409, "This GitHub account is already linked to another Slack user.")

    now = datetime.now(timezone.utc).isoformat()
    record = IdentityRecord(
        github_id=github_id,
        github_handle=github_handle,
        slack_user_id=slack_user_id,
        status="active",
        affiliation=affiliation,
        last_validated=now,
    )
    table.put_item(Item=record.to_dynamo_item())
    logger.info(f"IDENTITY_LINKED: slack_user={slack_user_id} workspace={workspace_id} github={github_handle} github_id={github_id} affiliation={affiliation}")

    return _html(200, "Successfully linked your GitHub account.")


class ChannelMembersFetchError(Exception):
    """Raised when a channel's membership cannot be fully and reliably fetched.

    Signals that validation must abort rather than risk expiring users based on
    an empty or partial member list.
    """


def _get_channel_members(bot_token: str, channel_id: str) -> set:
    """Fetch all members of a channel using cursor-based pagination.

    Raises ChannelMembersFetchError if the full membership cannot be retrieved
    (Slack API error, rate limit exhausted, or transport failure). Callers must
    treat a raised error as "unknown membership" and NOT expire any users.
    """
    members = set()
    cursor = None
    max_rate_limit_retries = 5
    while True:
        params = {"channel": channel_id, "limit": 1000}
        if cursor:
            params["cursor"] = cursor

        retries = 0
        while True:
            try:
                resp = requests.get(
                    "https://slack.com/api/conversations.members",
                    headers={"Authorization": f"Bearer {bot_token}"},
                    params=params,
                    timeout=10,
                )
            except requests.RequestException as e:
                raise ChannelMembersFetchError(f"transport error for {channel_id}: {e}") from e

            # Slack signals rate limiting with HTTP 429 and a Retry-After header.
            if resp.status_code == 429:
                if retries >= max_rate_limit_retries:
                    raise ChannelMembersFetchError(f"rate limited for {channel_id}: retries exhausted")
                retry_after = int(resp.headers.get("Retry-After", "1"))
                logger.warning(f"conversations.members rate limited for {channel_id}, retrying in {retry_after}s")
                time.sleep(retry_after)
                retries += 1
                continue
            break

        try:
            data = resp.json()
        except ValueError as e:
            raise ChannelMembersFetchError(f"non-JSON response for {channel_id}: {e}") from e

        if not data.get("ok"):
            # Any application-level error (ratelimited, invalid_auth, channel_not_found,
            # not_in_channel, ...) means we cannot trust the membership. Abort, do not expire.
            raise ChannelMembersFetchError(f"conversations.members failed for {channel_id}: {data.get('error')}")

        members.update(data.get("members", []))
        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return members


def _handle_validation():
    """Weekly validation: expire mappings for users no longer in monitored channels."""
    creds = _get_oauth_creds()
    bot_token = creds.get("SLACK_BOT_TOKEN", "")
    channel_ids = [c.strip() for c in creds.get("CHANNEL_ALLOW_LIST", "").split(",") if c.strip()]

    if not bot_token:
        logger.error("SLACK_BOT_TOKEN not found in central secret")
        return {"expired": 0, "error": "missing bot token"}

    if not channel_ids:
        logger.error("CHANNEL_ALLOW_LIST not found in central secret")
        return {"expired": 0, "error": "no channels configured"}

    table = _get_table()
    if not table:
        logger.error("IDENTITY_TABLE_NAME not configured")
        return {"expired": 0, "error": "no identity table"}

    # Step 1: Fetch active mappings first — skip Slack API if nothing to validate
    active = []
    scan_kwargs = {
        "FilterExpression": "#s = :active",
        "ExpressionAttributeNames": {"#s": "status"},
        "ExpressionAttributeValues": {":active": "active"},
        "ProjectionExpression": "github_id, slack_user_id",
    }
    while True:
        response = table.scan(**scan_kwargs)
        active.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    logger.info(f"Active mappings: {len(active)}")

    # Step 2: Fetch channel members.
    # If ANY channel fails to fetch fully, abort the entire run without expiring
    # anyone — a partial/empty member list would falsely expire legitimate users.
    valid_users = set()
    for channel_id in channel_ids:
        try:
            members = _get_channel_members(bot_token, channel_id)
        except ChannelMembersFetchError as e:
            logger.error(f"VALIDATION_ABORTED: could not fetch members for {channel_id}: {e}. No mappings expired.")
            return {"expired": 0, "error": "channel_fetch_failed", "channel": channel_id}
        valid_users.update(members)
        logger.info(f"Channel {channel_id}: {len(members)} members")

    logger.info(f"Total valid users across channels: {len(valid_users)}")

    # Defensive floor: if we have active mappings but resolved zero valid users,
    # something is wrong upstream. Abort rather than expire everyone.
    if active and not valid_users:
        logger.error("VALIDATION_ABORTED: active mappings exist but zero valid users resolved. No mappings expired.")
        return {"expired": 0, "error": "no_valid_users_resolved"}

    # Step 3: Expire mappings whose slack_user_id is not in any channel
    now = datetime.now(timezone.utc).isoformat()
    total_expired = 0

    for mapping in active:
        if mapping["slack_user_id"] not in valid_users:
            try:
                table.update_item(
                    Key={"github_id": mapping["github_id"]},
                    UpdateExpression="SET #s = :status, expired_at = :ts, expiry_reason = :reason",
                    ConditionExpression="#s = :active",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":status": "expired",
                        ":ts": now,
                        ":reason": "member_is_not_in_the_channel",
                        ":active": "active",
                    },
                )
                total_expired += 1
                logger.info(f"IDENTITY_EXPIRED: github_id={mapping['github_id']} slack_user={mapping['slack_user_id']}")
            except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                pass

    logger.info(f"VALIDATION_COMPLETE: expired={total_expired}")
    return {"expired": total_expired}


def _html(status_code, message):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": f"""<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;background:#f6f8fa}}
.card{{background:#fff;border-radius:12px;padding:64px 56px;text-align:center;box-shadow:0 4px 12px rgba(0,0,0,0.1);max-width:500px}}
h2{{color:#24292e;margin:0 0 24px;font-size:22px}}
p{{color:#586069;margin:0;font-size:14px}}
</style></head>
<body><div class="card"><h2>{message}</h2><p>You can close this tab.</p></div></body>
</html>""",
    }
