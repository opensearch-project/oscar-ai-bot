# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Two-person approval guard.

Shared validation logic used by any Lambda that enforces ENABLE_2PR.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def validate_two_person_approval(
    params: Dict[str, Any],
    enable_2pr: bool,
    action_label: str,
) -> Optional[Dict[str, Any]]:
    """Validate two-person approval if the feature flag is enabled.

    Args:
        params: Request parameters dict (must contain requester_user_id, approver_user_id).
        enable_2pr: Whether the ENABLE_2PR flag is active.
        action_label: Human-readable label for logs (e.g. 'job=docker-scan', 'channel=C123').

    Returns:
        None if validation passes (or flag is off). Otherwise a dict with
        'status'='error' and a 'message' suitable for returning to the caller.
    """
    if not enable_2pr:
        return None

    requester_user_id = params.get('requester_user_id')
    approver_user_id = params.get('approver_user_id')

    if not requester_user_id or not approver_user_id:
        return {
            'status': 'error',
            'message': 'SECURITY ERROR: requester_user_id and approver_user_id are required for two-person approval.',
        }

    if requester_user_id.strip() == approver_user_id.strip():
        return {
            'status': 'error',
            'message': (
                f'SECURITY ERROR: Self-approval is not permitted. The user who requested this action '
                f'({requester_user_id.strip()}) cannot also approve it. A different authorized user must confirm.'
            ),
        }

    logger.info(
        f'TWO_PERSON_APPROVAL: requester={requester_user_id.strip()}, '
        f'approver={approver_user_id.strip()}, {action_label}'
    )
    return None
