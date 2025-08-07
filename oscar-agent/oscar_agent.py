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
    
    def _determine_query_type(self, query: str) -> str:
        """
        Determine the type of query to route appropriately.
        
        Args:
            query: The user's query
            
        Returns:
            Query type: 'knowledge', 'metrics', or 'hybrid'
        """
        query_lower = query.lower()
        
        # Metrics-related keywords
        metrics_keywords = [
            'test', 'build', 'release', 'deployment', 'metrics', 'performance',
            'failure', 'success rate', 'coverage', 'pipeline', 'ci/cd',
            'current', 'recent', 'last week', 'last month', 'trends'
        ]
        
        # Knowledge-related keywords  
        knowledge_keywords = [
            'how to', 'configure', 'setup', 'install', 'documentation',
            'best practice', 'guide', 'tutorial', 'explain', 'what is',
            'troubleshoot', 'error', 'issue', 'problem'
        ]
        
        # Count keyword matches
        metrics_matches = sum(1 for keyword in metrics_keywords if keyword in query_lower)
        knowledge_matches = sum(1 for keyword in knowledge_keywords if keyword in query_lower)
        
        # Determine query type
        if metrics_matches > knowledge_matches and metrics_matches > 0:
            return 'metrics'
        elif knowledge_matches > metrics_matches and knowledge_matches > 0:
            return 'knowledge'
        else:
            # Default to hybrid for complex queries
            return 'hybrid'
    
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
            
            # Also check for session ID at the top level of the response
            if 'sessionId' in response:
                returned_session_id = response['sessionId']
            
            logger.info(f"Agent response received, length: {len(response_text)} characters")
            logger.info(f"Session ID: {returned_session_id}")
            
            return response_text.strip(), returned_session_id
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"Bedrock agent error ({error_code}): {error_message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error invoking agent: {e}", exc_info=True)
            raise
    
    def _retry_with_backoff(self, func, *args, **kwargs):
        """
        Retry a function with exponential backoff.
        
        Args:
            func: The function to retry
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            The result of the function call
            
        Raises:
            Exception: If all retries are exhausted
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except ClientError as e:
                error_code = e.response['Error']['Code']
                
                # Don't retry certain errors
                if error_code in ['AccessDeniedException', 'ValidationException']:
                    raise
                
                # For throttling and other retryable errors, use backoff
                if error_code in ['ThrottlingException', 'ServiceUnavailableException', 'InternalServerException']:
                    last_exception = e
                    if attempt < self.max_retries:
                        wait_time = (2 ** attempt) + (time.time() % 1)  # Add jitter
                        logger.warning(f"Retryable error ({error_code}), attempt {attempt + 1}/{self.max_retries + 1}. Waiting {wait_time:.2f}s")
                        time.sleep(wait_time)
                        continue
                
                # For other client errors, don't retry
                raise
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    wait_time = (2 ** attempt) + (time.time() % 1)  # Add jitter
                    logger.warning(f"Unexpected error, attempt {attempt + 1}/{self.max_retries + 1}. Waiting {wait_time:.2f}s")
                    time.sleep(wait_time)
                    continue
                raise
        
        # If we get here, all retries were exhausted
        if last_exception:
            raise last_exception
    
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
        logger.info(f"Querying Enhanced OSCAR agent with: {query[:100]}...")
        
        # The supervisor agent handles all routing internally through its
        # knowledge base integration and collaborator agents, so we just
        # need to invoke it directly
        
        # First attempt: Try with session_id if available
        if session_id:
            try:
                logger.info(f"Attempting query with session_id: {session_id}")
                return self._retry_with_backoff(self._invoke_agent, query, session_id)
            except Exception as e:
                logger.warning(f"Session-based query failed (possibly expired session): {e}")
                # Session ID might be expired, fall through to context summary fallback
        
        # Second attempt: Use enhanced query with context summary (without session_id)
        if context_summary:
            logger.info("Falling back to context-enhanced query without session_id")
            enhanced_query = f"Previous conversation context:\n{context_summary}\n\nCurrent question: {query}"
            try:
                return self._retry_with_backoff(self._invoke_agent, enhanced_query, None)
            except Exception as e:
                logger.warning(f"Context-enhanced query failed: {e}")
                # Fall through to plain query
        
        # Third attempt: Just use the plain query as last resort
        logger.info("Using plain query without context or session")
        try:
            return self._retry_with_backoff(self._invoke_agent, query, None)
        except Exception as e:
            logger.error(f"All query attempts failed: {e}", exc_info=True)
            error_message = self._handle_agent_error(e, query)
            return error_message, None
    
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