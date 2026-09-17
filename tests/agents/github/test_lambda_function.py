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
            "sessionAttributes": {"requester_user_id": "U_ADM", "requester_is_admin": "True", "requester_tier": "admin"},
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
            "sessionAttributes": {"requester_user_id": "U_ADM", "requester_is_admin": "True", "requester_tier": "admin"},
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
            "sessionAttributes": {"requester_user_id": "U_ADM", "requester_is_admin": "True", "requester_tier": "admin"},
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
            "sessionAttributes": {"requester_user_id": "U_ADM", "requester_is_admin": "True", "requester_tier": "admin"},
        }, None)
        body = _get_body(result)
        assert "CI failing" in body

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
            "sessionAttributes": {"requester_user_id": "U_ADM", "requester_is_admin": "True", "requester_tier": "admin", "approver_is_admin": "True"},
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
            "sessionAttributes": {"requester_user_id": "U_ADM", "requester_is_admin": "True", "requester_tier": "admin", "approver_is_admin": "True"},
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
            "sessionAttributes": {"requester_user_id": "U_ADM", "requester_is_admin": "True", "requester_tier": "admin"},
        }, None)
        body = _get_body(result)
        assert "success" in body


class TestGroupGate:
    """Verify that the group gate rejects unauthorized users before token acquisition."""

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_contributor_blocked_from_admin_function(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "merge_pr",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "pr_number", "value": "10"},
            ],
            "sessionAttributes": {
                "requester_user_id": "U_CONTRIB",
                "requester_is_admin": "False",
                "requester_tier": "contributor",
                "requester_is_maintainer": "False",
            },
        }, None)
        body = _get_body(result)
        assert "AUTHORIZATION ERROR" in body
        assert "admin privileges" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_maintainer_blocked_from_admin_function(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "bulk_comment",
            "parameters": [
                {"name": "issues", "value": "OpenSearch#1"},
                {"name": "body", "value": "test"},
            ],
            "sessionAttributes": {
                "requester_user_id": "U_MAINT",
                "requester_is_admin": "False",
                "requester_tier": "maintainer",
                "requester_is_maintainer": "True",
            },
        }, None)
        body = _get_body(result)
        assert "AUTHORIZATION ERROR" in body
        assert "admin privileges" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_admin_passes_group_gate_for_maintainer_function(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "create_tag",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "tag_name", "value": "3.0.0"},
            ],
            "sessionAttributes": {
                "requester_user_id": "U_ADM",
                "requester_is_admin": "True",
                "requester_tier": "admin",
                "requester_is_maintainer": "False",
            },
        }, None)
        body = _get_body(result)
        assert "AUTHORIZATION ERROR" not in body or "maintainer privileges" not in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_non_maintainer_blocked_from_maintainer_function(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "create_tag",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "tag_name", "value": "3.0.0"},
            ],
            "sessionAttributes": {
                "requester_user_id": "U_CONTRIB",
                "requester_is_admin": "False",
                "requester_tier": "contributor",
                "requester_is_maintainer": "False",
            },
        }, None)
        body = _get_body(result)
        assert "AUTHORIZATION ERROR" in body
        assert "maintainer privileges" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_contributor_passes_group_gate_for_read_ops(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "list_prs",
            "parameters": [{"name": "repo", "value": "OpenSearch"}],
            "sessionAttributes": {
                "requester_user_id": "U_CONTRIB",
                "requester_is_admin": "False",
                "requester_tier": "contributor",
                "requester_is_maintainer": "False",
            },
        }, None)
        body = _get_body(result)
        assert "AUTHORIZATION ERROR" not in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_github_enable_2pr_flag_enforces_2pr(self, mock_boto):
        """GITHUB_ENABLE_2PR alone (without ENABLE_2PR) enforces 2PR on writes."""
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "bulk_comment",
            "parameters": [
                {"name": "issues", "value": "OpenSearch#1"},
                {"name": "body", "value": "test"},
            ],
            "sessionAttributes": {
                "requester_user_id": "U_ADM",
                "requester_is_admin": "True",
                "requester_tier": "admin",
            },
        }, None)
        body = _get_body(result)
        assert "SECURITY ERROR" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_non_admin_blocked_from_create_issue(self, mock_boto):
        """Non-admin users are blocked from create_issue by group gate."""
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "create_issue",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "title", "value": "test issue"},
            ],
            "sessionAttributes": {
                "requester_user_id": "U_CONTRIB",
                "requester_is_admin": "False",
                "requester_tier": "contributor",
            },
        }, None)
        body = _get_body(result)
        assert "AUTHORIZATION ERROR" in body
        assert "admin privileges" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_admin_passes_group_gate_for_admin_ops(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "list_merge_candidates",
            "parameters": [{"name": "version", "value": "3.0.0"}],
            "sessionAttributes": {
                "requester_user_id": "U_ADM",
                "requester_is_admin": "True",
                "requester_tier": "admin",
            },
        }, None)
        body = _get_body(result)
        assert "AUTHORIZATION ERROR" not in body


class TestValidateRefName:
    """Cover _validate_ref_name: empty, invalid sequences, bad chars."""

    def test_empty_name_returns_error(self):
        mod = _load_lambda()
        result = mod._validate_ref_name("", "Tag")
        assert result["status"] == "error"
        assert "must not be empty" in result["message"]

    def test_double_dot_rejected(self):
        mod = _load_lambda()
        result = mod._validate_ref_name("v1..2", "Tag")
        assert result["status"] == "error"
        assert "invalid sequences" in result["message"]

    def test_starts_with_dot_rejected(self):
        mod = _load_lambda()
        result = mod._validate_ref_name(".hidden", "Branch")
        assert result["status"] == "error"
        assert "invalid sequences" in result["message"]

    def test_ends_with_lock_rejected(self):
        mod = _load_lambda()
        result = mod._validate_ref_name("main.lock", "Branch")
        assert result["status"] == "error"
        assert "invalid sequences" in result["message"]

    def test_starts_with_dash_rejected(self):
        mod = _load_lambda()
        result = mod._validate_ref_name("-bad", "Tag")
        assert result["status"] == "error"
        assert "invalid sequences" in result["message"]

    def test_invalid_chars_rejected(self):
        mod = _load_lambda()
        result = mod._validate_ref_name("v1.0 beta", "Tag")
        assert result["status"] == "error"
        assert "invalid characters" in result["message"]

    def test_valid_name_returns_none(self):
        mod = _load_lambda()
        assert mod._validate_ref_name("v3.0.0", "Tag") is None

    def test_valid_name_with_slash(self):
        mod = _load_lambda()
        assert mod._validate_ref_name("release/3.0", "Branch") is None


class TestResolveCommitSha:
    """Cover _resolve_commit_sha: empty SHA → HEAD, short SHA → expand."""

    @patch.dict(os.environ, {'GITHUB_SECRET_NAME': 'test'})
    def test_empty_sha_resolves_to_head(self):
        mod = _load_lambda()
        mock_get = sys.modules['http_client'].get
        mock_get.side_effect = [
            {"default_branch": "main"},
            {"commit": {"sha": "abc123full"}},
        ]
        result = mod._resolve_commit_sha("tok", "OpenSearch", "")
        assert result == "abc123full"
        assert mock_get.call_count == 2

    @patch.dict(os.environ, {'GITHUB_SECRET_NAME': 'test'})
    def test_short_sha_expanded(self):
        mod = _load_lambda()
        mock_get = sys.modules['http_client'].get
        mock_get.return_value = {"sha": "abc123fullexpanded"}
        result = mod._resolve_commit_sha("tok", "OpenSearch", "abc123")
        assert result == "abc123fullexpanded"

    @patch.dict(os.environ, {'GITHUB_SECRET_NAME': 'test'})
    def test_full_sha_returned_as_is(self):
        mod = _load_lambda()
        full = "a" * 40
        result = mod._resolve_commit_sha("tok", "OpenSearch", full)
        assert result == full


class TestIsRepoMaintainer:
    """Cover _is_repo_maintainer: admin, no handle, in maintainers, not in maintainers."""

    def test_admin_always_true(self):
        mod = _load_lambda()
        assert mod._is_repo_maintainer("tok", "repo", "", "True") is True

    def test_no_handle_returns_false(self):
        mod = _load_lambda()
        assert mod._is_repo_maintainer("tok", "repo", "", "False") is False

    def test_maintainer_in_list(self):
        mod = _load_lambda()
        sys.modules['github_api'].get_repo_maintainers.return_value = json.dumps({
            "status": "success",
            "maintainers": [{"github_id": "alice"}, {"github_id": "bob"}],
        })
        assert mod._is_repo_maintainer("tok", "repo", "alice", "False") is True

    def test_not_in_maintainer_list(self):
        mod = _load_lambda()
        sys.modules['github_api'].get_repo_maintainers.return_value = json.dumps({
            "status": "success",
            "maintainers": [{"github_id": "alice"}],
        })
        assert mod._is_repo_maintainer("tok", "repo", "bob", "False") is False

    def test_maintainer_lookup_failure(self):
        mod = _load_lambda()
        sys.modules['github_api'].get_repo_maintainers.return_value = json.dumps({
            "status": "error",
        })
        assert mod._is_repo_maintainer("tok", "repo", "alice", "False") is False


class TestValidateAdminOnly:
    """Cover _validate_admin_only: non-admin rejected, admin passes."""

    def test_non_admin_rejected(self):
        mod = _load_lambda()
        result = mod._validate_admin_only({"requester_is_admin": "False"}, "close_issue")
        assert result["status"] == "error"
        assert "admin privileges" in result["message"]

    def test_admin_passes(self):
        mod = _load_lambda()
        result = mod._validate_admin_only({"requester_is_admin": "True"}, "close_issue")
        assert result is None


class TestValidateMaintainerAuthorization:
    """Cover _validate_maintainer_authorization: missing requester, non-maintainer, passes."""

    def test_missing_requester_rejected(self):
        mod = _load_lambda()
        result = mod._validate_maintainer_authorization("tok", "repo", {}, "create_tag")
        assert result["status"] == "error"
        assert "requester" in result["message"]

    def test_non_maintainer_rejected(self):
        mod = _load_lambda()
        sys.modules['github_api'].get_repo_maintainers.return_value = json.dumps({
            "status": "success",
            "maintainers": [{"github_id": "alice"}],
        })
        result = mod._validate_maintainer_authorization(
            "tok", "repo",
            {"requester_user_id": "U1", "requester_is_admin": "False", "requester_github_handle": "bob"},
            "create_tag on repo",
        )
        assert result["status"] == "error"
        assert "not an admin or maintainer" in result["message"]

    def test_maintainer_passes(self):
        mod = _load_lambda()
        sys.modules['github_api'].get_repo_maintainers.return_value = json.dumps({
            "status": "success",
            "maintainers": [{"github_id": "alice"}],
        })
        result = mod._validate_maintainer_authorization(
            "tok", "repo",
            {"requester_user_id": "U1", "requester_is_admin": "False", "requester_github_handle": "alice"},
            "create_tag on repo",
        )
        assert result is None


class TestHandleCreateRef:
    """Cover _handle_create_ref: validation error, auth error."""

    @patch.dict(os.environ, {'GITHUB_SECRET_NAME': 'test'})
    def test_invalid_ref_name_returns_error(self):
        mod = _load_lambda()
        result = mod._handle_create_ref(
            "tok", {"repo": "OpenSearch", "tag_name": ""}, "req1",
            {"requester_user_id": "U1", "requester_is_admin": "True"},
            ref_type="tags",
        )
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "must not be empty" in parsed["message"]

    @patch.dict(os.environ, {'GITHUB_SECRET_NAME': 'test'})
    def test_auth_error_returns_error(self):
        mod = _load_lambda()
        sys.modules['github_api'].get_repo_maintainers.return_value = json.dumps({
            "status": "success", "maintainers": [],
        })
        result = mod._handle_create_ref(
            "tok", {"repo": "OpenSearch", "tag_name": "v1.0.0"}, "req1",
            {"requester_user_id": "U1", "requester_is_admin": "False", "requester_github_handle": "nobody"},
            ref_type="tags",
        )
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "not an admin or maintainer" in parsed["message"]


class TestFunctionGateAdminPolicy:
    """Cover the per-function admin gate (lines 552-556) in lambda_handler."""

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_non_admin_blocked_by_function_gate(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "close_issue",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "issue_number", "value": "7"},
            ],
            "sessionAttributes": {
                "requester_user_id": "U_NON",
                "requester_is_admin": "False",
                "requester_tier": "admin",
            },
        }, None)
        body = _get_body(result)
        assert "admin privileges" in body


class TestTwoPRApprovalInHandler:
    """Cover the 2PR approval_error branch (lines 555-556) in lambda_handler."""

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_2pr_rejection_returned(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        result = mod.lambda_handler({
            "function": "close_issue",
            "parameters": [
                {"name": "repo", "value": "OpenSearch"},
                {"name": "issue_number", "value": "7"},
            ],
            "sessionAttributes": {
                "requester_user_id": "U_ADM",
                "requester_is_admin": "True",
                "requester_tier": "admin",
            },
        }, None)
        body = _get_body(result)
        assert "SECURITY ERROR" in body


class TestForceMerge2PR:
    """Cover force merge 2PR approval + logging (lines 601-617)."""

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_force_merge_with_valid_2pr_succeeds(self, mock_boto):
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
            "sessionAttributes": {
                "requester_user_id": "U_REQ",
                "approver_user_id": "U_APP",
                "requester_is_admin": "True",
                "approver_is_admin": "True",
                "requester_tier": "admin",
            },
        }, None)
        body = _get_body(result)
        assert "success" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_force_merge_rejects_without_approver(self, mock_boto):
        """When global 2PR is off, force merge still enforces its own 2PR — rejection path."""
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
            "sessionAttributes": {
                "requester_user_id": "U_ADM",
                "requester_is_admin": "True",
                "requester_tier": "admin",
            },
        }, None)
        body = _get_body(result)
        assert "SECURITY ERROR" in body


class TestGenericGuardrailFailure:
    """Cover the non-merge guardrail failure branch (lines 630-637)."""

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_bulk_comment_guardrail_blocks(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        guardrail_fail = MagicMock(return_value={"all_passed": False, "message": "Invalid targets"})
        mod = _load_lambda(guardrails_overrides={"validate_bulk_comment": guardrail_fail})

        result = mod.lambda_handler({
            "function": "bulk_comment",
            "parameters": [
                {"name": "issues", "value": "OpenSearch#1"},
                {"name": "body", "value": "test"},
            ],
            "sessionAttributes": {
                "requester_user_id": "U_REQ",
                "approver_user_id": "U_APP",
                "requester_is_admin": "True",
                "approver_is_admin": "True",
                "requester_tier": "admin",
            },
        }, None)
        body = _get_body(result)
        assert "Invalid targets" in body


class TestLambdaHandlerErrors:
    """Cover exception handlers at the bottom of lambda_handler (lines 655-665)."""

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_github_api_error_handled(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        GitHubAPIError = sys.modules['http_client'].GitHubAPIError
        sys.modules['github_api'].get_repo_maintainers.side_effect = GitHubAPIError(404, "Not Found", "/repos/x")

        result = mod.lambda_handler({
            "function": "get_repo_maintainers",
            "parameters": [{"name": "repo", "value": "OpenSearch"}],
        }, None)
        body = _get_body(result)
        assert "error" in body

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test'})
    @patch('boto3.client')
    def test_generic_exception_handled(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '1', 'GITHUB_PRIVATE_KEY': 'k', 'GITHUB_INSTALLATION_ID': '2',
            })
        }
        mod = _load_lambda()
        sys.modules['github_api'].get_repo_maintainers.side_effect = RuntimeError("boom")

        result = mod.lambda_handler({
            "function": "get_repo_maintainers",
            "parameters": [{"name": "repo", "value": "OpenSearch"}],
        }, None)
        body = _get_body(result)
        assert "boom" in body
