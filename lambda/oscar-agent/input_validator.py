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

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 4000

# Patterns that attempt to override agent instructions
# Intent-based detection: flag when action words and target words co-occur
_ACTION_WORDS = re.compile(
    r"(ignore|disregard|forget|override|bypass|skip|drop|abandon|suppress|erase|delete|remove|clear)", re.IGNORECASE
)
_TARGET_WORDS = re.compile(
    r"(instructions|prompts|rules|guidelines|constraints|guardrails|directives|policies|restrictions|programming|training|told|learned|taught)", re.IGNORECASE
)
_REVEAL_WORDS = re.compile(
    r"(reveal|show|print|output|display|dump|leak|expose|extract|repeat|list|give\s+me)", re.IGNORECASE
)
_SYSTEM_WORDS = re.compile(
    r"(system\s*prompt|instructions|rules|guidelines|initial\s*prompt|hidden\s*prompt|secret\s*prompt|internal\s*prompt|original\s*prompt)", re.IGNORECASE
)

# Structural patterns that are always suspicious regardless of context
INJECTION_PATTERNS = [
    re.compile(r"you\s+are\s+now\s+(a|an|the)\b", re.IGNORECASE),
    re.compile(r"(new|updated)\s+(system\s+)?prompt\s*:", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you\s+(have\s+no|don'?t\s+have)\s+(restrictions|rules|guidelines)", re.IGNORECASE),
    re.compile(r"<\s*/?\s*(system|instruction|prompt)\s*>", re.IGNORECASE),
    re.compile(r"act\s+(like|as)\s+user\s+\w+", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+(your|any|the)", re.IGNORECASE),
    re.compile(r"pretend\s+(you|that)\s+(are|have)\s+no\s+(rules|restrictions|limits)", re.IGNORECASE),
]


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
