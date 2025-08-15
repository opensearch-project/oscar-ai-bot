#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Constants for Slack Handler.
"""

# Channel allow list
CHANNEL_ALLOW_LIST = ['C096MV7JZ0T', 'C09827S7CEB', 'C091EH1JKCL', 'C088XMSH4DA']

# Authorized users for automated message sending functionality
AUTHORIZED_MESSAGE_SENDERS = [
    'U091B0QH1QD',  # Rishabh
    'W017PN2ADN0',  # Sayali
    'W017VV9TD33',  # Prudhvi
    'W017VPMPKH7',  # Divyam
    'W017PKU06CC',  # Peter
    'U032Q5N0HTM'   # Saurabh
]

# Timeout thresholds
HOURGLASS_THRESHOLD = 45  # seconds
TIMEOUT_THRESHOLD = 120   # seconds

# Thread pool settings
MAX_WORKERS = 50
MAX_ACTIVE_QUERIES = 50

# Agent query templates
AGENT_QUERIES = {
    "announce": "Send a release announcement message to channel {channel} using the release-announcement template for version {version} {rc_param}. Ensure the template is filled out correctly.",
    "assign_owner": "Send a release owner assignment message to channel {channel} using the release-owner-assignment template for version {version} {rc_param}. Make sure to ping any relevant people and ensure the template is filled out correctly.",
    "request_owner": "Send a request for release owner message to channel {channel} using the request-release-owner template for version {version} {rc_param}. Ensure the template is filled out correctly.",
    "rc_details": "Send RC details message to channel {channel} using the rc-details template for version {version} {rc_param}. Ensure the template is filled out correctly.",
    "missing_notes": "Send a missing release notes message to channel {channel} using the missing-release-notes template for version {version} {rc_param}. Ensure that relevant maintainers are pinged and the template is filled out correctly.",
    "integration_test": "Send an integration test status message to channel {channel} for version {version} {rc_param}. Format the response well.",
    "broadcast": "Process the following user_query and broadcast the response to channel {channel}. Here is the user_query: {user_query}."
}