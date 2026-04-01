#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Bedrock Agent SSM Parameter Store configuration.

This module provides SSM parameter paths for Bedrock agents.
"""

from typing import Dict, List, Optional


def get_ssm_param_paths(env: str, agents: Optional[List] = None) -> Dict[str, str]:
    """Get SSM parameter paths for agent IDs and aliases.

    Args:
        env: Environment name (e.g., 'dev', 'prod')
        agents: Optional list of agents to generate paths for

    Returns:
        Dictionary mapping logical names to SSM parameter paths
    """
    paths = {
        "supervisor_agent_id": f"/oscar/{env}/bedrock/supervisor-agent-id",
        "supervisor_agent_alias": f"/oscar/{env}/bedrock/supervisor-agent-alias",
        "limited_supervisor_agent_id": f"/oscar/{env}/bedrock/limited-supervisor-agent-id",
        "limited_supervisor_agent_alias": f"/oscar/{env}/bedrock/limited-supervisor-agent-alias",
    }
    if agents:
        for agent in agents:
            paths[f"{agent.name}_agent_id"] = f"/oscar/{env}/bedrock/{agent.name}-agent-id"
            paths[f"{agent.name}_agent_alias"] = f"/oscar/{env}/bedrock/{agent.name}-agent-alias"
    return paths
