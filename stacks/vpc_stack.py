#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
"""
VPC and networking stack for OSCAR Slack Bot.

This module defines the VPC configuration, security groups, and VPC endpoints
used by the OSCAR Slack Bot infrastructure. It imports existing VPC resources
and configures networking for Lambda functions with OpenSearch access.
"""

import logging

from aws_cdk import Stack
from aws_cdk import aws_ec2 as ec2
from constructs import Construct

logger = logging.getLogger(__name__)


class OscarVpcStack(Stack):
    """
    VPC and networking resources for OSCAR Slack Bot.
    This construct imports existing VPC resources and configures security groups,
    VPC endpoints, and network ACLs for proper isolation and secure access to
    AWS services and OpenSearch clusters.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        """
        Initialize VPC and networking resources.
        Args:
            scope: The CDK construct scope
            construct_id: The ID of the construct
            **kwargs: Additional arguments for Stack
        """
        super().__init__(scope, construct_id, **kwargs)

        # Import existing VPC configuration
        self.vpc: ec2.IVpc = self._configure_vpc()
        self.lambda_security_group: ec2.ISecurityGroup = self._create_lambda_security_group()

        # Create VPC endpoints for STS and Secrets Manager
        self._create_vpc_endpoints()

    def _configure_vpc(self) -> ec2.IVpc:
        """
        Import the existing VPC configuration.
        Returns:
            The imported VPC
        """
        # Use the VPC ID from .env file
        vpc_id = self.node.try_get_context("VPC_ID")

        if not vpc_id:
            try:
                logging.info("VPC_ID environment variable not found. A new VPC will be created")
                vpc: ec2.IVpc = ec2.Vpc(
                    self, "OscarVpc",
                    max_azs=6,
                    subnet_configuration=[
                        ec2.SubnetConfiguration(
                            name="public",
                            subnet_type=ec2.SubnetType.PUBLIC,
                            map_public_ip_on_launch=True,
                        )
                    ],
                )
                return vpc
            except Exception:
                logger.error("Failed to create VPC with given CIDR.")
                raise ValueError("Could not create VPC. Please check your account for details.")
        else:
            try:
                vpc = ec2.Vpc.from_lookup(
                    self, "ExistingVpc",
                    vpc_id=vpc_id
                )

                logger.info(f"Successfully imported VPC: {vpc_id}")
                return vpc

            except Exception as e:
                logger.error(f"Failed to import VPC {vpc_id}: {e}")
                raise ValueError(f"Could not import VPC {vpc_id}. Please verify the VPC_ID in your .env file.")

    def _create_lambda_security_group(self) -> ec2.ISecurityGroup:
        """
        Create or import security group for Lambda functions with OpenSearch access.
        Returns:
            The Lambda security group
        """
        # Try to import existing security group first
        existing_sg_id = self.node.try_get_context("LAMBDA_SECURITY_GROUP_ID")

        if existing_sg_id:
            try:
                logger.info(f"Importing existing security group: {existing_sg_id}")
                return ec2.SecurityGroup.from_security_group_id(
                    self, "ExistingLambdaSecurityGroup",
                    security_group_id=existing_sg_id
                )
            except Exception as e:
                logger.warning(f"Failed to import security group {existing_sg_id}: {e}")
                logger.info("Creating new security group")

        # Create new security group
        security_group = ec2.SecurityGroup(
            self, "OscarLambdaSecurityGroup",
            vpc=self.vpc,
            description="Security group for OSCAR Lambda functions with OpenSearch access",
            allow_all_outbound=True,
        )

        # Inbound: all traffic from itself (Lambda <-> VPC endpoints)
        security_group.add_ingress_rule(
            peer=security_group,
            connection=ec2.Port.all_traffic(),
        )

        # Inbound: HTTPS from VPC CIDR
        security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(443),
            description=f"from {self.vpc.vpc_cidr_block}:443",
        )

        return security_group

    def _create_vpc_endpoints(self) -> None:
        """Create STS and Secrets Manager VPC endpoints for Lambda access."""
        subnet_selection = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)

        ec2.InterfaceVpcEndpoint(
            self, "STSVpcEndpoint",
            vpc=self.vpc,
            service=ec2.InterfaceVpcEndpointAwsService.STS,
            subnets=subnet_selection,
            security_groups=[self.lambda_security_group],
            private_dns_enabled=True,
        )

        ec2.InterfaceVpcEndpoint(
            self, "SecretsManagerVpcEndpoint",
            vpc=self.vpc,
            service=ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
            subnets=subnet_selection,
            security_groups=[self.lambda_security_group],
            private_dns_enabled=True,
        )

