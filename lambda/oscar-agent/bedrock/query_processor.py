#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Query Processor Module for OSCAR Agent.

This module handles query routing, context management, and the multi-attempt
query strategy for the OSCAR agent system.
"""

import logging
import re
from typing import Optional, Tuple

from bedrock.agent_invoker import BedrockAgentCore
from bedrock.error_handler import AgentErrorHandler
from config import config
from constants import LIMITED_ACCESS_MESSAGE

logger = logging.getLogger(__name__)


class QueryProcessor:
    """Processes queries with intelligent routing and context management."""

    def __init__(self, bedrock_agent: BedrockAgentCore, error_handler: AgentErrorHandler) -> None:
        """
        Initialize the query processor.

        Args:
            bedrock_agent: The Bedrock agent core instance
            error_handler: The error handler instance
        """
        self.bedrock_agent = bedrock_agent
        self.error_handler = error_handler

        logger.info("Initialized QueryProcessor")

    def process_query(
        self,
        query: str,
        privilege: bool,
        session_id: Optional[str] = None,
        context_summary: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Process a query with intelligent routing and context management.

        This method implements a multi-attempt strategy:
        1. Try with session_id if available (with context if provided)
        2. Try with context summary but no session_id
        3. Try with plain query as fallback

        Args:
            query: The user's query to the agent
            session_id: Optional session ID for maintaining conversation context
            context_summary: Optional summary of previous conversation context

        Returns:
            A tuple containing (response_text, session_id)
        """
        logger.info(f"AGENT_QUERY: Starting query - query_len={len(query)}, session_id='{session_id}', context_len={len(context_summary) if context_summary else 0}")
        logger.info(f"AGENT_QUERY: Query preview: {query[:config.log_query_preview_length]}...")

        # Store original session ID for context preservation
        original_session_id = session_id

        # Sanitize context for limited-tier users to prevent leaking privileged
        # security advisory details that may exist in shared thread history.
        if not privilege and context_summary:
            context_summary = self._sanitize_context_for_limited_user(context_summary)

        # The supervisor agent handles all routing internally through its
        # knowledge base integration and collaborator agents, so we just
        # need to invoke it directly

        # First attempt: Try with session_id if available
        if session_id:
            try:
                # Check if we also have context_summary - if so, use enhanced query WITH session_id
                if context_summary and context_summary.strip():
                    enhanced_query = f"Previous conversation context:\n{context_summary}\n\nCurrent question: {query}"
                    logger.info(f"AGENT_QUERY: Attempting enhanced query WITH session_id: {session_id}, context_len={len(context_summary)}")
                    logger.info(f"AGENT_QUERY: Enhanced query length: {len(enhanced_query)} characters")
                    response, returned_session_id = self.bedrock_agent.invoke_agent(enhanced_query, privilege, session_id)
                else:
                    # No context available, use plain query with session_id
                    logger.info(f"AGENT_QUERY: Attempting plain query with session_id: {session_id} (no context available)")
                    response, returned_session_id = self.bedrock_agent.invoke_agent(query, privilege, session_id)

                # Ensure we return the session ID (either returned or original)
                final_session_id = returned_session_id or session_id
                logger.info(f"AGENT_QUERY: Session-based query succeeded with session_id: {final_session_id}")
                logger.info(f"AGENT_QUERY: Response length: {len(response)} characters")
                return self._apply_limited_tier_override(response, privilege), final_session_id
            except Exception as e:
                logger.warning(f"AGENT_QUERY: Session-based query failed (possibly expired session): {e}")

        # Second attempt: Use enhanced query with context summary (without session_id)
        if context_summary and context_summary.strip():  # Check for non-empty context
            logger.info(f"AGENT_QUERY: Using context-enhanced query without session_id, context_len={len(context_summary)}")
            enhanced_query = f"Previous conversation context:\n{context_summary}\n\nCurrent question: {query}"
            logger.info(f"AGENT_QUERY: Enhanced query length: {len(enhanced_query)} characters")
            try:
                response, new_session_id = self.bedrock_agent.invoke_agent(enhanced_query, privilege, None)
                logger.info(f"AGENT_QUERY: Context-enhanced query succeeded with new session: {new_session_id}")
                logger.info(f"AGENT_QUERY: Response length: {len(response)} characters")
                return self._apply_limited_tier_override(response, privilege), new_session_id
            except Exception as e:
                logger.warning(f"AGENT_QUERY: Context-enhanced query failed: {e}")
        else:
            logger.info("AGENT_QUERY: No context summary provided or empty context")

        # Third attempt: Just use the plain query as last resort
        logger.info("AGENT_QUERY: Using plain query without context or session")
        try:
            response, new_session_id = self.bedrock_agent.invoke_agent(query, privilege, None)
            logger.info(f"AGENT_QUERY: Plain query succeeded with new session: {new_session_id}")
            logger.info(f"AGENT_QUERY: Response length: {len(response)} characters")
            return self._apply_limited_tier_override(response, privilege), new_session_id
        except Exception as e:
            logger.error(f"AGENT_QUERY: All query attempts failed: {e}", exc_info=True)
            error_message = self.error_handler.handle_agent_error(e, query)
            return error_message, original_session_id  # Return original session ID to preserve context

    # Canonical limited-tier message — single source of truth
    LIMITED_TIER_MESSAGE = LIMITED_ACCESS_MESSAGE

    # Pattern to detect CVE/security advisory content in text
    _CVE_PATTERN = re.compile(r'CVE-\d{4}-\d+|GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}')

    # Keywords that indicate security advisory content in conversation context
    _SECURITY_CONTEXT_INDICATORS = (
        'advisories.opensearch.org',
        'vulnerability',
        'vulnerabilities',
        'severity',
        'CRITICAL',
    )

    def _sanitize_context_for_limited_user(self, context_summary: str) -> str:
        """Remove security advisory details from conversation context for limited users.

        When a limited user messages in a thread where a privileged user previously
        received CVE details, those details exist in the shared conversation context.
        This method redacts assistant turns that contain security advisory data so the
        limited supervisor LLM cannot simply summarize them from context.

        Args:
            context_summary: The raw conversation context string with
                             ``User: ...`` / ``Assistant: ...`` turns.

        Returns:
            Sanitized context with security advisory responses replaced by the
            canonical limited-access message.
        """
        if not context_summary:
            return context_summary

        lines = context_summary.split('\n')
        sanitized_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Detect assistant turns that contain CVE/advisory content
            if line.startswith('Assistant:'):
                # Collect the full assistant response (may span multiple lines)
                assistant_block = [line]
                i += 1
                while i < len(lines) and not lines[i].startswith(('User:', 'Assistant:')):
                    assistant_block.append(lines[i])
                    i += 1

                full_response = '\n'.join(assistant_block)

                # Check if this assistant turn contains security advisory data
                if self._contains_security_advisory_content(full_response):
                    logger.info(
                        "AGENT_QUERY: Sanitized security advisory content from conversation context "
                        f"(original length: {len(full_response)} chars)"
                    )
                    sanitized_lines.append(f'Assistant: {self.LIMITED_TIER_MESSAGE}')
                else:
                    sanitized_lines.extend(assistant_block)
            else:
                sanitized_lines.append(line)
                i += 1

        return '\n'.join(sanitized_lines)

    def _contains_security_advisory_content(self, text: str) -> bool:
        """Check whether text contains security advisory/CVE data.

        Uses both regex pattern matching (CVE IDs, GHSA IDs) and keyword
        detection to identify advisory content that should not be exposed
        to limited-tier users.

        Args:
            text: The text to check.

        Returns:
            True if the text contains security advisory content.
        """
        # Check for CVE/GHSA identifiers
        if self._CVE_PATTERN.search(text):
            return True

        # Check for advisory-specific keywords (require multiple indicators
        # to avoid false positives on generic mentions)
        indicator_count = sum(
            1 for indicator in self._SECURITY_CONTEXT_INDICATORS
            if indicator in text
        )
        return indicator_count >= 2

    def _apply_limited_tier_override(self, response: str, privilege: bool) -> str:
        """Replace LLM response with canonical message for limited-tier security advisory queries.

        The Bedrock LLM cannot be reliably constrained via prompt instructions alone.
        When the user is not privileged and the response contains the advisory dashboard
        link OR CVE identifiers (indicating security advisory data leaked into the
        response — e.g. via conversation context), we replace the entire response
        deterministically.

        Args:
            response: The raw LLM response text.
            privilege: Whether the user has privileged access.

        Returns:
            The original response if privileged, or the canonical message if limited.
        """
        if not privilege and response:
            if ('advisories.opensearch.org' in response or
                    self._CVE_PATTERN.search(response)):
                logger.info("AGENT_QUERY: Limited-tier override applied — replacing LLM response with canonical message")
                return self.LIMITED_TIER_MESSAGE
        return response
