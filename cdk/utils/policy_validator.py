#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
"""
Policy validation utilities for OSCAR IAM policies.

This module provides utilities to validate IAM policies for compliance
with least-privilege principles and security best practices.
"""

import json
import re
from typing import Dict, List, Set, Tuple, Optional
from aws_cdk import aws_iam as iam


class PolicyValidator:
    """
    Validator for IAM policies to ensure least-privilege compliance.
    
    This class provides methods to validate IAM policies against security
    best practices and least-privilege principles.
    """
    
    # Dangerous actions that should be avoided or heavily restricted
    DANGEROUS_ACTIONS = {
        "*",
        "iam:*",
        "sts:AssumeRole",  # Should be restricted to specific resources
        "s3:*",
        "dynamodb:*",
        "lambda:*",
        "bedrock:*"
    }
    
    # Actions that should have resource constraints
    RESOURCE_CONSTRAINED_ACTIONS = {
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "lambda:InvokeFunction",
        "secretsmanager:GetSecretValue",
        "bedrock:InvokeAgent",
        "bedrock:InvokeModel"
    }
    
    def __init__(self) -> None:
        """Initialize the policy validator."""
        self.validation_results: List[Dict[str, str]] = []
    
    def validate_policy_statement(self, statement: iam.PolicyStatement) -> List[Dict[str, str]]:
        """
        Validate a single IAM policy statement.
        
        Args:
            statement: The IAM policy statement to validate
            
        Returns:
            List of validation issues found
        """
        issues = []
        
        # Convert statement to dict for easier analysis
        statement_dict = statement.to_json()
        
        # Check for overly broad actions
        issues.extend(self._check_broad_actions(statement_dict))
        
        # Check for missing resource constraints
        issues.extend(self._check_resource_constraints(statement_dict))
        
        # Check for missing conditions where appropriate
        issues.extend(self._check_conditions(statement_dict))
        
        # Check for proper effect usage
        issues.extend(self._check_effect_usage(statement_dict))
        
        return issues
    
    def validate_role_policies(self, role: iam.Role) -> Dict[str, List[Dict[str, str]]]:
        """
        Validate all policies attached to an IAM role.
        
        Args:
            role: The IAM role to validate
            
        Returns:
            Dictionary of validation results by policy type
        """
        results = {
            "inline_policies": [],
            "managed_policies": [],
            "summary": []
        }
        
        # Note: In CDK, we can't easily access the actual policy documents
        # This would be used in conjunction with AWS APIs for full validation
        
        return results
    
    def _check_broad_actions(self, statement: Dict) -> List[Dict[str, str]]:
        """
        Check for overly broad actions in policy statements.
        
        Args:
            statement: Policy statement as dictionary
            
        Returns:
            List of issues found
        """
        issues = []
        actions = statement.get("Action", [])
        
        if isinstance(actions, str):
            actions = [actions]
        
        for action in actions:
            if action in self.DANGEROUS_ACTIONS:
                issues.append({
                    "severity": "HIGH",
                    "type": "BROAD_ACTION",
                    "message": f"Overly broad action '{action}' detected. Consider using more specific actions.",
                    "action": action
                })
            
            # Check for wildcard usage
            if "*" in action and action not in ["logs:*"]:  # logs:* is often acceptable
                issues.append({
                    "severity": "MEDIUM",
                    "type": "WILDCARD_ACTION",
                    "message": f"Wildcard action '{action}' detected. Consider using specific actions.",
                    "action": action
                })
        
        return issues
    
    def _check_resource_constraints(self, statement: Dict) -> List[Dict[str, str]]:
        """
        Check for missing resource constraints on sensitive actions.
        
        Args:
            statement: Policy statement as dictionary
            
        Returns:
            List of issues found
        """
        issues = []
        actions = statement.get("Action", [])
        resources = statement.get("Resource", [])
        
        if isinstance(actions, str):
            actions = [actions]
        if isinstance(resources, str):
            resources = [resources]
        
        # Check if resource-constrained actions have proper resource restrictions
        for action in actions:
            if action in self.RESOURCE_CONSTRAINED_ACTIONS:
                if "*" in resources:
                    issues.append({
                        "severity": "HIGH",
                        "type": "MISSING_RESOURCE_CONSTRAINT",
                        "message": f"Action '{action}' should have specific resource constraints, not '*'.",
                        "action": action
                    })
        
        return issues
    
    def _check_conditions(self, statement: Dict) -> List[Dict[str, str]]:
        """
        Check for missing conditions where they should be present.
        
        Args:
            statement: Policy statement as dictionary
            
        Returns:
            List of issues found
        """
        issues = []
        actions = statement.get("Action", [])
        conditions = statement.get("Condition", {})
        
        if isinstance(actions, str):
            actions = [actions]
        
        # Check for sts:AssumeRole without conditions
        if "sts:AssumeRole" in actions and not conditions:
            issues.append({
                "severity": "HIGH",
                "type": "MISSING_CONDITION",
                "message": "sts:AssumeRole should include conditions like StringEquals for aws:SourceAccount.",
                "action": "sts:AssumeRole"
            })
        
        # Check for DynamoDB actions without attribute conditions
        dynamodb_actions = [action for action in actions if action.startswith("dynamodb:")]
        if dynamodb_actions and "ForAllValues:StringEquals" not in str(conditions):
            issues.append({
                "severity": "MEDIUM",
                "type": "MISSING_ATTRIBUTE_CONDITION",
                "message": "DynamoDB actions should include attribute-level conditions for better security.",
                "action": "dynamodb:*"
            })
        
        return issues
    
    def _check_effect_usage(self, statement: Dict) -> List[Dict[str, str]]:
        """
        Check for proper Effect usage in policy statements.
        
        Args:
            statement: Policy statement as dictionary
            
        Returns:
            List of issues found
        """
        issues = []
        effect = statement.get("Effect", "Allow")
        
        # Generally, we should avoid Deny statements in service roles
        # unless there's a specific security requirement
        if effect == "Deny":
            issues.append({
                "severity": "MEDIUM",
                "type": "DENY_EFFECT",
                "message": "Deny effect detected. Ensure this is intentional and necessary.",
                "effect": effect
            })
        
        return issues
    
    def generate_validation_report(self, validation_results: Dict[str, List[Dict[str, str]]]) -> str:
        """
        Generate a human-readable validation report.
        
        Args:
            validation_results: Results from policy validation
            
        Returns:
            Formatted validation report
        """
        report_lines = ["IAM Policy Validation Report", "=" * 30, ""]
        
        total_issues = 0
        severity_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        
        for policy_type, issues in validation_results.items():
            if issues:
                report_lines.append(f"{policy_type.upper()}:")
                report_lines.append("-" * len(policy_type))
                
                for issue in issues:
                    severity = issue.get("severity", "UNKNOWN")
                    issue_type = issue.get("type", "UNKNOWN")
                    message = issue.get("message", "No message")
                    
                    report_lines.append(f"  [{severity}] {issue_type}: {message}")
                    
                    severity_counts[severity] = severity_counts.get(severity, 0) + 1
                    total_issues += 1
                
                report_lines.append("")
        
        # Summary
        report_lines.extend([
            "SUMMARY:",
            f"Total Issues: {total_issues}",
            f"High Severity: {severity_counts['HIGH']}",
            f"Medium Severity: {severity_counts['MEDIUM']}",
            f"Low Severity: {severity_counts['LOW']}"
        ])
        
        return "\n".join(report_lines)
    
    def get_policy_recommendations(self, role_type: str) -> List[str]:
        """
        Get security recommendations for specific role types.
        
        Args:
            role_type: Type of role (bedrock_agent, lambda_base, etc.)
            
        Returns:
            List of security recommendations
        """
        recommendations = {
            "bedrock_agent": [
                "Use specific Lambda function ARNs instead of wildcards",
                "Restrict model access to only required foundation models",
                "Add source account conditions to trust policy",
                "Use specific Knowledge Base ARNs when possible"
            ],
            
            "lambda_base": [
                "Use DynamoDB attribute-level conditions",
                "Restrict Secrets Manager access to specific secret ARNs",
                "Add VPC endpoint policies for enhanced security",
                "Use resource-based policies where appropriate"
            ],
            
            "lambda_vpc": [
                "Add external ID conditions for cross-account assume role",
                "Restrict S3 access to specific buckets and prefixes",
                "Use VPC endpoints to avoid internet traffic",
                "Monitor cross-account access patterns"
            ],
            
            "api_gateway": [
                "Use resource-based policies for additional security",
                "Implement request validation and rate limiting",
                "Add CloudWatch logging for audit trails",
                "Use API keys and request signing where appropriate"
            ]
        }
        
        return recommendations.get(role_type, [
            "Follow principle of least privilege",
            "Use specific resource ARNs instead of wildcards",
            "Add appropriate conditions to policy statements",
            "Regularly review and audit permissions"
        ])