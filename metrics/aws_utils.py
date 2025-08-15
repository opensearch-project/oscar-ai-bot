#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
AWS Utilities for Metrics Lambda Functions.

This module provides AWS-related utilities including session management,
cross-account role assumption, and OpenSearch request handling.

Functions:
    get_opensearch_session: Get boto3 session with assumed cross-account role
    opensearch_request: Make signed HTTP request to OpenSearch
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from config import config

logger = logging.getLogger(__name__)


def get_opensearch_session():
    """Get boto3 session with assumed cross-account role."""
    sts_client = boto3.client('sts')
    response = sts_client.assume_role(
        RoleArn=config.metrics_cross_account_role_arn,
        RoleSessionName='oscar-metrics-session'
    )
    
    return boto3.Session(
        aws_access_key_id=response['Credentials']['AccessKeyId'],
        aws_secret_access_key=response['Credentials']['SecretAccessKey'],
        aws_session_token=response['Credentials']['SessionToken']
    )


def opensearch_request(method, path, body=None):
    """Make signed HTTP request to OpenSearch."""
    opensearch_host = config.get_opensearch_host_clean()
    if not opensearch_host:
        raise ValueError("OPENSEARCH_HOST not configured")
    
    url = f'https://{opensearch_host}{path}'
    session = get_opensearch_session()
    
    # Create signed request
    request = AWSRequest(
        method=method,
        url=url,
        data=json.dumps(body) if body else None,
        headers={'Content-Type': 'application/json'} if body else {}
    )
    
    # Sign the request
    credentials = session.get_credentials()
    SigV4Auth(credentials, config.opensearch_service, config.opensearch_region).add_auth(request)
    
    # Make the request
    response = requests.request(
        method=request.method,
        url=request.url,
        data=request.body,
        headers=dict(request.headers),
        timeout=config.opensearch_request_timeout
    )
    
    if response.status_code in [200, 201]:
        return response.json()
    else:
        raise Exception(f'OpenSearch request failed: {response.status_code} - {response.text}')


def test_role_assumption() -> Dict[str, Any]:
    """Test cross-account role assumption."""
    try:
        import time
        
        logger.info("Testing role assumption")
        
        start_time = time.time()
        session = get_opensearch_session()
        end_time = time.time()
        
        # Test assumed identity
        sts_client = session.client('sts')
        assumed_identity = sts_client.get_caller_identity()
        
        return {
            'status': 'success',
            'duration_seconds': round(end_time - start_time, 3),
            'assumed_identity': {
                'account': assumed_identity.get('Account'),
                'arn': assumed_identity.get('Arn'),
                'user_id': assumed_identity.get('UserId')
            }
        }
        
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_type': type(e).__name__
        }


def test_opensearch_connectivity() -> Dict[str, Any]:
    """Test OpenSearch connectivity and basic queries."""
    try:
        # Test basic cluster health
        health = opensearch_request('GET', '/_cluster/health')
        
        # Test a simple search
        search_result = opensearch_request('POST', f'/{config.release_metrics_index}/_search', {
            "size": 1,
            "query": {"match_all": {}}
        })
        
        return {
            'status': 'success',
            'cluster_health': health.get('status', 'unknown'),
            'cluster_name': health.get('cluster_name', 'unknown'),
            'total_documents': search_result.get('hits', {}).get('total', {}).get('value', 0)
        }
        
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_type': type(e).__name__
        }