# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for GitHub comment reaction in the webhook handler."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_MODULE_PATH = Path(__file__).resolve().parents[3] / "lambda" / "github-webhook-handler" / "lambda_function.py"

with patch("boto3.client"):
    _spec = importlib.util.spec_from_file_location("github_webhook_lambda_function", _MODULE_PATH)
    lambda_function = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = lambda_function
    _spec.loader.exec_module(lambda_function)

_react_to_comment = lambda_function._react_to_comment

_PAYLOAD = {
    "comment": {"id": 12345, "body": "@oscar-bot help"},
    "repository": {"full_name": "opensearch-project/test-repo"},
}

_GITHUB_CREDS = {
    "GITHUB_APP_ID": "123",
    "GITHUB_PRIVATE_KEY": "fake-key",
    "GITHUB_INSTALLATION_ID": "456",
}


class TestReactToComment:
    @patch.object(lambda_function, "_github_creds", return_value={})
    def test_skips_when_no_github_creds(self, _mock_creds):
        _react_to_comment(_PAYLOAD)

    @patch.object(lambda_function, "requests")
    @patch.object(lambda_function, "jwt")
    @patch.object(lambda_function, "_github_creds", return_value=_GITHUB_CREDS)
    def test_calls_reaction_api_on_success(self, _mock_creds, mock_jwt, mock_requests):
        mock_jwt.encode.return_value = "fake-jwt"
        token_resp = MagicMock(status_code=201)
        token_resp.json.return_value = {"token": "inst-token"}
        reaction_resp = MagicMock(status_code=201)
        mock_requests.post.side_effect = [token_resp, reaction_resp]

        _react_to_comment(_PAYLOAD)

        assert mock_requests.post.call_count == 2
        reaction_call = mock_requests.post.call_args_list[1]
        assert "/issues/comments/12345/reactions" in reaction_call.args[0]
        assert reaction_call.kwargs["json"] == {"content": "eyes"}

    @patch.object(lambda_function, "requests")
    @patch.object(lambda_function, "jwt")
    @patch.object(lambda_function, "_github_creds", return_value=_GITHUB_CREDS)
    def test_returns_silently_on_token_failure(self, _mock_creds, mock_jwt, mock_requests):
        mock_jwt.encode.return_value = "fake-jwt"
        mock_requests.post.return_value = MagicMock(status_code=401)
        _react_to_comment(_PAYLOAD)
        assert mock_requests.post.call_count == 1

    @patch.object(lambda_function, "requests")
    @patch.object(lambda_function, "jwt")
    @patch.object(lambda_function, "_github_creds", return_value=_GITHUB_CREDS)
    def test_swallows_exceptions(self, _mock_creds, mock_jwt, mock_requests):
        mock_jwt.encode.return_value = "fake-jwt"
        mock_requests.post.side_effect = Exception("network")
        _react_to_comment(_PAYLOAD)
