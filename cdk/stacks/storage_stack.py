"""
Storage stack for OSCAR Slack Bot.

This module defines the DynamoDB tables and S3 bucket used by the OSCAR Slack Bot.
"""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment,
    aws_iam as iam,
    CfnOutput
)
from constructs import Construct

class OscarStorageStack(Construct):
    """Storage resources for OSCAR Slack Bot."""
    
    def __init__(self, scope: Construct, construct_id: str) -> None:
        """Initialize storage resources."""
        super().__init__(scope, construct_id)
        
        # Create DynamoDB Tables
        self.sessions_table = dynamodb.Table(
            self, "OscarSessionsTable",
            table_name="oscar-sessions",
            partition_key=dynamodb.Attribute(
                name="event_id",
                type=dynamodb.AttributeType.STRING
            ),
            time_to_live_attribute="ttl",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY
        )

        self.context_table = dynamodb.Table(
            self, "OscarContextTable",
            table_name="oscar-context",
            partition_key=dynamodb.Attribute(
                name="thread_key",
                type=dynamodb.AttributeType.STRING
            ),
            time_to_live_attribute="ttl",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Create S3 bucket for knowledge base documents
        self.docs_bucket = s3.Bucket(
            self, "OscarDocsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # Deploy documents to S3 bucket
        try:
            s3_deployment.BucketDeployment(
                self, "DeployDocs",
                sources=[s3_deployment.Source.asset("../build_docs")],
                destination_bucket=self.docs_bucket
            )
        except Exception as e:
            print(f"Warning: Could not deploy documents to S3 bucket: {e}")
            print("Continuing without document deployment...")
        
        # Create IAM role for Bedrock Knowledge Base
        self.kb_role = iam.Role(
            self, "BedrockKnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            role_name=f"OscarBedrockKBRole-{Stack.of(self).account}-{Stack.of(self).region}"
        )
        
        # Add permissions for S3
        self.kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:ListBucket"
                ],
                resources=[
                    self.docs_bucket.bucket_arn,
                    f"{self.docs_bucket.bucket_arn}/*"
                ]
            )
        )
        
        # Outputs
        CfnOutput(
            self, "DocsBucketName",
            value=self.docs_bucket.bucket_name,
            description="Name of the S3 bucket for knowledge base documents"
        )