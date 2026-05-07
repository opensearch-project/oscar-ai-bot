# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for security advisories agentic_search.py.

These tests verify query enhancement, agentic search execution,
DSL logging, error handling, and the stateless flow agent contract
(no memory_id).

**Validates Property 1: Query enhancement preserves all provided context**
"""

import importlib
import json
import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Path to the real agentic_search module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)


def _load_agentic_search():
    """Import agentic_search from security_advisories lambda, fresh each time."""
    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)

    spec = importlib.util.spec_from_file_location(
        'sa_agentic_search', os.path.join(_LAMBDA_PATH, 'agentic_search.py'),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# enhance_query tests
# ---------------------------------------------------------------------------


class TestEnhanceQueryPreservesOriginal:
    """Test that enhance_query preserves the original query text."""

    def test_original_query_present_in_result(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('Show me critical CVEs')
        assert 'Show me critical CVEs' in result

    def test_original_query_present_with_version(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('Show me critical CVEs', version='2.19.6')
        assert 'Show me critical CVEs' in result

    def test_original_query_present_with_project_name(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('Show me critical CVEs', project_name='OpenSearch')
        assert 'Show me critical CVEs' in result

    def test_original_query_present_with_all_params(self):
        mod = _load_agentic_search()
        result = mod.enhance_query(
            'Show me critical CVEs', version='2.19.6', project_name='OpenSearch',
        )
        assert 'Show me critical CVEs' in result


class TestEnhanceQueryAppendsVersion:
    """Test that enhance_query appends version when provided."""

    def test_version_appended(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('List CVEs', version='2.19.6')
        assert '2.19.6' in result

    def test_version_not_present_when_none(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('List CVEs', version=None)
        assert result == 'List CVEs'

    def test_version_not_present_when_empty(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('List CVEs', version='')
        assert result == 'List CVEs'


class TestEnhanceQueryAppendsProjectName:
    """Test that enhance_query appends project name when provided."""

    def test_project_name_appended(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('List CVEs', project_name='OpenSearch Dashboards')
        assert 'OpenSearch Dashboards' in result

    def test_project_name_not_present_when_none(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('List CVEs', project_name=None)
        assert result == 'List CVEs'

    def test_project_name_not_present_when_empty(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('List CVEs', project_name='')
        assert result == 'List CVEs'


class TestEnhanceQueryAllParamsAndMissing:
    """Test enhance_query with all params and with missing optional params.

    **Validates Property 1: Query enhancement preserves all provided context**
    """

    def test_all_params_present(self):
        mod = _load_agentic_search()
        result = mod.enhance_query(
            'Show critical CVEs', version='3.0.0', project_name='OpenSearch',
        )
        assert 'Show critical CVEs' in result
        assert '3.0.0' in result
        assert 'OpenSearch' in result

    def test_only_query(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('Show critical CVEs')
        assert result == 'Show critical CVEs'

    def test_query_and_version_only(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('Show critical CVEs', version='2.19.6')
        assert 'Show critical CVEs' in result
        assert '2.19.6' in result

    def test_query_and_project_name_only(self):
        mod = _load_agentic_search()
        result = mod.enhance_query('Show critical CVEs', project_name='OpenSearch')
        assert 'Show critical CVEs' in result
        assert 'OpenSearch' in result

    def test_none_optionals_same_as_omitted(self):
        mod = _load_agentic_search()
        result_none = mod.enhance_query('query', version=None, project_name=None)
        result_omit = mod.enhance_query('query')
        assert result_none == result_omit


# ---------------------------------------------------------------------------
# agentic_search tests
# ---------------------------------------------------------------------------


class TestAgenticSearchLogsDSL:
    """Test that agentic_search logs generated DSL from ext.dsl_query."""

    def test_logs_dsl_query_when_present(self, caplog):
        _load_agentic_search()

        dsl = {'bool': {'filter': [{'term': {'project.name': 'OpenSearch'}}]}}
        mock_response = {
            'hits': {'total': {'value': 1}, 'hits': []},
            'ext': {'dsl_query': dsl},
        }

        with patch.dict('sys.modules', {'aws_utils': MagicMock()}):
            # Re-import to pick up the mocked aws_utils
            spec = importlib.util.spec_from_file_location(
                'sa_agentic_search_test', os.path.join(_LAMBDA_PATH, 'agentic_search.py'),
            )
            test_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(test_mod)

            with patch.object(
                sys.modules['aws_utils'], 'opensearch_request', return_value=mock_response,
            ):
                with caplog.at_level(logging.INFO):
                    test_mod.agentic_search('oscar-agentic-pipeline', 'test query')

                assert any(
                    'Generated DSL' in r.message and 'project.name' in r.message
                    for r in caplog.records
                )

    def test_no_dsl_log_when_ext_missing(self, caplog):
        _load_agentic_search()

        mock_response = {
            'hits': {'total': {'value': 0}, 'hits': []},
        }

        with patch.dict('sys.modules', {'aws_utils': MagicMock()}):
            spec = importlib.util.spec_from_file_location(
                'sa_agentic_search_test2', os.path.join(_LAMBDA_PATH, 'agentic_search.py'),
            )
            test_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(test_mod)

            with patch.object(
                sys.modules['aws_utils'], 'opensearch_request', return_value=mock_response,
            ):
                with caplog.at_level(logging.INFO):
                    test_mod.agentic_search('oscar-agentic-pipeline', 'test query')

                assert not any(
                    'Generated DSL' in r.message for r in caplog.records
                )


class TestAgenticSearchErrorOnFailure:
    """Test AgenticSearchError raised on HTTP failure with status code."""

    def test_raises_agentic_search_error_on_failure(self):
        with patch.dict('sys.modules', {'aws_utils': MagicMock()}):
            spec = importlib.util.spec_from_file_location(
                'sa_agentic_search_err', os.path.join(_LAMBDA_PATH, 'agentic_search.py'),
            )
            test_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(test_mod)

            sys.modules['aws_utils'].opensearch_request.side_effect = Exception(
                'OpenSearch request failed: 500 - Internal Server Error',
            )

            with pytest.raises(test_mod.AgenticSearchError) as exc_info:
                test_mod.agentic_search('oscar-agentic-pipeline', 'test query')

            assert exc_info.value.status_code == 500

    def test_raises_agentic_search_error_without_status_code(self):
        with patch.dict('sys.modules', {'aws_utils': MagicMock()}):
            spec = importlib.util.spec_from_file_location(
                'sa_agentic_search_err2', os.path.join(_LAMBDA_PATH, 'agentic_search.py'),
            )
            test_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(test_mod)

            sys.modules['aws_utils'].opensearch_request.side_effect = ConnectionError(
                'Connection refused',
            )

            with pytest.raises(test_mod.AgenticSearchError) as exc_info:
                test_mod.agentic_search('oscar-agentic-pipeline', 'test query')

            assert exc_info.value.status_code is None

    def test_logs_agentic_search_failed_on_error(self, caplog):
        with patch.dict('sys.modules', {'aws_utils': MagicMock()}):
            spec = importlib.util.spec_from_file_location(
                'sa_agentic_search_err3', os.path.join(_LAMBDA_PATH, 'agentic_search.py'),
            )
            test_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(test_mod)

            sys.modules['aws_utils'].opensearch_request.side_effect = Exception(
                'OpenSearch request failed: 400 - Bad Request',
            )

            with caplog.at_level(logging.ERROR):
                with pytest.raises(test_mod.AgenticSearchError):
                    test_mod.agentic_search('oscar-agentic-pipeline', 'test query')

            assert any('SECURITY_ADVISORIES_AGENTIC_SEARCH_FAILED' in r.message for r in caplog.records)


class TestNoMemoryIdInRequest:
    """Test no memory_id is sent in the request body (flow agent is stateless)."""

    def test_request_body_has_no_memory_id(self):
        with patch.dict('sys.modules', {'aws_utils': MagicMock()}):
            spec = importlib.util.spec_from_file_location(
                'sa_agentic_search_nomem', os.path.join(_LAMBDA_PATH, 'agentic_search.py'),
            )
            test_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(test_mod)

            mock_response = {
                'hits': {'total': {'value': 0}, 'hits': []},
            }
            mock_os_request = sys.modules['aws_utils'].opensearch_request
            mock_os_request.return_value = mock_response

            test_mod.agentic_search('oscar-agentic-pipeline', 'test query')

            # Verify the body sent to opensearch_request
            call_args = mock_os_request.call_args
            body = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
            assert 'memory_id' not in json.dumps(body)

    def test_agentic_search_function_signature_has_no_memory_id(self):
        """Verify the function signature does not accept memory_id."""
        import inspect
        mod = _load_agentic_search()
        sig = inspect.signature(mod.agentic_search)
        assert 'memory_id' not in sig.parameters


class TestAgenticSearchErrorClass:
    """Test AgenticSearchError exception class."""

    def test_error_with_status_code(self):
        mod = _load_agentic_search()
        err = mod.AgenticSearchError('test error', status_code=503)
        assert str(err) == 'test error'
        assert err.status_code == 503

    def test_error_without_status_code(self):
        mod = _load_agentic_search()
        err = mod.AgenticSearchError('test error')
        assert str(err) == 'test error'
        assert err.status_code is None

    def test_error_is_exception(self):
        mod = _load_agentic_search()
        assert issubclass(mod.AgenticSearchError, Exception)
