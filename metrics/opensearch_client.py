#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
OpenSearch client WITHOUT role assumption - for testing.
"""

import logging
from typing import Dict, Any, Optional

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth

from config import Config

logger = logging.getLogger(__name__)


class OpenSearchClient:
    """OpenSearch client WITHOUT cross-account role assumption."""
    
    def __init__(self, config: Config):
        """Initialize OpenSearch client with VPC endpoint configuration."""
        self.config = config
        self.client = self._create_client()
        logger.info("OpenSearch client initialized for VPC deployment")
    
    def _create_client(self) -> OpenSearch:
        """Create OpenSearch client with cross-account role assumption."""
        # Assume the cross-account OpenSearchOscarAccessRole
        credentials = self._assume_cross_account_role()
        
        if not credentials:
            raise ValueError("Failed to assume OpenSearchOscarAccessRole")
        
        # Create AWS authentication for VPC endpoint using assumed role credentials
        # Extract just the hostname for AWS auth (no https://)
        # hostname = self.config.opensearch_host.replace('https://', '').replace('http://', '')
        hostname = 'https://aos-a4f4c9d2accb-brkjnnuiccoheln4bmcpzv4auq.us-east-1.es.amazonaws.com'
        auth = AWSRequestsAuth(
            aws_access_key=credentials.access_key,
            aws_secret_access_key=credentials.secret_key,
            aws_token=credentials.token,
            aws_host=hostname,  # Just hostname for signature
            aws_region=self.config.opensearch_region,
            aws_service=self.config.opensearch_service #es
        )
        
        # Configure OpenSearch client for VPC endpoint
        return OpenSearch(
            hosts=[{'host': hostname, 'port': 443}],  # Separate host and port --> needed?
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=self.config.request_timeout,
            max_retries=5,
            retry_on_timeout=True,
            headers={'Content-Type': 'application/json'}
        )
    
    def _assume_cross_account_role(self):
        """Assume the cross-account OpenSearch access role."""
        logger.info("Starting role assumption process")
        
        try:
            logger.info("Creating STS client")
            sts_client = boto3.client('sts')
            logger.info("STS client created successfully")
            
            logger.info("About to call assume_role")
            response = sts_client.assume_role(
                RoleArn='arn:aws:iam::979020455945:role/OpenSearchOscarAccessRole',
                RoleSessionName='oscar-metrics-session',
            )
            logger.info("assume_role call completed successfully")
            
            creds = response['Credentials']
            logger.info(f"Credentials received, expires at: {creds['Expiration']}")
            
            from botocore.credentials import Credentials
            credentials = Credentials(
                access_key=creds['AccessKeyId'],
                secret_key=creds['SecretAccessKey'],
                token=creds['SessionToken']
            )
            logger.info("Credentials object created successfully")
            return credentials
            
        except Exception as e:
            logger.error(f"Failed to assume cross-account role: {e}")
            # Return None instead of raising to allow graceful fallback
            return None
    
    def _parse_host(self, host: str) -> str:
        """Keep full HTTPS URL for VPC endpoint."""
        if not host.startswith('https://'):
            return f'https://{host}'
        return host
    
    def test_connection(self) -> bool:
        """Test connection to OpenSearch cluster via VPC endpoint."""
        try:
            health = self.client.cluster.health(timeout=5)
            logger.info(f"OpenSearch connection successful - Status: {health.get('status', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"OpenSearch connection failed: {e}")
            return False
    
    def query_test_failures(self, repository: str, time_range: str, 
                           status_filter: str = 'fail') -> Dict[str, Any]:
        """Query opensearch_release_metrics for release data (matching Groovy implementation)."""
        try:
            # Query opensearch_release_metrics index like the Groovy code
            result = self.client.search(
                index="opensearch_release_metrics",
                body={
                    "size": 10,
                    "_source": ["version", "component", "repository", "release_owners", "current_date"],
                    "query": {"match_all": {}}, #match_all instead of search_all, currently
                    "sort": [
                        {"current_date": {"order": "desc"}}
                    ]
                }
            )
            return result
        except Exception as e:
            logger.error(f"Release metrics query failed: {e}")
            # Return mock search result structure if query fails
            return {
                "hits": {
                    "total": {"value": 0},
                    "hits": []
                },
                "error": str(e),
                "no_role_assumption": True
            }
    
    # Minimal implementations for other methods
    def query_release_status(self, version=None, component=None):
        return {"test": "no_role_assumption"}
    
    def search_metrics(self, query_text, metric_types='all', repository=None, time_range='7d'):
        return {"test": "no_role_assumption"}
    
    def get_cluster_health(self):
        try:
            health = self.client.cluster.health()
            return {
                "type": "cluster_health",
                "connectivity": "success", 
                "cluster_status": health.get('status', 'unknown'),
                "number_of_nodes": health.get('number_of_nodes', 0),
                "no_role_assumption": True
            }
        except Exception as e:
            return {
                "type": "error",
                "message": str(e),
                "no_role_assumption": True
            }
    
    def test_role_assumption_only(self):
        """Test ONLY role assumption without OpenSearch client creation."""
        logger.info("Testing role assumption in isolation")
        
        try:
            logger.info("Creating STS client for isolated test")
            sts_client = boto3.client('sts')
            
            logger.info("Calling assume_role for isolated test")
            response = sts_client.assume_role(
                RoleArn='arn:aws:iam::979020455945:role/OpenSearchOscarAccessRole',
                RoleSessionName='oscar-test-session',
                DurationSeconds=900,
                ExternalId='oscar-metrics-cross-account-access'
            )
            
            logger.info("Role assumption successful in isolation")
            return {
                "status": "success",
                "assumed_role_arn": response['AssumedRoleUser']['Arn'],
                "expiration": str(response['Credentials']['Expiration']),
                "access_key_prefix": response['Credentials']['AccessKeyId'][:10]
            }
            
        except Exception as e:
            logger.error(f"Role assumption failed in isolation: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    def test_multiple_queries(self):
        """Test multiple query variations to find what works."""
        results = {}
        
        # Test 1: Cluster health
        try:
            results["cluster_health"] = self.client.cluster.health()
        except Exception as e:
            results["cluster_health"] = {"error": str(e)}
        
        # Test 2: List indices
        try:
            results["indices"] = self.client.cat.indices(format='json')
        except Exception as e:
            results["indices"] = {"error": str(e)}
        
        # Test 3: opensearch_release_metrics
        try:
            results["release_metrics"] = self.client.search(
                index="opensearch_release_metrics",
                body={"query": {"match_all": {}}, "size": 3}
            )
        except Exception as e:
            results["release_metrics"] = {"error": str(e)}
        
        # Test 4: gradle-check indices
        try:
            results["gradle_check"] = self.client.search(
                index="gradle-check-*",
                body={"query": {"match_all": {}}, "size": 3}
            )
        except Exception as e:
            results["gradle_check"] = {"error": str(e)}
        
        return results