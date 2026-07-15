# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Property-based and unit tests for tickets_handler.py.

These tests verify universal correctness properties of the tickets handler
module across many randomly generated inputs, plus example-based tests for
specific scenarios and error handling.

**Validates Property 2: Response field filtering**
**Validates Property 3: Result count consistency**
**Validates Property 4: Project extraction from collapsed hits**
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

# Path to the real lambda module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)


def _load_tickets_handler(mock_opensearch_request=None):
    """Import tickets_handler with mocked dependencies.

    Args:
        mock_opensearch_request: A MagicMock or callable to use as
            aws_utils.opensearch_request. If None, defaults to returning
            empty hits.

    Returns:
        Tuple of (module, mock_aws_utils, mock_tickets_query_builder).
    """
    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)

    mock_aws_utils = MagicMock()
    if mock_opensearch_request is not None:
        mock_aws_utils.opensearch_request = mock_opensearch_request
    else:
        mock_aws_utils.opensearch_request = MagicMock(return_value={'hits': {'hits': []}})

    mock_config = MagicMock()

    mock_tickets_query_builder = MagicMock()
    mock_tickets_query_builder.build_tickets_query = MagicMock(return_value={})
    mock_tickets_query_builder.build_list_projects_query = MagicMock(return_value={})

    # Load the real query_utils module so error_response/connection_error work
    query_utils_spec = importlib.util.spec_from_file_location(
        'query_utils',
        os.path.join(_LAMBDA_PATH, 'query_utils.py'),
    )
    query_utils_mod = importlib.util.module_from_spec(query_utils_spec)
    query_utils_spec.loader.exec_module(query_utils_mod)

    with patch.dict('sys.modules', {
        'aws_utils': mock_aws_utils,
        'config': mock_config,
        'query_utils': query_utils_mod,
        'tickets_query_builder': mock_tickets_query_builder,
    }):
        spec = importlib.util.spec_from_file_location(
            'sa_tickets_handler',
            os.path.join(_LAMBDA_PATH, 'tickets_handler.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mock_aws_utils, mock_tickets_query_builder


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Strategy for extra fields that might appear in _source documents
_extra_field_keys = st.sampled_from([
    'cveId', 'projectName', 'branches', 'status', 'severity',
    'createdAt', 'timestamp',
])

_extra_field_values = st.one_of(
    st.text(min_size=0, max_size=50),
    st.lists(st.text(min_size=1, max_size=20), max_size=5),
    st.integers(),
    st.booleans(),
)

# Strategy for a _source dict: always has ticketId plus random extra fields
_ticket_source = st.builds(
    lambda ticket_id, extras: {'ticketId': ticket_id, **extras},
    ticket_id=st.text(min_size=1, max_size=30),
    extras=st.dictionaries(
        keys=_extra_field_keys,
        values=_extra_field_values,
        min_size=0,
        max_size=7,
    ),
)

# Strategy for a list of OpenSearch hit dicts
_hits_strategy = st.lists(
    _ticket_source.map(lambda source: {'_source': source}),
    min_size=0,
    max_size=20,
)


# ---------------------------------------------------------------------------
# Feature: ticket-query, Property 2: Response field filtering
# ---------------------------------------------------------------------------


class TestResponseFieldFiltering:
    """Property 2: Response field filtering — only permitted fields in results.

    For any set of ticket documents returned from OpenSearch (containing
    arbitrary combinations of fields like ticketId, cveId, projectName,
    branches, status, severity, createdAt, timestamp), the handler SHALL
    produce result objects containing only the key `ticketId`. No other
    fields from the source document SHALL appear in the response.

    **Validates: Requirements 1.2, 2.2, 5.4, 8.2**
    """

    @given(hits=_hits_strategy)
    @settings(max_examples=100)
    def test_only_ticket_id_in_results(self, hits):
        """Regardless of extra fields in _source, only ticketId appears in results."""
        opensearch_response = {'hits': {'hits': hits}}

        mock_opensearch_request = MagicMock(return_value=opensearch_response)
        mod, _, _ = _load_tickets_handler(mock_opensearch_request=mock_opensearch_request)

        result = mod.handle_query_tickets({'cve_id': 'CVE-2024-0001'}, 'test-prop2')

        assert result['status'] == 'success'
        for entry in result['results']:
            assert set(entry.keys()) == {'ticketId', 'ticket_url'}, (
                f'Expected only "ticketId" and "ticket_url" keys but got keys: {set(entry.keys())}'
            )
            assert entry['ticket_url'] == f'https://t.corp.amazon.com/{entry["ticketId"]}', (
                f'ticket_url should be https://t.corp.amazon.com/{entry["ticketId"]}, '
                f'got {entry["ticket_url"]}'
            )


# ---------------------------------------------------------------------------
# Feature: ticket-query, Property 3: Result count consistency
# ---------------------------------------------------------------------------


class TestResultCountConsistency:
    """Property 3: Result count consistency.

    For any handler response with status "success", the result_count field
    SHALL always equal the length of the results array.

    **Validates: Requirements 5.2, 5.3**
    """

    @given(
        hits=st.lists(
            st.fixed_dictionaries({
                '_source': st.fixed_dictionaries({
                    'ticketId': st.text(min_size=1, max_size=20),
                }),
            }),
            min_size=0,
            max_size=50,
        ),
    )
    @settings(max_examples=100)
    def test_result_count_equals_results_length(self, hits):
        """result_count always equals len(results) for any number of hits.

        **Validates: Requirements 5.2, 5.3**
        """
        mock_opensearch_request = MagicMock(
            return_value={'hits': {'hits': hits}},
        )
        mod, _, _ = _load_tickets_handler(mock_opensearch_request=mock_opensearch_request)

        response = mod.handle_query_tickets({'cve_id': 'CVE-2024-0001'}, 'test-req')

        assert response['status'] == 'success'
        assert response['result_count'] == len(response['results'])

    @given(
        hits=st.lists(
            st.fixed_dictionaries({
                '_source': st.fixed_dictionaries({
                    'ticketId': st.text(min_size=1, max_size=20),
                }),
            }),
            min_size=0,
            max_size=0,
        ),
    )
    @settings(max_examples=100)
    def test_empty_results_has_zero_count(self, hits):
        """When results is empty, result_count is 0.

        **Validates: Requirements 5.2, 5.3**
        """
        mock_opensearch_request = MagicMock(
            return_value={'hits': {'hits': hits}},
        )
        mod, _, _ = _load_tickets_handler(mock_opensearch_request=mock_opensearch_request)

        response = mod.handle_query_tickets({'cve_id': 'CVE-2024-0001'}, 'test-req')

        assert response['status'] == 'success'
        assert response['result_count'] == 0
        assert response['results'] == []


# ---------------------------------------------------------------------------
# Feature: ticket-query, Property 4: Project extraction from collapsed hits
# ---------------------------------------------------------------------------


class TestProjectExtractionFromCollapsedHits:
    """Property 4: Project extraction from collapsed hits.

    For any list of OpenSearch hit documents containing _source.projectName
    values, the handle_list_ticket_projects handler SHALL extract exactly the
    set of projectName values — one per hit — producing a projects array whose
    elements match the input projectName values with no duplicates introduced
    by the handler itself.

    **Validates: Requirements 7.3, 7.4**
    """

    @given(project_names=st.lists(st.text(min_size=1), min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_extracted_projects_match_input_project_names(self, project_names):
        """Extracted projects match input projectName values exactly.

        **Validates: Requirements 7.3, 7.4**
        """
        generated_hits = [{"_source": {"projectName": name}} for name in project_names]

        mock_opensearch_request = MagicMock(
            return_value={"hits": {"hits": generated_hits}},
        )

        mod, _, _ = _load_tickets_handler(mock_opensearch_request=mock_opensearch_request)

        response = mod.handle_list_ticket_projects('test-req')

        assert response['projects'] == project_names, (
            f"Expected projects {project_names}, got {response['projects']}"
        )

    @given(project_names=st.lists(st.text(min_size=1), min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_no_duplicates_introduced_by_handler(self, project_names):
        """The handler does not introduce duplicates beyond what is in the input.

        **Validates: Requirements 7.3, 7.4**
        """
        generated_hits = [{"_source": {"projectName": name}} for name in project_names]

        mock_opensearch_request = MagicMock(
            return_value={"hits": {"hits": generated_hits}},
        )

        mod, _, _ = _load_tickets_handler(mock_opensearch_request=mock_opensearch_request)

        response = mod.handle_list_ticket_projects('test-req')

        assert len(response['projects']) == len(project_names), (
            f"Handler introduced duplicates: input had {len(project_names)} items, "
            f"output has {len(response['projects'])} items"
        )

        for project in response['projects']:
            assert project in project_names, (
                f"Handler introduced a value '{project}' not in the input"
            )


# ---------------------------------------------------------------------------
# Unit Tests: Example-based tests for tickets_handler
# Requirements: 1.3, 1.4, 2.3, 2.4, 5.2, 5.3, 7.6, 7.7
# ---------------------------------------------------------------------------


class TestQueryTicketsEmptyResults:
    """Test query_tickets returns correct response when no hits found.

    **Validates: Requirements 1.3, 5.2, 5.3**
    """

    def test_empty_results_response(self):
        """Empty hits returns success with result_count 0 and empty results."""
        mock_opensearch_request = MagicMock(return_value={'hits': {'hits': []}})
        mod, _, _ = _load_tickets_handler(mock_opensearch_request=mock_opensearch_request)

        result = mod.handle_query_tickets({'cve_id': 'CVE-2024-0001'}, 'req-123')

        assert result == {
            'status': 'success',
            'result_count': 0,
            'results': [],
        }


class TestQueryTicketsConnectionError:
    """Test query_tickets handles connection errors correctly.

    **Validates: Requirements 1.4, 2.4**
    """

    def test_connection_error_response(self):
        """ConnectionError produces a sanitized connection_error typed response."""
        mock_opensearch_request = MagicMock(
            side_effect=ConnectionError('socket timeout on 10.0.1.42:9200'),
        )
        mod, _, _ = _load_tickets_handler(mock_opensearch_request=mock_opensearch_request)

        result = mod.handle_query_tickets({'cve_id': 'CVE-2024-0001'}, 'req-123')

        assert result['status'] == 'error'
        assert result['type'] == 'connection_error'
        assert result['retryable'] is False
        assert 'message' in result
        # Sanitized message should NOT contain raw internal details
        assert '10.0.1.42' not in result['message']
        assert 'socket timeout' not in result['message']
        # Should contain the generic sanitized message
        assert 'OpenSearch cluster' in result['message']


class TestQueryTicketsOpenSearchError:
    """Test query_tickets handles OpenSearch errors correctly.

    **Validates: Requirements 1.4, 2.4**
    """

    def test_opensearch_error_response(self):
        """RuntimeError from opensearch_request produces an opensearch_error typed response."""
        mock_opensearch_request = MagicMock(
            side_effect=RuntimeError('OpenSearch request failed: 400 - Bad Request'),
        )
        mod, _, _ = _load_tickets_handler(mock_opensearch_request=mock_opensearch_request)

        result = mod.handle_query_tickets({'cve_id': 'CVE-2024-0001'}, 'req-123')

        assert result['status'] == 'error'
        assert result['type'] == 'opensearch_error'
        assert result['retryable'] is False
        assert 'message' in result
        assert 'OpenSearch request failed' in result['message']


class TestListTicketProjectsEmptyState:
    """Test list_ticket_projects returns correct response when no projects found.

    **Validates: Requirements 7.6**
    """

    def test_empty_projects_response(self):
        """Empty hits returns success with empty projects array."""
        mock_opensearch_request = MagicMock(return_value={'hits': {'hits': []}})
        mod, _, _ = _load_tickets_handler(mock_opensearch_request=mock_opensearch_request)

        result = mod.handle_list_ticket_projects('req-123')

        assert result == {
            'status': 'success',
            'projects': [],
        }


class TestListTicketProjectsConnectionError:
    """Test list_ticket_projects handles connection errors correctly.

    **Validates: Requirements 7.7**
    """

    def test_connection_error_response(self):
        """ConnectionError produces a sanitized connection_error typed response."""
        mock_opensearch_request = MagicMock(
            side_effect=ConnectionError('socket timeout on 10.0.1.42:9200'),
        )
        mod, _, _ = _load_tickets_handler(mock_opensearch_request=mock_opensearch_request)

        result = mod.handle_list_ticket_projects('req-123')

        assert result['status'] == 'error'
        assert result['type'] == 'connection_error'
        assert result['retryable'] is False
        assert 'message' in result
        # Sanitized message should NOT contain raw internal details
        assert '10.0.1.42' not in result['message']
        assert 'socket timeout' not in result['message']
        # Should contain the generic sanitized message
        assert 'OpenSearch cluster' in result['message']


class TestListTicketProjectsOpenSearchError:
    """Test list_ticket_projects handles OpenSearch errors correctly.

    **Validates: Requirements 7.7**
    """

    def test_opensearch_error_response(self):
        """RuntimeError from opensearch_request produces an opensearch_error typed response."""
        mock_opensearch_request = MagicMock(
            side_effect=RuntimeError('OpenSearch request failed: 500 - Internal Server Error'),
        )
        mod, _, _ = _load_tickets_handler(mock_opensearch_request=mock_opensearch_request)

        result = mod.handle_list_ticket_projects('req-123')

        assert result['status'] == 'error'
        assert result['type'] == 'opensearch_error'
        assert result['retryable'] is False
        assert 'message' in result
        assert 'OpenSearch request failed' in result['message']


class TestQueryTicketsWithResults:
    """Test query_tickets correctly extracts ticketId from hits.

    **Validates: Requirements 1.2, 2.2, 5.2**
    """

    def test_results_extracted_correctly(self):
        """Hits with ticketIds are extracted into results array."""
        opensearch_response = {
            'hits': {
                'hits': [
                    {'_source': {'ticketId': 'V123456'}},
                    {'_source': {'ticketId': 'V123457'}},
                    {'_source': {'ticketId': 'V123458'}},
                ],
            },
        }
        mock_opensearch_request = MagicMock(return_value=opensearch_response)
        mod, _, _ = _load_tickets_handler(mock_opensearch_request=mock_opensearch_request)

        result = mod.handle_query_tickets({'cve_id': 'CVE-2024-0001'}, 'req-123')

        assert result['status'] == 'success'
        assert result['result_count'] == 3
        assert result['results'] == [
            {'ticketId': 'V123456', 'ticket_url': 'https://t.corp.amazon.com/V123456'},
            {'ticketId': 'V123457', 'ticket_url': 'https://t.corp.amazon.com/V123457'},
            {'ticketId': 'V123458', 'ticket_url': 'https://t.corp.amazon.com/V123458'},
        ]
