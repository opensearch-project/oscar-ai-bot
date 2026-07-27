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
from datetime import date
from typing import Dict, Optional, Tuple

from bedrock.agent_invoker import BedrockAgentCore
from bedrock.error_handler import AgentErrorHandler
from config import config

logger = logging.getLogger(__name__)

# Pattern to detect CVE/security advisory content in conversation context
_CVE_PATTERN = re.compile(r'CVE-\d{4}-\d+|GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}')


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
        context_summary: Optional[str] = None,
        session_attributes: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, Optional[str]]:
        """
        Process a query with intelligent routing and context management.

        This method implements a multi-attempt strategy:
        1. Try with session_id if available (with context if provided)
        2. Try with context summary but no session_id
        3. Try with plain query as fallback

        Access tier separation is handled entirely at the supervisor agent level:
        - Privileged users are routed to the privileged supervisor (full capabilities)
        - Limited users are routed to the limited supervisor (no security advisories)

        Args:
            query: The user's query to the agent
            privilege: Whether the user has privileged access
            session_id: Optional session ID for maintaining conversation context
            context_summary: Optional summary of previous conversation context
            session_attributes: Out-of-band session attributes (identity provenance)

        Returns:
            A tuple containing (response_text, session_id)
        """
        query = f"[TODAY: {date.today().isoformat()}] {query}"
        logger.info(f"AGENT_QUERY: Starting query - query_len={len(query)}, session_id='{session_id}', context_len={len(context_summary) if context_summary else 0}")
        logger.info(f"AGENT_QUERY: Query preview: {query[:config.log_query_preview_length]}...")

        # Store original session ID for context preservation
        original_session_id = session_id

        # Strip security advisory data from thread context for limited users.
        # In shared threads, a privileged user's prior CVE responses would be
        # visible in the context — the LLM can't reliably ignore them via
        # instruction alone, so we remove them before sending to the agent.
        if not privilege and context_summary:
            context_summary = self._strip_advisory_content(context_summary)

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
                    response, returned_session_id = self.bedrock_agent.invoke_agent(enhanced_query, privilege, session_id, session_attributes)
                else:
                    # No context available, use plain query with session_id
                    logger.info(f"AGENT_QUERY: Attempting plain query with session_id: {session_id} (no context available)")
                    response, returned_session_id = self.bedrock_agent.invoke_agent(query, privilege, session_id, session_attributes)

                # Ensure we return the session ID (either returned or original)
                final_session_id = returned_session_id or session_id
                logger.info(f"AGENT_QUERY: Session-based query succeeded with session_id: {final_session_id}")
                logger.info(f"AGENT_QUERY: Response length: {len(response)} characters")
                return response, final_session_id
            except Exception as e:
                logger.warning(f"AGENT_QUERY: Session-based query failed (possibly expired session): {e}")

        # Second attempt: Use enhanced query with context summary (without session_id)
        if context_summary and context_summary.strip():  # Check for non-empty context
            logger.info(f"AGENT_QUERY: Using context-enhanced query without session_id, context_len={len(context_summary)}")
            enhanced_query = f"Previous conversation context:\n{context_summary}\n\nCurrent question: {query}"
            logger.info(f"AGENT_QUERY: Enhanced query length: {len(enhanced_query)} characters")
            try:
                response, new_session_id = self.bedrock_agent.invoke_agent(enhanced_query, privilege, None, session_attributes)
                logger.info(f"AGENT_QUERY: Context-enhanced query succeeded with new session: {new_session_id}")
                logger.info(f"AGENT_QUERY: Response length: {len(response)} characters")
                return response, new_session_id
            except Exception as e:
                logger.warning(f"AGENT_QUERY: Context-enhanced query failed: {e}")
        else:
            logger.info("AGENT_QUERY: No context summary provided or empty context")

        # Third attempt: Just use the plain query as last resort
        logger.info("AGENT_QUERY: Using plain query without context or session")
        try:
            response, new_session_id = self.bedrock_agent.invoke_agent(query, privilege, None, session_attributes)
            logger.info(f"AGENT_QUERY: Plain query succeeded with new session: {new_session_id}")
            logger.info(f"AGENT_QUERY: Response length: {len(response)} characters")
            return response, new_session_id
        except Exception as e:
            logger.error(f"AGENT_QUERY: All query attempts failed: {e}", exc_info=True)
            error_message = self.error_handler.handle_agent_error(e, query)
            return error_message, original_session_id  # Return original session ID to preserve context

    @staticmethod
    def _strip_advisory_content(context_summary: str) -> str:
        """Remove security advisory data from conversation context.

        In shared Slack threads, a privileged user may have previously received
        CVE details. When a limited user messages in the same thread, those
        details are part of the context string. The LLM cannot reliably ignore
        data in its context via instruction alone, so we strip assistant turns
        that contain CVE/GHSA identifiers before passing context to the agent.

        Args:
            context_summary: Conversation context with User:/Assistant: turns.

        Returns:
            Context with advisory-containing assistant turns removed.
        """
        if not context_summary:
            return context_summary

        lines = context_summary.split('\n')
        cleaned_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]

            if line.startswith('Assistant:'):
                # Collect the full assistant turn (may span multiple lines)
                block = [line]
                i += 1
                while i < len(lines) and not lines[i].startswith(('User:', 'Assistant:')):
                    block.append(lines[i])
                    i += 1

                # Only keep the turn if it doesn't contain CVE/GHSA data
                full_turn = '\n'.join(block)
                if _CVE_PATTERN.search(full_turn):
                    logger.info(
                        "AGENT_QUERY: Stripped advisory content from thread context "
                        f"({len(full_turn)} chars)"
                    )
                else:
                    cleaned_lines.extend(block)
            else:
                cleaned_lines.append(line)
                i += 1

        return '\n'.join(cleaned_lines)
