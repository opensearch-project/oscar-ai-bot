# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""HMAC-signed OAuth state to prevent CSRF/state forgery."""

import base64
import hashlib
import hmac
import time


STATE_TTL_SECONDS = 600


def generate_state(user_id: str, workspace_id: str, signing_key: str) -> str:
    """Generate an opaque, HMAC-signed OAuth state parameter."""
    timestamp = str(int(time.time()))
    payload = f"{user_id}:{workspace_id}:{timestamp}"
    signature = hmac.HMAC(
        signing_key.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    state = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(state.encode()).decode()


def verify_state(state_token: str, signing_key: str) -> tuple:
    """Verify and decode an HMAC-signed OAuth state parameter.

    Returns:
        (user_id, workspace_id) on success

    Raises:
        ValueError if the state is invalid, tampered, or expired.
    """
    try:
        decoded = base64.urlsafe_b64decode(state_token.encode()).decode()
    except Exception:
        raise ValueError("Invalid state encoding.")

    parts = decoded.rsplit(":", 1)
    if len(parts) != 2:
        raise ValueError("Invalid state format.")

    payload, signature = parts
    expected_sig = hmac.HMAC(
        signing_key.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_sig):
        raise ValueError("State signature verification failed.")

    segments = payload.split(":")
    if len(segments) != 3:
        raise ValueError("Invalid state payload.")

    user_id, workspace_id, timestamp_str = segments

    try:
        timestamp = int(timestamp_str)
    except ValueError:
        raise ValueError("Invalid state timestamp.")

    if time.time() - timestamp > STATE_TTL_SECONDS:
        raise ValueError("State has expired.")

    return user_id, workspace_id