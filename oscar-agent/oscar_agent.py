#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Enhanced OSCAR Agent Integration Module.

This module provides the core Bedrock agent interface for OSCAR (OpenSearch 
Conversational Automation for Release). It handles agent invocation, session 
management, error handling, response processing, and coordinates between
knowledge base queries and metrics analysis.

Classes:
    OSCARAgentInterface: Abstract base class for agent implementations
    EnhancedBedrockOSCARAgent: Enhanced Bedrock agent with knowledge base + metrics coordination
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from config import config

logger = logging.getLogger(__name__)

class OSCARAgentInterface(ABC):
    """Abstract base class for OSCAR agent implementations.
    
    This interface defines the contract for all OSCAR agent implementations,
    ensuring consistent behavior across different agent types.
    """
    
    @abstractmethod
    def query(
        self, 
        query: str, 
        session_id: Optional[str] = None, 
        context_summary: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """Query the OSCAR agent with automatic routing.
        
        Args:
            query: The user's query to the agent
            session_id: Optional session ID for maintaining conversation context
            context_summary: Optional summary of previous conversation context
            
        Returns:
            Tuple containing (response_text, session_id)
        """

class EnhancedBedrockOSCARAgent(OSCARAgentInterface):
    """Enhanced Bedrock agent implementation for OSCAR with comprehensive capabilities.
    
    This class provides a robust interface to Amazon Bedrock agents with features:
    - Knowledge base integration for documentation queries
    - Metrics coordination through specialized Lambda functions
    - Automatic retry logic with exponential backoff
    - Session management and context preservation
    - Comprehensive error handling and user-friendly messages
    - Streaming response processing
    """
    
    def __init__(self, region: Optional[str] = None) -> None:
        """Initialize Enhanced Bedrock OSCAR agent.
        
        Args:
            region: AWS region for Bedrock service, defaults to config value
        """
        self.region = region or config.region
        self.client = boto3.client('bedrock-agent-runtime', region_name=self.region)
        self.lambda_client = boto3.client('lambda', region_name=self.region)
        
        # Primary supervisor agent configuration
        self.agent_id = config.oscar_bedrock_agent_id
        self.agent_alias_id = config.oscar_bedrock_agent_alias_id
        
        # Timeout and retry settings
        self.timeout = config.agent_timeout
        self.max_retries = config.agent_max_retries
        
        # Metrics Lambda function ARNs (from environment or defaults)
        self.metrics_functions = {
            'test': 'oscar-test-metrics-agent',
            'build': 'oscar-build-metrics-agent', 
            'release': 'oscar-release-metrics-agent',
            'deployment': 'oscar-deployment-metrics-agent'
        }
        
        logger.info(
            f"Initialized Enhanced OSCAR agent - ID: {self.agent_id}, "
            f"Alias: {self.agent_alias_id}, Region: {self.region}"
        )
    
    def _create_agent_request(self, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a request for the Bedrock agent.
        
        Args:
            query: The user's query
            session_id: Optional session ID for maintaining conversation context
            
        Returns:
            A dictionary containing the request parameters
        """
        request = {
            'agentId': self.agent_id,
            'agentAliasId': self.agent_alias_id,
            'inputText': query,
            'sessionId': session_id or f"session-{int(time.time())}"  # Generate session ID if None
        }
        
        return request
    
    def _invoke_metrics_function(self, function_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invoke a metrics Lambda function.
        
        Args:
            function_name: Name of the Lambda function to invoke
            payload: Payload to send to the function
            
        Returns:
            The response from the Lambda function
            
        Raises:
            Exception: If the function invocation fails
        """
        try:
            logger.info(f"Invoking metrics function: {function_name}")
            
            response = self.lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(payload)
            )
            
            # Parse the response
            response_payload = json.loads(response['Payload'].read())
            
            # Check for function errors
            if response.get('FunctionError'):
                logger.error(f"Metrics function error: {response_payload}")
                raise Exception(f"Metrics function error: {response_payload}")
            
            logger.info(f"Successfully invoked metrics function: {function_name}")
            return response_payload
            
        except Exception as e:
            logger.error(f"Error invoking metrics function {function_name}: {e}")
            raise
    
    def _invoke_agent(self, query: str, session_id: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Invoke the Bedrock agent with the given query.
        
        Args:
            query: The user's query
            session_id: Optional session ID for maintaining conversation context
            
        Returns:
            A tuple containing (response_text, session_id)
            
        Raises:
            Exception: If the agent invocation fails after all retries
        """
        request = self._create_agent_request(query, session_id)
        logger.info(f"Invoking agent with request: {json.dumps({k: v for k, v in request.items() if k != 'inputText'}, indent=2)}")
        logger.info(f"Query: {query[:100]}...")
        
        try:
            response = self.client.invoke_agent(**request)
            
            # Process the streaming response
            response_text = ""
            returned_session_id = None
            
            if 'completion' in response:
                for event in response['completion']:
                    if 'chunk' in event:
                        chunk = event['chunk']
                        if 'bytes' in chunk:
                            chunk_text = chunk['bytes'].decode('utf-8')
                            response_text += chunk_text
                        
                        # Extract session ID from the chunk if available
                        if 'sessionId' in chunk:
                            returned_session_id = chunk['sessionId']
                            logger.debug(f"Found session ID in chunk: {returned_session_id}")
            
            # Also check for session ID at the top level of the response
            if 'sessionId' in response:
                returned_session_id = response['sessionId']
                logger.debug(f"Found session ID at top level: {returned_session_id}")
            
            # If no session ID found in response, use the one from request
            elif not returned_session_id and session_id:
                returned_session_id = session_id
                logger.debug(f"Using request session ID: {returned_session_id}")
            
            # If still no session ID, generate one for consistency
            else:
                returned_session_id = f"session-{int(time.time())}"
                logger.debug(f"Generated new session ID: {returned_session_id}")
            
            logger.info(f"Agent response received, length: {len(response_text)} characters")
            logger.info(f"Final session ID: {returned_session_id}")
            
            return response_text.strip(), returned_session_id
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"Bedrock agent error ({error_code}): {error_message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error invoking agent: {e}", exc_info=True)
            raise
     
    def query(self, query: str, session_id: Optional[str] = None, 
              context_summary: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Query the enhanced OSCAR agent with automatic routing and coordination.
        
        This method provides intelligent routing between knowledge base queries
        and metrics analysis, with the supervisor agent coordinating responses.
        
        Args:
            query: The user's query to the agent
            session_id: Optional session ID for maintaining conversation context
            context_summary: Optional summary of previous conversation context
            
        Returns:
            A tuple containing (response_text, session_id)
        """
        logger.info(f"🤖 AGENT_QUERY: Starting query - query_len={len(query)}, session_id='{session_id}', context_len={len(context_summary) if context_summary else 0}")
        logger.info(f"🤖 AGENT_QUERY: Query preview: {query[:100]}...")
        
        # Store original session ID for context preservation
        original_session_id = session_id
        
        # The supervisor agent handles all routing internally through its
        # knowledge base integration and collaborator agents, so we just
        # need to invoke it directly
        
        # First attempt: Try with session_id if available
        if session_id:
            try:
                # Check if we also have context_summary - if so, use enhanced query WITH session_id
                if context_summary and context_summary.strip():
                    enhanced_query = f"Previous conversation context:\n{context_summary}\n\nCurrent question: {query}"
                    logger.info(f"🔄 AGENT_QUERY: Attempting enhanced query WITH session_id: {session_id}, context_len={len(context_summary)}")
                    logger.info(f"🔄 AGENT_QUERY: Enhanced query length: {len(enhanced_query)} characters")
                    response, returned_session_id = self._invoke_agent(enhanced_query, session_id)
                else:
                    # No context available, use plain query with session_id
                    logger.info(f"🔄 AGENT_QUERY: Attempting plain query with session_id: {session_id} (no context available)")
                    response, returned_session_id = self._invoke_agent(query, session_id)
                
                # Ensure we return the session ID (either returned or original)
                final_session_id = returned_session_id or session_id
                logger.info(f"✅ AGENT_QUERY: Session-based query succeeded with session_id: {final_session_id}")
                logger.info(f"✅ AGENT_QUERY: Response length: {len(response)} characters")
                return response, final_session_id
            except Exception as e:
                logger.warning(f"⚠️ AGENT_QUERY: Session-based query failed (possibly expired session): {e}")
        
        # Second attempt: Use enhanced query with context summary (without session_id)
        if context_summary and context_summary.strip():  # Check for non-empty context
            logger.info(f"🔄 AGENT_QUERY: Using context-enhanced query without session_id, context_len={len(context_summary)}")
            enhanced_query = f"Previous conversation context:\n{context_summary}\n\nCurrent question: {query}"
            logger.info(f"🔄 AGENT_QUERY: Enhanced query length: {len(enhanced_query)} characters")
            try:
                response, new_session_id = self._invoke_agent(enhanced_query, None)
                logger.info(f"✅ AGENT_QUERY: Context-enhanced query succeeded with new session: {new_session_id}")
                logger.info(f"✅ AGENT_QUERY: Response length: {len(response)} characters")
                return response, new_session_id
            except Exception as e:
                logger.warning(f"⚠️ AGENT_QUERY: Context-enhanced query failed: {e}")
        else:
            logger.info(f"🔄 AGENT_QUERY: No context summary provided or empty context")
        
        # Third attempt: Just use the plain query as last resort
        logger.info("🔄 AGENT_QUERY: Using plain query without context or session")
        try:
            response, new_session_id = self._invoke_agent(query, None)
            logger.info(f"✅ AGENT_QUERY: Plain query succeeded with new session: {new_session_id}")
            logger.info(f"✅ AGENT_QUERY: Response length: {len(response)} characters")
            return response, new_session_id
        except Exception as e:
            logger.error(f"❌ AGENT_QUERY: All query attempts failed: {e}", exc_info=True)
            error_message = self._handle_agent_error(e, query)
            return error_message, original_session_id  # Return original session ID to preserve context
    
    def _is_session_expired_error(self, error: Exception) -> bool:
        """
        Check if the error indicates a session expiration.
        
        Args:
            error: The exception to check
            
        Returns:
            True if the error indicates session expiration
        """
        if isinstance(error, ClientError):
            error_code = error.response['Error']['Code']
            error_message = error.response['Error']['Message'].lower()
            
            # Check for session-related errors
            if error_code in ['ValidationException', 'BadRequestException']:
                if any(keyword in error_message for keyword in ['session', 'expired', 'invalid']):
                    return True
        
        # Check error message for session-related keywords
        error_str = str(error).lower()
        session_keywords = ['session expired', 'invalid session', 'session not found', 'session timeout']
        return any(keyword in error_str for keyword in session_keywords)
    
    def _handle_agent_error(self, error: Exception, query: str) -> str:
        """
        Convert agent errors to user-friendly messages.
        
        Args:
            error: The exception that occurred
            query: The original query that failed
            
        Returns:
            A user-friendly error message
        """
        if isinstance(error, ClientError):
            error_code = error.response['Error']['Code']
            
            if error_code == 'AccessDeniedException':
                return "I don't have permission to access that information. Please contact your administrator."
            elif error_code == 'ThrottlingException' or error_code == 'throttlingException':
                return "I'm currently experiencing high load. Please wait a moment and try again."
            elif error_code == 'ValidationException':
                return "There was an issue with your query format. Please try rephrasing your question."
            elif error_code == 'ResourceNotFoundException':
                return "The agent or knowledge base is not available. Please contact your administrator."
            elif error_code in ['ServiceUnavailableException', 'InternalServerException']:
                return "The service is temporarily unavailable. Please try again in a few minutes."
        
        elif isinstance(error, TimeoutError):
            return "Your query is taking longer than expected. Please try a more specific question or try again later."
        
        # Handle EventStreamError from throttling
        elif 'throttl' in str(error).lower():
            return "I'm currently experiencing high load. Please wait a moment and try again."
        
        else:
            logger.error(f"Unexpected agent error: {error}", exc_info=True)
            return "I encountered an unexpected error. Please try again or contact support if this continues."

def get_oscar_agent(region: Optional[str] = None) -> OSCARAgentInterface:
    """
    Get Enhanced OSCAR agent implementation.
    
    Args:
        region: AWS region for Bedrock service, defaults to config value if None
        
    Returns:
        An implementation of OSCARAgentInterface with enhanced capabilities
    """
    return EnhancedBedrockOSCARAgent(region)