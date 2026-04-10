# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Lambda handler for GitHub webhook events.

Receives issue_comment and issues events from GitHub, verifies the webhook
signature, detects @mentions of the bot, and posts notifications to Slack
via incoming webhook URL.
"""

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, Optional

import boto3
import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BOT_MENTION = os.environ.get("GITHUB_BOT_USERNAME", "oscar-github-agent-test")


def _get_secrets() -> Dict[str, str]:
    """Load secrets from Secrets Manager."""
    secret_name = os.environ.get("WEBHOOK_SECRET_NAME", "")
    if not secret_name:
        raise ValueError("WEBHOOK_SECRET_NAME not set")
    sm = boto3.client("secretsmanager")
    resp = sm.get_secret_value(SecretId=secret_name)
    return json.loads(resp["SecretString"])


_cached_secrets: Optional[Dict[str, str]] = None


def _secrets() -> Dict[str, str]:
    global _cached_secrets
    if _cached_secrets is None:
        _cached_secrets = _get_secrets()
    return _cached_secrets


def _verify_signature(payload_body: str, signature_header: str) -> bool:
    """Verify the GitHub webhook HMAC-SHA256 signature."""
    if not signature_header:
        return False
    secret = _secrets().get("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        logger.error("GITHUB_WEBHOOK_SECRET not configured in secret")
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload_body.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _post_to_slack(payload: Dict[str, Any]) -> None:
    """Post a message to Slack via incoming webhook URL."""
    webhook_url = _secrets().get("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        logger.error("SLACK_WEBHOOK_URL not configured in secret")
        return
    resp = requests.post(webhook_url, json=payload, timeout=10)
    if resp.status_code != 200:
        logger.error("Slack webhook returned %d: %s", resp.status_code, resp.text)


def _build_slack_message(event_type: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a Slack message from a GitHub webhook payload."""
    if event_type == "issue_comment":
        action = payload.get("action")
        if action != "created":
            return None
        comment = payload.get("comment", {})
        issue = payload.get("issue", {})
        repo = payload.get("repository", {})
        sender = payload.get("sender", {})
        body = comment.get("body", "")

        if f"@{BOT_MENTION}" not in body:
            return None

        issue_type = "PR" if issue.get("pull_request") else "Issue"
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"GitHub @mention on {issue_type} #{issue.get('number', '')}",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Repo:*\n{repo.get('full_name', '')}"},
                        {"type": "mrkdwn", "text": f"*{issue_type}:*\n<{issue.get('html_url', '')}|#{issue.get('number', '')} {issue.get('title', '')}>"},
                        {"type": "mrkdwn", "text": f"*From:*\n{sender.get('login', '')}"},
                        {"type": "mrkdwn", "text": f"*Comment:*\n<{comment.get('html_url', '')}|View comment>"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f">>> {body[:500]}{'...' if len(body) > 500 else ''}",
                    },
                },
                {"type": "divider"},
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "Reply to this request in the Slack channel by mentioning @oscar with the action you'd like to take.",
                        }
                    ],
                },
            ],
        }

    if event_type == "issues":
        action = payload.get("action")
        if action not in ("opened", "labeled"):
            return None
        issue = payload.get("issue", {})
        repo = payload.get("repository", {})
        sender = payload.get("sender", {})
        title = issue.get("title", "")
        labels = [lab.get("name", "") for lab in issue.get("labels", [])]

        is_repo_request = title.startswith("[Repository Request]")
        is_maintainer_request = "[GitHub Request] Add" in title and "maintainers" in title.lower()

        if not is_repo_request and not is_maintainer_request:
            return None

        request_type = "Repository Creation" if is_repo_request else "Maintainer Addition"
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"New {request_type} Request",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Repo:*\n{repo.get('full_name', '')}"},
                        {"type": "mrkdwn", "text": f"*Issue:*\n<{issue.get('html_url', '')}|#{issue.get('number', '')} {title}>"},
                        {"type": "mrkdwn", "text": f"*From:*\n{sender.get('login', '')}"},
                        {"type": "mrkdwn", "text": f"*Labels:*\n{', '.join(labels) or 'None'}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f">>> {issue.get('body', '')[:500] or 'No description provided.'}",
                    },
                },
                {"type": "divider"},
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "Reply to this request in the Slack channel by mentioning @oscar with the action you'd like to take.",
                        }
                    ],
                },
            ],
        }

    return None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler for GitHub webhook events."""
    headers = event.get("headers") or {}
    # API Gateway lowercases header keys in proxy mode
    signature = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256", "")
    event_type = headers.get("x-github-event") or headers.get("X-GitHub-Event", "")
    body_str = event.get("body", "")

    if not body_str:
        return {"statusCode": 400, "body": "Empty body"}

    if not _verify_signature(body_str, signature):
        logger.warning("Webhook signature verification failed")
        return {"statusCode": 401, "body": "Invalid signature"}

    try:
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "Invalid JSON"}

    logger.info(
        "GitHub webhook: event=%s action=%s repo=%s",
        event_type,
        payload.get("action", ""),
        payload.get("repository", {}).get("full_name", ""),
    )

    slack_message = _build_slack_message(event_type, payload)
    if slack_message:
        _post_to_slack(slack_message)
        logger.info("Slack notification sent for %s event", event_type)
    else:
        logger.info("No notification needed for %s event (action=%s)", event_type, payload.get("action", ""))

    return {"statusCode": 200, "body": "OK"}
