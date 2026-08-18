# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Ensure the Jenkins lambda_function is in sys.modules for this package.

The test_two_person_approval.py in the github test package injects a mock
lambda_function into sys.modules. This conftest re-loads the real Jenkins
lambda_function before each test to avoid cross-contamination.
"""

import importlib.util
import os
import sys

import pytest

_JENKINS_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'jenkins', 'lambda',
)


@pytest.fixture(autouse=True)
def _ensure_jenkins_lambda_function():
    """Re-seat sys.modules['lambda_function'] to the Jenkins module before each test."""
    if _JENKINS_LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _JENKINS_LAMBDA_PATH)
    sys.modules.pop('lambda_function', None)
    spec = importlib.util.spec_from_file_location(
        'lambda_function',
        os.path.join(_JENKINS_LAMBDA_PATH, 'lambda_function.py'),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules['lambda_function'] = mod
    spec.loader.exec_module(mod)
    yield
