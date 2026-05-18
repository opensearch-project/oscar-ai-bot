# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for security advisories aws_utils.py.

These tests verify cross-account role assumption, direct credentials,
SigV4-signed OpenSearch requests, TLS enforcement, timeout configuration,
and error log markers.
"""

import importlib
import json
import os
from unittest.mock import MagicMock, patch

import pytest

# Path to the real aws_utils module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)


def _load_aws_utils():
    """Import aws_utils from security_advisories lambda, fresh each time."""
    # Ensure the lambda directory is on sys.path so ``import config`` works
    import sys
    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)

    spec = importlib.util.spec_from_file_location(
        'sa_aws_utils', os.path.join(_LAMBDA_PATH, 'aws_utils.py'),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_config_mock(**overrides):
    """Create a mock config object with sensible defaults."""
    defaults = {
        'cross_account_role_arn': '',
        'opensearch_service': 'es',
        'opensearch_region': 'us-east-1',
        'request_timeout': 60,
    }
    defaults.update(overrides)
    cfg = MagicMock()
    for k, v in defaults.items():
        setattr(cfg, k, v)
    cfg.get_opensearch_host_clean.return_value = 'search-advisory.us-east-1.es.amazonaws.com'
    return cfg


# ---------------------------------------------------------------------------
# get_opensearch_session tests
# ---------------------------------------------------------------------------

class TestGetOpensearchSessionCrossAccount:
    """Test cross-account role assumption path (mocked STS)."""

    def test_assumes_role_when_cross_account_arn_set(self):
        mod = _load_aws_utils()
        cfg = _make_config_mock(
            cross_account_role_arn='arn:aws:iam::123456789012:role/advisory-role',
        )

        fake_creds = {
            'Credentials': {
                'AccessKeyId': 'AKID',
                'SecretAccessKey': 'SECRET',
                'SessionToken': 'TOKEN',
            },
        }

        with patch.object(mod, 'config', cfg), \
             patch.object(mod, 'boto3') as mock_boto3:
            mock_sts = MagicMock()
            mock_sts.assume_role.return_value = fake_creds
            mock_boto3.client.return_value = mock_sts

            session = mod.get_opensearch_session()

            mock_sts.assume_role.assert_called_once_with(
                RoleArn='arn:aws:iam::123456789012:role/advisory-role',
                RoleSessionName='oscar-security-advisories-session',
            )
            mock_boto3.Session.assert_called_once_with(
                aws_access_key_id='AKID',
                aws_secret_access_key='SECRET',
                aws_session_token='TOKEN',
            )
            assert session == mock_boto3.Session.return_value


class TestGetOpensearchSessionDirect:
    """Test direct credentials path when no cross-account role configured."""

    def test_uses_default_session_when_no_cross_account_role(self):
        mod = _load_aws_utils()
        cfg = _make_config_mock(cross_account_role_arn='')

        with patch.object(mod, 'config', cfg), \
             patch.object(mod, 'boto3') as mock_boto3:
            session = mod.get_opensearch_session()

            mock_boto3.client.assert_not_called()
            mock_boto3.Session.assert_called_once_with()
            assert session == mock_boto3.Session.return_value


# ---------------------------------------------------------------------------
# Log marker tests
# ---------------------------------------------------------------------------

class TestCrossAccountRoleFailedLogMarker:
    """Test CROSS_ACCOUNT_ROLE_FAILED log marker on STS failure."""

    def test_logs_cross_account_role_failed_on_sts_error(self, caplog):
        mod = _load_aws_utils()
        cfg = _make_config_mock(
            cross_account_role_arn='arn:aws:iam::123456789012:role/bad-role',
        )

        with patch.object(mod, 'config', cfg), \
             patch.object(mod, 'boto3') as mock_boto3:
            mock_sts = MagicMock()
            mock_sts.assume_role.side_effect = Exception('Access denied')
            mock_boto3.client.return_value = mock_sts

            import logging
            with caplog.at_level(logging.ERROR):
                with pytest.raises(Exception, match='Access denied'):
                    mod.get_opensearch_session()

            assert any('SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_FAILED' in r.message for r in caplog.records)


class TestOpensearchConnectionFailedLogMarker:
    """Test OPENSEARCH_CONNECTION_FAILED log marker on connection failure."""

    def test_logs_opensearch_connection_failed_on_request_error(self, caplog):
        mod = _load_aws_utils()
        cfg = _make_config_mock(cross_account_role_arn='')

        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_session.get_credentials.return_value = mock_creds

        with patch.object(mod, 'config', cfg), \
             patch.object(mod, 'boto3') as mock_boto3, \
             patch.object(mod, 'requests') as mock_requests, \
             patch.object(mod, 'SigV4Auth'):
            mock_boto3.Session.return_value = mock_session
            mock_requests.request.side_effect = ConnectionError('Connection refused')

            import logging
            with caplog.at_level(logging.ERROR):
                with pytest.raises(ConnectionError, match='Connection refused'):
                    mod.opensearch_request('GET', '/_search')

            assert any(
                'SECURITY_ADVISORIES_OPENSEARCH_CONNECTION_FAILED' in r.message for r in caplog.records
            )


# ---------------------------------------------------------------------------
# TLS enforcement tests
# ---------------------------------------------------------------------------

class TestTLSEnforcement:
    """Test TLS enforcement (URL uses https://)."""

    def test_url_uses_https(self):
        mod = _load_aws_utils()
        cfg = _make_config_mock(cross_account_role_arn='')

        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_session.get_credentials.return_value = mock_creds

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'hits': []}

        with patch.object(mod, 'config', cfg), \
             patch.object(mod, 'boto3') as mock_boto3, \
             patch.object(mod, 'requests') as mock_requests, \
             patch.object(mod, 'SigV4Auth'):
            mock_boto3.Session.return_value = mock_session
            mock_requests.request.return_value = mock_response

            mod.opensearch_request('GET', '/_search')

            call_kwargs = mock_requests.request.call_args
            url = call_kwargs[1].get('url') or call_kwargs[0][1] if call_kwargs[0] else call_kwargs[1]['url']
            assert url.startswith('https://')


# ---------------------------------------------------------------------------
# Request timeout tests
# ---------------------------------------------------------------------------

class TestRequestTimeout:
    """Test request timeout configuration is respected."""

    def test_timeout_passed_to_requests(self):
        mod = _load_aws_utils()
        cfg = _make_config_mock(cross_account_role_arn='', request_timeout=120)

        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_session.get_credentials.return_value = mock_creds

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'hits': []}

        with patch.object(mod, 'config', cfg), \
             patch.object(mod, 'boto3') as mock_boto3, \
             patch.object(mod, 'requests') as mock_requests, \
             patch.object(mod, 'SigV4Auth'):
            mock_boto3.Session.return_value = mock_session
            mock_requests.request.return_value = mock_response

            mod.opensearch_request('GET', '/_search')

            call_kwargs = mock_requests.request.call_args
            assert call_kwargs[1]['timeout'] == 120

    def test_default_timeout_is_60(self):
        mod = _load_aws_utils()
        cfg = _make_config_mock(cross_account_role_arn='', request_timeout=60)

        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_session.get_credentials.return_value = mock_creds

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch.object(mod, 'config', cfg), \
             patch.object(mod, 'boto3') as mock_boto3, \
             patch.object(mod, 'requests') as mock_requests, \
             patch.object(mod, 'SigV4Auth'):
            mock_boto3.Session.return_value = mock_session
            mock_requests.request.return_value = mock_response

            mod.opensearch_request('POST', '/_search', body={'query': {}})

            call_kwargs = mock_requests.request.call_args
            assert call_kwargs[1]['timeout'] == 60


# ---------------------------------------------------------------------------
# opensearch_request additional tests
# ---------------------------------------------------------------------------

class TestOpensearchRequest:
    """Additional tests for opensearch_request."""

    def test_raises_value_error_when_host_not_configured(self):
        mod = _load_aws_utils()
        cfg = _make_config_mock(cross_account_role_arn='')
        cfg.get_opensearch_host_clean.return_value = ''

        with patch.object(mod, 'config', cfg):
            with pytest.raises(ValueError, match='OPENSEARCH_HOST not configured'):
                mod.opensearch_request('GET', '/_search')

    def test_raises_on_non_2xx_response(self):
        mod = _load_aws_utils()
        cfg = _make_config_mock(cross_account_role_arn='')

        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_session.get_credentials.return_value = mock_creds

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'

        with patch.object(mod, 'config', cfg), \
             patch.object(mod, 'boto3') as mock_boto3, \
             patch.object(mod, 'requests') as mock_requests, \
             patch.object(mod, 'SigV4Auth'):
            mock_boto3.Session.return_value = mock_session
            mock_requests.request.return_value = mock_response

            with pytest.raises(Exception, match='OpenSearch request failed: 500'):
                mod.opensearch_request('GET', '/_search')

    def test_sends_json_body_when_provided(self):
        mod = _load_aws_utils()
        cfg = _make_config_mock(cross_account_role_arn='')

        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_session.get_credentials.return_value = mock_creds

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'hits': []}

        with patch.object(mod, 'config', cfg), \
             patch.object(mod, 'boto3') as mock_boto3, \
             patch.object(mod, 'requests') as mock_requests, \
             patch.object(mod, 'SigV4Auth'):
            mock_boto3.Session.return_value = mock_session
            mock_requests.request.return_value = mock_response

            body = json.dumps({'query': {'match_all': {}}})
            mod.opensearch_request('POST', '/_search', body=body)

            call_kwargs = mock_requests.request.call_args
            sent_data = call_kwargs[1].get('data') or call_kwargs[0][2] if len(call_kwargs[0]) > 2 else call_kwargs[1]['data']
            assert json.loads(sent_data) == json.loads(body)

    def test_returns_parsed_json_on_success(self):
        mod = _load_aws_utils()
        cfg = _make_config_mock(cross_account_role_arn='')

        mock_session = MagicMock()
        mock_creds = MagicMock()
        mock_session.get_credentials.return_value = mock_creds

        expected = {'hits': {'total': {'value': 5}}}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = expected

        with patch.object(mod, 'config', cfg), \
             patch.object(mod, 'boto3') as mock_boto3, \
             patch.object(mod, 'requests') as mock_requests, \
             patch.object(mod, 'SigV4Auth'):
            mock_boto3.Session.return_value = mock_session
            mock_requests.request.return_value = mock_response

            result = mod.opensearch_request('GET', '/_search')
            assert result == expected
