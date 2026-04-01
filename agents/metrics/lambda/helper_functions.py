#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Pre-agentic fallback utilities for component resolution and RC build mapping.
Not used by the current agentic search flow. Uncomment if reverting to direct DSL queries.
"""

# import logging
# from typing import Any, Dict, List, Optional
#
# from aws_utils import opensearch_request
# from config import config
#
# logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)
#
#
# def resolve_components_from_build_numbers(version: str, build_numbers: List[str]) -> Dict[str, List[str]]:
#     """Resolve components from build numbers."""
#     query_body = {
#         "size": config.large_query_size,
#         "_source": ["component", "distribution_build_number"],
#         "query": {
#             "bool": {
#                 "must": [
#                     {"match_phrase": {"version": version}},
#                     {"terms": {"distribution_build_number": [str(bn) for bn in build_numbers]}}
#                 ]
#             }
#         }
#     }
#
#     result = opensearch_request('GET', f'/{config.get_build_results_index_pattern()}/_search', query_body)
#
#     build_component_map = {}
#     for hit in result.get('hits', {}).get('hits', []):
#         source = hit['_source']
#         build_num = source['distribution_build_number']
#         component = source['component']
#
#         if build_num not in build_component_map:
#             build_component_map[build_num] = []
#         if component not in build_component_map[build_num]:
#             build_component_map[build_num].append(component)
#
#     return build_component_map
#
#

# def get_rc_distribution_build_number(version: str, rc_number: int, component_name: Optional[str] = None):
#     """Get build numbers for RC."""
#     query_body = {
#         "_source": ["distribution_build_number", "component"],
#         "sort": [{"distribution_build_number": {"order": "desc"}}],
#         "size": config.large_query_size,
#         "query": {
#             "bool": {
#                 "must": [
#                     {"match_phrase": {"version": version}},
#                     {"match_phrase": {"rc_number": str(rc_number)}}
#                 ]
#             }
#         }
#     }
#
#     if component_name:
#         query_body["query"]["bool"]["must"].append(
#             {"match_phrase": {"component": component_name}}
#         )
#
#     result = opensearch_request('GET', f'/{config.get_integration_test_index_pattern()}/_search', query_body)
#     hits = result.get('hits', {}).get('hits', [])
#
#     if not hits:
#         return [] if component_name else {}
#
#     if component_name:
#         build_numbers = []
#         for hit in hits:
#             build_num = hit['_source'].get('distribution_build_number')
#             if build_num and build_num not in build_numbers:
#                 build_numbers.append(build_num)
#         return build_numbers
#
#     component_builds = {}
#     for hit in hits:
#         source = hit['_source']
#         component = source.get('component')
#         build_num = source.get('distribution_build_number')
#
#         if component and build_num:
#             if component not in component_builds:
#                 component_builds[component] = []
#             if build_num not in component_builds[component]:
#                 component_builds[component].append(build_num)
#
#     return component_builds
#
#
# def handle_component_resolution(params: Dict[str, Any]) -> Dict[str, Any]:
#     """Handle resolve_components_from_builds requests."""
#     try:
#         version = params.get('version')
#         build_numbers = params.get('build_numbers', [])
#
#         if not version:
#             return {'error': 'Version is required for component resolution'}
#         if not build_numbers:
#             return {'error': 'Build numbers are required for component resolution'}
#
#         if isinstance(build_numbers, str):
#             build_numbers = [item.strip() for item in build_numbers.split(',') if item.strip()]
#
#         logger.info(f"Resolving components for version {version}, build numbers: {build_numbers}")
#         component_mapping = resolve_components_from_build_numbers(version, build_numbers)
#
#         return {
#             'version': version,
#             'build_numbers': build_numbers,
#             'component_mapping': component_mapping,
#             'total_builds': len(component_mapping),
#             'total_components': sum(len(components) for components in component_mapping.values())
#         }
#     except Exception as e:
#         logger.error(f"Component resolution failed: {e}")
#         return {'error': str(e), 'type': 'component_resolution_error'}
#
#
# def handle_rc_build_mapping(params: Dict[str, Any]) -> Dict[str, Any]:
#     """Handle get_rc_build_mapping requests."""
#     try:
#         version = params.get('version')
#         rc_numbers = params.get('rc_numbers', [])
#         component_name = params.get('component_name')
#
#         if not version:
#             return {'error': 'Version is required for RC build mapping'}
#         if not rc_numbers:
#             return {'error': 'RC numbers are required for RC build mapping'}
#
#         if isinstance(rc_numbers, str):
#             rc_numbers = [item.strip() for item in rc_numbers.split(',') if item.strip()]
#
#         try:
#             rc_numbers = [int(rc) for rc in rc_numbers]
#         except ValueError as e:
#             return {'error': f'Invalid RC number format: {e}'}
#
#         logger.info(f"Getting RC build mapping for version {version}, RC numbers: {rc_numbers}, component: {component_name}")
#
#         rc_mappings = {}
#         for rc_number in rc_numbers:
#             rc_mappings[str(rc_number)] = get_rc_distribution_build_number(version, rc_number, component_name)
#
#         return {
#             'version': version,
#             'rc_numbers': rc_numbers,
#             'component_name': component_name,
#             'rc_mappings': rc_mappings
#         }
#     except Exception as e:
#         logger.error(f"RC build mapping failed: {e}")
#         return {'error': str(e), 'type': 'rc_mapping_error'}
