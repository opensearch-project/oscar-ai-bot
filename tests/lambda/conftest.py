# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for Lambda function tests."""

import os
import sys
from unittest.mock import MagicMock

# Add Lambda source paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda', 'oscar-agent'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lambda', 'oscar-communication-handler'))


def _build_mock_config():
    """Build a mock config object.

    MagicMock auto-returns mocks for any attribute access, so we only
    need to set values that production code accesses as dicts or lists
    (which would fail on a bare Mock).
    """
    cfg = MagicMock()
    cfg.patterns = {
        'channel_id': r'\b(C[A-Z0-9]{10,})\b',
        'channel_ref': r'#([a-z0-9-]+)',
        'at_symbol': r'@([a-zA-Z0-9_-]+)',
        'mention': r'<@[A-Z0-9]+>',
        'heading': r'^#{1,6}\s+(.+)$',
        'bold': r'\*\*(.+?)\*\*',
        'italic': r'(?<!\*)\*([^*]+?)\*(?!\*)',
        'link': r'\[([^\]]+)\]\(([^)]+)\)',
        'bullet': r'^[\*\-]\s+',
        'channel_mention': r'(?<!<)#([a-zA-Z0-9_-]+)(?!>)',
        'version': r'version\s+(\d+\.\d+\.\d+)',
    }
    cfg.fully_authorized_users = ['U_ADMIN']
    cfg.dm_authorized_users = ['U_DM']
    cfg.channel_allow_list = ['C_ALLOWED']
    cfg.agent_queries = {}
    return cfg


# Patch config module BEFORE any oscar-agent modules are imported.
# This prevents _ConfigProxy from trying to load real AWS secrets.
_mock_config = _build_mock_config()
sys.modules.setdefault('config', MagicMock())
sys.modules['config'].config = _mock_config
sys.modules['config'].Config = MagicMock
sys.modules['config']._ConfigProxy = MagicMock
