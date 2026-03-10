# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for Config and _ConfigProxy.

These tests need the REAL config module, so we reload it from source
to bypass the mock in conftest.py.
"""

import importlib
import json
import os
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

# Path to the real config module
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lambda', 'oscar-agent')


def _load_real_config_module():
    """Import the real config module from oscar-agent, bypassing the conftest mock."""
    spec = importlib.util.spec_from_file_location(
        'real_config', os.path.join(_CONFIG_PATH, 'config.py'),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup_aws(slack_token='xoxb-test', signing_secret='secret123',
               users='U1,U2', channels='C1,C2'):
    """Create central secret and SSM params in moto."""
    sm = boto3.client('secretsmanager', region_name='us-east-1')
    sm.create_secret(
        Name='oscar-central-env-test',
        SecretString=json.dumps({
            'SLACK_BOT_TOKEN': slack_token,
            'SLACK_SIGNING_SECRET': signing_secret,
            'FULLY_AUTHORIZED_USERS': users,
            'CHANNEL_ALLOW_LIST': channels,
        }),
    )
    ssm = boto3.client('ssm', region_name='us-east-1')
    for param, value in [
        ('/oscar/test/priv-id', 'agent-priv'),
        ('/oscar/test/priv-alias', 'alias-priv'),
        ('/oscar/test/ltd-id', 'agent-ltd'),
        ('/oscar/test/ltd-alias', 'alias-ltd'),
    ]:
        ssm.put_parameter(Name=param, Value=value, Type='String')


BASE_ENV = {
    'AWS_REGION': 'us-east-1',
    'CENTRAL_SECRET_NAME': 'oscar-central-env-test',
    'CONTEXT_TABLE_NAME': 'test-context',
    'OSCAR_PRIVILEGED_BEDROCK_AGENT_ID_PARAM_PATH': '/oscar/test/priv-id',
    'OSCAR_PRIVILEGED_BEDROCK_AGENT_ALIAS_PARAM_PATH': '/oscar/test/priv-alias',
    'OSCAR_LIMITED_BEDROCK_AGENT_ID_PARAM_PATH': '/oscar/test/ltd-id',
    'OSCAR_LIMITED_BEDROCK_AGENT_ALIAS_PARAM_PATH': '/oscar/test/ltd-alias',
}


class TestConfig:

    @mock_aws
    def test_loads_slack_tokens_from_central_secret(self):
        _setup_aws()
        with patch.dict(os.environ, BASE_ENV, clear=False):
            mod = _load_real_config_module()
            cfg = mod.Config(validate_required=False)
            assert cfg.slack_bot_token == 'xoxb-test'
            assert cfg.slack_signing_secret == 'secret123'

    @mock_aws
    def test_parses_comma_separated_user_lists(self):
        _setup_aws()
        with patch.dict(os.environ, BASE_ENV, clear=False):
            mod = _load_real_config_module()
            cfg = mod.Config(validate_required=False)
            assert cfg.fully_authorized_users == ['U1', 'U2']

    @mock_aws
    def test_parses_channel_allow_list(self):
        _setup_aws()
        with patch.dict(os.environ, BASE_ENV, clear=False):
            mod = _load_real_config_module()
            cfg = mod.Config(validate_required=False)
            assert cfg.channel_allow_list == ['C1', 'C2']

    @mock_aws
    def test_loads_agent_ids_from_ssm(self):
        _setup_aws()
        with patch.dict(os.environ, BASE_ENV, clear=False):
            mod = _load_real_config_module()
            cfg = mod.Config(validate_required=False)
            assert cfg.oscar_privileged_bedrock_agent_id == 'agent-priv'
            assert cfg.oscar_privileged_bedrock_agent_alias_id == 'alias-priv'
            assert cfg.oscar_limited_bedrock_agent_id == 'agent-ltd'
            assert cfg.oscar_limited_bedrock_agent_alias_id == 'alias-ltd'

    def test_missing_central_secret_name_returns_empty_tokens(self):
        env = {k: v for k, v in BASE_ENV.items() if k != 'CENTRAL_SECRET_NAME'}
        with patch.dict(os.environ, env, clear=False):
            mod = _load_real_config_module()
            cfg = mod.Config(validate_required=False)
            assert cfg.slack_bot_token == ''

    @mock_aws
    def test_validation_raises_on_missing_slack_token(self):
        _setup_aws(slack_token='')
        with patch.dict(os.environ, BASE_ENV, clear=False):
            mod = _load_real_config_module()
            with pytest.raises(ValueError, match='SLACK_BOT_TOKEN'):
                mod.Config(validate_required=True)

    def test_context_ttl_default_604800(self):
        with patch.dict(os.environ, BASE_ENV, clear=False):
            mod = _load_real_config_module()
            cfg = mod.Config(validate_required=False)
            assert cfg.context_ttl == 604800

    def test_context_ttl_from_env(self):
        with patch.dict(os.environ, {**BASE_ENV, 'CONTEXT_TTL': '3600'}, clear=False):
            mod = _load_real_config_module()
            cfg = mod.Config(validate_required=False)
            assert cfg.context_ttl == 3600

    def test_enable_dm_default_false(self):
        with patch.dict(os.environ, BASE_ENV, clear=False):
            mod = _load_real_config_module()
            cfg = mod.Config(validate_required=False)
            assert cfg.enable_dm is False

    def test_enable_dm_true_from_env(self):
        with patch.dict(os.environ, {**BASE_ENV, 'ENABLE_DM': 'true'}, clear=False):
            mod = _load_real_config_module()
            cfg = mod.Config(validate_required=False)
            assert cfg.enable_dm is True

    def test_agent_timeout_default_90(self):
        with patch.dict(os.environ, BASE_ENV, clear=False):
            mod = _load_real_config_module()
            cfg = mod.Config(validate_required=False)
            assert cfg.agent_timeout == 90

    def test_regex_patterns_populated(self):
        with patch.dict(os.environ, BASE_ENV, clear=False):
            mod = _load_real_config_module()
            cfg = mod.Config(validate_required=False)
            for key, value in cfg.patterns.items():
                assert value, f"Pattern '{key}' is empty"


class TestConfigProxy:

    def test_proxy_tracks_request_id(self):
        mod = _load_real_config_module()
        proxy = mod._ConfigProxy()
        proxy.set_request_id('req-123')
        assert proxy.aws_request_id == 'req-123'

    def test_proxy_starts_uncached(self):
        mod = _load_real_config_module()
        proxy = mod._ConfigProxy()
        assert proxy._cached_config is None
