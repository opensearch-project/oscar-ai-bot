# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for plugin tests."""

import os
import sys

# Add plugin source paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'plugins', 'jenkins', 'lambda'))
