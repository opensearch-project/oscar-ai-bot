# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for agent tests."""

import os
import sys

# Add agent source paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'agents', 'jenkins', 'lambda'))
