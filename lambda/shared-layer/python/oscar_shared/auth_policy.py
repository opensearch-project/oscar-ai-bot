# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared authorization policy checks for OSCAR agent Lambdas.

Provides the group gate (coarse, pre-token tier check) and simple
tier-resolution helpers used by any agent Lambda that enforces
tier-based authorization.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def check_group_gate(
    tier: Optional[str], session_attributes: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """Coarse pre-token authorization by function tier.

    Runs before token acquisition — no I/O, no API calls.

    Args:
        tier: The function's tier from the registry ("contributor", "maintainer", "admin").
        session_attributes: Out-of-band session attributes from the Bedrock event.

    Returns:
        None if the gate passes, or an error dict to return to the caller.
    """
    if tier in (None, "contributor"):
        return None

    if tier == "maintainer":
        if (session_attributes.get("requester_is_maintainer") != "True"
                and session_attributes.get("requester_tier") != "admin"):
            logger.warning(
                "GROUP_GATE_DENIED: maintainer tier required, "
                "requester_is_maintainer=%s, requester_tier=%s",
                session_attributes.get("requester_is_maintainer"),
                session_attributes.get("requester_tier"),
            )
            return {
                "status": "error",
                "message": (
                    "AUTHORIZATION ERROR: This operation requires maintainer privileges. "
                    "You are not a maintainer of any repository in the organization."
                ),
            }

    elif tier == "admin":
        if session_attributes.get("requester_tier") != "admin":
            logger.warning(
                "GROUP_GATE_DENIED: admin tier required, requester_tier=%s",
                session_attributes.get("requester_tier"),
            )
            return {
                "status": "error",
                "message": (
                    "AUTHORIZATION ERROR: This operation requires admin privileges. "
                    "Only fully authorized users can perform this operation."
                ),
            }

    return None


def derive_tier(is_admin_flag: bool, is_maintainer_flag: bool) -> str:
    """Derive the authorization tier from identity flags."""
    if is_admin_flag:
        return "admin"
    if is_maintainer_flag:
        return "maintainer"
    return "contributor"
