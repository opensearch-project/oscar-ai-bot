# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the authorization resolver."""

import os
import sys

# Add shared layer path so oscar_shared can be found
_SHARED_LAYER_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lambda', 'shared-layer', 'python')
sys.path.insert(0, _SHARED_LAYER_DIR)

from oscar_shared.authorization import resolve_authorized_agents  # noqa: E402

_GLOBAL = ['admin-gh']
_AGENTS = {'jenkins': ['jenkins-gh', 'admin-gh'], 'metrics': ['metrics-gh']}


class TestResolveAuthorizedAgents:

    def test_global_admin(self):
        is_global, agents = resolve_authorized_agents('admin-gh', _GLOBAL, _AGENTS)
        assert is_global is True
        # admin-gh is also explicitly listed under jenkins
        assert agents == {'jenkins'}

    def test_agent_level_only(self):
        is_global, agents = resolve_authorized_agents('jenkins-gh', _GLOBAL, _AGENTS)
        assert is_global is False
        assert agents == {'jenkins'}

    def test_different_agent_only(self):
        is_global, agents = resolve_authorized_agents('metrics-gh', _GLOBAL, _AGENTS)
        assert is_global is False
        assert agents == {'metrics'}

    def test_unknown_handle(self):
        is_global, agents = resolve_authorized_agents('nobody-gh', _GLOBAL, _AGENTS)
        assert is_global is False
        assert agents == set()

    def test_empty_handle_fails_closed(self):
        is_global, agents = resolve_authorized_agents('', _GLOBAL, _AGENTS)
        assert is_global is False
        assert agents == set()

    def test_none_config_fails_closed(self):
        is_global, agents = resolve_authorized_agents('admin-gh', None, None)
        assert is_global is False
        assert agents == set()

    def test_handle_in_multiple_agents(self):
        agents_cfg = {'jenkins': ['multi-gh'], 'metrics': ['multi-gh']}
        is_global, agents = resolve_authorized_agents('multi-gh', [], agents_cfg)
        assert is_global is False
        assert agents == {'jenkins', 'metrics'}
