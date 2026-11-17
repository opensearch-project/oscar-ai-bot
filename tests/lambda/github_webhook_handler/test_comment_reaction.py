# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_MODULE_PATH = Path(__file__).resolve().parents[3] / "lambda" / "github-webhook-handler" / "lambda_function.py"
with patch("boto3.client"):
    _spec = importlib.util.spec_from_file_location("ghwh", _MODULE_PATH)
    mod = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = mod
    _spec.loader.exec_module(mod)

_PAYLOAD = {"comment": {"id": 123}, "repository": {"full_name": "org/repo"}}
_CREDS = {"GITHUB_APP_ID": "1", "GITHUB_PRIVATE_KEY": "k", "GITHUB_INSTALLATION_ID": "2"}


class TestReactToComment:
    @patch.object(mod, "_github_creds", return_value={})
    def test_no_creds_skips(self, _):
        mod._react_to_comment(_PAYLOAD)

    @patch.object(mod, "requests")
    @patch.object(mod, "jwt")
    @patch.object(mod, "_github_creds", return_value=_CREDS)
    def test_happy_path(self, _, mock_jwt, mock_req):
        mock_jwt.encode.return_value = "j"
        mock_req.post.side_effect = [
            MagicMock(status_code=201, json=MagicMock(return_value={"token": "t"})),
            MagicMock(status_code=201),
        ]
        mod._react_to_comment(_PAYLOAD)
        assert mock_req.post.call_count == 2
        assert "/comments/123/reactions" in mock_req.post.call_args_list[1].args[0]

    @patch.object(mod, "requests")
    @patch.object(mod, "jwt")
    @patch.object(mod, "_github_creds", return_value=_CREDS)
    def test_token_failure_stops(self, _, mock_jwt, mock_req):
        mock_jwt.encode.return_value = "j"
        mock_req.post.return_value = MagicMock(status_code=401)
        mod._react_to_comment(_PAYLOAD)
        assert mock_req.post.call_count == 1

    @patch.object(mod, "requests")
    @patch.object(mod, "jwt")
    @patch.object(mod, "_github_creds", return_value=_CREDS)
    def test_exception_swallowed(self, _, mock_jwt, mock_req):
        mock_jwt.encode.return_value = "j"
        mock_req.post.side_effect = Exception("net")
        mod._react_to_comment(_PAYLOAD)


class TestGithubCreds:
    def setup_method(self):
        mod._cached_github_creds = None

    def teardown_method(self):
        mod._cached_github_creds = None

    @patch.dict("os.environ", {"GITHUB_ENV_SECRET_NAME": ""})
    def test_no_env_returns_empty(self):
        assert mod._github_creds() == {}

    @patch.object(mod, "boto3")
    @patch.dict("os.environ", {"GITHUB_ENV_SECRET_NAME": "s"})
    def test_loads_and_caches(self, mock_boto):
        mock_boto.client.return_value.get_secret_value.return_value = {"SecretString": '{"k":"v"}'}
        assert mod._github_creds() == {"k": "v"}
        mod._github_creds()
        mock_boto.client.return_value.get_secret_value.assert_called_once()
