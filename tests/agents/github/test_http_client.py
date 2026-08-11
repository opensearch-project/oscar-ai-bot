# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for agents/github/lambda/http_client.py."""

import importlib.util
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

_GITHUB_LAMBDA_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'github', 'lambda',
))


@pytest.fixture(autouse=True)
def _isolate_module():
    """Load http_client fresh for each test, then clean up."""
    sys.path.insert(0, _GITHUB_LAMBDA_DIR)
    yield
    sys.path.remove(_GITHUB_LAMBDA_DIR)
    sys.modules.pop('http_client', None)


def _load_http_client():
    """Import http_client from the lambda directory."""
    sys.modules.pop('http_client', None)
    spec = importlib.util.spec_from_file_location(
        'http_client', os.path.join(_GITHUB_LAMBDA_DIR, 'http_client.py'),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestHeaders:

    def test_returns_correct_structure(self):
        mod = _load_http_client()
        h = mod.headers("ghp_testtoken123")
        assert h["Authorization"] == "Bearer ghp_testtoken123"
        assert h["Accept"] == "application/vnd.github+json"
        assert "X-GitHub-Api-Version" in h


class TestRequest:

    @patch('requests.request')
    def test_successful_json_response(self, mock_req):
        mod = _load_http_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1, "title": "test"}
        mock_req.return_value = mock_resp

        result = mod.request("GET", "https://api.github.com/repos/org/repo", "token")
        assert result == {"id": 1, "title": "test"}

    @patch('requests.request')
    def test_204_returns_success(self, mock_req):
        mod = _load_http_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_req.return_value = mock_resp

        result = mod.request("PUT", "https://api.github.com/repos/org/repo/pulls/1/merge", "token")
        assert result == {"status": "success"}

    @patch('requests.request')
    def test_client_error_raises_immediately(self, mock_req):
        mod = _load_http_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        mock_req.return_value = mock_resp

        with pytest.raises(mod.GitHubAPIError) as exc_info:
            mod.request("GET", "https://api.github.com/repos/x/y", "token")
        assert exc_info.value.status_code == 404

    @patch('time.sleep')
    @patch('requests.request')
    def test_rate_limit_retries(self, mock_req, mock_sleep):
        mod = _load_http_client()
        rate_resp = MagicMock()
        rate_resp.status_code = 403
        rate_resp.text = "API rate limit exceeded"
        rate_resp.headers = {}

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = {"ok": True}

        mock_req.side_effect = [rate_resp, success_resp]

        result = mod.request("GET", "https://api.github.com/test", "token")
        assert result == {"ok": True}
        assert mock_sleep.called

    @patch('time.sleep')
    @patch('requests.request')
    def test_rate_limit_with_reset_header(self, mock_req, mock_sleep):
        mod = _load_http_client()
        rate_resp = MagicMock()
        rate_resp.status_code = 403
        rate_resp.text = "API rate limit exceeded"
        rate_resp.headers = {"x-ratelimit-reset": str(int(time.time()) + 5)}

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = {"ok": True}

        mock_req.side_effect = [rate_resp, success_resp]

        result = mod.request("GET", "https://api.github.com/test", "token")
        assert result == {"ok": True}
        mock_sleep.assert_called_once()
        wait_time = mock_sleep.call_args[0][0]
        assert 1 <= wait_time <= 60

    @patch('time.sleep')
    @patch('requests.request')
    def test_server_error_retries_and_succeeds(self, mock_req, mock_sleep):
        mod = _load_http_client()
        err_resp = MagicMock()
        err_resp.status_code = 502
        err_resp.text = "Bad Gateway"

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {"data": "recovered"}

        mock_req.side_effect = [err_resp, ok_resp]

        result = mod.request("GET", "https://api.github.com/test", "token")
        assert result == {"data": "recovered"}
        assert mock_sleep.call_count == 1

    @patch('time.sleep')
    @patch('requests.request')
    def test_server_error_exhausts_retries(self, mock_req, mock_sleep):
        mod = _load_http_client()
        err_resp = MagicMock()
        err_resp.status_code = 500
        err_resp.text = "Internal Server Error"
        mock_req.return_value = err_resp

        with pytest.raises(mod.GitHubAPIError) as exc_info:
            mod.request("GET", "https://api.github.com/test", "token")
        assert exc_info.value.status_code == 500
        assert mock_req.call_count == 3

    @patch('time.sleep')
    @patch('requests.request')
    def test_request_exception_retries(self, mock_req, mock_sleep):
        import requests as req_lib
        mod = _load_http_client()

        mock_req.side_effect = [
            req_lib.ConnectionError("Connection refused"),
            req_lib.ConnectionError("Connection refused"),
            req_lib.ConnectionError("Connection refused"),
        ]

        with pytest.raises(req_lib.ConnectionError):
            mod.request("GET", "https://api.github.com/test", "token")
        assert mock_req.call_count == 3


class TestGetPutPost:

    @patch('requests.request')
    def test_get_prepends_api_base(self, mock_req):
        mod = _load_http_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"items": []}
        mock_req.return_value = mock_resp

        mod.get("token", "/repos/opensearch-project/OpenSearch/pulls")
        call_args = mock_req.call_args
        assert call_args[0][1] == "https://api.github.com/repos/opensearch-project/OpenSearch/pulls"

    @patch('requests.request')
    def test_put_sends_json_body(self, mock_req):
        mod = _load_http_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"merged": True}
        mock_req.return_value = mock_resp

        mod.put("token", "/repos/org/repo/pulls/1/merge", {"merge_method": "squash"})
        call_args = mock_req.call_args
        assert call_args[1]["json"] == {"merge_method": "squash"}

    @patch('requests.request')
    def test_post_sends_json_body(self, mock_req):
        mod = _load_http_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 99}
        mock_req.return_value = mock_resp

        mod.post("token", "/repos/org/repo/issues", {"title": "Bug"})
        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"
        assert call_args[1]["json"] == {"title": "Bug"}


class TestGitHubAPIError:

    def test_attributes(self):
        mod = _load_http_client()
        err = mod.GitHubAPIError(422, "Validation Failed", "https://api.github.com/repos/x")
        assert err.status_code == 422
        assert err.url == "https://api.github.com/repos/x"
        assert "422" in str(err)
        assert "Validation Failed" in str(err)


class TestTokenManager:

    @patch('jwt.encode', return_value='fake-jwt-token')
    @patch('requests.post')
    def test_get_token_fresh(self, mock_post, mock_jwt):
        mod = _load_http_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "token": "ghs_test123",
            "expires_at": "2099-01-01T00:00:00Z",
        }
        mock_post.return_value = mock_resp

        tm = mod.TokenManager("12345", "fake-key", "67890")
        token, expires = tm.get_token(repositories=["OpenSearch"])

        assert token == "ghs_test123"
        assert expires > time.time()
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1].get("json")
        assert call_json == {"repositories": ["OpenSearch"]}

    @patch('jwt.encode', return_value='fake-jwt-token')
    @patch('requests.post')
    def test_get_token_cached(self, mock_post, mock_jwt):
        mod = _load_http_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "token": "ghs_cached",
            "expires_at": "2099-01-01T00:00:00Z",
        }
        mock_post.return_value = mock_resp

        tm = mod.TokenManager("12345", "fake-key", "67890")
        tm.get_token(repositories=["OpenSearch"])
        mock_post.reset_mock()

        token, _ = tm.get_token(repositories=["OpenSearch"])
        assert token == "ghs_cached"
        mock_post.assert_not_called()

    @patch('jwt.encode', return_value='fake-jwt-token')
    @patch('requests.post')
    def test_get_token_org_wide(self, mock_post, mock_jwt):
        mod = _load_http_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "token": "ghs_org",
            "expires_at": "2099-01-01T00:00:00Z",
        }
        mock_post.return_value = mock_resp

        tm = mod.TokenManager("12345", "fake-key", "67890")
        token, _ = tm.get_token(repositories=None)

        assert token == "ghs_org"
        call_json = mock_post.call_args[1].get("json")
        assert call_json is None

    @patch('jwt.encode', return_value='fake-jwt-token')
    @patch('requests.post')
    def test_get_token_refreshes_on_scope_change(self, mock_post, mock_jwt):
        mod = _load_http_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "token": "ghs_new_scope",
            "expires_at": "2099-01-01T00:00:00Z",
        }
        mock_post.return_value = mock_resp

        tm = mod.TokenManager("12345", "fake-key", "67890")
        tm.get_token(repositories=["RepoA"])
        mock_post.reset_mock()

        # Request a different repo — should trigger refresh
        tm.get_token(repositories=["RepoB"])
        mock_post.assert_called_once()

    @patch('jwt.encode', return_value='fake-jwt-token')
    @patch('requests.post')
    def test_get_token_no_expires_at_defaults(self, mock_post, mock_jwt):
        mod = _load_http_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"token": "ghs_noexpiry"}
        mock_post.return_value = mock_resp

        tm = mod.TokenManager("12345", "fake-key", "67890")
        token, expires = tm.get_token()

        assert token == "ghs_noexpiry"
        assert expires > time.time()
        assert expires <= time.time() + 3601

    def test_needs_refresh_expired(self):
        mod = _load_http_client()
        tm = mod.TokenManager("12345", "fake-key", "67890")
        tm._token = "old"
        tm._token_expires_at = time.time() - 100
        assert tm.needs_refresh() is True

    def test_needs_refresh_within_buffer(self):
        mod = _load_http_client()
        tm = mod.TokenManager("12345", "fake-key", "67890")
        tm._token = "old"
        tm._token_expires_at = time.time() + 100  # within 300s buffer
        assert tm.needs_refresh() is True

    def test_needs_refresh_false_when_fresh(self):
        mod = _load_http_client()
        tm = mod.TokenManager("12345", "fake-key", "67890")
        tm._token = "valid"
        tm._token_expires_at = time.time() + 3600
        tm._token_repos = frozenset(["OpenSearch"])
        assert tm.needs_refresh(repositories=["OpenSearch"]) is False

    def test_needs_refresh_true_when_new_repo_requested(self):
        mod = _load_http_client()
        tm = mod.TokenManager("12345", "fake-key", "67890")
        tm._token = "valid"
        tm._token_expires_at = time.time() + 3600
        tm._token_repos = frozenset(["OpenSearch"])
        assert tm.needs_refresh(repositories=["NewRepo"]) is True
