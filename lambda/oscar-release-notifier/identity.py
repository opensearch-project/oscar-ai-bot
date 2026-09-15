#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""GitHub handle to Slack user resolution for the release notifier.

The schedule index records the release manager as a GitHub handle, which means nothing to
Slack - posting it as text leaves the one person who has to act on the message to notice it
themselves. The identity table already maps GitHub accounts to Slack users, so the handle is
translated here into a real mention.

The lookup is a scan rather than an indexed query, deliberately. The table is keyed on the
GitHub numeric id with a secondary index on slack_user_id, so a handle is a non-key
attribute, and adding an index for it would buy little: the table holds one small item per
person who has linked an account, the notifier runs four times a day, and one scan per run
serves every release in it. A scan also compares handles case-insensitively, which a
case-sensitive index key could not - the handle in the schedule is typed by hand into a
Jenkins parameter, while the table stores the casing GitHub reported.
"""

import logging
import os
from typing import Dict, Optional, Set

import boto3

logger = logging.getLogger()

GITHUB_PROFILE_URL = 'https://github.com'


def normalize_handle(handle: Optional[str]) -> str:
    """Reduce whatever was registered as the release manager to a bare GitHub handle.

    The value is a free-text Jenkins parameter, so it arrives as a handle, an @handle or a
    pasted profile URL depending on who filled the form in.
    """
    if not handle:
        return ''
    value = str(handle).strip().rstrip('/')
    if '/' in value:
        value = value.rsplit('/', 1)[-1]
    return value.lstrip('@')


def load_handle_map() -> Dict[str, str]:
    """Map lowercased GitHub handle to Slack user ID for every unambiguous active mapping.

    Returns an empty map where there is no identity table (no Slack workspace id was
    configured for the deployment) or when the table cannot be read. A missing mention is a
    cosmetic loss, so it must never cost the release manager the notification itself.

    A handle claimed by two different Slack users is left out entirely - see the collision
    branch below.
    """
    table_name = os.environ.get('IDENTITY_TABLE_NAME')
    if not table_name:
        return {}

    resource = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    table = resource.Table(table_name)

    mapping: Dict[str, str] = {}
    ambiguous: Set[str] = set()
    # The filter does not reduce what DynamoDB charges for - it is applied after the scan -
    # but it keeps expired mappings out of the response, so the payload and the pages this
    # loop walks stay proportional to the people who can actually be mentioned.
    scan_kwargs = {
        'ProjectionExpression': 'github_handle, slack_user_id, #s',
        'FilterExpression': '#s = :active',
        'ExpressionAttributeNames': {'#s': 'status'},
        'ExpressionAttributeValues': {':active': 'active'},
    }

    try:
        while True:
            response = table.scan(**scan_kwargs)
            for item in response.get('Items', []):
                # Belt and braces with the filter above: an expired mapping's Slack user may
                # have left the workspace already.
                if item.get('status') != 'active':
                    continue
                handle = item.get('github_handle')
                slack_user_id = item.get('slack_user_id')
                if not isinstance(handle, str) or not isinstance(slack_user_id, str):
                    # Skipped rather than allowed to raise: the handler below would turn one
                    # malformed row into an empty map, costing every release manager their
                    # mention. Only a hand-edited item can get here.
                    logger.warning('RELEASE_NOTIFY_IDENTITY_MALFORMED: skipping an item whose '
                                   'handle or Slack id is not a string')
                    continue
                if not handle or not slack_user_id:
                    continue

                key = handle.lower()
                existing = mapping.get(key)
                if existing is not None and existing != slack_user_id:
                    # GitHub handles are reusable, and this table is keyed on the numeric id:
                    # rename an account, let someone else take the old handle, and two active
                    # rows claim it. Tagging the wrong person on a release-blocking alert is
                    # worse than tagging nobody, so the handle is dropped below and the message
                    # falls back to a profile link.
                    logger.warning(f'RELEASE_NOTIFY_IDENTITY_COLLISION: {key} is claimed by more '
                                   f'than one active mapping and will not be mentioned')
                    ambiguous.add(key)
                    continue
                mapping[key] = slack_user_id
            if 'LastEvaluatedKey' not in response:
                break
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
    except Exception as e:
        logger.warning(f'RELEASE_NOTIFY_IDENTITY_LOOKUP_FAILED: {e}')
        return {}

    for key in ambiguous:
        mapping.pop(key, None)

    logger.info(f'RELEASE_NOTIFY_IDENTITY: {len(mapping)} active mapping(s) loaded')
    return mapping


def render_release_manager(handle: Optional[str], handle_map: Optional[Dict[str, str]] = None) -> str:
    """Render the release manager as a Slack mention, falling back to their profile link.

    The fallback applies until the release manager has run /oscar-link-github, and in any
    deployment that has no identity table.
    """
    normalized = normalize_handle(handle)
    if not normalized:
        return ''

    slack_user_id = (handle_map or {}).get(normalized.lower())
    if slack_user_id:
        return f'<@{slack_user_id}>'
    return f'<{GITHUB_PROFILE_URL}/{normalized}|@{normalized}>'
