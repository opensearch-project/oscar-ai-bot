# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Property-based tests for tickets_query_builder.py using Hypothesis.

These tests verify universal correctness properties of the tickets DSL query
builder module across many randomly generated inputs.
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

# Path to the real lambda module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'agents', 'security-advisories', 'lambda',
)


def _load_tickets_query_builder():
    """Import tickets_query_builder with mocked aws_utils and config."""
    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)

    mock_aws_utils = MagicMock()
    mock_config_module = MagicMock()

    with patch.dict('sys.modules', {
        'aws_utils': mock_aws_utils,
        'config': mock_config_module,
    }):
        spec = importlib.util.spec_from_file_location(
            'tickets_query_builder', os.path.join(_LAMBDA_PATH, 'tickets_query_builder.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


# Load the module once for all tests
_mod = _load_tickets_query_builder()
build_tickets_query = _mod.build_tickets_query


# ---------------------------------------------------------------------------
# Feature: ticket-query, Property 1: Query structure invariant
# ---------------------------------------------------------------------------


class TestQueryStructureInvariant:
    """Property 1: Query structure invariant — status filter and sort always present.

    For any combination of cve_id, project_name, and branch (present or absent,
    with any string value), the DSL query body produced by build_tickets_query
    SHALL always contain:
    - A term filter {"term": {"status": "Assigned"}} in the filter clause
    - A sort clause [{"timestamp.created": {"order": "desc"}}]
    - A _source field of ["ticketId"]
    - A size of 1000
    - When cve_id is truthy: {"term": {"cveId": cve_id}} in filters
    - When project_name is truthy: {"term": {"projectName": project_name}} in filters
    - When branch is truthy: {"term": {"branches": branch}} in filters

    **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 1.1, 2.1, 8.1**
    """

    @given(
        cve_id=st.one_of(st.none(), st.text()),
        project_name=st.one_of(st.none(), st.text()),
        branch=st.one_of(st.none(), st.text()),
    )
    @settings(max_examples=100)
    def test_status_filter_always_present(self, cve_id, project_name, branch):
        """The mandatory status filter is always present in the query.

        **Validates: Requirements 4.1**
        """
        query = build_tickets_query(cve_id=cve_id, project_name=project_name, branch=branch)
        filters = query['query']['bool']['filter']
        assert {'term': {'status': 'Assigned'}} in filters, (
            f'Status filter missing for inputs cve_id={cve_id!r}, '
            f'project_name={project_name!r}, branch={branch!r}'
        )

    @given(
        cve_id=st.one_of(st.none(), st.text()),
        project_name=st.one_of(st.none(), st.text()),
        branch=st.one_of(st.none(), st.text()),
    )
    @settings(max_examples=100)
    def test_sort_always_present(self, cve_id, project_name, branch):
        """The sort clause is always present in the query.

        **Validates: Requirements 4.7**
        """
        query = build_tickets_query(cve_id=cve_id, project_name=project_name, branch=branch)
        assert query['sort'] == [{'timestamp.created': {'order': 'desc'}}], (
            f'Sort clause incorrect for inputs cve_id={cve_id!r}, '
            f'project_name={project_name!r}, branch={branch!r}'
        )

    @given(
        cve_id=st.one_of(st.none(), st.text()),
        project_name=st.one_of(st.none(), st.text()),
        branch=st.one_of(st.none(), st.text()),
    )
    @settings(max_examples=100)
    def test_source_always_ticket_id_only(self, cve_id, project_name, branch):
        """The _source field is always ["ticketId"].

        **Validates: Requirements 4.6**
        """
        query = build_tickets_query(cve_id=cve_id, project_name=project_name, branch=branch)
        assert query['_source'] == ['ticketId'], (
            f'_source incorrect for inputs cve_id={cve_id!r}, '
            f'project_name={project_name!r}, branch={branch!r}'
        )

    @given(
        cve_id=st.one_of(st.none(), st.text()),
        project_name=st.one_of(st.none(), st.text()),
        branch=st.one_of(st.none(), st.text()),
    )
    @settings(max_examples=100)
    def test_size_correct(self, cve_id, project_name, branch):
        """Size is 1 when cve_id is truthy (most recent ticket), 1000 otherwise.

        **Validates: Requirements 4.1**
        """
        query = build_tickets_query(cve_id=cve_id, project_name=project_name, branch=branch)
        expected_size = 1 if cve_id else 1000
        assert query['size'] == expected_size, (
            f'Size incorrect for inputs cve_id={cve_id!r}, '
            f'project_name={project_name!r}, branch={branch!r}'
        )

    @given(
        cve_id=st.one_of(st.none(), st.text()),
        project_name=st.one_of(st.none(), st.text()),
        branch=st.one_of(st.none(), st.text()),
    )
    @settings(max_examples=100)
    def test_conditional_filters_present_when_truthy(self, cve_id, project_name, branch):
        """Conditional term filters are present when their parameter is truthy.

        **Validates: Requirements 4.2, 4.3, 4.4, 1.1, 2.1, 8.1**
        """
        query = build_tickets_query(cve_id=cve_id, project_name=project_name, branch=branch)
        filters = query['query']['bool']['filter']

        if cve_id:
            # cve_id uses a bool/should to match either cveId or cveIds.keyword
            expected_cve_filter = {
                'bool': {
                    'should': [
                        {'term': {'cveId': cve_id}},
                        {'term': {'cveIds.keyword': cve_id}},
                    ],
                    'minimum_should_match': 1,
                },
            }
            assert expected_cve_filter in filters, (
                f'cveId bool/should filter missing when cve_id={cve_id!r}'
            )

        if project_name:
            assert {'term': {'projectName': project_name}} in filters, (
                f'projectName filter missing when project_name={project_name!r}'
            )

        if branch:
            assert {'term': {'branches': branch}} in filters, (
                f'branches filter missing when branch={branch!r}'
            )

    @given(
        cve_id=st.one_of(st.none(), st.text()),
        project_name=st.one_of(st.none(), st.text()),
        branch=st.one_of(st.none(), st.text()),
    )
    @settings(max_examples=100)
    def test_no_must_clause_present(self, cve_id, project_name, branch):
        """The query never contains a must clause — bool/filter is sufficient.

        **Validates: Requirements 4.5**
        """
        query = build_tickets_query(cve_id=cve_id, project_name=project_name, branch=branch)
        assert 'must' not in query['query']['bool'], (
            'must clause should not be present; bool/filter alone handles all cases'
        )
