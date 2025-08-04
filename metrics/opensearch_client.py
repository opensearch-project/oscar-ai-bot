#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
OpenSearch client optimized for VPC Lambda deployment.
Handles cross-account access via VPC endpoint with AWS authentication.
"""

import logging
from typing import Dict, Any, Optional

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth

from config import Config

logger = logging.getLogger(__name__)


class OpenSearchClient:
    """
    OpenSearch client optimized for VPC Lambda deployment.
    
    Features:
    - VPC endpoint connectivity for cross-account access
    - AWS IAM authentication
    - Connection pooling and retry logic
    - Optimized queries for metrics data
    """
    
    def __init__(self, config: Config):
        """Initialize OpenSearch client with VPC endpoint configuration."""
        self.config = config
        self.client = self._create_client()
        logger.info("OpenSearch client initialized for VPC deployment")
    
    def _create_client(self) -> OpenSearch:
        """Create OpenSearch client with AWS authentication for VPC endpoint."""
        # Get AWS credentials from Lambda execution role
        session = boto3.Session()
        credentials = session.get_credentials()
        
        if not credentials:
            raise ValueError("No AWS credentials found in Lambda execution context")
        
        # Create AWS authentication for VPC endpoint
        auth = AWSRequestsAuth(
            aws_access_key=credentials.access_key,
            aws_secret_access_key=credentials.secret_key,
            aws_token=credentials.token,
            aws_host=self._parse_host(self.config.opensearch_host),
            aws_region=self.config.opensearch_region,
            aws_service=self.config.opensearch_service
        )
        
        # Configure OpenSearch client for VPC endpoint
        return OpenSearch(
            hosts=[{
                'host': self._parse_host(self.config.opensearch_host),
                'port': 443
            }],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=self.config.request_timeout,
            max_retries=3,
            retry_on_timeout=True,
            # VPC endpoint specific settings
            headers={'Content-Type': 'application/json'}
        )
    
    def _parse_host(self, host: str) -> str:
        """Parse host URL to extract hostname for VPC endpoint."""
        if host.startswith('https://'):
            return host[8:]
        elif host.startswith('http://'):
            return host[7:]
        return host
    
    def test_connection(self) -> bool:
        """Test connection to OpenSearch cluster via VPC endpoint."""
        try:
            # Use a shorter timeout for connection test (numeric value, not string)
            health = self.client.cluster.health(timeout=5)
            logger.info(f"OpenSearch connection successful - Status: {health.get('status', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"OpenSearch connection failed: {e}")
            # In VPC environment, connection failures are expected during testing
            # Return False but don't raise exception to allow mock mode fallback
            return False
    
    def query_test_failures(self, repository: str, time_range: str, 
                           status_filter: str = 'fail') -> Dict[str, Any]:
        """
        Query gradle-check indices for test failures.
        Optimized for VPC endpoint performance.
        """
        must_clauses = [
            {"range": {"build_start_time": {"gte": f"now-{time_range}"}}}
        ]
        
        # Repository filter
        if repository and repository.lower() != 'all':
            must_clauses.append({"term": {"repository.keyword": repository}})
        
        # Status filter
        if status_filter.lower() == 'fail':
            must_clauses.append({"term": {"test_status.keyword": "FAILED"}})
        elif status_filter.lower() == 'pass':
            must_clauses.append({"term": {"test_status.keyword": "PASSED"}})
        elif status_filter.lower() == 'skip':
            must_clauses.append({"term": {"test_status.keyword": "SKIPPED"}})
        
        query = {
            "query": {
                "bool": {"must": must_clauses}
            },
            "aggs": {
                "failed_by_class": {
                    "terms": {
                        "field": "test_class.keyword", 
                        "size": 10,
                        "order": {"_count": "desc"}
                    }
                },
                "failed_by_repository": {
                    "terms": {
                        "field": "repository.keyword", 
                        "size": 10,
                        "order": {"_count": "desc"}
                    }
                }
            },
            "sort": [{"build_start_time": {"order": "desc"}}],
            "size": min(self.config.max_results, 50),
            "_source": [
                "test_class", "test_name", "build_number", 
                "repository", "test_status", "build_start_time"
            ]
        }
        
        try:
            return self.client.search(index="gradle-check-*", body=query)
        except Exception as e:
            logger.error(f"Test failures query failed: {e}")
            raise
    
    def query_release_status(self, version: Optional[str] = None, 
                           component: Optional[str] = None) -> Dict[str, Any]:
        """
        Query opensearch_release_metrics for release information.
        Optimized for VPC endpoint performance.
        """
        must_clauses = []
        
        if version:
            must_clauses.append({"match": {"version": version}})
        if component:
            must_clauses.append({"match": {"component": component}})
        
        query = {
            "query": {
                "bool": {"must": must_clauses} if must_clauses else {"match_all": {}}
            },
            "sort": [{"current_date": {"order": "desc"}}],
            "size": min(self.config.max_results, 20),
            "_source": [
                "version", "component", "repository", "release_owners",
                "release_issue_exists", "release_issue", "current_date"
            ]
        }
        
        try:
            return self.client.search(index="opensearch_release_metrics", body=query)
        except Exception as e:
            logger.error(f"Release status query failed: {e}")
            raise
    
    def search_metrics(self, query_text: str, metric_types: str = 'all', 
                      repository: Optional[str] = None, 
                      time_range: str = '7d') -> Dict[str, Any]:
        """
        General search across metrics indices.
        Optimized for cross-index queries via VPC endpoint.
        """
        # Determine index pattern
        if metric_types == 'test':
            index_pattern = "gradle-check-*"
        elif metric_types in ['build', 'release']:
            index_pattern = "opensearch_release_metrics"
        else:
            index_pattern = "gradle-check-*,opensearch_release_metrics"
        
        must_clauses = []
        
        # Text search
        if query_text:
            must_clauses.append({
                "multi_match": {
                    "query": query_text,
                    "fields": [
                        "test_class^2", "component^2", "repository^2", 
                        "test_name", "version", "build_number"
                    ],
                    "type": "best_fields"
                }
            })
        
        # Repository filter
        if repository and repository.lower() != 'all':
            must_clauses.append({"term": {"repository.keyword": repository}})
        
        # Time range filter (flexible field matching)
        must_clauses.append({
            "bool": {
                "should": [
                    {"range": {"build_start_time": {"gte": f"now-{time_range}"}}},
                    {"range": {"current_date": {"gte": f"now-{time_range}"}}}
                ],
                "minimum_should_match": 1
            }
        })
        
        query = {
            "query": {
                "bool": {"must": must_clauses} if must_clauses else {"match_all": {}}
            },
            "sort": [{"_score": {"order": "desc"}}],
            "size": min(self.config.max_results, 30)
        }
        
        try:
            return self.client.search(index=index_pattern, body=query)
        except Exception as e:
            logger.error(f"Metrics search failed: {e}")
            raise
    
    def get_cluster_health(self) -> Dict[str, Any]:
        """Get cluster health information via VPC endpoint."""
        try:
            health = self.client.cluster.health()
            logger.info(f"Cluster health retrieved - Status: {health.get('status', 'unknown')}")
            return health
        except Exception as e:
            logger.error(f"Cluster health check failed: {e}")
            return {'status': 'unknown', 'error': str(e)}