#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""DSL Query Builder for Tickets Index Queries.

This module constructs OpenSearch Query DSL bodies for querying the tickets
index. It supports filtering by CVE identifier, project name, and branch,
and always applies a mandatory status filter for assigned tickets.

Functions:
    build_tickets_query: Construct a DSL query to find tickets by CVE, project, or branch.
    build_list_projects_query: Construct a DSL query to list unique projects with assigned tickets.
"""

import logging
from typing import Any, Dict, Optional

from query_utils import resolve_version_tag

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Default query size — matches the existing codebase configuration
_DEFAULT_QUERY_SIZE = 1000


def build_tickets_query(
    cve_id: Optional[str] = None,
    project_name: Optional[str] = None,
    branch: Optional[str] = None,
) -> Dict[str, Any]:
    """Build DSL query for the tickets index.

    Always includes:
    - term filter: {"status": "Assigned"}
    - sort: [{"timestamp.created": {"order": "desc"}}]
    - _source: ["ticketId"]
    - size: 1000

    Conditional filters added when parameters are provided:
    - If cve_id provided: adds bool/should matching either {"term": {"cveId": cve_id}}
      or {"term": {"cveIds.keyword": cve_id}}, and limits size to 1 (most recent ticket).
    - If project_name provided: adds {"term": {"projectName": project_name}}
    - If branch provided: resolves via resolve_version_tag, then adds {"term": {"branches": resolved_branch}}
    - If none provided: uses bool/filter with only the mandatory status filter

    Args:
        cve_id: Optional CVE identifier to filter tickets (e.g., "CVE-2026-27903").
        project_name: Optional project or component name to filter tickets.
        branch: Optional branch name to filter tickets (e.g., "origin/main").

    Returns:
        A dict representing the OpenSearch query body, ready for json.dumps().
    """
    filters = [{'term': {'status': 'Assigned'}}]

    if cve_id:
        filters.append({
            'bool': {
                'should': [
                    {'term': {'cveId': cve_id}},
                    {'term': {'cveIds.keyword': cve_id}},
                ],
                'minimum_should_match': 1,
            },
        })

    if project_name:
        filters.append({'term': {'projectName': project_name}})

    if branch:
        branch = resolve_version_tag(branch)
        filters.append({'term': {'branches': branch}})

    sort = [{'timestamp.created': {'order': 'desc'}}]
    size = 1 if cve_id else _DEFAULT_QUERY_SIZE

    query = {
        'size': size,
        '_source': ['ticketId'],
        'sort': sort,
        'query': {
            'bool': {
                'filter': filters,
            },
        },
    }

    logger.info(f'TICKETS_QUERY: Built query with {len(filters)} filter(s)')
    return query


def build_list_projects_query() -> Dict[str, Any]:
    """Build DSL query to list unique projects with assigned tickets.

    Uses:
    - match_all query
    - term filter: {"status": "Assigned"}
    - collapse on "projectName" field
    - _source: ["projectName"]
    - size: 1000

    Returns:
        A dict representing the OpenSearch query body, ready for json.dumps().
    """
    query = {
        'size': _DEFAULT_QUERY_SIZE,
        '_source': ['projectName'],
        'query': {
            'bool': {
                'must': {'match_all': {}},
                'filter': [
                    {'term': {'status': 'Assigned'}},
                ],
            },
        },
        'collapse': {'field': 'projectName'},
    }

    logger.info('TICKETS_QUERY: Built list_projects query')
    return query
