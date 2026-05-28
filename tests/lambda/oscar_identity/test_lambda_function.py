# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the identity OAuth callback Lambda."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add Lambda source path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lambda', 'oscar-identity'))

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


@pytest.fixture(autouse=True)
def clear_module_cache():
    """Ensure lambda_function is reimported fresh each test."""
    yield
    for mod in list(sys.modules.keys()):
        if "lambda_function" in mod:
            del sys.modules[mod]


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

        import lambda_function
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

            import lambda_function
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

            import lambda_function
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

            import lambda_function
            lambda_function._oauth_creds = None
            result = lambda_function.lambda_handler(
                {"queryStringParameters": {"code": "expired", "state": state}}, None
            )

        assert result["statusCode"] == 400
        assert "authorization failed" in result["body"]