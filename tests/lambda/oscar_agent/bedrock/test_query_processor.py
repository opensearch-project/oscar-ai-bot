"""Tests for QueryProcessor saw_confirmation_in_trace passthrough."""

from unittest.mock import Mock

import pytest
from bedrock.query_processor import QueryProcessor


@pytest.fixture
def qp():
    agent = Mock()
    eh = Mock()
    return QueryProcessor(agent, eh), agent, eh


class TestProcessQuery:

    def test_session_with_context(self, qp):
        proc, agent, _ = qp
        agent.invoke_agent.return_value = ('r', 's1', True)
        _, _, saw = proc.process_query('q', True, session_id='s', context_summary='c')
        assert saw is True

    def test_session_without_context(self, qp):
        proc, agent, _ = qp
        agent.invoke_agent.return_value = ('r', 's1', False)
        _, _, saw = proc.process_query('q', True, session_id='s', context_summary='')
        assert saw is False

    def test_fallback_to_context_on_session_failure(self, qp):
        proc, agent, _ = qp
        agent.invoke_agent.side_effect = [Exception(), ('r', 's2', True)]
        _, _, saw = proc.process_query('q', True, session_id='s', context_summary='c')
        assert saw is True

    def test_fallback_to_plain_on_all_prior_failures(self, qp):
        proc, agent, _ = qp
        agent.invoke_agent.side_effect = [Exception(), Exception(), ('r', 's3', False)]
        _, _, saw = proc.process_query('q', True, session_id='s', context_summary='c')
        assert saw is False

    def test_all_fail_returns_false(self, qp):
        proc, agent, eh = qp
        agent.invoke_agent.side_effect = Exception()
        eh.handle_agent_error.return_value = 'err'
        _, _, saw = proc.process_query('q', True, session_id='s', context_summary='c')
        assert saw is False

    def test_no_session_no_context(self, qp):
        proc, agent, _ = qp
        agent.invoke_agent.return_value = ('r', 's1', True)
        _, _, saw = proc.process_query('q', True)
        assert saw is True

    def test_no_session_with_context(self, qp):
        proc, agent, _ = qp
        agent.invoke_agent.return_value = ('r', 's1', False)
        _, _, saw = proc.process_query('q', True, context_summary='c')
        assert saw is False
