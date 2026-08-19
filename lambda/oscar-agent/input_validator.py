#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Input validation and sanitization for OSCAR Agent.

Defends against prompt injection, oversized payloads, and malicious input
before queries reach the Bedrock agent.
"""

import logging
import re

from oscar_shared.injection_patterns import (ACTION_WORDS, REVEAL_WORDS,
                                             STRUCTURAL_INJECTION_PATTERNS,
                                             SYSTEM_WORDS, TARGET_WORDS,
                                             USER_ID_MARKER)

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 4000

_USER_ID_MARKER = USER_ID_MARKER
_ACTION_WORDS = ACTION_WORDS
_TARGET_WORDS = TARGET_WORDS
_REVEAL_WORDS = REVEAL_WORDS
_SYSTEM_WORDS = SYSTEM_WORDS
INJECTION_PATTERNS = STRUCTURAL_INJECTION_PATTERNS


class InputValidationError(Exception):
    """Raised when input fails validation."""

    def __init__(self, message: str, user_message: str):
        super().__init__(message)
        self.user_message = user_message


def validate_and_sanitize(query: str) -> str:
    """Validate and sanitize user input before sending to the agent.

    Args:
        query: Raw user query

    Returns:
        Sanitized query

    Raises:
        InputValidationError: If the query fails validation
    """
    if not query or not query.strip():
        raise InputValidationError(
            "Empty query",
            "Please provide a question or request."
        )

    # Strip control characters (keep newlines and tabs)
    query = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', query)

    # Strip [USER_ID:] markers — these are system-injected and must not come from users
    if _USER_ID_MARKER.search(query):
        logger.warning("IDENTITY_SPOOFING_ATTEMPT: [USER_ID:] marker found in user input")
        query = _USER_ID_MARKER.sub('', query).strip()

    if len(query) > MAX_QUERY_LENGTH:
        raise InputValidationError(
            f"Query too long: {len(query)} chars (max {MAX_QUERY_LENGTH})",
            f"Your message is too long ({len(query)} characters). Please keep it under {MAX_QUERY_LENGTH} characters."
        )

    for pattern in INJECTION_PATTERNS:
        if pattern.search(query):
            logger.warning(f"PROMPT_INJECTION_DETECTED: pattern={pattern.pattern}")
            raise InputValidationError(
                f"Prompt injection detected: {pattern.pattern}",
                "Your message contains patterns that aren't allowed. Please rephrase your request."
            )

    # Intent-based detection: action + target co-occurrence
    if _ACTION_WORDS.search(query) and _TARGET_WORDS.search(query):
        logger.warning("PROMPT_INJECTION_DETECTED: action+target co-occurrence")
        raise InputValidationError(
            "Prompt injection detected: action+target co-occurrence",
            "Your message contains patterns that aren't allowed. Please rephrase your request."
        )

    # Reveal + system co-occurrence
    if _REVEAL_WORDS.search(query) and _SYSTEM_WORDS.search(query):
        logger.warning("PROMPT_INJECTION_DETECTED: reveal+system co-occurrence")
        raise InputValidationError(
            "Prompt injection detected: reveal+system co-occurrence",
            "Your message contains patterns that aren't allowed. Please rephrase your request."
        )

    return query
