#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
"""
Knowledge Base stack for OSCAR CDK automation.

This module defines the Knowledge Base infrastructure including S3 bucket for document storage,
OpenSearch Serverless collection for vector search, and Bedrock Knowledge Base with document
ingestion pipeline and vector embeddings using Titan.
"""

from typing import List

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_opensearchserverless as opensearchserverless
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from aws_cdk import custom_resources
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from constructs import Construct

from utils.foundation_models import FoundationModels


class OscarKnowledgeBaseStack(Stack):
    """
    Knowledge Base infrastructure for OSCAR.

    This construct creates and configures the Knowledge Base infrastructure including:
    - S3 bucket for document storage with versioning and lifecycle policies
    - OpenSearch Serverless collection with vector search capabilities
    - Bedrock Knowledge Base with document ingestion pipeline
    - Vector embeddings using Titan and metadata extraction
    """

    KNOWLEDGE_BASE_NAME_BASE = "oscar-kb"

    @classmethod
    def get_knowledge_base_name(cls, environment: str) -> str:
        return f"{cls.KNOWLEDGE_BASE_NAME_BASE}-{environment}"

    def __init__(self, scope: Construct, construct_id: str, environment: str,
                 github_repositories: List[str], **kwargs) -> None:
        """
        Initialize Knowledge Base stack.

        Args:
            scope: The CDK construct scope
            construct_id: The ID of the construct
            environment: The deployment environment
            github_repositories: List of GitHub repositories to sync
            **kwargs: Additional keyword arguments
        """
        super().__init__(scope, construct_id, **kwargs)

        self.github_repositories = github_repositories

        # Get configuration from environment
        self.account_id = self.env.account
        self.aws_region = self.env.region
        self.env_name = environment

        # Determine removal policy based on environment
        self.removal_policy = (
            RemovalPolicy.RETAIN if self.env_name == "prod" else RemovalPolicy.DESTROY
        )

        # Create S3 bucket for document storage
        self.documents_bucket = self._create_documents_bucket()

        # Create OpenSearch Serverless collection
        self.opensearch_collection = self._create_opensearch_collection()

        # Create KB service role (needed for data access policy)
        self.kb_service_role = self._create_kb_service_role()

        # Create data access policy (needed before index creation)
        self.data_access_policy = self._create_data_access_policy()

        # Create OpenSearch index
        self.opensearch_index = self._create_opensearch_index()

        # Create Knowledge Base
        self.knowledge_base = self._create_knowledge_base()

        # Create data source for document ingestion
        self.data_source = self._create_data_source()

        # Create Lambda function for GitHub docs uploader
        self.docs_uploader_lambda = self._create_docs_uploader_lambda()

        # Create Lambda function for automatic document synchronization
        self.sync_lambda = self._create_document_sync_lambda()

        # Add S3 event notification for automatic sync
        self._configure_s3_notifications()

        # Add EventBridge schedule for docs uploader
        self._configure_docs_uploader_schedule()

        # Create outputs
        self._create_outputs()

    def _create_documents_bucket(self) -> s3.Bucket:
        """
        Create S3 bucket for document storage with versioning and lifecycle policies.
        Returns:
            The S3 bucket for document storage
        """
        bucket = s3.Bucket(
            self, "OscarDocumentsBucket",
            bucket_name=f"oscar-knowledge-docs-{self.env_name}-{self.account_id}-{self.aws_region}",
            versioned=True,
            removal_policy=self.removal_policy,
            auto_delete_objects=self.removal_policy == RemovalPolicy.DESTROY,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    enabled=True,
                    noncurrent_version_expiration=Duration.days(90),
                    abort_incomplete_multipart_upload_after=Duration.days(7)
                ),
                s3.LifecycleRule(
                    id="TransitionToIA",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30)
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90)
                        )
                    ]
                )
            ]
        )

        # We'll add the S3 event notification after creating the Lambda function

        return bucket

    def _create_opensearch_collection(self) -> opensearchserverless.CfnCollection:
        """
        Create OpenSearch Serverless collection with vector search capabilities.
        Returns:
            The OpenSearch Serverless collection
        """
        # Create encryption policy (shortened name to fit 32 char limit)
        encryption_policy = opensearchserverless.CfnSecurityPolicy(
            self, "OscarKnowledgeBaseEncryptionPolicy",
            name=f"oscar-kb-encrypt-cdk-{self.env_name}",
            type="encryption",
            policy=f"""{{
                "Rules": [
                    {{
                        "ResourceType": "collection",
                        "Resource": ["collection/oscar-kb-cdk-{self.env_name}"]
                    }}
                ],
                "AWSOwnedKey": true
            }}"""
        )

        # Create network policy (shortened name to fit 32 char limit)
        network_policy = opensearchserverless.CfnSecurityPolicy(
            self, "OscarKnowledgeBaseNetworkPolicy",
            name=f"oscar-kb-network-cdk-{self.env_name}",
            type="network",
            policy=f"""[{{
                "Rules": [
                    {{
                        "ResourceType": "collection",
                        "Resource": ["collection/oscar-kb-cdk-{self.env_name}"]
                    }},
                    {{
                        "ResourceType": "dashboard",
                        "Resource": ["collection/oscar-kb-cdk-{self.env_name}"]
                    }}
                ],
                "AllowFromPublic": true
            }}]"""
        )

        # Create data access policy (shortened name to fit 32 char limit)
        # Note: We'll create this after the KB service role is created
        data_access_policy = None  # noqa: F841

        # Create the collection
        collection = opensearchserverless.CfnCollection(
            self, "OscarKnowledgeBaseCollection",
            name=f"oscar-kb-cdk-{self.env_name}",
            description="OpenSearch Serverless collection for OSCAR Knowledge Base vector search",
            type="VECTORSEARCH",
            standby_replicas="DISABLED"  # Cost optimization for non-prod
        )

        # Add dependencies
        collection.add_dependency(encryption_policy)
        collection.add_dependency(network_policy)

        return collection

    def _create_kb_service_role(self) -> iam.Role:
        """
        Create service role for Knowledge Base.
        Returns:
            The IAM role for Knowledge Base
        """
        kb_service_role = iam.Role(
            self, "KnowledgeBaseServiceRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Service role for OSCAR Bedrock Knowledge Base"
        )

        # Add permissions for S3 access
        kb_service_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3Access",
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:ListBucket"
                ],
                resources=[
                    self.documents_bucket.bucket_arn,
                    f"{self.documents_bucket.bucket_arn}/*"
                ]
            )
        )

        # Add permissions for OpenSearch Serverless access
        kb_service_role.add_to_policy(
            iam.PolicyStatement(
                sid="OpenSearchServerlessAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "aoss:APIAccessAll"
                ],
                resources=[
                    f"arn:aws:aoss:{self.aws_region}:{self.account_id}:collection/*"
                ]
            )
        )

        # Add permissions for Bedrock model access
        kb_service_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockModelAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.aws_region}::foundation-model/{FoundationModels.AMAZON_TITAN_2_0.value}"
                ]
            )
        )

        return kb_service_role

    def _create_data_access_policy(self) -> opensearchserverless.CfnAccessPolicy:
        """
        Create data access policy for OpenSearch Serverless.
        Returns:
            The data access policy
        """
        data_access_policy = opensearchserverless.CfnAccessPolicy(
            self, "OscarKnowledgeBaseDataAccessPolicy",
            name=f"oscar-kb-data-cdk-{self.env_name}",
            type="data",
            policy=f"""[{{
                "Rules": [
                    {{
                        "ResourceType": "collection",
                        "Resource": ["collection/oscar-kb-cdk-{self.env_name}"],
                        "Permission": [
                            "aoss:CreateCollectionItems",
                            "aoss:DeleteCollectionItems",
                            "aoss:UpdateCollectionItems",
                            "aoss:DescribeCollectionItems"
                        ]
                    }},
                    {{
                        "ResourceType": "index",
                        "Resource": ["index/*/*"],
                        "Permission": [
                            "aoss:CreateIndex",
                            "aoss:DeleteIndex",
                            "aoss:UpdateIndex",
                            "aoss:DescribeIndex",
                            "aoss:ReadDocument",
                            "aoss:WriteDocument"
                        ]
                    }}
                ],
                "Principal": [
                    "arn:aws:iam::{self.account_id}:root",
                    "{self.kb_service_role.role_arn}"
                ]
            }}]"""
        )

        # Add dependency on collection
        data_access_policy.node.add_dependency(self.opensearch_collection)

        return data_access_policy

    def _create_opensearch_index(self) -> opensearchserverless.CfnIndex:
        """
        Create OpenSearch index with proper vector mappings for Bedrock Knowledge Base.
        Returns:
            The OpenSearch Serverless index
        """

        # Add a wait condition to ensure collection is active
        wait_condition = custom_resources.AwsCustomResource(
            self,
            "WaitForCollection",
            on_create=custom_resources.AwsSdkCall(
                service="OpenSearchServerless",
                action="listCollections",
                parameters={},
                physical_resource_id=custom_resources.PhysicalResourceId.of("WaitForCollection")
            ),
            policy=custom_resources.AwsCustomResourcePolicy.from_sdk_calls(
                resources=custom_resources.AwsCustomResourcePolicy.ANY_RESOURCE
            )
        )

        wait_condition.node.add_dependency(self.opensearch_collection)

        oss_index = opensearchserverless.CfnIndex(
            self, 'OSSCfnIndex',
            collection_endpoint=self.opensearch_collection.attr_collection_endpoint,
            index_name="bedrock-knowledge-base-default-index",
            mappings=opensearchserverless.CfnIndex.MappingsProperty(
                properties={
                    "bedrock-knowledge-base-default-vector": opensearchserverless.CfnIndex.PropertyMappingProperty(
                        type="knn_vector",
                        dimension=1024,
                        method=opensearchserverless.CfnIndex.MethodProperty(
                            engine="faiss",
                            name="hnsw",
                            space_type="l2"
                        )
                    ),
                    "AMAZON_BEDROCK_METADATA": opensearchserverless.CfnIndex.PropertyMappingProperty(
                        type="text",
                        index=False
                    ),
                    "AMAZON_BEDROCK_TEXT": opensearchserverless.CfnIndex.PropertyMappingProperty(
                        type="text"
                    ),
                    "AMAZON_BEDROCK_TEXT_CHUNK": opensearchserverless.CfnIndex.PropertyMappingProperty(
                        type="text"
                    ),
                    "id": opensearchserverless.CfnIndex.PropertyMappingProperty(
                        type="text"
                    )
                }
            ),
            settings=opensearchserverless.CfnIndex.IndexSettingsProperty(
                index=opensearchserverless.CfnIndex.IndexProperty(
                    knn=True
                )
            )
        )

        # Add dependencies
        oss_index.node.add_dependency(self.opensearch_collection)
        oss_index.node.add_dependency(self.data_access_policy)

        return oss_index

    def _create_knowledge_base(self) -> bedrock.CfnKnowledgeBase:
        """
        Create Bedrock Knowledge Base with vector embeddings using Titan.
        Returns:
            The Bedrock Knowledge Base
        """
        # Add a wait condition to ensure index is created. Index creation is delayed a bit.
        index_wait_condition = custom_resources.AwsCustomResource(
            self,
            "WaitForIndex",
            on_create=custom_resources.AwsSdkCall(
                service="OpenSearchServerless",
                action="batchGetCollection",  # Use batchGetCollection instead
                parameters={"ids": [self.opensearch_collection.attr_id]},
                # physical_resource_id=custom_resources.PhysicalResourceId.from_response(
                #     "collections.0.id"
                # ),
                physical_resource_id=custom_resources.PhysicalResourceId.of(
                    "wait-for-index-creation"
                ),
            ),
            policy=custom_resources.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=["aoss:BatchGetCollection", "aoss:APIAccessAll"],
                        resources=[f"arn:aws:aoss:{self.region}:{self.account_id}:collection/*"],
                    )
                ]
            ),
        )

        index_wait_condition.node.add_dependency(self.opensearch_index)

        # Create the Knowledge Base using existing service role
        knowledge_base = bedrock.CfnKnowledgeBase(
            self, "OscarKnowledgeBase",
            name=self.get_knowledge_base_name(self.env_name),
            description="OSCAR Knowledge Base for OpenSearch release management documentation",
            role_arn=self.kb_service_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=f"arn:aws:bedrock:{self.aws_region}::foundation-model/{FoundationModels.AMAZON_TITAN_2_0.value}"
                )
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="OPENSEARCH_SERVERLESS",
                opensearch_serverless_configuration=bedrock.CfnKnowledgeBase.OpenSearchServerlessConfigurationProperty(
                    collection_arn=self.opensearch_collection.attr_arn,
                    vector_index_name="bedrock-knowledge-base-default-index",
                    field_mapping=bedrock.CfnKnowledgeBase.OpenSearchServerlessFieldMappingProperty(
                        vector_field="bedrock-knowledge-base-default-vector",
                        text_field="AMAZON_BEDROCK_TEXT_CHUNK",
                        metadata_field="AMAZON_BEDROCK_METADATA"
                    )
                )
            )
        )

        # Add dependencies
        knowledge_base.add_dependency(self.opensearch_collection)
        knowledge_base.add_dependency(self.opensearch_index)
        knowledge_base.add_dependency(self.data_access_policy)
        knowledge_base.node.add_dependency(index_wait_condition)

        return knowledge_base

    def _create_data_source(self) -> bedrock.CfnDataSource:
        """
        Create data source for document ingestion from S3.
        Returns:
            The Bedrock data source
        """
        data_source = bedrock.CfnDataSource(
            self, "OscarKnowledgeBaseDataSource",
            name=f"oscar-docs-data-source-{self.env_name}",
            description="Data source for OSCAR documentation ingestion",
            knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=self.documents_bucket.bucket_arn
                )
            ),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=300,
                        overlap_percentage=20
                    )
                )
            )
        )

        # Add dependency on knowledge base
        data_source.add_dependency(self.knowledge_base)

        return data_source

    def _create_document_sync_lambda(self) -> lambda_.Function:
        """
        Create Lambda function for automatic document synchronization.
        Returns:
            The Lambda function for document sync
        """
        # Create execution role for the Lambda function
        sync_lambda_role = iam.Role(
            self, "DocumentSyncLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
            description="Execution role for OSCAR document sync Lambda function"
        )

        # Add permissions for Bedrock agent operations
        sync_lambda_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockAgentAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:StartIngestionJob",
                    "bedrock:ListIngestionJobs",
                    "bedrock:GetIngestionJob"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.aws_region}:{self.account_id}:knowledge-base/{self.knowledge_base.attr_knowledge_base_id}",
                    f"arn:aws:bedrock:{self.aws_region}:{self.account_id}:knowledge-base/{self.knowledge_base.attr_knowledge_base_id}/data-source/*"
                ]
            )
        )

        # Create the Lambda function
        sync_lambda = PythonFunction(
            self, "DocumentSyncLambda",
            function_name=f"DocumentSyncLambda-{self.env_name}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda_handler",
            entry="lambda/knowledge-base",
            index="document_sync_handler.py",
            role=sync_lambda_role,
            timeout=Duration.minutes(5),
            memory_size=256,
            environment={
                "KNOWLEDGE_BASE_ID": self.knowledge_base.attr_knowledge_base_id,
                "DATA_SOURCE_ID": self.data_source.attr_data_source_id,
                "LOG_LEVEL": "INFO"
            },
            description="Handles automatic Knowledge Base synchronization when documents are updated"
        )

        # Add dependency on data source
        sync_lambda.node.add_dependency(self.data_source)

        return sync_lambda

    def _configure_s3_notifications(self) -> None:
        """
        Configure S3 event notifications for automatic document synchronization.
        """
        # Add S3 event notifications for document changes
        self.documents_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.sync_lambda)
        )

        self.documents_bucket.add_event_notification(
            s3.EventType.OBJECT_REMOVED,
            s3n.LambdaDestination(self.sync_lambda)
        )

    def _create_docs_uploader_lambda(self) -> lambda_.Function:
        """
        Create Lambda function for uploading GitHub documentation to S3.
        Returns:
            The docs uploader Lambda function
        """
        function = lambda_.DockerImageFunction(
            self, "DocsUploaderLambda",
            function_name=f"DocsUploaderLambda-{self.env_name}",
            code=lambda_.DockerImageCode.from_image_asset("lambda/knowledge-base"),
            architecture=lambda_.Architecture.X86_64,
            timeout=Duration.minutes(15),
            memory_size=512,
            description="Upload markdown files from GitHub repos to S3",
            environment={
                "LOG_LEVEL": "INFO",
                "BUCKET_NAME": self.documents_bucket.bucket_name
            }
        )

        # Grant S3 write permissions
        self.documents_bucket.grant_write(function)
        self.documents_bucket.grant_read(function)
        function.node.add_dependency(self.documents_bucket)
        return function

    def _configure_docs_uploader_schedule(self) -> None:
        """
        Configure EventBridge schedule to run docs uploader daily.
        """
        rule = events.Rule(
            self, "DocsUploaderSchedule",
            schedule=events.Schedule.cron(hour="0", minute="0"),
            description="Daily GitHub documentation sync to S3"
        )

        rule.add_target(targets.LambdaFunction(
            self.docs_uploader_lambda,
            event=events.RuleTargetInput.from_object({
                "repositories": self.github_repositories
            })
        ))
        rule.node.add_dependency(self.docs_uploader_lambda)

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs for the Knowledge Base resources."""

        # Knowledge Base outputs
        CfnOutput(
            self, "KnowledgeBaseId",
            value=self.knowledge_base.attr_knowledge_base_id,
            description="ID of the Bedrock Knowledge Base",
            export_name="OscarKnowledgeBaseId"
        )
