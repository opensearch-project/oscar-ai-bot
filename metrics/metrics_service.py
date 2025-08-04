#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Business logic for metrics analysis.
Optimized for VPC Lambda deployment with efficient data processing.
"""

import logging
from typing import Dict, Any, List, Optional

from opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)


class MetricsService:
    """
    Core business logic for metrics analysis.
    Optimized for VPC Lambda deployment with efficient processing.
    """
    
    def __init__(self, opensearch_client: OpenSearchClient):
        """Initialize metrics service with OpenSearch client."""
        self.opensearch_client = opensearch_client
        logger.info("Metrics service initialized")
    
    def get_test_metrics(self, metric_type: str = 'execution', 
                        time_range: str = '7d',
                        project_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze test metrics based on type.
        
        Args:
            metric_type: Type of test metric (execution, coverage, trends)
            time_range: Time range for analysis (1d, 7d, 30d)
            project_filter: Filter by specific project or component
            
        Returns:
            Structured test metrics data
        """
        try:
            repository = project_filter or 'all'
            
            # Get test failure data
            results = self.opensearch_client.query_test_failures(
                repository=repository,
                time_range=time_range,
                status_filter='fail'
            )
            
            # Process results
            total_failures = results['hits']['total']['value']
            test_results = results['hits']['hits']
            
            # Extract aggregations
            class_aggs = results.get('aggregations', {}).get('failed_by_class', {}).get('buckets', [])
            repo_aggs = results.get('aggregations', {}).get('failed_by_repository', {}).get('buckets', [])
            
            # Process top failing classes
            top_failing_classes = [
                {
                    'class_name': bucket['key'],
                    'failure_count': bucket['doc_count'],
                    'percentage': round((bucket['doc_count'] / total_failures * 100), 1) if total_failures > 0 else 0
                }
                for bucket in class_aggs[:5]
            ]
            
            # Process repository breakdown
            repository_breakdown = [
                {
                    'repository': bucket['key'],
                    'failure_count': bucket['doc_count'],
                    'percentage': round((bucket['doc_count'] / total_failures * 100), 1) if total_failures > 0 else 0
                }
                for bucket in repo_aggs
            ]
            
            # Process recent failures
            recent_failures = []
            for test in test_results[:10]:
                source = test.get('_source', {})
                recent_failures.append({
                    'test_class': source.get('test_class', 'Unknown'),
                    'test_name': source.get('test_name', 'Unknown'),
                    'build_number': source.get('build_number', 'Unknown'),
                    'repository': source.get('repository', 'Unknown'),
                    'timestamp': source.get('build_start_time', 'Unknown')
                })
            
            return {
                'type': 'test_metrics',
                'metric_type': metric_type,
                'time_range': time_range,
                'project_filter': project_filter,
                'summary': {
                    'total_failures': total_failures,
                    'repositories_affected': len(repository_breakdown),
                    'top_failing_class': top_failing_classes[0]['class_name'] if top_failing_classes else 'None'
                },
                'top_failing_classes': top_failing_classes,
                'repository_breakdown': repository_breakdown,
                'recent_failures': recent_failures
            }
            
        except Exception as e:
            logger.error(f"Test metrics analysis failed: {e}")
            
            # Check if this is an authorization error
            if "AuthorizationException" in str(e) or "not authorized" in str(e):
                return {
                    'type': 'authorization_error',
                    'message': 'Cross-account OpenSearch access requires domain policy configuration',
                    'metric_type': metric_type,
                    'suggestion': 'Contact the OpenSearch domain administrator to add cross-account access policy'
                }
            
            return {'type': 'error', 'message': str(e), 'metric_type': metric_type}
    
    def get_build_metrics(self, metric_type: str = 'performance',
                         time_range: str = '7d',
                         branch_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze build metrics based on type.
        
        Args:
            metric_type: Type of build metric (performance, success_rate, pipeline)
            time_range: Time range for analysis
            branch_filter: Filter by specific branch or environment
            
        Returns:
            Structured build metrics data
        """
        try:
            # Use release data as build status proxy
            results = self.opensearch_client.query_release_status(
                component=branch_filter
            )
            
            builds = []
            active_builds = 0
            pending_builds = 0
            
            for release in results['hits']['hits']:
                source = release.get('_source', {})
                
                # Determine build status
                has_issue = source.get('release_issue_exists', False)
                status = 'Active' if has_issue else 'Pending'
                
                if status == 'Active':
                    active_builds += 1
                else:
                    pending_builds += 1
                
                builds.append({
                    'version': source.get('version', 'Unknown'),
                    'component': source.get('component', 'Unknown'),
                    'repository': source.get('repository', 'Unknown'),
                    'status': status,
                    'owners': source.get('release_owners', []),
                    'date': source.get('current_date', 'Unknown'),
                    'issue_url': source.get('release_issue', '')
                })
            
            total_builds = len(builds)
            success_rate = round((active_builds / total_builds * 100), 1) if total_builds > 0 else 0
            
            return {
                'type': 'build_metrics',
                'metric_type': metric_type,
                'time_range': time_range,
                'branch_filter': branch_filter,
                'summary': {
                    'total_builds': total_builds,
                    'active_builds': active_builds,
                    'pending_builds': pending_builds,
                    'success_rate': success_rate
                },
                'builds': builds[:10],  # Limit for response size
                'performance_insights': {
                    'most_active_component': self._get_most_active_component(builds),
                    'components_count': len(set(b['component'] for b in builds))
                }
            }
            
        except Exception as e:
            logger.error(f"Build metrics analysis failed: {e}")
            return {'type': 'error', 'message': str(e), 'metric_type': metric_type}
    
    def get_release_metrics(self, metric_type: str = 'frequency',
                           time_range: str = '30d',
                           environment_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze release metrics based on type.
        
        Args:
            metric_type: Type of release metric (frequency, success_rate, quality)
            time_range: Time range for analysis
            environment_filter: Filter by deployment environment
            
        Returns:
            Structured release metrics data
        """
        try:
            results = self.opensearch_client.query_release_status(
                component=environment_filter
            )
            
            releases = []
            versions = {}
            ready_components = 0
            total_components = 0
            
            for release in results['hits']['hits']:
                source = release.get('_source', {})
                
                version = source.get('version', 'Unknown')
                component = source.get('component', 'Unknown')
                is_ready = source.get('release_issue_exists', False)
                
                # Track version readiness
                if version not in versions:
                    versions[version] = {'ready': 0, 'total': 0, 'components': []}
                
                versions[version]['total'] += 1
                if is_ready:
                    versions[version]['ready'] += 1
                    ready_components += 1
                
                versions[version]['components'].append(component)
                total_components += 1
                
                releases.append({
                    'version': version,
                    'component': component,
                    'repository': source.get('repository', 'Unknown'),
                    'status': 'Ready' if is_ready else 'Pending',
                    'owners': source.get('release_owners', []),
                    'date': source.get('current_date', 'Unknown'),
                    'issue_url': source.get('release_issue', '')
                })
            
            # Calculate version readiness
            version_readiness = []
            for version, data in versions.items():
                readiness_pct = round((data['ready'] / data['total'] * 100), 1) if data['total'] > 0 else 0
                version_readiness.append({
                    'version': version,
                    'total_components': data['total'],
                    'ready_components': data['ready'],
                    'readiness_percentage': readiness_pct,
                    'status': 'Release Ready' if readiness_pct == 100 else f'{readiness_pct}% Ready'
                })
            
            overall_readiness = round((ready_components / total_components * 100), 1) if total_components > 0 else 0
            
            return {
                'type': 'release_metrics',
                'metric_type': metric_type,
                'time_range': time_range,
                'environment_filter': environment_filter,
                'summary': {
                    'total_releases': len(releases),
                    'ready_components': ready_components,
                    'total_components': total_components,
                    'overall_readiness': overall_readiness,
                    'versions_tracked': len(versions)
                },
                'version_readiness': sorted(version_readiness, key=lambda x: x['readiness_percentage'], reverse=True),
                'recent_releases': releases[:10]
            }
            
        except Exception as e:
            logger.error(f"Release metrics analysis failed: {e}")
            return {'type': 'error', 'message': str(e), 'metric_type': metric_type}
    
    def get_deployment_metrics(self, metric_type: str = 'performance',
                              time_range: str = '7d',
                              service_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze deployment metrics based on type.
        
        Args:
            metric_type: Type of deployment metric (performance, infrastructure, health)
            time_range: Time range for analysis
            service_filter: Filter by specific service or component
            
        Returns:
            Structured deployment metrics data
        """
        try:
            # Use release data as deployment proxy
            results = self.opensearch_client.query_release_status(
                component=service_filter
            )
            
            deployments = []
            services = {}
            active_deployments = 0
            
            for deployment in results['hits']['hits']:
                source = deployment.get('_source', {})
                
                component = source.get('component', 'Unknown')
                version = source.get('version', 'Unknown')
                is_active = source.get('release_issue_exists', False)
                
                # Track service deployment status
                if component not in services:
                    services[component] = {'versions': [], 'active': 0, 'total': 0}
                
                services[component]['versions'].append(version)
                services[component]['total'] += 1
                if is_active:
                    services[component]['active'] += 1
                    active_deployments += 1
                
                deployments.append({
                    'service': component,
                    'version': version,
                    'repository': source.get('repository', 'Unknown'),
                    'status': 'Active' if is_active else 'Pending',
                    'environment': 'production',  # Default for this data
                    'owners': source.get('release_owners', []),
                    'date': source.get('current_date', 'Unknown')
                })
            
            # Calculate service health
            service_health = []
            for service, data in services.items():
                health_pct = round((data['active'] / data['total'] * 100), 1) if data['total'] > 0 else 0
                service_health.append({
                    'service': service,
                    'total_deployments': data['total'],
                    'active_deployments': data['active'],
                    'health_percentage': health_pct,
                    'unique_versions': len(set(data['versions'])),
                    'status': 'Healthy' if health_pct >= 80 else 'Needs Attention'
                })
            
            total_deployments = len(deployments)
            overall_health = round((active_deployments / total_deployments * 100), 1) if total_deployments > 0 else 0
            
            return {
                'type': 'deployment_metrics',
                'metric_type': metric_type,
                'time_range': time_range,
                'service_filter': service_filter,
                'summary': {
                    'total_deployments': total_deployments,
                    'active_deployments': active_deployments,
                    'overall_health': overall_health,
                    'services_monitored': len(services)
                },
                'service_health': sorted(service_health, key=lambda x: x['health_percentage'], reverse=True),
                'recent_deployments': deployments[:10]
            }
            
        except Exception as e:
            logger.error(f"Deployment metrics analysis failed: {e}")
            return {'type': 'error', 'message': str(e), 'metric_type': metric_type}
    
    def _get_most_active_component(self, builds: List[Dict[str, Any]]) -> str:
        """Get the most active component from builds list."""
        if not builds:
            return 'None'
        
        component_counts = {}
        for build in builds:
            component = build.get('component', 'Unknown')
            component_counts[component] = component_counts.get(component, 0) + 1
        
        return max(component_counts.items(), key=lambda x: x[1])[0] if component_counts else 'None'