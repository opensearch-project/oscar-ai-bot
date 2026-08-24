# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for agents/github/lambda/lambda_function.py — transforms, parsing, and handler routing."""

import importlib.util
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_GITHUB_LAMBDA_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'github', 'lambda',
))
_SHARED_LAYER_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'lambda', 'shared-layer', 'python',
))


@pytest.fixture(autouse=True)
def _isolate():
    yield
    for mod_name in ['lambda_function', 'authorizer', 'guardrails',
                     'github_api', 'http_client', 'mcp_client',
                     'response_builder', 'registry']:
        sys.modules.pop(mod_name, None)


def _load_lambda(guardrails_overrides=None):
    """Load lambda_function with fully mocked dependencies."""
    sys.path.insert(0, _SHARED_LAYER_DIR)
    sys.path.insert(0, _GITHUB_LAMBDA_DIR)
    try:
        for mod_name in ['lambda_function', 'authorizer', 'guardrails',
                         'github_api', 'http_client', 'mcp_client',
                         'response_builder', 'registry']:
            sys.modules.pop(mod_name, None)

        mock_mcp = MagicMock()
        mock_mcp.MCPClient.return_value.get_token.return_value = 'fake-token'
        mock_mcp.MCPClient.return_value.call_tool.return_value = json.dumps({"status": "success"})
        sys.modules['mcp_client'] = mock_mcp

        mock_http = MagicMock()
        mock_http.ORG = 'opensearch-project'
        mock_http.GitHubAPIError = type('GitHubAPIError', (Exception,), {
            '__init__': lambda self, sc, msg, url: (
                setattr(self, 'status_code', sc) or
                setattr(self, 'url', url) or
                Exception.__init__(self, f"GitHub API error {sc} for {url}: {msg}")
            ),
            'status_code': 500,
        })
        sys.modules['http_client'] = mock_http

        mock_github_api = MagicMock()
        mock_github_api.add_comment.return_value = json.dumps({"status": "success"})
        mock_github_api.bulk_comment.return_value = json.dumps({"status": "success", "commented": 2})
        mock_github_api.transfer_issue.return_value = json.dumps({"status": "success"})
        mock_github_api.get_repo_maintainers.return_value = json.dumps({"maintainers": ["user1"]})
        sys.modules['github_api'] = mock_github_api

        mock_guardrails = MagicMock()
        mock_guardrails.validate_single_pr.return_value = {"all_passed": True, "head_sha": "abc123"}
        mock_guardrails.validate_comment.return_value = {"all_passed": True}
        mock_guardrails.validate_bulk_comment.return_value = {"all_passed": True}
        mock_guardrails.validate_transfer_issue.return_value = {"all_passed": True}
        mock_guardrails.bulk_merge.return_value = json.dumps({"status": "success", "merged_count": 3})
        mock_guardrails.list_merge_candidates.return_value = json.dumps({"candidates": []})
        if guardrails_overrides:
            for k, v in guardrails_overrides.items():
                setattr(mock_guardrails, k, v)
        sys.modules['guardrails'] = mock_guardrails

        mock_authorizer = MagicMock()
        mock_authorizer.validate_org_scope.return_value = None
        mock_authorizer.audit_log = MagicMock()
        sys.modules['authorizer'] = mock_authorizer

        mock_rb = MagicMock()
        mock_rb.create_response.side_effect = lambda event, result: {
            'response': {
                'functionResponse': {
                    'responseBody': {
                        'TEXT': {'body': json.dumps(result) if isinstance(result, dict) else str(result)}
                    }
                }
            },
            'messageVersion': '1.0',
        }
        sys.modules['response_builder'] = mock_rb

        spec = importlib.util.spec_from_file_location(
            'lambda_function', os.path.join(_GITHUB_LAMBDA_DIR, 'lambda_function.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if _GITHUB_LAMBDA_DIR in sys.path:
            sys.path.remove(_GITHUB_LAMBDA_DIR)
        if _SHARED_LAYER_DIR in sys.path:
            sys.path.remove(_SHARED_LAYER_DIR)


def _get_body(result):
    return result['response']['functionResponse']['responseBody']['TEXT']['body']


class TestParseParams:

    def test_standard_params(self):
        mod = _load_lambda()
        event = {"parameters": [
            {"name": "repo", "value": "OpenSearch"},
            {"name": "pr_number", "value": "42"},
        ]}
        params = mod._parse_params(event)
        assert params == {"repo": "OpenSearch", "pr_number": "42"}

    def test_empty_params(self):
        mod = _load_lambda()
        assert mod._parse_params({}) == {}
        assert mod._parse_params({"parameters": []}) == {}

    def test_malformed_params_skipped(self):
        mod = _load_lambda()
        event = {"parameters": [
            {"name": "repo", "value": "OpenSearch"},
            {"bad": "entry"},
            "not-a-dict",
        ]}
        params = mod._parse_params(event)
        assert params == {"repo": "OpenSearch"}


class TestTransforms:

    def test_transform_get_pr_details(self):
        mod = _load_lambda()
        result = mod._transform_get_pr_details({"repo": "OpenSearch", "pr_number": "42"})
        assert result["pullNumber"] == 42
        assert result["method"] == "get"
        assert "pr_number" not in result

    def test_transform_get_issue_details(self):
        mod = _load_lambda()
        result = mod._transform_get_issue_details({"repo": "OpenSearch", "issue_number": "10"})
        assert result["issue_number"] == 10
        assert result["method"] == "get"

    def test_transform_list_issues_with_state_and_labels(self):
        mod = _load_lambda()
        result = mod._transform_list_issues({"state": "open", "labels": "bug, enhancement"})
        assert result["state"] == "OPEN"
        assert result["labels"] == ["bug", "enhancement"]

    def test_transform_list_issues_no_labels(self):
        mod = _load_lambda()
        result = mod._transform_list_issues({"state": "closed"})
        assert result["state"] == "CLOSED"
        assert "labels" not in result

    def test_transform_merge_pr(self):
        mod = _load_lambda()
        result = mod._transform_merge_pr({"repo": "OpenSearch", "pr_number": "5", "force": "true"})
        assert result["pullNumber"] == 5
        assert result["merge_method"] == "merge"
        assert "force" not in result

    def test_transform_merge_pr_custom_method(self):
        mod = _load_lambda()
        result = mod._transform_merge_pr({"repo": "R", "pr_number": "1", "merge_method": "squash"})
        assert result["merge_method"] == "squash"

    def test_transform_create_issue(self):
        mod = _load_lambda()
        result = mod._transform_create_issue({
            "title": "Bug", "labels": "bug,urgent", "assignees": "user1, user2",
        })
        assert result["method"] == "create"
        assert result["labels"] == ["bug", "urgent"]
        assert result["assignees"] == ["user1", "user2"]

    def test_transform_close_issue(self):
        mod = _load_lambda()
        result = mod._transform_close_issue({"issue_number": "7", "reason": "not_planned"})
        assert result["method"] == "update"
        assert result["issue_number"] == 7
        assert result["state"] == "closed"
        assert result["state_reason"] == "not_planned"

    def test_transform_close_issue_default_reason(self):
        mod = _load_lambda()
        result = mod._transform_close_issue({"issue_number": "7"})
        assert result["state_reason"] == "completed"

    def test_transform_search_issues_adds_org(self):
        mod = _load_lambda()
        result = mod._transform_search_issues({"query": "is:open label:bug"})
        assert "org:opensearch-project" in result["query"]

    def test_transform_search_issues_no_duplicate_org(self):
        mod = _load_lambda()
        result = mod._transform_search_issues({"query": "org:opensearch-project is:open"})
        assert result["query"].count("org:opensearch-project") == 1

    def test_transform_search_pull_requests_adds_org(self):
        mod = _load_lambda()
        result = mod._transform_search_pull_requests({"query": "is:merged"})
        assert "org:opensearch-project" in result["query"]


class TestParseIssueTargets:

    def test_parses_targets(self):
        mod = _load_lambda()
        targets = mod._parse_issue_targets("OpenSearch#1,OpenSearch-Dashboards#2")
        assert targets == [("OpenSearch", 1), ("OpenSearch-Dashboards", 2)]

    def test_handles_whitespace(self):
        mod = _load_lambda()
        targets = mod._parse_issue_targets(" OpenSearch#10 , Repo#20 ")
        assert targets == [("OpenSearch", 10), ("Repo", 20)]

    def test_skips_invalid_entries(self):
        mod = _load_lambda()
        targets = mod._parse_issue_targets("OpenSearch#1,invalid,Repo#3")
        assert targets == [("OpenSearch", 1), ("Repo", 3)]


class TestLambdaHandlerRouting:

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_unknown_function(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({"function": "nonexistent", "parameters": []}, None)
        body = _get_body(result)
        assert "Unknown function" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_org_validation_failure(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        sys.modules['authorizer'].validate_org_scope.return_value = "Operation rejected"

        result = mod.lambda_handler({
            "function": "list_issues",
            "parameters": [{"name": "organization", "value": "evil-org"}],
        }, None)
        body = _get_body(result)
        assert "Operation rejected" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_direct_api_handler_add_comment(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "add_comment",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "issue_number", "value": "5"},
                {"name": "body", "value": "Hello"},
            ],
        }, None)
        body = _get_body(result)
        assert "success" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_mcp_routed_function(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "get_pr_details",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "pr_number", "value": "100"},
            ],
        }, None)
        body = _get_body(result)
        assert "success" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_get_repo_maintainers(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "get_repo_maintainers",
            "parameters": [{"name": "repo", "value": "OpenSearch"}],
        }, None)
        body = _get_body(result)
        assert "maintainers" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_bulk_merge_no_confirmed_param(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "bulk_merge_prs",
            "parameters": [{"name": "version", "value": "3.0.0"}],
        }, None)
        body = _get_body(result)
        assert "SECURITY ERROR" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_bulk_merge_confirmed_false(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "bulk_merge_prs",
            "parameters": [
                {"name": "version", "value": "3.0.0"},
                {"name": "confirmed", "value": "false"},
            ],
        }, None)
        body = _get_body(result)
        assert "cancelled" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_list_merge_candidates(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "list_merge_candidates",
            "parameters": [{"name": "version", "value": "3.0.0"}],
        }, None)
        body = _get_body(result)
        assert "candidates" in body


class TestGuardrailBlocking:

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_merge_pr_guardrail_failure_blocks(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        guardrail_fail = MagicMock(return_value={"all_passed": False, "message": "CI failing"})
        mod = _load_lambda(guardrails_overrides={"validate_single_pr": guardrail_fail})

        result = mod.lambda_handler({
            "function": "merge_pr",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "pr_number", "value": "10"},
            ],
        }, None)
        body = _get_body(result)
        assert "CI failing" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_add_comment_guardrail_failure_blocks(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        guardrail_fail = MagicMock(return_value={"all_passed": False, "message": "Comment rejected"})
        mod = _load_lambda(guardrails_overrides={"validate_comment": guardrail_fail})

        result = mod.lambda_handler({
            "function": "add_comment",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "issue_number", "value": "5"},
                {"name": "body", "value": "spam"},
            ],
        }, None)
        body = _get_body(result)
        assert "Comment rejected" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_merge_pr_force_requires_2pr(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        guardrail_fail = MagicMock(return_value={"all_passed": False, "message": "CI failing"})
        mod = _load_lambda(guardrails_overrides={"validate_single_pr": guardrail_fail})

        result = mod.lambda_handler({
            "function": "merge_pr",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "pr_number", "value": "10"},
                {"name": "force", "value": "true"},
            ],
            "sessionAttributes": {},
        }, None)
        body = _get_body(result)
        assert "SECURITY ERROR" in body


class TestTransferIssue:

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_transfer_issue_requires_2pr(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "transfer_issue",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "issue_number", "value": "5"},
                {"name": "target_repo", "value": "other-repo"},
            ],
            "sessionAttributes": {},
        }, None)
        body = _get_body(result)
        assert "SECURITY ERROR" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_transfer_issue_succeeds_without_2pr(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "transfer_issue",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "issue_number", "value": "5"},
                {"name": "target_repo", "value": "other-repo"},
            ],
        }, None)
        body = _get_body(result)
        assert "success" in body
