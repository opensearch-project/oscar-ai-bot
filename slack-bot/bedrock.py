"""
Bedrock integration module for OSCAR.

This module provides classes for interacting with Amazon Bedrock.
"""

import logging
import json
import boto3
from abc import ABC, abstractmethod
from config import config

# Configure logging
logger = logging.getLogger(__name__)

class KnowledgeBaseInterface(ABC):
    """Abstract base class for knowledge base implementations."""
    
    @abstractmethod
    def query(self, query, session_id=None, context_summary=None):
        """Query the knowledge base."""
        pass

class BedrockKnowledgeBase(KnowledgeBaseInterface):
    """Amazon Bedrock implementation of knowledge base interface."""
    
    def __init__(self, region=None):
        """Initialize Bedrock knowledge base."""
        self.region = region or config.region
        self.client = boto3.client('bedrock-agent-runtime', region_name=self.region)
        self.knowledge_base_id = config.knowledge_base_id
        self.model_arn = config.model_arn
        self.prompt_template = config.prompt_template
    
    def query(self, query, session_id=None, context_summary=None):
        """Query Bedrock knowledge base with session or context."""
        # Build prompt with context if available
        if context_summary and not session_id:
            enhanced_query = f"Previous conversation context:\n{context_summary}\n\nCurrent question: {query}"
        else:
            enhanced_query = query
        
        logger.info(f"Querying knowledge base with: {enhanced_query[:100]}...")
        logger.info(f"Using model ARN: {self.model_arn}")
        
        # Check if we're using an inference profile ARN
        is_inference_profile = "inference-profile" in self.model_arn
        
        # Prepare request with query decomposition
        request = {
            'input': {'text': enhanced_query},
            'retrieveAndGenerateConfiguration': {
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': self.knowledge_base_id,
                    'modelArn': self.model_arn
                }
            }
        }
        
        # Add query decomposition configuration
        # For inference profiles, the structure is different
        if not is_inference_profile:
            # Standard structure for foundation models
            request['retrieveAndGenerateConfiguration']['knowledgeBaseConfiguration']['orchestrationConfiguration'] = {
                'queryTransformationConfiguration': {
                    'type': 'QUERY_DECOMPOSITION'
                }
            }
        
        # Add generation configuration
        # Same configuration for both types, but log differently
        request['retrieveAndGenerateConfiguration']['knowledgeBaseConfiguration']['generationConfiguration'] = {
            'promptTemplate': {
                'textPromptTemplate': self.prompt_template
            }
        }
        
        if is_inference_profile:
            # Log that we're using inference profile configuration
            logger.info("Using inference profile configuration")
        
        # Add session ID if available
        if session_id:
            request['sessionId'] = session_id
            logger.info(f"Using session ID: {session_id}")
        
        # Log the full request for debugging
        logger.info(f"Full request: {json.dumps(request, indent=2)}")
        
        try:
            response = self.client.retrieve_and_generate(**request)
            logger.info("Query with decomposition succeeded")
            return response['output']['text'], response.get('sessionId')
        except Exception as e:
            logger.warning(f"Error with query decomposition: {e}")
            
            # If query decomposition fails, try without it
            logger.info("Retrying without query decomposition...")
            try:
                # Create a new request without query decomposition
                request_no_decomp = {
                    'input': {'text': enhanced_query},
                    'retrieveAndGenerateConfiguration': {
                        'type': 'KNOWLEDGE_BASE',
                        'knowledgeBaseConfiguration': {
                            'knowledgeBaseId': self.knowledge_base_id,
                            'modelArn': self.model_arn,
                            'generationConfiguration': {
                                'promptTemplate': {
                                    'textPromptTemplate': self.prompt_template
                                }
                            }
                        }
                    }
                }
                
                if session_id:
                    request_no_decomp['sessionId'] = session_id
                
                logger.info(f"Fallback request: {json.dumps(request_no_decomp, indent=2)}")
                response = self.client.retrieve_and_generate(**request_no_decomp)
                logger.info("Query without decomposition succeeded")
                return response['output']['text'], response.get('sessionId')
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
                raise fallback_error

# Factory function to create the appropriate knowledge base implementation
def get_knowledge_base(kb_type='bedrock', region=None):
    """Get knowledge base implementation based on type."""
    # No mock implementation here - moved to tests
    return BedrockKnowledgeBase(region)