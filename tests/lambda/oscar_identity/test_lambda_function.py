# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the identity OAuth callback Lambda."""

import importlib
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add Lambda source path so oauth_state can be found
_IDENTITY_LAMBDA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lambda', 'oscar-identity')
sys.path.insert(0, _IDENTITY_LAMBDA_DIR)

# Set required env vars before import
os.environ.setdefault("IDENTITY_TABLE_PREFIX", "oscar-identity")
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("CENTRAL_SECRET_NAME", "oscar-central-env-dev")

TEST_SIGNING_SECRET = "test-signing-secret"
TEST_SECRETS = {
    "GITHUB_OAUTH_CLIENT_ID": "test-client-id",
    "GITHUB_OAUTH_CLIENT_SECRET": "test-client-secret",
    "OAUTH_CALLBACK_URL": "https://example.com/oauth/callback",
    "OAUTH_STATE_SECRET": TEST_SIGNING_SECRET,
    "SLACK_BOT_TOKEN": "xoxb-test-token",
    "CHANNEL_ALLOW_LIST": "C001,C002",
}


def _make_signed_state(user_id="U123", workspace_id="T01INTERNAL"):
    """Generate a valid signed state token for tests."""
    from oauth_state import generate_state
    return generate_state(user_id, workspace_id, TEST_SIGNING_SECRET)


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setenv("IDENTITY_TABLE_PREFIX", "oscar-identity")
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("CENTRAL_SECRET_NAME", "oscar-central-env-dev")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("SLACK_WORKSPACE_IDS", "T01INTERNAL")


@pytest.fixture(autouse=True)
def clear_module_cache():
    """Ensure lambda_function is reimported fresh each test."""
    for mod in list(sys.modules.keys()):
        if "lambda_function" in mod or "oauth_state" in mod:
            del sys.modules[mod]
    yield
    for mod in list(sys.modules.keys()):
        if "lambda_function" in mod or "oauth_state" in mod:
            del sys.modules[mod]


def _load_identity_lambda():
    """Load the oscar-identity lambda_function module by file path."""
    for mod in list(sys.modules.keys()):
        if "lambda_function" in mod:
            del sys.modules[mod]
    spec = importlib.util.spec_from_file_location(
        "lambda_function",
        os.path.join(_IDENTITY_LAMBDA_DIR, "lambda_function.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lambda_function"] = mod
    spec.loader.exec_module(mod)
    return mod


def _invoke(event):
    """Import and invoke the lambda handler with full mocking."""
    with patch("boto3.resource") as mock_resource, \
         patch("boto3.client") as mock_client:

        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        mock_secrets = MagicMock()
        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps(TEST_SECRETS)
        }
        mock_client.return_value = mock_secrets

        lambda_function = _load_identity_lambda()
        lambda_function._oauth_creds = None

        return lambda_function.lambda_handler(event, None), mock_table, lambda_function


class TestValidation:

    def test_missing_code_returns_400(self):
        state = _make_signed_state()
        result, _, _ = _invoke({"queryStringParameters": {"state": state}})
        assert result["statusCode"] == 400
        assert "Missing code or state" in result["body"]

    def test_missing_state_returns_400(self):
        result, _, _ = _invoke({"queryStringParameters": {"code": "abc"}})
        assert result["statusCode"] == 400
        assert "Missing code or state" in result["body"]

    def test_no_params_returns_400(self):
        result, _, _ = _invoke({"queryStringParameters": None})
        assert result["statusCode"] == 400

    def test_invalid_state_format_returns_400(self):
        result, _, _ = _invoke({"queryStringParameters": {"code": "abc", "state": "not-valid-base64!!"}})
        assert result["statusCode"] == 400
        assert "Invalid or expired" in result["body"]

    def test_tampered_state_returns_400(self):
        """Attacker tries to swap user_id in state."""
        import base64

        # Craft a tampered state with wrong user but no valid signature
        tampered = base64.urlsafe_b64encode(b"ATTACKER:T01INTERNAL:9999999999:fakesig").decode()
        result, _, _ = _invoke({"queryStringParameters": {"code": "abc", "state": tampered}})
        assert result["statusCode"] == 400
        assert "Invalid or expired" in result["body"]


class TestOAuthFlow:

    @patch("requests.post")
    @patch("requests.get")
    def test_successful_link(self, mock_get, mock_post):
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = {"access_token": "gho_test"}
        mock_post_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_post_resp
        mock_get.return_value = MagicMock(json=lambda: {"login": "octocat", "id": 583231, "company": "@amazon"})

        state = _make_signed_state("U123", "T01INTERNAL")

        with patch("boto3.resource") as mock_resource, \
             patch("boto3.client") as mock_client:

            mock_table = MagicMock()
            mock_table.get_item.return_value = {}
            mock_resource.return_value.Table.return_value = mock_table

            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.return_value = {
                "SecretString": json.dumps(TEST_SECRETS)
            }
            mock_client.return_value = mock_secrets

            lambda_function = _load_identity_lambda()
            lambda_function._oauth_creds = None
            result = lambda_function.lambda_handler(
                {"queryStringParameters": {"code": "valid", "state": state}}, None
            )

        assert result["statusCode"] == 200
        assert "Successfully linked" in result["body"]
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["github_id"] == 583231
        assert item["slack_user_id"] == "U123"
        assert item["affiliation"] == "@amazon"
        assert item["status"] == "active"

    @patch("requests.post")
    @patch("requests.get")
    def test_duplicate_returns_409(self, mock_get, mock_post):
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = {"access_token": "gho_test"}
        mock_post_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_post_resp
        mock_get.return_value = MagicMock(json=lambda: {"login": "octocat", "id": 583231, "company": ""})

        state = _make_signed_state("U123", "T01INTERNAL")

        with patch("boto3.resource") as mock_resource, \
             patch("boto3.client") as mock_client:

            mock_table = MagicMock()
            mock_table.get_item.return_value = {"Item": {"slack_user_id": "U999", "status": "active"}}
            mock_resource.return_value.Table.return_value = mock_table

            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.return_value = {
                "SecretString": json.dumps(TEST_SECRETS)
            }
            mock_client.return_value = mock_secrets

            lambda_function = _load_identity_lambda()
            lambda_function._oauth_creds = None
            result = lambda_function.lambda_handler(
                {"queryStringParameters": {"code": "valid", "state": state}}, None
            )

        assert result["statusCode"] == 409
        assert "already linked" in result["body"]

    @patch("requests.post")
    def test_token_exchange_failure(self, mock_post):
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = {"error": "bad_code"}
        mock_post_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_post_resp

        state = _make_signed_state("U123", "T01INTERNAL")

        with patch("boto3.resource") as mock_resource, \
             patch("boto3.client") as mock_client:

            mock_resource.return_value.Table.return_value = MagicMock()
            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.return_value = {
                "SecretString": json.dumps(TEST_SECRETS)
            }
            mock_client.return_value = mock_secrets

            lambda_function = _load_identity_lambda()
            lambda_function._oauth_creds = None
            result = lambda_function.lambda_handler(
                {"queryStringParameters": {"code": "expired", "state": state}}, None
            )

        assert result["statusCode"] == 400
        assert "authorization failed" in result["body"]

    @patch("requests.post")
    @patch("requests.get")
    def test_user_fetch_failure_returns_400(self, mock_get, mock_post):
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = {"access_token": "gho_test"}
        mock_post_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_post_resp

        import requests as req
        mock_get.side_effect = req.RequestException("Connection timed out")

        state = _make_signed_state("U123", "T01INTERNAL")

        with patch("boto3.resource") as mock_resource, \
             patch("boto3.client") as mock_client:

            mock_resource.return_value.Table.return_value = MagicMock()
            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.return_value = {
                "SecretString": json.dumps(TEST_SECRETS)
            }
            mock_client.return_value = mock_secrets

            lambda_function = _load_identity_lambda()
            lambda_function._oauth_creds = None
            result = lambda_function.lambda_handler(
                {"queryStringParameters": {"code": "valid", "state": state}}, None
            )

        assert result["statusCode"] == 400
        assert "Could not retrieve GitHub profile" in result["body"]


class TestWeeklyValidation:

    @patch("requests.get")
    def test_expires_user_not_in_channel(self, mock_get):
        """User in identity table but not in any monitored channel gets expired."""
        mock_get.return_value = MagicMock(json=lambda: {
            "ok": True,
            "members": ["U999", "U888"],
            "response_metadata": {"next_cursor": ""},
        })

        with patch("boto3.resource") as mock_resource, \
             patch("boto3.client") as mock_client:

            mock_table = MagicMock()
            mock_table.scan.return_value = {
                "Items": [
                    {"github_id": 111, "slack_user_id": "U123"},
                ],
            }
            mock_table.update_item.return_value = {}
            mock_resource.return_value.Table.return_value = mock_table

            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.return_value = {
                "SecretString": json.dumps(TEST_SECRETS)
            }
            mock_client.return_value = mock_secrets

            lambda_function = _load_identity_lambda()
            lambda_function._oauth_creds = None
            result = lambda_function.lambda_handler(
                {"source": "aws.events"}, None
            )

        assert result["expired"] == 1
        mock_table.update_item.assert_called_once()

    @patch("requests.get")
    def test_keeps_user_in_channel(self, mock_get):
        """User present in a monitored channel is not expired."""
        mock_get.return_value = MagicMock(json=lambda: {
            "ok": True,
            "members": ["U123", "U888"],
            "response_metadata": {"next_cursor": ""},
        })

        with patch("boto3.resource") as mock_resource, \
             patch("boto3.client") as mock_client:

            mock_table = MagicMock()
            mock_table.scan.return_value = {
                "Items": [
                    {"github_id": 111, "slack_user_id": "U123"},
                ],
            }
            mock_resource.return_value.Table.return_value = mock_table

            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.return_value = {
                "SecretString": json.dumps(TEST_SECRETS)
            }
            mock_client.return_value = mock_secrets

            lambda_function = _load_identity_lambda()
            lambda_function._oauth_creds = None
            result = lambda_function.lambda_handler(
                {"source": "aws.events"}, None
            )

        assert result["expired"] == 0
        mock_table.update_item.assert_not_called()

    def test_validation_fails_without_bot_token(self):
        """Returns error when SLACK_BOT_TOKEN is missing from secret."""
        secrets_no_token = {k: v for k, v in TEST_SECRETS.items() if k != "SLACK_BOT_TOKEN"}

        with patch("boto3.resource"), \
             patch("boto3.client") as mock_client:

            mock_secrets = MagicMock()
            mock_secrets.get_secret_value.return_value = {
                "SecretString": json.dumps(secrets_no_token)
            }
            mock_client.return_value = mock_secrets

            lambda_function = _load_identity_lambda()
            lambda_function._oauth_creds = None
            result = lambda_function.lambda_handler(
                {"source": "aws.events"}, None
            )

        assert result["error"] == "missing bot token"
