# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the metrics agent definition.

Covers the action-group function schema (metrics plus the release-readiness actions),
Lambda configuration and env passthrough, monitoring patterns, secrets, and the
instruction text that decides which function is authoritative for what.
"""

from agents.metrics import MetricsAgent
from agents.metrics.iam_policies import get_policies

LAMBDA_ARN = 'arn:aws:lambda:us-east-1:123456789012:function:oscar-metrics-dev'
RELEASE_ENV_KEYS = (
    'RELEASE_AGENTIC_PIPELINE',
    'RELEASE_STATE_INDEX',
    'RELEASE_SCHEDULE_INDEX',
)


def _functions():
    groups = MetricsAgent().get_action_groups(LAMBDA_ARN)
    assert len(groups) == 1
    return {f.name: f for f in groups[0].function_schema.functions}


class TestAgentIdentity:

    def test_name_and_collaborator(self):
        agent = MetricsAgent()
        assert agent.name == 'metrics'
        assert agent.get_collaborator_name() == 'Metrics-Specialist'

    def test_available_to_both_supervisors(self):
        assert MetricsAgent().get_access_level() == 'both'

    def test_uses_knowledge_base(self):
        assert MetricsAgent().uses_knowledge_base() is True

    def test_declares_its_own_secret(self):
        secrets = MetricsAgent().get_secrets()
        assert [s.env_var for s in secrets] == ['METRICS_SECRET_NAME']
        assert secrets[0].name_suffix == 'env'


class TestActionGroup:

    def test_action_group_is_wired_to_the_lambda(self):
        group = MetricsAgent().get_action_groups(LAMBDA_ARN)[0]
        assert group.action_group_name == 'metricsActionGroup'
        assert group.action_group_state == 'ENABLED'
        assert group.action_group_executor.lambda_ == LAMBDA_ARN

    def test_all_functions_present(self):
        assert set(_functions()) == {
            'query_metrics',
            'get_release_status',
            'get_release_window',
            'list_active_releases',
            'query_release_state',
        }

    def test_query_metrics_parameters(self):
        params = _functions()['query_metrics'].parameters
        assert params['query'].required is True
        assert params['version'].required is True
        assert params['memory_id'].required is False

    def test_status_and_window_take_only_a_required_version(self):
        functions = _functions()
        for name in ('get_release_status', 'get_release_window'):
            params = functions[name].parameters
            assert set(params) == {'version'}
            assert params['version'].required is True

    def test_query_release_state_parameters(self):
        params = _functions()['query_release_state'].parameters
        assert params['query'].required is True
        assert params['version'].required is False
        assert params['scope'].required is False
        assert 'schedule' in params['scope'].description

    def test_list_active_releases_takes_no_parameters(self):
        assert _functions()['list_active_releases'].parameters == {}

    def test_query_release_state_defers_verdict_and_dates(self):
        # The free-form action must not be used to derive a verdict or a date.
        description = _functions()['query_release_state'].description
        assert 'get_release_status' in description
        assert 'get_release_window' in description


class TestLambdaConfig:

    def test_lambda_entry_and_vpc(self):
        config = MetricsAgent().get_lambda_config()
        assert config.entry == 'agents/metrics/lambda'
        assert config.needs_vpc is True

    def test_vpc_managed_policy_attached(self):
        assert 'service-role/AWSLambdaVPCAccessExecutionRole' in \
            MetricsAgent().get_managed_policies()

    def test_release_env_keys_are_passed_through(self, monkeypatch):
        for key in RELEASE_ENV_KEYS:
            monkeypatch.setenv(key, f'value-for-{key}')
        env = MetricsAgent().get_lambda_config().environment_variables
        for key in RELEASE_ENV_KEYS:
            assert env[key] == f'value-for-{key}'

    def test_release_env_keys_are_optional(self, monkeypatch):
        # config.py holds defaults, so an unset variable must simply be omitted.
        for key in RELEASE_ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        env = MetricsAgent().get_lambda_config().environment_variables
        assert not [key for key in RELEASE_ENV_KEYS if key in env]

    def test_metrics_agentic_pipeline_still_passed_through(self, monkeypatch):
        monkeypatch.setenv('AGENTIC_PIPELINE', 'metrics-agentic-pipeline')
        env = MetricsAgent().get_lambda_config().environment_variables
        assert env['AGENTIC_PIPELINE'] == 'metrics-agentic-pipeline'


class TestMonitoring:

    def test_release_query_failures_are_monitored(self):
        patterns = {m.pattern for m in MetricsAgent().get_monitoring_config()}
        assert 'RELEASE_STATE_QUERY_FAILED' in patterns
        assert 'RELEASE_SCHEDULE_QUERY_FAILED' in patterns

    def test_existing_agentic_and_connectivity_alarms_kept(self):
        patterns = {m.pattern for m in MetricsAgent().get_monitoring_config()}
        assert {'AGENTIC_SEARCH_FAILED', 'OPENSEARCH_CONNECTION_FAILED',
                'CROSS_ACCOUNT_ROLE_FAILED'} <= patterns


class TestIamPolicies:

    def test_cross_account_assume_role_when_configured(self, monkeypatch):
        monkeypatch.setenv('METRICS_CROSS_ACCOUNT_ROLE_ARN',
                           'arn:aws:iam::123456789012:role/OpenSearchOscarAccessRole')
        sids = [p.sid for p in get_policies('123456789012', 'us-east-1', 'dev')]
        assert 'CrossAccountOpenSearchAssumeRole' in sids

    def test_no_assume_role_policy_without_the_arn(self, monkeypatch):
        monkeypatch.delenv('METRICS_CROSS_ACCOUNT_ROLE_ARN', raising=False)
        sids = [p.sid for p in get_policies('123456789012', 'us-east-1', 'dev')]
        assert 'CrossAccountOpenSearchAssumeRole' not in sids


class TestInstructions:

    def test_release_functions_are_documented(self):
        instruction = MetricsAgent().get_agent_instruction()
        for name in ('get_release_status', 'get_release_window', 'query_release_state'):
            assert name in instruction

    def test_verdict_may_not_be_invented(self):
        assert 'NEVER infer, estimate, or invent a verdict' in \
            MetricsAgent().get_agent_instruction()

    def test_release_metrics_index_no_longer_claims_to_hold_dates(self):
        # The earlier wording advertised release-date tracking this index cannot back.
        assert 'This index has NO release dates and NO overall verdict' in \
            MetricsAgent().get_agent_instruction()

    def test_collaborator_instruction_advertises_release_readiness(self):
        instruction = MetricsAgent().get_collaborator_instruction()
        assert 'red/yellow/green' in instruction
        assert 'release schedule' in instruction
