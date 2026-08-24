# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared prompt injection detection patterns.

Used by inbound screening (webhook handler, input validator) and outbound
screening (github_api) to detect injection attempts in untrusted content.
"""

import re
from typing import List

# Structural patterns — always suspicious regardless of surrounding context.
STRUCTURAL_INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r'<\s*/?\s*(system|instruction|prompt)\s*>', re.IGNORECASE),
    re.compile(r'\[INST\]|\[/INST\]', re.IGNORECASE),
    re.compile(r'```\s*system', re.IGNORECASE),
    re.compile(
        r'(ignore|disregard|override|forget)\s+(all\s+)?(previous|prior|above)'
        r'\s+(instructions?|rules?|prompts?)',
        re.IGNORECASE,
    ),
    re.compile(r'(new|updated?)\s+(system\s+)?prompt', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+(a|an|the)\b', re.IGNORECASE),
    re.compile(r'act\s+(like|as)\s+(a\s+)?different', re.IGNORECASE),
    re.compile(
        r'(reveal|show|print|dump|expose)\s+(your\s+)?(system\s*prompt|instructions|rules)',
        re.IGNORECASE,
    ),
    re.compile(r'do\s+not\s+follow\s+(your|any|the)', re.IGNORECASE),
    re.compile(
        r'pretend\s+(you|that)\s+(are|have)\s+no\s+(rules|restrictions|limits)',
        re.IGNORECASE,
    ),
    re.compile(
        r"act\s+as\s+if\s+you\s+(have\s+no|don'?t\s+have)\s+(restrictions|rules|guidelines)",
        re.IGNORECASE,
    ),
    re.compile(r'act\s+(like|as)\s+user\s+\w+', re.IGNORECASE),
]

# Co-occurrence word lists for intent-based detection.
# Flag when an action word and a target word appear together.
ACTION_WORDS = re.compile(
    r'(ignore|disregard|forget|override|bypass|skip|drop|abandon'
    r'|suppress|erase|delete|remove|clear)',
    re.IGNORECASE,
)
TARGET_WORDS = re.compile(
    r'(instructions|prompts|rules|guidelines|constraints|guardrails'
    r'|directives|policies|restrictions|programming|training|told|learned|taught)',
    re.IGNORECASE,
)
REVEAL_WORDS = re.compile(
    r'(reveal|show|print|output|display|dump|leak|expose|extract|repeat|list|give\s+me)',
    re.IGNORECASE,
)
SYSTEM_WORDS = re.compile(
    r'(system\s*prompt|instructions|rules|guidelines|initial\s*prompt'
    r'|hidden\s*prompt|secret\s*prompt|internal\s*prompt|original\s*prompt)',
    re.IGNORECASE,
)

# System-injected markers — must never appear in raw user input.
USER_ID_MARKER = re.compile(r'\[USER_ID:\s*[^\]]*\]', re.IGNORECASE)
