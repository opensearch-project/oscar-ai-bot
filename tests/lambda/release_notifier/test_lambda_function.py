# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the release notifier Lambda handler.

The notifier owns no verdict logic - it invokes the metrics Lambda and posts the result.
These tests pin the action-group envelope it speaks, that a failure on one release does not
silence the others, and that nothing is recorded as posted when Slack rejected it.
"""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

ENV = {
    'METRICS_FUNCTION_NAME': 'oscar-metrics-dev',
    'CENTRAL_SECRET_NAME': 'oscar-central-env-dev',
    'RELEASE_NOTIFY_TABLE_NAME': 'oscar-release-notify-state-dev',
    'AWS_REGION': 'us-east-1',
}

ACTIVE_RELEASE = {
    'version': '3.9.0',
    'cadence_phase': 'pre_rc_frequent',
    'rc_date': '2026-09-15',
    'release_date': '2026-09-29',
    'days_to_rc': 4,
    'days_to_release': 18,
    'release_manager': 'someone',
}

RELEASE_STATUS = {
    'version': '3.9.0',
    'found': True,
    'verdict': 'red',
    'blocking_failures': ['release_notes_ready'],
    'blocking_in_progress': [],
    'blocking_unknowns': [],
    'non_blocking_gaps': [],
    'criteria': [{
        'criterion_name': 'release_notes_ready',
        'status': 'not_met',
        'criterion_type': 'entrance',
        'severity': 'blocking',
    }],
}


def _envelope(body):
    """Wrap a result the way the metrics Lambda returns it to a Bedrock action group."""
    payload = {'response': {'functionResponse': {'responseBody': {'TEXT': {
        'body': json.dumps(body),
    }}}}}
    return {'Payload': MagicMock(read=lambda: json.dumps(payload).encode())}


@pytest.fixture
def notifier_env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def harness(notifier, notifier_env):
    """Patch out every boundary: Lambda invoke, Secrets Manager, DynamoDB, Slack."""
    responses = {
        'list_active_releases': {'releases': [ACTIVE_RELEASE], 'total_results': 1},
        'get_release_status': RELEASE_STATUS,
    }

    lambda_client = MagicMock()
    lambda_client.invoke.side_effect = lambda **kwargs: _envelope(
        responses[json.loads(kwargs['Payload'])['function']]
    )

    secrets_client = MagicMock()
    secrets_client.get_secret_value.return_value = {'SecretString': json.dumps({
        'SLACK_BOT_TOKEN': 'xoxb-test',
        'RELEASE_CHANNELS': 'C123, C456',
    })}

    table = MagicMock()
    table.get_item.return_value = {}
    dynamodb = MagicMock()
    dynamodb.Table.return_value = table

    slack = MagicMock()

    def client(service, **kwargs):
        return {'lambda': lambda_client, 'secretsmanager': secrets_client}[service]

    with patch.object(notifier.boto3, 'client', side_effect=client), \
            patch.object(notifier.boto3, 'resource', return_value=dynamodb), \
            patch.object(notifier, 'WebClient', return_value=slack):
        yield MagicMock(
            module=notifier, responses=responses, lambda_client=lambda_client,
            table=table, slack=slack,
        )


class TestMetricsInvocation:

    def test_action_group_envelope(self, harness):
        harness.module.lambda_handler({}, None)

        payloads = [
            json.loads(call.kwargs['Payload'])
            for call in harness.lambda_client.invoke.call_args_list
        ]
        assert payloads[0] == {
            'actionGroup': 'metricsActionGroup',
            'function': 'list_active_releases',
            'parameters': [],
        }
        assert payloads[1] == {
            'actionGroup': 'metricsActionGroup',
            'function': 'get_release_status',
            'parameters': [{'name': 'version', 'value': '3.9.0'}],
        }
        assert harness.lambda_client.invoke.call_args.kwargs['FunctionName'] == \
            'oscar-metrics-dev'

    def test_function_error_is_surfaced(self, harness):
        harness.lambda_client.invoke.side_effect = None
        harness.lambda_client.invoke.return_value = {'FunctionError': 'Unhandled'}
        result = harness.module.lambda_handler({}, None)
        assert result['statusCode'] == 502

    def test_unexpected_envelope_is_surfaced(self, harness):
        harness.lambda_client.invoke.side_effect = None
        harness.lambda_client.invoke.return_value = {
            'Payload': MagicMock(read=lambda: json.dumps({'oops': True}).encode())
        }
        result = harness.module.lambda_handler({}, None)
        assert result['statusCode'] == 502


class TestPosting:

    def test_posts_to_every_channel_and_records_the_post(self, harness):
        result = harness.module.lambda_handler({}, None)

        assert result == {'statusCode': 200, 'posted': 1, 'results': [{
            'version': '3.9.0',
            'posted': True,
            'reason': 'first post for this release',
            'channels_delivered': 2,
            'channels_total': 2,
            'verdict': 'red',
        }]}
        assert [c.kwargs['channel'] for c in harness.slack.chat_postMessage.call_args_list] == \
            ['C123', 'C456']

        recorded = harness.table.put_item.call_args.kwargs['Item']
        assert recorded['version'] == '3.9.0'
        assert recorded['verdict'] == 'red'
        assert recorded['cadence_phase'] == 'pre_rc_frequent'
        assert recorded['blocking_failures'] == ['release_notes_ready']
        assert recorded['last_posted_at'].endswith('Z')

    def test_message_carries_the_verdict(self, harness):
        harness.module.lambda_handler({}, None)
        text = harness.slack.chat_postMessage.call_args.kwargs['text']
        assert '*3.9.0* — RED' in text
        assert 'release_notes_ready' in text

    def test_silent_phase_skips_the_verdict_lookup_entirely(self, harness):
        harness.responses['list_active_releases'] = {
            'releases': [{**ACTIVE_RELEASE, 'cadence_phase': 'out_of_window'}],
        }
        result = harness.module.lambda_handler({}, None)

        assert result['posted'] == 0
        assert 'does not notify' in result['results'][0]['reason']
        # Only list_active_releases was called - no point paying for a verdict nobody reads.
        assert harness.lambda_client.invoke.call_count == 1
        harness.slack.chat_postMessage.assert_not_called()

    def test_nothing_recorded_when_slack_rejected_every_channel(self, harness):
        from slack_sdk.errors import SlackApiError
        harness.slack.chat_postMessage.side_effect = SlackApiError(
            'nope', MagicMock(**{'get.return_value': 'channel_not_found'}))

        result = harness.module.lambda_handler({}, None)

        # Recording a post that never arrived would suppress the next real one.
        assert result['results'][0]['posted'] is False
        harness.table.put_item.assert_not_called()

    def test_partial_delivery_is_recorded_and_logged(self, harness, caplog):
        """A post that reached some channels must not be resent to those channels.

        Re-posting on the next run to make one broken channel whole would duplicate the
        message in every healthy channel, every run, until it recovers. The state is
        recorded instead and the shortfall is logged loudly enough to alarm on.
        """
        from slack_sdk.errors import SlackApiError
        harness.slack.chat_postMessage.side_effect = [
            None,
            SlackApiError('nope', MagicMock(**{'get.return_value': 'channel_not_found'})),
        ]

        with caplog.at_level(logging.ERROR):
            result = harness.module.lambda_handler({}, None)

        assert result['results'][0]['posted'] is True
        assert result['results'][0]['channels_delivered'] == 1
        assert result['results'][0]['channels_total'] == 2
        harness.table.put_item.assert_called_once()
        assert 'RELEASE_NOTIFY_PARTIAL_DELIVERY' in caplog.text

    def test_full_delivery_is_not_logged_as_partial(self, harness, caplog):
        with caplog.at_level(logging.ERROR):
            harness.module.lambda_handler({}, None)
        assert 'RELEASE_NOTIFY_PARTIAL_DELIVERY' not in caplog.text

    def test_unchanged_release_inside_the_interval_stays_quiet(self, harness):
        harness.table.get_item.return_value = {'Item': {
            'version': '3.9.0',
            'verdict': 'red',
            'blocking_failures': ['release_notes_ready'],
            'last_posted_at': '2026-09-11T11:00:00Z',
        }}
        with patch.object(harness.module, '_hours_since', return_value=1.0):
            result = harness.module.lambda_handler({}, None)

        assert result['posted'] == 0
        harness.slack.chat_postMessage.assert_not_called()

    def test_missing_release_state_is_reported_not_posted(self, harness):
        harness.responses['get_release_status'] = {
            'version': '3.9.0', 'found': False, 'message': 'No indexed release state',
        }
        result = harness.module.lambda_handler({}, None)

        assert result['posted'] == 0
        assert result['results'][0]['reason'] == 'No indexed release state'
        harness.slack.chat_postMessage.assert_not_called()

    def test_one_broken_release_does_not_stop_the_others(self, harness):
        harness.responses['list_active_releases'] = {'releases': [
            {**ACTIVE_RELEASE, 'version': '3.9.0'},
            {**ACTIVE_RELEASE, 'version': '4.0.0'},
        ]}
        original = harness.module._process_release

        def process(release, *args):
            if release['version'] == '3.9.0':
                raise RuntimeError('boom')
            return original(release, *args)

        with patch.object(harness.module, '_process_release', side_effect=process):
            result = harness.module.lambda_handler({}, None)

        assert result['statusCode'] == 200
        assert result['results'][0]['error'] == 'boom'
        assert result['results'][1]['posted'] is True


class TestReleaseManagerMention:

    def test_linked_manager_is_tagged_in_the_post(self, harness):
        with patch.object(harness.module, 'load_handle_map', return_value={'someone': 'U111'}):
            harness.module.lambda_handler({}, None)
        assert '<@U111>' in harness.slack.chat_postMessage.call_args.kwargs['text']

    def test_falls_back_to_a_profile_link_without_identity_mapping(self, harness):
        """No IDENTITY_TABLE_NAME here - the same as a deployment with no identity table."""
        harness.module.lambda_handler({}, None)
        text = harness.slack.chat_postMessage.call_args.kwargs['text']
        assert '<https://github.com/someone|@someone>' in text

    def test_table_is_read_once_per_run_not_once_per_release(self, harness):
        harness.responses['list_active_releases'] = {'releases': [
            {**ACTIVE_RELEASE, 'version': '3.9.0'},
            {**ACTIVE_RELEASE, 'version': '4.0.0'},
        ]}
        with patch.object(harness.module, 'load_handle_map', return_value={}) as load:
            harness.module.lambda_handler({}, None)
        load.assert_called_once()


class TestConfiguration:

    def test_no_channels_configured_is_not_an_error(self, harness):
        with patch.object(harness.module, '_load_slack_config',
                          return_value={'token': 'xoxb-test', 'channels': []}):
            result = harness.module.lambda_handler({}, None)
        assert result == {'statusCode': 200, 'posted': 0, 'reason': 'no channels configured'}

    def test_missing_token_fails_loudly(self, harness):
        with patch.object(harness.module, '_load_slack_config',
                          return_value={'token': '', 'channels': ['C123']}):
            result = harness.module.lambda_handler({}, None)
        assert result['statusCode'] == 500

    def test_channels_are_split_and_trimmed(self, harness):
        assert harness.module._load_slack_config() == {
            'token': 'xoxb-test', 'channels': ['C123', 'C456'],
        }

    def test_unset_secret_name_fails_loudly(self, harness, monkeypatch):
        monkeypatch.delenv('CENTRAL_SECRET_NAME')
        result = harness.module.lambda_handler({}, None)
        assert result['statusCode'] == 500

    def test_unset_metrics_function_name_fails_loudly(self, harness, monkeypatch):
        monkeypatch.delenv('METRICS_FUNCTION_NAME')
        result = harness.module.lambda_handler({}, None)
        assert result['statusCode'] == 502


class TestHoursSince:

    def test_missing_timestamp(self, notifier):
        assert notifier._hours_since(None) is None

    def test_unparseable_timestamp(self, notifier):
        assert notifier._hours_since('not-a-timestamp') is None

    def test_naive_timestamp_is_read_as_utc(self, notifier):
        # A naive value would otherwise raise when subtracted from an aware now().
        assert notifier._hours_since('2020-01-01T00:00:00') > 0
