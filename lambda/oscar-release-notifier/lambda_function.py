#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Scheduled release-readiness notifier for OSCAR.

Invoked by EventBridge every six hours. For each active release it decides whether a post
is due, and if so posts the readiness summary to the configured Slack channels.

The verdict is NOT computed here. This Lambda invokes the metrics Lambda, which owns the
rubric, so the number an RM reads in Slack is the same number they get by asking OSCAR
directly. That is also why this function needs no cluster access, no VPC attachment and no
cross-account role.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from cadence import (PHASE_INTERVAL_HOURS, diff_gaps, gap_signature,
                     should_notify)
from message_builder import build_message
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BEDROCK_ACTION_GROUP = 'metricsActionGroup'


def _metrics_function(function_name: str, parameters: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Invoke one metrics-Lambda action-group function and return its parsed result.

    The metrics Lambda speaks the Bedrock action-group envelope, so calls are shaped the
    same way Bedrock shapes them and the response body is unwrapped back to a dict.
    """
    target = os.environ.get('METRICS_FUNCTION_NAME')
    if not target:
        raise ValueError('METRICS_FUNCTION_NAME is not set')

    event = {
        'actionGroup': BEDROCK_ACTION_GROUP,
        'function': function_name,
        'parameters': [
            {'name': name, 'value': value}
            for name, value in (parameters or {}).items()
        ],
    }

    client = boto3.client('lambda', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    response = client.invoke(
        FunctionName=target,
        InvocationType='RequestResponse',
        Payload=json.dumps(event).encode(),
    )

    if response.get('FunctionError'):
        raise RuntimeError(
            f"metrics Lambda returned {response['FunctionError']} for {function_name}"
        )

    payload = json.loads(response['Payload'].read())
    body = (
        payload.get('response', {})
        .get('functionResponse', {})
        .get('responseBody', {})
        .get('TEXT', {})
        .get('body')
    )
    if body is None:
        raise RuntimeError(f'Unexpected response envelope from {function_name}')
    return json.loads(body)


def _load_slack_config() -> Dict[str, Any]:
    """Load the Slack token and release channels from the central secret."""
    secret_name = os.environ.get('CENTRAL_SECRET_NAME')
    if not secret_name:
        raise ValueError('CENTRAL_SECRET_NAME is not set')

    client = boto3.client('secretsmanager', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    secret = json.loads(client.get_secret_value(SecretId=secret_name)['SecretString'])

    return {
        'token': secret.get('SLACK_BOT_TOKEN', ''),
        'channels': [c.strip() for c in secret.get('RELEASE_CHANNELS', '').split(',') if c.strip()],
    }


def _state_table():
    table_name = os.environ.get('RELEASE_NOTIFY_TABLE_NAME')
    if not table_name:
        raise ValueError('RELEASE_NOTIFY_TABLE_NAME is not set')
    resource = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    return resource.Table(table_name)


def _hours_since(timestamp: Optional[str]) -> Optional[float]:
    if not timestamp:
        return None
    try:
        posted = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
    except ValueError:
        logger.warning(f'Could not parse last_posted_at: {timestamp!r}')
        return None
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - posted).total_seconds() / 3600


def _post_to_slack(client: WebClient, channels: List[str], text: str) -> int:
    """Post to every configured channel, returning how many succeeded."""
    delivered = 0
    for channel in channels:
        try:
            client.chat_postMessage(channel=channel, text=text, unfurl_links=False)
            delivered += 1
        except SlackApiError as e:
            logger.error(f'RELEASE_NOTIFY_SLACK_FAILED: {channel}: {e.response.get("error")}')
    return delivered


def _process_release(release: Dict[str, Any], table, slack: WebClient, channels: List[str]) -> Dict[str, Any]:
    """Evaluate one release and post if it is due. Returns a summary for the response."""
    version = release.get('version')
    phase = release.get('cadence_phase', 'not_scheduled')

    if PHASE_INTERVAL_HOURS.get(phase) is None:
        logger.info(f'RELEASE_NOTIFY [{version}]: skipped, phase {phase} does not notify')
        return {'version': version, 'posted': False, 'reason': f'phase {phase} does not notify'}

    status = _metrics_function('get_release_status', {'version': version})
    if status.get('error') or not status.get('found'):
        reason = status.get('error') or status.get('message', 'no release state indexed')
        logger.warning(f'RELEASE_NOTIFY [{version}]: no verdict available: {reason}')
        return {'version': version, 'posted': False, 'reason': reason}

    gaps = gap_signature(status)
    record = table.get_item(Key={'version': version}).get('Item')
    hours_since_last = _hours_since(record.get('last_posted_at') if record else None)

    notify, reason = should_notify(phase, status['verdict'], gaps, record, hours_since_last)
    logger.info(f'RELEASE_NOTIFY [{version}]: notify={notify} ({reason})')
    if not notify:
        return {'version': version, 'posted': False, 'reason': reason}

    delta = diff_gaps(record, gaps)
    text = build_message(version, release, status, delta)
    delivered = _post_to_slack(slack, channels, text)

    if delivered:
        table.put_item(Item={
            'version': version,
            'verdict': status['verdict'],
            'last_posted_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'cadence_phase': phase,
            **gaps,
        })

    return {
        'version': version,
        'posted': bool(delivered),
        'reason': reason,
        'channels_delivered': delivered,
        'verdict': status['verdict'],
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Check every active release and notify the ones that are due."""
    logger.info('RELEASE_NOTIFY: starting scheduled run')

    try:
        slack_config = _load_slack_config()
    except Exception as e:
        logger.error(f'RELEASE_NOTIFY_CONFIG_FAILED: {e}')
        return {'statusCode': 500, 'error': str(e)}

    if not slack_config['channels']:
        logger.warning('RELEASE_NOTIFY: RELEASE_CHANNELS is empty, nothing to notify')
        return {'statusCode': 200, 'posted': 0, 'reason': 'no channels configured'}
    if not slack_config['token']:
        logger.error('RELEASE_NOTIFY_CONFIG_FAILED: SLACK_BOT_TOKEN missing')
        return {'statusCode': 500, 'error': 'SLACK_BOT_TOKEN missing'}

    try:
        active = _metrics_function('list_active_releases')
    except Exception as e:
        logger.error(f'RELEASE_NOTIFY_METRICS_FAILED: {e}')
        return {'statusCode': 502, 'error': str(e)}

    if active.get('error'):
        logger.error(f"RELEASE_NOTIFY_METRICS_FAILED: {active['error']}")
        return {'statusCode': 502, 'error': active['error']}

    releases = active.get('releases', [])
    logger.info(f'RELEASE_NOTIFY: {len(releases)} active release(s)')

    slack = WebClient(token=slack_config['token'])
    table = _state_table()

    results = []
    for release in releases:
        try:
            results.append(_process_release(release, table, slack, slack_config['channels']))
        except Exception as e:
            # One broken release must not stop the others from being reported.
            logger.error(f"RELEASE_NOTIFY_FAILED [{release.get('version')}]: {e}")
            results.append({'version': release.get('version'), 'posted': False, 'error': str(e)})

    posted = sum(1 for r in results if r.get('posted'))
    logger.info(f'RELEASE_NOTIFY: posted for {posted} of {len(results)} release(s)')
    return {'statusCode': 200, 'posted': posted, 'results': results}
