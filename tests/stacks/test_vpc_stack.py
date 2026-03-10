# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for OSCAR VPC stack."""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from stacks.vpc_stack import OscarVpcStack


@pytest.fixture
def template():
    """Synthesise the VPC stack (creates a new VPC when no VPC_ID context is set)."""
    app = App()
    stack = OscarVpcStack(
        app, "TestVpcStack",
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


class TestVpcStack:
    """Test cases for OscarVpcStack."""

    def test_vpc_created(self, template):
        """A VPC should be created when no VPC_ID context is provided."""
        template.resource_count_is("AWS::EC2::VPC", 1)

    def test_subnets_created(self, template):
        """Public and private subnets should be created."""
        # With max_azs=3: 3 public + 3 private = 6 subnets
        template.resource_count_is("AWS::EC2::Subnet", 6)

    def test_nat_gateway_created(self, template):
        """One NAT gateway should be created (nat_gateways=1)."""
        template.resource_count_is("AWS::EC2::NatGateway", 1)

    def test_lambda_security_group_created(self, template):
        """Lambda security group should be created."""
        template.has_resource_properties("AWS::EC2::SecurityGroup", {
            "GroupDescription":
                "Security group for OSCAR Lambda functions with OpenSearch access",
        })

    def test_security_group_has_egress_rules(self, template):
        """Lambda security group should have egress rules for required ports."""
        template_dict = template.to_json()
        for resource in template_dict["Resources"].values():
            if resource.get("Type") == "AWS::EC2::SecurityGroup":
                props = resource.get("Properties", {})
                if "OSCAR Lambda" in props.get("GroupDescription", ""):
                    egress = props.get("SecurityGroupEgress", [])
                    ports = {r.get("ToPort") for r in egress}
                    assert 443 in ports, "Missing HTTPS egress (443)"
                    assert 80 in ports, "Missing HTTP egress (80)"
                    assert 53 in ports, "Missing DNS egress (53)"
                    assert 9200 in ports, "Missing OpenSearch egress (9200)"
                    return
        pytest.fail("Lambda security group not found")

    def test_network_acl_created(self, template):
        """Custom Network ACL for Lambda subnets should exist."""
        template.has_resource_properties("AWS::EC2::NetworkAcl", {
            "Tags": [{
                "Key": "Name",
                "Value": "oscar-lambda-nacl",
            }],
        })
