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


def _bulk_merge_event(**extra_params):
    """Build a bulk_merge_prs event with optional extra params."""
    params = [
        {'name': 'version', 'value': '3.6.0'},
        {'name': 'confirmed', 'value': 'true'},
    ]
    for name, value in extra_params.items():
        params.append({'name': name, 'value': value})
    return {'function': 'bulk_merge_prs', 'parameters': params}


class TestTwoPersonApprovalBulkMerge(unittest.TestCase):
    """Test 2PR enforcement in bulk_merge_prs."""

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

        result = mod.lambda_handler(_bulk_merge_event(), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('SECURITY ERROR', parsed['message'])
        self.assertIn('requester_user_id', parsed['message'])
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

        event = _bulk_merge_event(requester_user_id='U_SAME', approver_user_id='U_SAME')
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

        event = _bulk_merge_event(requester_user_id='U_REQ', approver_user_id='U_APP')
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')
        mock_guardrails.bulk_merge.assert_called_once()

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_disabled_skips_check(self, mock_boto):
        """When ENABLE_2PR is off, missing/equal user IDs should not block the merge."""
        mock_boto.return_value.get_secret_value.return_value = {
            'SecretString': json.dumps({
                'GITHUB_APP_ID': '123',
                'GITHUB_PRIVATE_KEY': 'key',
                'GITHUB_INSTALLATION_ID': '456',
            })
        }
        mod, mock_guardrails = _load_lambda_handler()

        # No requester/approver IDs at all — should succeed
        result = mod.lambda_handler(_bulk_merge_event(), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')
        mock_guardrails.bulk_merge.assert_called_once()

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

        event = _bulk_merge_event(requester_user_id='U_SAME ', approver_user_id=' U_SAME')
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('Self-approval', parsed['message'])
        mock_guardrails.bulk_merge.assert_not_called()


def _merge_pr_event(**extra_params):
    """Build a merge_pr event with optional extra params."""
    params = [
        {'name': 'repo', 'value': 'OpenSearch'},
        {'name': 'pr_number', 'value': '42'},
    ]
    for name, value in extra_params.items():
        params.append({'name': name, 'value': value})
    return {'function': 'merge_pr', 'parameters': params}


class TestTwoPersonApprovalMergePr(unittest.TestCase):
    """Test 2PR enforcement in merge_pr."""

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

        result = mod.lambda_handler(_merge_pr_event(), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'error')
        self.assertIn('SECURITY ERROR', parsed['message'])
        self.assertIn('requester_user_id', parsed['message'])

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

        event = _merge_pr_event(requester_user_id='U_SAME', approver_user_id='U_SAME')
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

        event = _merge_pr_event(requester_user_id='U_REQ', approver_user_id='U_APP')
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_disabled_skips_check(self, mock_boto):
        """When ENABLE_2PR is off, missing user IDs should not block the merge."""
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

        result = mod.lambda_handler(_merge_pr_event(), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')


def _bulk_comment_event(**extra_params):
    """Build a bulk_comment event with optional extra params."""
    params = [
        {'name': 'repo', 'value': 'OpenSearch'},
        {'name': 'issue_numbers', 'value': '1,2,3'},
        {'name': 'body', 'value': 'Release 3.6.0 is out!'},
    ]
    for name, value in extra_params.items():
        params.append({'name': name, 'value': value})
    return {'function': 'bulk_comment', 'parameters': params}


class TestTwoPersonApprovalBulkComment(unittest.TestCase):
    """Test 2PR enforcement in bulk_comment."""

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

        result = mod.lambda_handler(_bulk_comment_event(), None)
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

        event = _bulk_comment_event(requester_user_id='U_SAME', approver_user_id='U_SAME')
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

        event = _bulk_comment_event(requester_user_id='U_REQ', approver_user_id='U_APP')
        result = mod.lambda_handler(event, None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')
        mock_bulk_comment.assert_called_once()

    @patch.dict(os.environ, {'ENABLE_2PR': 'false', 'GITHUB_SECRET_NAME': 'test-secret'})
    @patch('boto3.client')
    def test_2pr_disabled_skips_check(self, mock_boto):
        """When ENABLE_2PR is off, missing user IDs should not block the comment."""
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

        result = mod.lambda_handler(_bulk_comment_event(), None)
        body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        self.assertEqual(parsed['status'], 'success')
        mock_bulk_comment.assert_called_once()


if __name__ == '__main__':
    unittest.main()
