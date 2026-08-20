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
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
import requests
from oscar_shared.injection_patterns import STRUCTURAL_INJECTION_PATTERNS

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

WEBHOOK_TIMESTAMP_TOLERANCE = 300  # 5 minutes
MAX_EXTERNAL_BODY_LENGTH = 1000

_INJECTION_PATTERNS = STRUCTURAL_INJECTION_PATTERNS


def _screen_content(text: str) -> dict:
    """Detect injection patterns, sanitize, and truncate."""
    if not text:
        return {"sanitized": "", "flagged": False, "flags": []}

    flags = []
    sanitized = text

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(sanitized):
            flags.append(pattern.pattern)
            sanitized = pattern.sub('[FILTERED]', sanitized)

    sanitized = sanitized[:MAX_EXTERNAL_BODY_LENGTH]

    return {
        "sanitized": sanitized,
        "flagged": bool(flags),
        "flags": flags,
    }


_bot_mention_re: Optional[re.Pattern] = None


def _get_bot_mention_re() -> re.Pattern:
    """Lazily compile the bot @mention regex from the secret."""
    global _bot_mention_re
    if _bot_mention_re is None:
        bot_username = _secrets().get("GITHUB_BOT_USERNAME", "")
        if not bot_username:
            raise ValueError(
                "GITHUB_BOT_USERNAME not configured in webhook secret"
            )
        _bot_mention_re = re.compile(
            r'(?<![a-zA-Z0-9_-])@' + re.escape(bot_username) + r'(?![a-zA-Z0-9_-])',
            re.IGNORECASE,
        )
    return _bot_mention_re


def _is_bot_mentioned(text: str) -> bool:
    """Check for exact @mention of the bot (word-boundary match, not substring)."""
    return bool(_get_bot_mention_re().search(text))


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


def _escape_mrkdwn(text: str) -> str:
    """Escape Slack mrkdwn special characters in untrusted content."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _screened_body_blocks(raw_body: str, repo_name: str, issue_number, sender_login: str) -> list:
    """Screen untrusted body text and return warning + body + injection alert blocks."""
    screening = _screen_content(raw_body)
    display_body = _escape_mrkdwn(screening["sanitized"]) or "No description provided."
    truncated = len(raw_body) > MAX_EXTERNAL_BODY_LENGTH

    blocks = [
        {
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": ":warning: Please review carefully before approving.",
            }],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f">>> {display_body}{'...' if truncated else ''}"},
        },
    ]

    if screening["flagged"]:
        logger.warning(
            "SUSPICIOUS_CONTENT_FLAGGED: repo=%s issue=%s sender=%s patterns=%d",
            repo_name, issue_number, sender_login, len(screening["flags"]),
        )
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":rotating_light: *Potential prompt injection detected.* "
                        "Suspicious patterns replaced with `[FILTERED]`. "
                        "Review the original on GitHub before proceeding.",
            },
        })

    return blocks


_FOOTER_BLOCKS = [
    {"type": "divider"},
    {
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": "Reply in this thread by mentioning @oscar with the action you'd like to take.",
        }],
    },
]


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

        if not _is_bot_mentioned(body):
            return None

        issue_type = "PR" if issue.get("pull_request") else "Issue"
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"GitHub @mention on {issue_type} #{issue.get('number', '')}"},
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
            *_screened_body_blocks(body, repo.get("full_name", ""), issue.get("number", ""), sender.get("login", "")),
            *_FOOTER_BLOCKS,
        ]
        return {"blocks": blocks}

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
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"New {request_type} Request"},
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
            *_screened_body_blocks(issue.get("body", "") or "", repo.get("full_name", ""), issue.get("number", ""), sender.get("login", "")),
            *_FOOTER_BLOCKS,
        ]
        return {"blocks": blocks}

    return None


def _check_payload_freshness(payload: Dict[str, Any]) -> bool:
    """Check if the webhook payload's event timestamp is within tolerance."""
    # Check comment.created_at or issue.created_at/updated_at
    timestamp_str = None
    if "comment" in payload:
        timestamp_str = payload["comment"].get("created_at")
    elif "issue" in payload:
        timestamp_str = payload["issue"].get("updated_at") or payload["issue"].get("created_at")

    if not timestamp_str:
        return True

    try:
        event_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - event_time).total_seconds()
        if age > WEBHOOK_TIMESTAMP_TOLERANCE:
            logger.warning(
                "WEBHOOK_REPLAY_REJECTED: payload age %.0fs exceeds %ds tolerance (timestamp=%s)",
                age, WEBHOOK_TIMESTAMP_TOLERANCE, timestamp_str,
            )
            return False
    except (ValueError, TypeError) as e:
        logger.warning("Could not parse webhook timestamp '%s': %s", timestamp_str, e)

    return True


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

    if not _check_payload_freshness(payload):
        return {"statusCode": 400, "body": "Webhook payload too old (possible replay)"}

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
