# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for OAuth state generation and verification."""

import os
import sys
import time

import pytest
from oauth_state import STATE_TTL_SECONDS, generate_state, verify_state

# Add Lambda source path so oauth_state can be found
_IDENTITY_LAMBDA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lambda', 'oscar-identity')
sys.path.insert(0, _IDENTITY_LAMBDA_DIR)


SIGNING_KEY = "test-secret-key"


class TestGenerateState:

    def test_returns_base64_string(self):
        state = generate_state("U123", "T01WORK", SIGNING_KEY)
        assert isinstance(state, str)
        assert len(state) > 0

    def test_different_users_produce_different_states(self):
        s1 = generate_state("U111", "T01", SIGNING_KEY)
        s2 = generate_state("U222", "T01", SIGNING_KEY)
        assert s1 != s2

    def test_different_workspaces_produce_different_states(self):
        s1 = generate_state("U123", "T01", SIGNING_KEY)
        s2 = generate_state("U123", "T02", SIGNING_KEY)
        assert s1 != s2


class TestVerifyState:

    def test_valid_state_returns_user_and_workspace(self):
        state = generate_state("U123", "T01WORK", SIGNING_KEY)
        user_id, workspace_id = verify_state(state, SIGNING_KEY)
        assert user_id == "U123"
        assert workspace_id == "T01WORK"

    def test_tampered_state_raises(self):
        import base64
        state = generate_state("U123", "T01", SIGNING_KEY)
        decoded = base64.urlsafe_b64decode(state.encode()).decode()
        tampered = decoded.replace("U123", "U999")
        tampered_token = base64.urlsafe_b64encode(tampered.encode()).decode()
        with pytest.raises(ValueError, match="signature verification failed"):
            verify_state(tampered_token, SIGNING_KEY)

    def test_wrong_key_raises(self):
        state = generate_state("U123", "T01", SIGNING_KEY)
        with pytest.raises(ValueError, match="signature verification failed"):
            verify_state(state, "wrong-key")

    def test_invalid_base64_raises(self):
        with pytest.raises(ValueError, match="Invalid state encoding"):
            verify_state("not-valid-base64!!!", SIGNING_KEY)

    def test_expired_state_raises(self):
        import base64
        import hashlib
        import hmac

        # Create a state with an old timestamp
        old_timestamp = str(int(time.time()) - STATE_TTL_SECONDS - 100)
        payload = f"U123:T01:{old_timestamp}"
        signature = hmac.HMAC(
            SIGNING_KEY.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        state_str = f"{payload}:{signature}"
        token = base64.urlsafe_b64encode(state_str.encode()).decode()

        with pytest.raises(ValueError, match="expired"):
            verify_state(token, SIGNING_KEY)

    def test_invalid_timestamp_raises(self):
        import base64
        import hashlib
        import hmac

        payload = "U123:T01:not_a_number"
        signature = hmac.HMAC(
            SIGNING_KEY.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        state_str = f"{payload}:{signature}"
        token = base64.urlsafe_b64encode(state_str.encode()).decode()

        with pytest.raises(ValueError, match="Invalid state timestamp"):
            verify_state(token, SIGNING_KEY)

    def test_missing_segments_raises(self):
        import base64
        import hashlib
        import hmac

        # Only 2 segments instead of 3
        payload = "U123:T01"
        signature = hmac.HMAC(
            SIGNING_KEY.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        state_str = f"{payload}:{signature}"
        token = base64.urlsafe_b64encode(state_str.encode()).decode()

        with pytest.raises(ValueError, match="Invalid state payload"):
            verify_state(token, SIGNING_KEY)
