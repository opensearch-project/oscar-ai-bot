#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
"""
Script for initial ingestion of knowledge documents into OSCAR Knowledge Base.

This script uploads all documents from the cdk/knowledge_docs/ directory to the
Knowledge Base S3 bucket and triggers the initial synchronization.
"""

import os
import sys
import json
import logging
from pathlib import Path
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Add the utils directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'utils'))

from document_manager import DocumentManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_stack_outputs(stack_name: str, region: str = "us-east-1") -> dict:
    """
    Get CloudFormation stack outputs.
    
    Args:
        stack_name: Name of the CloudFormation stack
        region: AWS region
        
    Returns:
        Dictionary of stack outputs
    """
    try:
        cloudformation = boto3.client('cloudformation', region_name=region)
        
        response = cloudformation.describe_stacks(StackName=stack_name)
        stacks = response['Stacks']
        
        if not stacks:
            raise ValueError(f"Stack {stack_name} not found")
        
        stack = stacks[0]
        outputs = {}
        
        for output in stack.get('Outputs', []):
            outputs[output['OutputKey']] = output['OutputValue']
        
        return outputs
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ValidationError':
            raise ValueError(f"Stack {stack_name} does not exist")
        else:
            raise


def main():
    """
    Main function for document ingestion.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingest OSCAR knowledge documents")
    parser.add_argument("--stack-name", default="OscarSlackBotStack", 
                       help="CloudFormation stack name")
    parser.add_argument("--docs-dir", default="cdk/knowledge_docs", 
                       help="Documents directory")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be done without actually doing it")
    
    args = parser.parse_args()
    
    try:
        logger.info(f"Starting document ingestion for stack: {args.stack_name}")
        
        # Get stack outputs
        logger.info("Retrieving stack outputs...")
        outputs = get_stack_outputs(args.stack_name, args.region)
        
        # Extract required values
        bucket_name = outputs.get('DocumentsBucketName')
        knowledge_base_id = outputs.get('KnowledgeBaseId')
        data_source_id = outputs.get('DataSourceId')
        
        if not all([bucket_name, knowledge_base_id, data_source_id]):
            missing = []
            if not bucket_name:
                missing.append('DocumentsBucketName')
            if not knowledge_base_id:
                missing.append('KnowledgeBaseId')
            if not data_source_id:
                missing.append('DataSourceId')
            
            raise ValueError(f"Missing required stack outputs: {', '.join(missing)}")
        
        logger.info(f"Using bucket: {bucket_name}")
        logger.info(f"Knowledge Base ID: {knowledge_base_id}")
        logger.info(f"Data Source ID: {data_source_id}")
        
        # Check if documents directory exists
        docs_path = Path(args.docs_dir)
        if not docs_path.exists():
            raise FileNotFoundError(f"Documents directory not found: {args.docs_dir}")
        
        # Count documents to be processed
        supported_extensions = {'.md', '.txt', '.rst', '.json'}
        doc_files = [
            f for f in docs_path.rglob("*") 
            if f.is_file() and f.suffix.lower() in supported_extensions
        ]
        
        logger.info(f"Found {len(doc_files)} documents to process")
        
        if args.dry_run:
            logger.info("DRY RUN - Documents that would be processed:")
            for doc_file in doc_files:
                logger.info(f"  - {doc_file.relative_to(docs_path)}")
            return 0
        
        # Initialize document manager
        doc_manager = DocumentManager(
            bucket_name=bucket_name,
            knowledge_base_id=knowledge_base_id,
            data_source_id=data_source_id,
            region=args.region
        )
        
        # Ingest documents
        logger.info("Starting document ingestion...")
        result = doc_manager.ingest_documents_from_directory(args.docs_dir)
        
        logger.info(f"Successfully ingested {len(result)} documents")
        
        # Show results
        if result:
            logger.info("Ingested documents:")
            for local_path, s3_key in result.items():
                logger.info(f"  {Path(local_path).name} -> {s3_key}")
        
        # Wait a moment and check sync status
        import time
        logger.info("Waiting for sync job to start...")
        time.sleep(5)
        
        status = doc_manager.get_sync_status()
        logger.info(f"Knowledge Base sync status: {json.dumps(status, indent=2)}")
        
        logger.info("Document ingestion completed successfully!")
        return 0
        
    except NoCredentialsError:
        logger.error("AWS credentials not found. Please configure your credentials.")
        return 1
    except Exception as e:
        logger.error(f"Document ingestion failed: {str(e)}")
        return 1


if __name__ == "__main__":
    exit(main())