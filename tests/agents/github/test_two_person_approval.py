# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Test two-person approval (2PR) enforcement for GitHub agent bulk_merge_prs."""

import importlib.util
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_GITHUB_LAMBDA_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'github', 'lambda',
)
_GITHUB_LAMBDA_DIR = os.path.abspath(_GITHUB_LAMBDA_DIR)
_SHARED_LAYER_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'lambda', 'shared-layer', 'python',
))


def _load_lambda_handler():
    """Load the GitHub lambda_function module with mocked dependencies."""
    sys.path.insert(0, _SHARED_LAYER_DIR)
    sys.path.insert(0, _GITHUB_LAMBDA_DIR)
    try:
        # Clear cached modules
        for mod_name in ['lambda_function', 'authorizer', 'guardrails',
                         'github_api', 'http_client', 'mcp_client', 'response_builder']:
            sys.modules.pop(mod_name, None)

        # Mock heavy dependencies
        mock_mcp = MagicMock()
        mock_mcp.MCPClient.return_value.get_token.return_value = 'fake-token'
        sys.modules['mcp_client'] = mock_mcp

        mock_http = MagicMock()
        mock_http.ORG = 'opensearch-project'
        mock_http.GitHubAPIError = type('GitHubAPIError', (Exception,), {'status_code': 500})
        sys.modules['http_client'] = mock_http

        mock_github_api = MagicMock()
        sys.modules['github_api'] = mock_github_api

        mock_guardrails = MagicMock()
        mock_guardrails.bulk_merge.return_value = json.dumps({
            'status': 'success',
            'merged_count': 3,
            'message': 'Bulk merge complete',
        })
        sys.modules['guardrails'] = mock_guardrails

        mock_authorizer = MagicMock()
        mock_authorizer.is_write_operation.return_value = True
        mock_authorizer.validate_org_scope.return_value = None
        sys.modules['authorizer'] = mock_authorizer

        mock_rb = MagicMock()
        mock_rb.create_response.side_effect = lambda event, result: {
            'response': {
                'functionResponse': {
                    'responseBody': {
                        'TEXT': {'body': json.dumps(result) if isinstance(result, dict) else result}
                    }
                }
            },
            'messageVersion': '1.0',
        }
        sys.modules['response_builder'] = mock_rb

        spec = importlib.util.spec_from_file_location(
            'lambda_function',
            os.path.join(_GITHUB_LAMBDA_DIR, 'lambda_function.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mock_guardrails
    finally:
        sys.path.remove(_GITHUB_LAMBDA_DIR)
        sys.path.remove(_SHARED_LAYER_DIR)


def _bulk_merge_event(session_attrs=None, **extra_params):
    """Build a bulk_merge_prs event with optional extra params."""
    params = [
        {'name': 'version', 'value': '3.6.0'},
        {'name': 'confirmed', 'value': 'true'},
    ]
    for name, value in extra_params.items():
        params.append({'name': name, 'value': value})
    event = {'function': 'bulk_merge_prs', 'parameters': params}
    if session_attrs is not None:
        event['sessionAttributes'] = session_attrs
    return event


class TestTwoPersonApprovalBulkMerge(unittest.TestCase):
    """Test 2PR enforcement in bulk_merge_prs.

    Identity is now passed via sessionAttributes (out-of-band from Slack event
    metadata), NOT via model-populated action-group parameters.
    """

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_missing_user_ids_rejected(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, mock_guardrails = _load_lambda_handler()

        # Admin flags present but no user IDs — 2PR rejects
        result = mod.lambda_handler(_bulk_merge_event(session_attrs={
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_tier': 'admin',
        }), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('SECURITY ERROR', parsed['message'])
        mock_guardrails.bulk_merge.assert_not_called()

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_self_approval_rejected(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, mock_guardrails = _load_lambda_handler()

        event = _bulk_merge_event(session_attrs={
            'requester_user_id': 'U_SAME', 'approver_user_id': 'U_SAME',
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_tier': 'admin',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('Self-approval is not permitted', parsed['message'])
        self.assertIn('U_SAME', parsed['message'])
        mock_guardrails.bulk_merge.assert_not_called()

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_distinct_users_proceeds(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, mock_guardrails = _load_lambda_handler()

        event = _bulk_merge_event(session_attrs={
            'requester_user_id': 'U_REQ', 'approver_user_id': 'U_APP',
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_tier': 'admin',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')
        mock_guardrails.bulk_merge.assert_called_once()

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_disabled_skips_check(self, mock_boto):
        """When ENABLE_2PR is off, admin check still enforced."""
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, mock_guardrails = _load_lambda_handler()

        # Admin requester, no approver — should succeed (2PR off, admin check passes)
        result = mod.lambda_handler(_bulk_merge_event(session_attrs={
            'requester_user_id': 'U_ADMIN', 'requester_is_admin': 'True', 'requester_tier': 'admin',
        }), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')
        mock_guardrails.bulk_merge.assert_called_once()

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_non_admin_rejected_even_with_2pr_disabled(self, mock_boto):
        """Non-admin users are rejected regardless of 2PR setting."""
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, mock_guardrails = _load_lambda_handler()

        result = mod.lambda_handler(_bulk_merge_event(session_attrs={
            'requester_user_id': 'U_NON_ADMIN', 'requester_is_admin': 'False', 'requester_tier': 'contributor',
        }), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('AUTHORIZATION ERROR', parsed['message'])
        mock_guardrails.bulk_merge.assert_not_called()

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_whitespace_trimmed(self, mock_boto):
        """Whitespace around user IDs should not allow self-approval bypass."""
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, mock_guardrails = _load_lambda_handler()

        event = _bulk_merge_event(session_attrs={
            'requester_user_id': 'U_SAME ', 'approver_user_id': ' U_SAME',
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_tier': 'admin',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('Self-approval', parsed['message'])
        mock_guardrails.bulk_merge.assert_not_called()


def _merge_pr_event(session_attrs=None, **extra_params):
    """Build a merge_pr event with optional extra params."""
    params = [
        {'name': 'repo', 'value': 'OpenSearch'},
        {'name': 'pr_number', 'value': '42'},
    ]
    for name, value in extra_params.items():
        params.append({'name': name, 'value': value})
    event = {'function': 'merge_pr', 'parameters': params}
    if session_attrs is not None:
        event['sessionAttributes'] = session_attrs
    return event


class TestTwoPersonApprovalMergePr(unittest.TestCase):
    """Test 2PR enforcement in merge_pr (identity via sessionAttributes)."""

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_missing_user_ids_rejected(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, mock_guardrails = _load_lambda_handler()
        mock_guardrails.validate_single_pr.return_value = {
            'is_auto_pr': False, 'all_passed': True,
        }

        result = mod.lambda_handler(_merge_pr_event(session_attrs={
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_tier': 'admin',
        }), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('SECURITY ERROR', parsed['message'])

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_self_approval_rejected(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, mock_guardrails = _load_lambda_handler()
        mock_guardrails.validate_single_pr.return_value = {
            'is_auto_pr': False, 'all_passed': True,
        }

        event = _merge_pr_event(session_attrs={
            'requester_user_id': 'U_SAME', 'approver_user_id': 'U_SAME',
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_tier': 'admin',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('Self-approval is not permitted', parsed['message'])
        self.assertIn('U_SAME', parsed['message'])

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_distinct_users_proceeds(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, mock_guardrails = _load_lambda_handler()
        mock_guardrails.validate_single_pr.return_value = {
            'is_auto_pr': False, 'all_passed': True,
        }
        mock_mcp = sys.modules['mcp_client']
        mock_mcp.MCPClient.return_value.call_tool.return_value = json.dumps({
            'status': 'success', 'merged': True,
        })

        event = _merge_pr_event(session_attrs={
            'requester_user_id': 'U_REQ', 'approver_user_id': 'U_APP',
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_tier': 'admin',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_disabled_skips_check(self, mock_boto):
        """When ENABLE_2PR is off, admin check still enforced."""
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, mock_guardrails = _load_lambda_handler()
        mock_guardrails.validate_single_pr.return_value = {
            'is_auto_pr': False, 'all_passed': True,
        }
        mock_mcp = sys.modules['mcp_client']
        mock_mcp.MCPClient.return_value.call_tool.return_value = json.dumps({
            'status': 'success', 'merged': True,
        })

        result = mod.lambda_handler(_merge_pr_event(session_attrs={
            'requester_user_id': 'U_ADMIN', 'requester_is_admin': 'True', 'requester_tier': 'admin',
        }), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')


def _bulk_comment_event(session_attrs=None, **extra_params):
    """Build a bulk_comment event with optional extra params."""
    params = [
        {'name': 'issues', 'value': 'OpenSearch#1,OpenSearch#2,OpenSearch#3'},
        {'name': 'body', 'value': 'Release 3.6.0 is out!'},
    ]
    for name, value in extra_params.items():
        params.append({'name': name, 'value': value})
    event = {'function': 'bulk_comment', 'parameters': params}
    if session_attrs is not None:
        event['sessionAttributes'] = session_attrs
    return event


class TestTwoPersonApprovalBulkComment(unittest.TestCase):
    """Test 2PR enforcement in bulk_comment (identity via sessionAttributes)."""

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_missing_user_ids_rejected(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_bulk_comment = sys.modules['github_api'].bulk_comment

        result = mod.lambda_handler(_bulk_comment_event(session_attrs={
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_tier': 'admin',
        }), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('SECURITY ERROR', parsed['message'])
        mock_bulk_comment.assert_not_called()

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_self_approval_rejected(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_bulk_comment = sys.modules['github_api'].bulk_comment

        event = _bulk_comment_event(session_attrs={
            'requester_user_id': 'U_SAME', 'approver_user_id': 'U_SAME',
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_tier': 'admin',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('Self-approval is not permitted', parsed['message'])
        mock_bulk_comment.assert_not_called()

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_distinct_users_proceeds(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_bulk_comment = sys.modules['github_api'].bulk_comment
        mock_bulk_comment.return_value = json.dumps({'status': 'success', 'commented': 3})

        event = _bulk_comment_event(session_attrs={
            'requester_user_id': 'U_REQ', 'approver_user_id': 'U_APP',
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_tier': 'admin',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')
        mock_bulk_comment.assert_called_once()

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_disabled_skips_check(self, mock_boto):
        """When ENABLE_2PR is off, admin check still enforced."""
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_bulk_comment = sys.modules['github_api'].bulk_comment
        mock_bulk_comment.return_value = json.dumps({'status': 'success', 'commented': 3})

        result = mod.lambda_handler(_bulk_comment_event(session_attrs={
            'requester_user_id': 'U_ADMIN', 'requester_is_admin': 'True', 'requester_tier': 'admin',
        }), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')
        mock_bulk_comment.assert_called_once()


def _create_tag_event(session_attrs=None):
    """Build a create_tag event with optional session attributes."""
    params = [
        {'name': 'repo', 'value': 'data-prepper'},
        {'name': 'tag_name', 'value': '3.12.0'},
        {'name': 'commit_sha', 'value': '1234abcd' * 5},
    ]
    event = {'function': 'create_tag', 'parameters': params}
    if session_attrs is not None:
        event['sessionAttributes'] = session_attrs
    return event


class TestTwoPersonApprovalCreateTag(unittest.TestCase):
    """Test 2PR and maintainer authorization in create_tag."""

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_missing_user_ids_rejected(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_create_ref = sys.modules['github_api'].create_ref

        result = mod.lambda_handler(_create_tag_event(session_attrs={
            'requester_is_admin': 'True', 'requester_is_maintainer': 'True',
        }), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('SECURITY ERROR', parsed['message'])
        mock_create_ref.assert_not_called()

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_self_approval_rejected(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_create_ref = sys.modules['github_api'].create_ref

        event = _create_tag_event(session_attrs={
            'requester_user_id': 'U_SAME', 'approver_user_id': 'U_SAME',
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_is_maintainer': 'True',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('Self-approval is not permitted', parsed['message'])
        mock_create_ref.assert_not_called()

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_distinct_admin_users_proceeds(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_create_ref = sys.modules['github_api'].create_ref
        mock_create_ref.return_value = json.dumps({
            'status': 'success', 'tag': '3.12.0', 'commit_sha': '1234abcd' * 5,
        })

        event = _create_tag_event(session_attrs={
            'requester_user_id': 'U_REQ', 'approver_user_id': 'U_APP',
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_is_maintainer': 'True',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')
        mock_create_ref.assert_called_once()

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_disabled_admin_proceeds(self, mock_boto):
        """Admin requester proceeds when ENABLE_2PR is off."""
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_create_ref = sys.modules['github_api'].create_ref
        mock_create_ref.return_value = json.dumps({
            'status': 'success', 'tag': '3.12.0', 'commit_sha': '1234abcd' * 5,
        })

        result = mod.lambda_handler(_create_tag_event(session_attrs={
            'requester_user_id': 'U_ADMIN', 'requester_is_admin': 'True', 'requester_is_maintainer': 'True',
        }), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')
        mock_create_ref.assert_called_once()

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_non_admin_non_maintainer_rejected(self, mock_boto):
        """Non-admin user without maintainer status is rejected at group gate."""
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_create_ref = sys.modules['github_api'].create_ref

        event = _create_tag_event(session_attrs={
            'requester_user_id': 'U_REQ', 'approver_user_id': 'U_APP',
            'requester_is_admin': 'False', 'approver_is_admin': 'True',
            'requester_is_maintainer': 'False',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('AUTHORIZATION ERROR', parsed['message'])
        self.assertIn('maintainer', parsed['message'])
        mock_create_ref.assert_not_called()


def _create_branch_event(session_attrs=None):
    """Build a create_branch event with optional session attributes."""
    params = [
        {'name': 'repo', 'value': 'data-prepper'},
        {'name': 'branch_name', 'value': '3.12'},
        {'name': 'commit_sha', 'value': '1234abcd' * 5},
    ]
    event = {'function': 'create_branch', 'parameters': params}
    if session_attrs is not None:
        event['sessionAttributes'] = session_attrs
    return event


class TestTwoPersonApprovalCreateBranch(unittest.TestCase):
    """Test 2PR and maintainer authorization in create_branch."""

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_missing_user_ids_rejected(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_create_ref = sys.modules['github_api'].create_ref

        result = mod.lambda_handler(_create_branch_event(session_attrs={
            'requester_is_admin': 'True', 'requester_is_maintainer': 'True',
        }), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('SECURITY ERROR', parsed['message'])
        mock_create_ref.assert_not_called()

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_self_approval_rejected(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_create_ref = sys.modules['github_api'].create_ref

        event = _create_branch_event(session_attrs={
            'requester_user_id': 'U_SAME', 'approver_user_id': 'U_SAME',
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_is_maintainer': 'True',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('Self-approval is not permitted', parsed['message'])
        mock_create_ref.assert_not_called()

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_enabled_distinct_admin_users_proceeds(self, mock_boto):
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_create_ref = sys.modules['github_api'].create_ref
        mock_create_ref.return_value = json.dumps({
            'status': 'success', 'branch': '3.12', 'commit_sha': '1234abcd' * 5,
        })

        event = _create_branch_event(session_attrs={
            'requester_user_id': 'U_REQ', 'approver_user_id': 'U_APP',
            'requester_is_admin': 'True', 'approver_is_admin': 'True', 'requester_is_maintainer': 'True',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')
        mock_create_ref.assert_called_once()

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_disabled_admin_proceeds(self, mock_boto):
        """Admin requester proceeds when ENABLE_2PR is off."""
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_create_ref = sys.modules['github_api'].create_ref
        mock_create_ref.return_value = json.dumps({
            'status': 'success', 'branch': '3.12', 'commit_sha': '1234abcd' * 5,
        })

        result = mod.lambda_handler(_create_branch_event(session_attrs={
            'requester_user_id': 'U_ADMIN', 'requester_is_admin': 'True', 'requester_is_maintainer': 'True',
        }), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')
        mock_create_ref.assert_called_once()

    @patch.dict(os.environ, {'ENABLE_2PR': 'true', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_non_admin_non_maintainer_rejected(self, mock_boto):
        """Non-admin user without maintainer status is rejected at group gate."""
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, _ = _load_lambda_handler()
        mock_create_ref = sys.modules['github_api'].create_ref

        event = _create_branch_event(session_attrs={
            'requester_user_id': 'U_REQ', 'approver_user_id': 'U_APP',
            'requester_is_admin': 'False', 'approver_is_admin': 'True',
            'requester_is_maintainer': 'False',
        })
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('AUTHORIZATION ERROR', parsed['message'])
        self.assertIn('maintainer', parsed['message'])
        mock_create_ref.assert_not_called()


class TestApprovalGuardExpired(unittest.TestCase):
    """Test the approval_expired branch in validate_two_person_approval."""

    def test_expired_approval_returns_specific_error(self):
        from oscar_shared.approval_guard import validate_two_person_approval
        result = validate_two_person_approval(
            session_attributes={
                'requester_user_id': 'U_LATE',
                'approval_expired': 'True',
            },
            enable_2pr=True,
            action_label='action=test',
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['status'], 'error')
        self.assertIn('approval window has expired', result['message'])
        self.assertIn('[2PR_PENDING]', result['message'])

    def test_expired_not_set_returns_generic_error(self):
        from oscar_shared.approval_guard import validate_two_person_approval
        result = validate_two_person_approval(
            session_attributes={'requester_user_id': 'U_ONLY'},
            enable_2pr=True,
            action_label='action=test',
        )
        self.assertIsNotNone(result)
        self.assertIn('Two-person approval requires', result['message'])

    def test_maintainer_op_non_admin_approver_rejected(self):
        from oscar_shared.approval_guard import validate_two_person_approval
        result = validate_two_person_approval(
            session_attributes={
                'requester_user_id': 'U_REQ',
                'approver_user_id': 'U_APP',
                'approver_is_admin': 'False',
            },
            enable_2pr=True,
            action_label='action=test',
            auth_policy='maintainer',
        )
        self.assertIsNotNone(result)
        self.assertIn('requires approval from an admin', result['message'])


class _SharedLayerMixin:
    """Add shared layer to sys.path for direct imports."""

    @classmethod
    def setUpClass(cls):
        if _SHARED_LAYER_DIR not in sys.path:
            sys.path.insert(0, _SHARED_LAYER_DIR)

    @classmethod
    def tearDownClass(cls):
        if _SHARED_LAYER_DIR in sys.path:
            sys.path.remove(_SHARED_LAYER_DIR)
        sys.modules.pop('oscar_shared.approval_guard', None)
        sys.modules.pop('oscar_shared.auth_policy', None)


class TestApprovalGuardAdminPolicy(_SharedLayerMixin, unittest.TestCase):
    """Cover line 89: admin auth_policy with non-admin approver."""

    def test_admin_op_non_admin_approver_rejected(self):
        from oscar_shared.approval_guard import validate_two_person_approval
        result = validate_two_person_approval(
            session_attributes={
                'requester_user_id': 'U_REQ',
                'approver_user_id': 'U_APP',
                'approver_is_admin': 'False',
            },
            enable_2pr=True,
            action_label='action=test',
            auth_policy='admin',
        )
        self.assertIsNotNone(result)
        self.assertIn('requires approval from a different admin', result['message'])

    def test_admin_op_admin_approver_passes(self):
        from oscar_shared.approval_guard import validate_two_person_approval
        result = validate_two_person_approval(
            session_attributes={
                'requester_user_id': 'U_REQ',
                'approver_user_id': 'U_APP',
                'approver_is_admin': 'True',
            },
            enable_2pr=True,
            action_label='action=test',
            auth_policy='admin',
        )
        self.assertIsNone(result)


class TestAuthPolicyDeriveTier(_SharedLayerMixin, unittest.TestCase):
    """Cover derive_tier — specifically the maintainer branch (line 74)."""

    def test_derive_tier_admin(self):
        from oscar_shared.auth_policy import derive_tier
        self.assertEqual(derive_tier(True, False), "admin")

    def test_derive_tier_maintainer(self):
        from oscar_shared.auth_policy import derive_tier
        self.assertEqual(derive_tier(False, True), "maintainer")

    def test_derive_tier_contributor(self):
        from oscar_shared.auth_policy import derive_tier
        self.assertEqual(derive_tier(False, False), "contributor")

    def test_derive_tier_admin_trumps_maintainer(self):
        from oscar_shared.auth_policy import derive_tier
        self.assertEqual(derive_tier(True, True), "admin")


class TestFunctionDefPostInit(unittest.TestCase):
    """Cover registry.py line 46: write=True with no auth_policy raises ValueError."""

    def test_write_without_auth_policy_raises(self):
        sys.path.insert(0, os.path.join(
            os.path.dirname(__file__), '..', '..', '..', 'agents', 'github', 'lambda',
        ))
        try:
            from registry import FunctionDef
            with self.assertRaises(ValueError) as ctx:
                FunctionDef(write=True, auth_policy=None)
            self.assertIn("write functions must declare", str(ctx.exception))
        finally:
            sys.modules.pop('registry', None)

    def test_write_with_auth_policy_ok(self):
        sys.path.insert(0, os.path.join(
            os.path.dirname(__file__), '..', '..', '..', 'agents', 'github', 'lambda',
        ))
        try:
            from registry import FunctionDef
            fd = FunctionDef(write=True, auth_policy="admin")
            self.assertTrue(fd.write)
        finally:
            sys.modules.pop('registry', None)


if __name__ == '__main__':
    unittest.main()
