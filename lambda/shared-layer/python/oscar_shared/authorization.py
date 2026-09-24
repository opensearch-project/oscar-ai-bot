# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Authorization resolver.

Shared logic for resolving per-agent privilege from the central authorization
config, keyed by GitHub handle. The config (``FULLY_AUTHORIZED_USERS`` in the
central secret) has the shape::

    {
        "global": ["gh-handle", ...],
        "agents": {"jenkins": ["gh-handle", ...]}
    }

- A handle in ``global`` is privileged for *every* agent.
- A handle in ``agents.<name>`` is privileged for that agent *only* and has no
  privilege on other agents.

All checks fail closed: an empty or unknown handle resolves to no privilege.
"""

from typing import Dict, List, Set, Tuple


def resolve_authorized_agents(
    github_handle: str,
    global_admins: List[str],
    agent_tiers: Dict[str, List[str]],
) -> Tuple[bool, Set[str]]:
    """Resolve the privilege of a GitHub handle.

    Args:
        github_handle: The caller's linked GitHub handle (may be empty).
        global_admins: Handles privileged for every agent.
        agent_tiers: Mapping of agent name -> handles privileged for that agent.

    Returns:
        (is_global, agents) where ``is_global`` is True when the handle is a
        global admin, and ``agents`` is the set of agent names the handle is
        privileged for (excluding the implicit global grant). Fails closed:
        an empty handle returns ``(False, set())``.
    """
    if not github_handle:
        return (False, set())

    is_global = github_handle in (global_admins or [])
    agents = {
        agent
        for agent, handles in (agent_tiers or {}).items()
        if github_handle in (handles or [])
    }
    return (is_global, agents)
