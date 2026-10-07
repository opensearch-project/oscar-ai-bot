# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Module loading for the release notifier Lambda.

The notifier's modules import each other by bare name the way they do inside the Lambda
bundle, so its directory goes on sys.path and each module is loaded from its own file
rather than by package import - several Lambdas in this repo have a `lambda_function`
module and the first one imported would otherwise win.
"""

import importlib.util
import os
import sys

import pytest

NOTIFIER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lambda', 'oscar-release-notifier')
)


def load(module_name: str):
    """Load one notifier module from its file, under a name unique to this Lambda."""
    if NOTIFIER_DIR not in sys.path:
        sys.path.insert(0, NOTIFIER_DIR)
    spec = importlib.util.spec_from_file_location(
        f'release_notifier_{module_name}', os.path.join(NOTIFIER_DIR, f'{module_name}.py'),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def cadence():
    return load('cadence')


@pytest.fixture(scope='module')
def identity():
    return load('identity')


@pytest.fixture(scope='module')
def message_builder():
    return load('message_builder')


@pytest.fixture(scope='module')
def notifier():
    return load('lambda_function')
