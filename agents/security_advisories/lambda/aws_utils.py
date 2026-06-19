#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""AWS Utilities for Security Advisories Lambda Functions.

This module provides AWS-related utilities including session management,
cross-account role assumption, and OpenSearch request handling.

Functions:
    get_opensearch_session: Get boto3 session with optional cross-account role
    get_latest_scans_index: Resolve the scans alias to its concrete index
    opensearch_request: Make signed HTTP request to OpenSearch
"""

import json
import logging

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from config import config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_opensearch_session():
    """Get boto3 session with assumed cross-account role if configured.

    When ``config.cross_account_role_arn`` is set, the function assumes that
    role via STS and returns a session with the temporary credentials.
    Otherwise it returns a default session using the Lambda execution role.

    Returns:
        boto3.Session: A session configured with the appropriate credentials.

    Raises:
        Exception: If the STS assume-role call fails.
    """
    if config.cross_account_role_arn:
        sts_client = boto3.client('sts')
        logger.info('Assuming cross-account role for security advisories')
        try:
            response = sts_client.assume_role(
                RoleArn=config.cross_account_role_arn,
                RoleSessionName='oscar-security-advisories-session',
            )
            logger.info('Successfully assumed cross-account role')
        except Exception as e:
            logger.error(
                f'SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_FAILED: Failed to assume cross-account role: {e}',
            )
            raise

        return boto3.Session(
            aws_access_key_id=response['Credentials']['AccessKeyId'],
            aws_secret_access_key=response['Credentials']['SecretAccessKey'],
            aws_session_token=response['Credentials']['SessionToken'],
        )

    # No cross-account role configured — use Lambda execution role
    logger.info('Using Lambda execution role credentials')
    return boto3.Session()


def get_latest_scans_index() -> str:
    """Get the most recently created scans index.

    Uses the ``_search`` API across all indices with a filter on the
    ``timestamp.scan`` field (which only exists in scan indices) and
    sorts by ``_index`` descending.  Since scan indices follow the
    naming pattern ``scans-NNNNNN``, lexicographic sort returns the
    highest-numbered (most recent) index first.

    Returns:
        The concrete index name (e.g. ``scans-000164``).

    Raises:
        RuntimeError: If no scans indices are found or the request fails.
    """

    body = json.dumps({
        'size': 1,
        'query': {
            'exists': {'field': 'timestamp.scan'},
        },
        'sort': [{'_index': {'order': 'desc'}}],
        '_source': False,
    })

    try:
        path = '/_search'
        response = opensearch_request('GET', path, body=body)

        hits = response.get('hits', {}).get('hits', [])
        if hits:
            latest_index = hits[0]['_index']
            logger.info(f'Latest scans index resolved via _search: {latest_index}')
            return latest_index
    except Exception as e:
        logger.error(
            f'SECURITY_ADVISORIES_INDEX_LOOKUP_FAILED: '
            f'Could not resolve latest scans index: {e}',
        )
        raise RuntimeError(
            f'Failed to resolve latest scans index: {e}',
        ) from e

    raise RuntimeError(
        'No scans indices found',
    )


def opensearch_request(method, path, body=None):
    """Make SigV4-signed HTTP request to OpenSearch.

    Args:
        method: HTTP method (GET, POST, PUT, etc.).
        path: URL path including query string (e.g. ``/_search?search_pipeline=...``).
        body: Optional request body as a JSON-encoded string.

    Returns:
        dict: Parsed JSON response from OpenSearch.

    Raises:
        ValueError: If ``OPENSEARCH_HOST`` is not configured.
        Exception: On connection or non-2xx response errors.
    """
    opensearch_host = config.get_opensearch_host_clean()
    if not opensearch_host:
        raise ValueError('OPENSEARCH_HOST not configured')

    url = f'https://{opensearch_host}{path}'
    session = get_opensearch_session()

    # Create signed request
    request = AWSRequest(
        method=method,
        url=url,
        data=body,
        headers={'Content-Type': 'application/json'} if body else {},
    )

    # Sign the request
    credentials = session.get_credentials()
    SigV4Auth(
        credentials, config.opensearch_service, config.opensearch_region,
    ).add_auth(request)

    # Make the request
    try:
        response = requests.request(
            method=request.method,
            url=request.url,
            data=request.body,
            headers=dict(request.headers),
            timeout=config.request_timeout,
        )
    except Exception as e:
        logger.error(
            f'SECURITY_ADVISORIES_OPENSEARCH_CONNECTION_FAILED: Failed to connect to OpenSearch cluster: {e}',
        )
        raise

    if response.status_code in [200, 201]:
        return response.json()
    else:
        raise Exception(
            f'OpenSearch request failed: {response.status_code} - {response.text}',
        )
