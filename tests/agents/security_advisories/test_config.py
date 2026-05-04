# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for security advisories config.py.

These tests verify configuration loading from environment variables and
Secrets Manager, default values, validation, and the _ConfigProxy pattern.
"""

import importlib
import json
import os

import boto3
import pytest
from moto import mock_aws

# Path to the real config module
_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)


def _load_config_module():
    """Import the config module from security_advisories lambda, fresh each time."""
    spec = importlib.util.spec_from_file_location(
        'sa_config', os.path.join(_CONFIG_PATH, 'config.py'),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _create_secret(host='https://search-advisory.us-east-1.es.amazonaws.com'):
    """Create the advisories secret in moto Secrets Manager."""
    sm = boto3.client('secretsmanager', region_name='us-east-1')
    sm.create_secret(
        Name='oscar-security-advisories-env-test',
        SecretString=json.dumps({'OPENSEARCH_HOST': host}),
    )


# Minimal env vars needed for tests
BASE_ENV = {
    'AWS_REGION': 'us-east-1',
    'SECURITY_ADVISORIES_SECRET_NAME': 'oscar-security-advisories-env-test',
}


class TestDefaultValues:
    """Test that default values are used when env vars are not set."""

    def test_opensearch_region_default(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv('OPENSEARCH_REGION', raising=False)
            mp.delenv('SECURITY_ADVISORIES_SECRET_NAME', raising=False)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.opensearch_region == 'us-east-1'

    def test_opensearch_service_default(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv('OPENSEARCH_SERVICE', raising=False)
            mp.delenv('SECURITY_ADVISORIES_SECRET_NAME', raising=False)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.opensearch_service == 'es'

    def test_request_timeout_default(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv('OPENSEARCH_REQUEST_TIMEOUT', raising=False)
            mp.delenv('SECURITY_ADVISORIES_SECRET_NAME', raising=False)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.request_timeout == 60

    def test_scans_index_default(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv('SCANS_INDEX', raising=False)
            mp.delenv('SECURITY_ADVISORIES_SECRET_NAME', raising=False)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.scans_index == 'scans-000001'

    def test_advisories_index_default(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv('ADVISORIES_INDEX', raising=False)
            mp.delenv('SECURITY_ADVISORIES_SECRET_NAME', raising=False)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.advisories_index == 'advisories'

    def test_bedrock_message_version_default(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv('BEDROCK_RESPONSE_MESSAGE_VERSION', raising=False)
            mp.delenv('SECURITY_ADVISORIES_SECRET_NAME', raising=False)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.bedrock_message_version == '1.0'

    def test_agentic_pipeline_default(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv('AGENTIC_PIPELINE', raising=False)
            mp.delenv('SECURITY_ADVISORIES_SECRET_NAME', raising=False)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.agentic_pipeline == 'oscar-agentic-pipeline'

    def test_cross_account_role_arn_default_empty(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv('SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_ARN', raising=False)
            mp.delenv('SECURITY_ADVISORIES_SECRET_NAME', raising=False)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.cross_account_role_arn == ''


class TestEnvVarOverrides:
    """Test that environment variables override default values."""

    def test_opensearch_region_override(self):
        env = {**BASE_ENV, 'OPENSEARCH_REGION': 'eu-west-1'}
        with pytest.MonkeyPatch.context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.opensearch_region == 'eu-west-1'

    def test_opensearch_service_override(self):
        env = {**BASE_ENV, 'OPENSEARCH_SERVICE': 'aoss'}
        with pytest.MonkeyPatch.context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.opensearch_service == 'aoss'

    def test_request_timeout_override(self):
        env = {**BASE_ENV, 'OPENSEARCH_REQUEST_TIMEOUT': '120'}
        with pytest.MonkeyPatch.context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.request_timeout == 120

    def test_scans_index_override(self):
        env = {**BASE_ENV, 'SCANS_INDEX': 'custom-scans'}
        with pytest.MonkeyPatch.context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.scans_index == 'custom-scans'

    def test_advisories_index_override(self):
        env = {**BASE_ENV, 'ADVISORIES_INDEX': 'custom-advisories'}
        with pytest.MonkeyPatch.context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.advisories_index == 'custom-advisories'

    def test_agentic_pipeline_override(self):
        env = {**BASE_ENV, 'AGENTIC_PIPELINE': 'my-custom-pipeline'}
        with pytest.MonkeyPatch.context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.agentic_pipeline == 'my-custom-pipeline'

    def test_cross_account_role_arn_override(self):
        env = {
            **BASE_ENV,
            'SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_ARN': 'arn:aws:iam::123456789012:role/test',
        }
        with pytest.MonkeyPatch.context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.cross_account_role_arn == 'arn:aws:iam::123456789012:role/test'


class TestSecretLoading:
    """Test loading secrets from AWS Secrets Manager using moto."""

    @mock_aws
    def test_loads_opensearch_host_from_secret(self):
        _create_secret(host='https://search-advisory.us-east-1.es.amazonaws.com')
        env = {**BASE_ENV}
        with pytest.MonkeyPatch.context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.opensearch_host == 'https://search-advisory.us-east-1.es.amazonaws.com'

    @mock_aws
    def test_missing_secret_name_returns_empty_host(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.delenv('SECURITY_ADVISORIES_SECRET_NAME', raising=False)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.opensearch_host == ''

    @mock_aws
    def test_secret_without_opensearch_host_key(self):
        sm = boto3.client('secretsmanager', region_name='us-east-1')
        sm.create_secret(
            Name='oscar-security-advisories-env-test',
            SecretString=json.dumps({'OTHER_KEY': 'some-value'}),
        )
        env = {**BASE_ENV}
        with pytest.MonkeyPatch.context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.opensearch_host == ''


class TestValidation:
    """Test ValueError raised when required config is missing."""

    @mock_aws
    def test_raises_when_opensearch_host_missing_and_validate_required(self):
        # Create secret without OPENSEARCH_HOST
        sm = boto3.client('secretsmanager', region_name='us-east-1')
        sm.create_secret(
            Name='oscar-security-advisories-env-test',
            SecretString=json.dumps({}),
        )
        env = {**BASE_ENV}
        with pytest.MonkeyPatch.context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            mod = _load_config_module()
            with pytest.raises(ValueError, match='OPENSEARCH_HOST'):
                mod.SecurityAdvisoriesConfig(validate_required=True)

    @mock_aws
    def test_no_error_when_validate_required_false(self):
        env = {**BASE_ENV}
        with pytest.MonkeyPatch.context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            # No secret created — host will be empty, but no error
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.opensearch_host == ''


class TestGetOpensearchHostClean:
    """Test get_opensearch_host_clean() strips https:// prefix."""

    @mock_aws
    def test_strips_https_prefix(self):
        _create_secret(host='https://search-advisory.us-east-1.es.amazonaws.com')
        env = {**BASE_ENV}
        with pytest.MonkeyPatch.context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            mod = _load_config_module()
            cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
            assert cfg.get_opensearch_host_clean() == 'search-advisory.us-east-1.es.amazonaws.com'

    def test_no_prefix_returns_unchanged(self):
        mod = _load_config_module()
        cfg = mod.SecurityAdvisoriesConfig(validate_required=False)
        cfg.opensearch_host = 'search-advisory.us-east-1.es.amazonaws.com'
        assert cfg.get_opensearch_host_clean() == 'search-advisory.us-east-1.es.amazonaws.com'


class TestConfigProxy:
    """Test the _ConfigProxy lazy-loading pattern."""

    def test_proxy_tracks_request_id(self):
        mod = _load_config_module()
        proxy = mod._ConfigProxy()
        proxy.set_request_id('req-123')
        assert proxy.aws_request_id == 'req-123'

    def test_proxy_starts_uncached(self):
        mod = _load_config_module()
        proxy = mod._ConfigProxy()
        assert proxy._cached_config is None

    def test_proxy_caches_config_on_first_access(self):
        mod = _load_config_module()
        proxy = mod._ConfigProxy()
        # Accessing any attribute triggers config creation
        _ = proxy.opensearch_region
        assert proxy._cached_config is not None

    def test_proxy_refreshes_on_new_request_id(self):
        mod = _load_config_module()
        proxy = mod._ConfigProxy()
        proxy.set_request_id('req-1')
        _ = proxy.opensearch_region
        first_config = proxy._cached_config

        proxy.set_request_id('req-2')
        _ = proxy.opensearch_region
        second_config = proxy._cached_config

        assert first_config is not second_config
