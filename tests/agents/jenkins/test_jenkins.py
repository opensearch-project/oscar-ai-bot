# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Jenkins integration components."""

import os
import sys
import unittest
from unittest.mock import patch

# Add jenkins directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'agents', 'jenkins', 'lambda'))

from jenkins_client import JenkinsClient, JenkinsCredentials  # noqa: E402
from job_definitions import (JobDefinition, JobParameter,  # noqa: E402
                             JobRegistry)
from lambda_function import _validate_build_params  # noqa: E402
from lambda_function import format_parameters_as_bullets  # noqa: E402

_JENKINS_ENV = {
    'JENKINS_URL': 'https://test-jenkins.example.com',
    'JENKINSFILE_GITHUB_REPO': 'https://github.com/test/repo',
}


def _reset_config_cache():
    """Reset the _ConfigProxy cached config so env changes take effect."""
    from config import config as _cfg
    _cfg._cached_config = None


@patch.dict(os.environ, _JENKINS_ENV)
class TestJenkinsCredentials(unittest.TestCase):
    """Test Jenkins credentials management."""

    def setUp(self):
        _reset_config_cache()

    @patch('jenkins_client.config')
    def test_load_credentials_success(self, mock_config):
        """Test successful credential loading."""
        mock_config.jenkins_api_token = 'testuser:testtoken'

        creds = JenkinsCredentials()
        auth = creds.get_auth()

        self.assertEqual(creds.get_username(), 'testuser')
        self.assertIsNotNone(auth)

    @patch('jenkins_client.config')
    def test_load_credentials_invalid_format(self, mock_config):
        """Test credential loading with invalid format."""
        mock_config.jenkins_api_token = 'invalidtoken'

        creds = JenkinsCredentials()

        with self.assertRaises(Exception):
            creds.get_auth()

    @patch('jenkins_client.config')
    def test_load_credentials_missing_token(self, mock_config):
        """Test credential loading with missing token."""
        mock_config.jenkins_api_token = None

        creds = JenkinsCredentials()

        with self.assertRaises(Exception):
            creds.get_auth()


def _build_test_registry():
    """Build a JobRegistry with sample jobs for testing."""
    registry = JobRegistry()

    registry.register_job(JobDefinition(
        job_name='docker-scan',
        description='Scan Docker images for vulnerabilities',
        parameters=[
            JobParameter(name='IMAGE_FULL_NAME', description='Full Docker image name', required=True),
        ],
    ))

    registry.register_job(JobDefinition(
        job_name='release-chores',
        description='Run release chore tasks',
        parameters=[
            JobParameter(name='CHORE', description='Chore type', required=True, choices=['buildRC', 'check']),
            JobParameter(name='VERSION', description='Release version', required=True),
            JobParameter(name='NOTES', description='Optional notes', required=False, default_value=''),
        ],
    ))

    return registry


class TestJobDefinitions(unittest.TestCase):
    """Test dynamic job definition and registry."""

    def setUp(self):
        self.registry = _build_test_registry()

    def test_registry_list_jobs(self):
        """Test listing registered jobs."""
        jobs = self.registry.list_jobs()
        self.assertIn('docker-scan', jobs)
        self.assertIn('release-chores', jobs)

    def test_registry_get_job(self):
        """Test getting a registered job."""
        job = self.registry.get_job('docker-scan')
        self.assertIsNotNone(job)
        self.assertEqual(job.job_name, 'docker-scan')

    def test_registry_get_unknown_job(self):
        """Test getting a non-existent job."""
        job = self.registry.get_job('nonexistent-job')
        self.assertIsNone(job)

    def test_get_job_info(self):
        """Test getting job info from registry."""
        info = self.registry.get_job_info('docker-scan')
        self.assertIsNotNone(info)
        self.assertEqual(info['name'], 'docker-scan')
        self.assertIn('IMAGE_FULL_NAME', info['parameters'])

    def test_parameter_info_required(self):
        """Test parameter info shows required status."""
        job = self.registry.get_job('docker-scan')
        params = job.get_parameter_info()
        self.assertTrue(params['IMAGE_FULL_NAME']['required'])

    def test_parameter_info_optional(self):
        """Test parameter info for optional params."""
        job = self.registry.get_job('release-chores')
        params = job.get_parameter_info()
        self.assertFalse(params['NOTES']['required'])
        self.assertEqual(params['NOTES']['default'], '')

    def test_parameter_info_choices(self):
        """Test parameter info shows choices."""
        job = self.registry.get_job('release-chores')
        params = job.get_parameter_info()
        self.assertIn('buildRC', params['CHORE']['choices'])
        self.assertIn('check', params['CHORE']['choices'])

    def test_validate_valid_params(self):
        """Test validation with valid parameters."""
        validated = self.registry.validate_job_parameters('docker-scan', {'IMAGE_FULL_NAME': 'alpine:3.19'})
        self.assertEqual(validated, {'IMAGE_FULL_NAME': 'alpine:3.19'})

    def test_validate_missing_required_param(self):
        """Test validation fails when required param is missing."""
        with self.assertRaises(ValueError):
            self.registry.validate_job_parameters('docker-scan', {})

    def test_validate_invalid_choice(self):
        """Test validation fails with invalid choice value."""
        with self.assertRaises(ValueError):
            self.registry.validate_job_parameters('release-chores', {
                'CHORE': 'invalidChoice',
                'VERSION': '2.12.0',
            })

    def test_validate_unknown_job(self):
        """Test validation fails for unknown job."""
        with self.assertRaises(ValueError):
            self.registry.validate_job_parameters('unknown-job', {})

    def test_validate_optional_param_uses_default(self):
        """Test that optional params get their default value."""
        validated = self.registry.validate_job_parameters('release-chores', {
            'CHORE': 'buildRC',
            'VERSION': '2.12.0',
        })
        self.assertEqual(validated['NOTES'], '')


@patch.dict(os.environ, _JENKINS_ENV)
class TestJenkinsClient(unittest.TestCase):
    """Test Jenkins client functionality."""

    @patch('jenkins_client.config')
    def setUp(self, mock_config):
        """Set up test client with a test registry."""
        mock_config.jenkins_api_token = 'testuser:testtoken'
        mock_config.request_timeout = 30
        mock_config.verify_ssl = True
        self.registry = _build_test_registry()
        self.client = JenkinsClient(self.registry)

    def test_get_job_info_success(self):
        """Test successful job info retrieval."""
        result = self.client.get_job_info('docker-scan')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['job_name'], 'docker-scan')
        self.assertIn('parameter_definitions', result)

    def test_get_job_info_unknown_job(self):
        """Test job info for unknown job."""
        result = self.client.get_job_info('unknown-job')
        self.assertEqual(result['status'], 'error')
        self.assertIn('Unknown job', result['message'])

    def test_list_available_jobs(self):
        """Test listing available jobs."""
        result = self.client.list_available_jobs()
        self.assertEqual(result['status'], 'success')
        self.assertIn('jobs', result)
        self.assertGreater(result['total_jobs'], 0)


@patch.dict(os.environ, _JENKINS_ENV)
class TestLambdaHandler(unittest.TestCase):
    """Test Lambda handler functionality."""

    def setUp(self):
        _reset_config_cache()

    @patch('lambda_function.get_job_registry')
    @patch('lambda_function.config')
    def test_unknown_function(self, mock_config, mock_get_registry):
        """Test unknown function handling."""
        from lambda_function import lambda_handler

        mock_get_registry.return_value = _build_test_registry()

        event = {
            'function': 'unknown_function',
            'parameters': [],
        }

        result = lambda_handler(event, None)
        response_body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        self.assertIn('Unknown function', response_body)

    @patch('lambda_function.get_job_registry')
    @patch('lambda_function.config')
    def test_trigger_job_missing_confirmation(self, mock_config, mock_get_registry):
        """Test trigger_job without confirmation."""
        from lambda_function import lambda_handler

        mock_get_registry.return_value = _build_test_registry()

        event = {
            'function': 'trigger_job',
            'parameters': [
                {'name': 'job_name', 'value': 'docker-scan'},
                {'name': 'IMAGE_FULL_NAME', 'value': 'alpine:3.19'},
            ],
        }

        result = lambda_handler(event, None)
        response_body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        self.assertIn('confirmed', response_body)

    @patch('lambda_function.get_job_registry')
    @patch('lambda_function.config')
    def test_trigger_job_confirmation_false(self, mock_config, mock_get_registry):
        """Test trigger_job with confirmation=false."""
        from lambda_function import lambda_handler

        mock_get_registry.return_value = _build_test_registry()

        event = {
            'function': 'trigger_job',
            'parameters': [
                {'name': 'job_name', 'value': 'docker-scan'},
                {'name': 'IMAGE_FULL_NAME', 'value': 'alpine:3.19'},
                {'name': 'confirmed', 'value': 'false'},
            ],
        }

        result = lambda_handler(event, None)
        response_body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        self.assertIn('cancelled', response_body)

    @patch('lambda_function.get_job_registry')
    @patch('lambda_function.config')
    def test_list_jobs_handler(self, mock_config, mock_get_registry):
        """Test list_jobs Lambda handler."""
        from lambda_function import lambda_handler

        mock_get_registry.return_value = _build_test_registry()

        event = {
            'function': 'list_jobs',
            'parameters': [],
        }

        result = lambda_handler(event, None)
        self.assertIn('response', result)
        self.assertEqual(result['messageVersion'], '1.0')
        response_body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        self.assertIn('Available Jenkins jobs', response_body)

    @patch('lambda_function.get_job_registry')
    @patch('lambda_function.config')
    def test_get_job_info_handler(self, mock_config, mock_get_registry):
        """Test get_job_info Lambda handler."""
        from lambda_function import lambda_handler

        mock_get_registry.return_value = _build_test_registry()

        event = {
            'function': 'get_job_info',
            'parameters': [
                {'name': 'job_name', 'value': 'docker-scan'},
            ],
        }

        result = lambda_handler(event, None)
        self.assertIn('response', result)
        self.assertEqual(result['messageVersion'], '1.0')


class TestValidateBuildParams(unittest.TestCase):
    """Test _validate_build_params helper."""

    def test_valid_params(self):
        job_name, build_number, error = _validate_build_params(
            {'job_name': 'docker-scan', 'build_number': '42'},
        )
        self.assertEqual(job_name, 'docker-scan')
        self.assertEqual(build_number, 42)
        self.assertIsNone(error)

    def test_missing_job_name(self):
        _, _, error = _validate_build_params({'build_number': '42'})
        self.assertEqual(error['status'], 'error')
        self.assertIn('job_name', error['message'])

    def test_missing_build_number(self):
        _, _, error = _validate_build_params({'job_name': 'docker-scan'})
        self.assertEqual(error['status'], 'error')
        self.assertIn('build_number', error['message'])

    def test_non_integer_build_number(self):
        _, _, error = _validate_build_params(
            {'job_name': 'docker-scan', 'build_number': 'abc'},
        )
        self.assertEqual(error['status'], 'error')
        self.assertIn('must be an integer', error['message'])


@patch.dict(os.environ, _JENKINS_ENV)
class TestGetBuildFailureDetailsHandler(unittest.TestCase):
    """Test get_build_failure_details Lambda handler routing."""

    def setUp(self):
        _reset_config_cache()

    @patch('lambda_function.get_job_registry')
    @patch('lambda_function.config')
    def test_get_build_failure_details_handler(self, mock_config, mock_get_registry):
        from lambda_function import lambda_handler

        mock_get_registry.return_value = _build_test_registry()

        event = {
            'function': 'get_build_failure_details',
            'parameters': [
                {'name': 'job_name', 'value': 'docker-scan'},
                {'name': 'build_number', 'value': '123'},
            ],
        }

        result = lambda_handler(event, None)
        self.assertIn('response', result)
        self.assertEqual(result['messageVersion'], '1.0')

    @patch('lambda_function.get_job_registry')
    @patch('lambda_function.config')
    def test_get_build_failure_details_missing_params(self, mock_config, mock_get_registry):
        from lambda_function import lambda_handler

        mock_get_registry.return_value = _build_test_registry()

        event = {
            'function': 'get_build_failure_details',
            'parameters': [],
        }

        result = lambda_handler(event, None)
        response_body = result['response']['functionResponse']['responseBody']['TEXT']['body']
        self.assertIn('job_name', response_body)


class TestJobParameterFormatting(unittest.TestCase):
    """Test job parameter formatting utilities."""

    def test_format_parameters_as_bullets(self):
        """Test parameter formatting function."""
        params = {
            'PARAM1': {'description': 'Test param 1', 'required': True},
            'PARAM2': {'description': 'Test param 2', 'required': False, 'default': 'default_value'},
        }

        result = format_parameters_as_bullets(params)

        self.assertIn('PARAM1 - Test param 1', result)
        self.assertIn('PARAM2 (Optional) - Test param 2', result)
        self.assertIn('Default: default_value', result)

    def test_format_parameters_empty(self):
        """Test parameter formatting with no parameters."""
        result = format_parameters_as_bullets({})
        self.assertEqual(result, "• No parameters required")


if __name__ == '__main__':
    unittest.main()
