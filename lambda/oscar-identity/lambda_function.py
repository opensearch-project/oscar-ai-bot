# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""OAuth callback Lambda for Slack-GitHub identity linking."""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
secrets_client = boto3.client("secretsmanager")

_oauth_creds = None

WORKSPACE_TABLES = json.loads(os.environ.get("WORKSPACE_TABLES", "{}"))


def _get_oauth_creds():
    global _oauth_creds
    if _oauth_creds is None:
        raw = secrets_client.get_secret_value(SecretId=os.environ["CENTRAL_SECRET_NAME"])
        _oauth_creds = json.loads(raw["SecretString"])
    return _oauth_creds


def _get_table(workspace_id):
    table_name = WORKSPACE_TABLES.get(workspace_id)
    if not table_name:
        return None
    return dynamodb.Table(table_name)


def lambda_handler(event, context):
    params = event.get("queryStringParameters") or {}
    code = params.get("code")
    state = params.get("state")

    if not code or not state:
        return _html(400, "Missing code or state parameter.")

    parts = state.split(":", 1)
    if len(parts) != 2:
        return _html(400, "Invalid state parameter.")
    slack_user_id, workspace_id = parts

    table = _get_table(workspace_id)
    if not table:
        return _html(400, "Workspace not configured for identity linking.")

    creds = _get_oauth_creds()
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
    access_token = token_resp.json().get("access_token")
    if not access_token:
        logger.warning(f"IDENTITY_AUTH_FAILED: slack_user={slack_user_id} workspace={workspace_id} reason=token_exchange_failed")
        return _html(400, "GitHub authorization failed. Run /oscar-link-github again.")

    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}

    try:
        user = requests.get("https://api.github.com/user", headers=headers, timeout=10).json()
        github_handle = user.get("login")
        github_id = user.get("id")

        if not github_handle or not github_id:
            return _html(400, "Could not retrieve GitHub profile.")

        affiliation = user.get("company") or ""

        # Duplicate check
        existing = table.get_item(Key={"github_id": github_id}).get("Item")
        if existing and existing.get("slack_user_id") != slack_user_id and existing.get("status") == "active":
            logger.warning(f"IDENTITY_DUPLICATE_REJECTED: slack_user={slack_user_id} workspace={workspace_id} github={github_handle} github_id={github_id} existing_slack_user={existing['slack_user_id']}")
            return _html(409, "This GitHub account is already linked to another Slack user.")

        now = datetime.now(timezone.utc).isoformat()
        table.put_item(Item={
            "github_id": github_id,
            "github_handle": github_handle,
            "slack_user_id": slack_user_id,
            "status": "active",
            "affiliation": affiliation,
            "last_validated": now,
        })
        logger.info(f"IDENTITY_LINKED: slack_user={slack_user_id} workspace={workspace_id} github={github_handle} github_id={github_id} affiliation={affiliation}")

        return _html(200, "Successfully linked your GitHub account.")

    finally:
        try:
            requests.delete(
                f"https://api.github.com/applications/{creds['GITHUB_OAUTH_CLIENT_ID']}/token",
                auth=(creds["GITHUB_OAUTH_CLIENT_ID"], creds["GITHUB_OAUTH_CLIENT_SECRET"]),
                headers={"Accept": "application/vnd.github+json"},
                json={"access_token": access_token},
                timeout=10,
            )
        except Exception as e:
            logger.warning(f"Token revocation failed (non-critical): {e}")


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
