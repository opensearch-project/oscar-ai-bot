# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""OAuth callback Lambda for Slack-GitHub identity linking."""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
secrets_client = boto3.client("secretsmanager")

_oauth_creds = None

IDENTITY_TABLE_PREFIX = "oscar-identity"
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
        import json
        _oauth_creds = json.loads(raw["SecretString"])
    return _oauth_creds


def _get_table(workspace_id) -> Optional[object]:
    if not IDENTITY_TABLE_PREFIX or not ENVIRONMENT:
        return None
    table_name = f"{IDENTITY_TABLE_PREFIX}-{workspace_id}-{ENVIRONMENT}"
    return dynamodb.Table(table_name)


def lambda_handler(event, context):
    params = event.get("queryStringParameters") or {}
    # code: the temporary OAuth authorization code returned by GitHub after user consent
    code = params.get("code")
    # state: HMAC-signed, base64url-encoded token containing slack_user_id, workspace_id, and timestamp
    state = params.get("state")

    if not code or not state:
        return _html(400, "Missing code or state parameter.")

    from oauth_state import verify_state

    creds = _get_oauth_creds()
    try:
        slack_user_id, workspace_id = verify_state(state, creds["OAUTH_STATE_SECRET"])
    except ValueError as e:
        logger.warning(f"IDENTITY_STATE_INVALID: reason={e}")
        return _html(400, "Invalid or expired link. Please run /oscar-link-github again.")

    table = _get_table(workspace_id)
    if not table:
        return _html(400, "Workspace not configured for identity linking.")

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

    user = requests.get("https://api.github.com/user", headers=headers, timeout=10).json()
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
