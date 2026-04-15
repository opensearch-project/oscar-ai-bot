#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
SNS-to-Slack notification Lambda for OSCAR alarms.

Receives CloudWatch alarm notifications via SNS and posts formatted
messages to Slack channels configured in ALERTS_CHANNEL.
"""

import json
import logging
import os
from typing import Any, Dict

import boto3
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_config() -> Dict[str, Any]:
    """Load Slack token and alert channels from central secret."""
    secret_name = os.environ.get("CENTRAL_SECRET_NAME")
    if not secret_name:
        raise ValueError("CENTRAL_SECRET_NAME not set")

    client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    secret = json.loads(client.get_secret_value(SecretId=secret_name)["SecretString"])

    return {
        "token": secret.get("SLACK_BOT_TOKEN", ""),
        "channels": [c.strip() for c in secret.get("ALERTS_CHANNELS", "").split(",") if c.strip()],
    }


def format_alarm_message(record: Dict[str, Any]) -> str:
    """Format an SNS alarm record into a Slack message."""
    try:
        message = json.loads(record["Sns"]["Message"])
        alarm_name = message.get("AlarmName", "Unknown")
        description = message.get("AlarmDescription", "")
        state = message.get("NewStateValue", "UNKNOWN")
        reason = message.get("NewStateReason", "")
        timestamp = message.get("StateChangeTime", "")

        emoji = ":rotating_light:" if state == "ALARM" else ":white_check_mark:"

        parts = [
            f"{emoji} *{alarm_name}* — {state}",
        ]
        if description:
            parts.append(f"_{description}_")
        if reason:
            parts.append(f"Reason: {reason}")
        if timestamp:
            parts.append(f"Time: {timestamp}")

        return "\n".join(parts)

    except (json.JSONDecodeError, KeyError):
        return f":bell: *OSCAR Alert*\n{record.get('Sns', {}).get('Message', 'No message')}"


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Process SNS events and post to Slack alert channels."""
    logger.info(f"Received event with {len(event.get('Records', []))} records")

    config = get_config()
    if not config["token"]:
        logger.error("NOTIFICATION_FAILED: SLACK_BOT_TOKEN not found in central secret")
        return {"statusCode": 500, "body": "Missing Slack token"}

    if not config["channels"]:
        logger.error("NOTIFICATION_FAILED: ALERTS_CHANNELS is empty")
        return {"statusCode": 500, "body": "No alert channels configured"}

    client = WebClient(token=config["token"])
    errors = []

    for record in event.get("Records", []):
        message = format_alarm_message(record)

        for channel in config["channels"]:
            try:
                client.chat_postMessage(
                    channel=channel,
                    text=message,
                    unfurl_links=False,
                    unfurl_media=False,
                )
                logger.info(f"NOTIFICATION_SENT: channel={channel}")
            except SlackApiError as e:
                logger.error(f"NOTIFICATION_FAILED: channel={channel}, error={e.response['error']}")
                errors.append(f"{channel}: {e.response['error']}")
            except Exception as e:
                logger.error(f"NOTIFICATION_FAILED: channel={channel}, error={e}")
                errors.append(f"{channel}: {str(e)}")

    if errors:
        return {"statusCode": 207, "body": f"Partial failure: {errors}"}
    return {"statusCode": 200, "body": "OK"}
