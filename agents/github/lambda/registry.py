# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Function registry for GitHub agent.

Single source of truth for every function the agent exposes. Adding a new
function means adding one entry here — no other file needs updating for
routing, token scoping, write classification, or owner injection.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass(frozen=True)
class FunctionDef:
    """Declarative definition of a GitHub agent function."""

    # Routing: MCP tool name, or None for direct API handlers
    mcp_tool: Optional[str] = None

    # Whether this function mutates state (controls audit logging level)
    write: bool = False

    # Token scope: "repo" = scoped to params["repo"], "org" = org-wide
    token_scope: str = "repo"

    # Whether the MCP tool needs owner/repo injected
    needs_owner: bool = False

    # Authorization policy: None = no pre-check, "admin" = admin-only,
    # "maintainer" = live per-repo MAINTAINERS.md check
    auth_policy: Optional[str] = None

    # Authorization tier for group gate: "contributor", "maintainer", "admin"
    tier: str = "contributor"

    # Transform function: (params) -> mcp_args (only for MCP-routed functions)
    transform: Optional[Callable[[Dict[str, str]], Dict[str, Any]]] = None

    # Direct API handler: (token, params, request_id) -> result
    handler: Optional[Callable] = None

    def __post_init__(self):
        if self.write and self.auth_policy is None:
            raise ValueError(
                "write functions must declare an explicit auth_policy"
            )

    @property
    def is_direct_api(self) -> bool:
        return self.mcp_tool is None
