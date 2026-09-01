#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
"""
API Gateway stack for OSCAR Slack Bot.

This module defines the API Gateway with Slack webhook endpoints, security,
and monitoring for the OSCAR Slack Bot infrastructure.
"""

from typing import Any, Optional

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_logs as logs
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as route53_targets
from aws_cdk import aws_wafv2 as wafv2
from constructs import Construct


class OscarApiGatewayStack(Stack):
    """
    API Gateway stack for OSCAR Slack Bot.
    This stack creates and configures the REST API Gateway with Slack webhook
    endpoints, security features, and monitoring capabilities.
    """

    WAF_RATE_LIMIT = 100  # requests per 5-minute window per IP
    WAF_MAX_BODY_SIZE = 8192  # 8KB — generous for Slack payloads (typically 1-4KB)

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        lambda_stack: Any,
        permissions_stack: Any,
        environment: str,
        custom_domain: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Initialize API Gateway stack.
        Args:
            scope: The CDK construct scope
            construct_id: The ID of the construct
            lambda_stack: The Lambda stack with functions
            permissions_stack: The permissions stack with IAM roles
            environment: The deployment environment name, only set for prod environment
            custom_domain: Optional custom domain name (e.g. oscar.opensearch.org).
                When set, this stack creates a PUBLIC Route 53 hosted zone for the
                domain, an ACM certificate validated against that zone, an API
                Gateway custom domain, and an alias A-record pointing at it.
            **kwargs: Additional keyword arguments for Stack
        """
        super().__init__(scope, construct_id, **kwargs)

        self.lambda_stack = lambda_stack
        self.permissions_stack = permissions_stack
        self.env_name = environment
        self.custom_domain = custom_domain
        # Get the main Lambda function and API Gateway role
        self.lambda_function = lambda_stack.lambda_functions[lambda_stack.get_supervisor_agent_function_name(self.env_name)]
        self.github_webhook_function = lambda_stack.lambda_functions[lambda_stack.get_github_webhook_handler_function_name(self.env_name)]
        self.api_gateway_role = permissions_stack.api_gateway_role

        # Create CloudWatch log group for API Gateway
        self.log_group = self._create_log_group()

        # Create the REST API Gateway
        self.api = self._create_rest_api()

        # Configure Slack webhook endpoints
        self._configure_slack_endpoints()

        # Configure GitHub webhook endpoint
        self._configure_github_webhook_endpoint()

        # Optionally attach a custom domain with an in-stack ACM certificate
        if self.custom_domain:
            self._configure_custom_domain()

        # Attach WAF for rate limiting and payload protection
        self.web_acl = self._create_waf()
        self._associate_waf()

    def _create_log_group(self) -> logs.LogGroup:
        """
        Create CloudWatch log group for API Gateway access logs.
        Returns:
            The created CloudWatch log group
        """
        return logs.LogGroup(
            self, "ApiGatewayLogGroup",
            log_group_name=f"/aws/apigateway/oscar-slack-bot-{self.env_name}",
            retention=logs.RetentionDays.ONE_YEAR,
            removal_policy=RemovalPolicy.DESTROY
        )

    def _create_rest_api(self) -> apigateway.RestApi:
        """
        Create the REST API Gateway with security and monitoring configuration.
        Returns:
            The created REST API Gateway
        """
        api = apigateway.RestApi(
            self, "OscarSlackBotApi",
            rest_api_name=f"oscar-slack-bot-api-{self.env_name}",
            description="OSCAR Slack Bot API Gateway for webhook endpoints",
            cloud_watch_role=True,
            # Keep minimal configuration
            deploy_options=apigateway.StageOptions(
                stage_name=self.env_name,
                access_log_destination=apigateway.LogGroupLogDestination(self.log_group),
                access_log_format=apigateway.AccessLogFormat.clf()
            ),

            # CORS disabled for Slack webhook compatibility

            # Security configuration
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
            ),

            # Enable execute API endpoint for Slack webhook access
            disable_execute_api_endpoint=False
        )

        # Remove CDK's auto-generated Endpoint output to avoid exposing the URL in deploy logs
        api.node.try_remove_child("Endpoint")

        return api

    def _configure_slack_endpoints(self) -> None:
        """
        Configure Slack webhook endpoints with proper methods and integration.
        """
        # Create /slack resource
        slack_resource = self.api.root.add_resource("slack")

        # No request validator to ensure Slack compatibility

        # Create Lambda proxy integration (required for Slack challenge handling)
        lambda_integration = apigateway.LambdaIntegration(
            self.lambda_function,
            proxy=True,  # Enable proxy integration for proper request/response handling
            allow_test_invoke=True
        )

        # Create /slack/events endpoint with proxy integration (only endpoint needed)
        events_resource = slack_resource.add_resource("events")
        events_resource.add_method(
            "POST",
            lambda_integration,
            authorization_type=apigateway.AuthorizationType.NONE
        )

        # Create /oauth/callback endpoint for GitHub OAuth redirect
        identity_fn = self.lambda_stack.lambda_functions.get("identity")
        if identity_fn:
            oauth_resource = self.api.root.add_resource("oauth")
            callback_resource = oauth_resource.add_resource("callback")
            callback_integration = apigateway.LambdaIntegration(
                identity_fn,
                proxy=True,
                allow_test_invoke=True
            )
            callback_resource.add_method(
                "GET",
                callback_integration,
                authorization_type=apigateway.AuthorizationType.NONE
            )

    def _configure_github_webhook_endpoint(self) -> None:
        """Configure GitHub webhook endpoint at /github/webhooks."""
        github_resource = self.api.root.add_resource("github")
        webhooks_resource = github_resource.add_resource("webhooks")

        github_integration = apigateway.LambdaIntegration(
            self.github_webhook_function,
            proxy=True,
            allow_test_invoke=True,
        )

        webhooks_resource.add_method(
            "POST",
            github_integration,
            authorization_type=apigateway.AuthorizationType.NONE,
        )

    def _configure_custom_domain(self) -> None:
        """
        Attach a custom domain to the API using an in-stack ACM certificate,
        backed by a public Route 53 hosted zone owned by this account.

        This account owns a public hosted zone for the custom domain (a subdomain delegated under the parent org's domain, e.g.
        ``oscar.opensearch.org`` under ``opensearch.org``). This stack:

        One-time delegation: after the hosted zone is created, its name servers
        must be given to the owner of the parent domain (opensearch.org), who
        creates NS records delegating the subdomain to them once. After that, all
        validation and routing records are managed automatically by this stack.

        """
        # This method is only invoked when custom_domain is set; assert for the
        # type checker and as a defensive runtime guard.
        assert self.custom_domain is not None
        custom_domain = self.custom_domain

        # 1. Public hosted zone owned by this account for the subdomain.
        #    Retain on stack deletion
        hosted_zone = route53.PublicHostedZone(
            self, "ApiCustomDomainHostedZone",
            zone_name=custom_domain,
        )
        hosted_zone.apply_removal_policy(RemovalPolicy.RETAIN)
        self.hosted_zone = hosted_zone

        # 2. ACM certificate validated against the zone above (automatic).
        certificate = acm.Certificate(
            self, "ApiCustomDomainCert",
            domain_name=custom_domain,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        # 3. Regional API Gateway custom domain using the validated certificate.
        domain_name = apigateway.DomainName(
            self, "ApiCustomDomain",
            domain_name=custom_domain,
            certificate=certificate,
            endpoint_type=apigateway.EndpointType.REGIONAL,
            security_policy=apigateway.SecurityPolicy.TLS_1_2,
        )

        # 3a. Base path mapping under the environment name (e.g. "prod") so URLs keep the stage prefix: https://<domain>/prod/slack/events. This
        #     mirrors the default execute-api URL structure (/<stage>/...).
        domain_name.add_base_path_mapping(
            self.api,
            base_path=self.env_name,
            stage=self.api.deployment_stage,
        )

        # 4. Alias A-record at the zone apex routing the domain at the API
        route53.ARecord(
            self, "ApiCustomDomainAliasRecord",
            zone=hosted_zone,
            target=route53.RecordTarget.from_alias(
                route53_targets.ApiGatewayDomain(domain_name)
            ),
        )

    def _create_waf(self) -> wafv2.CfnWebACL:
        """Create a WAFv2 WebACL with rate limiting, managed rules, and size constraints."""

        def _visibility(name: str) -> wafv2.CfnWebACL.VisibilityConfigProperty:
            return wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name=f"oscar-waf-{name}-{self.env_name}",
                sampled_requests_enabled=True,
            )

        rules = [
            # 1. Rate-based rule — block IPs exceeding threshold
            wafv2.CfnWebACL.RuleProperty(
                name="RateLimitPerIP",
                priority=1,
                statement=wafv2.CfnWebACL.StatementProperty(
                    rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                        limit=self.WAF_RATE_LIMIT,
                        aggregate_key_type="IP",
                    )
                ),
                action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                visibility_config=_visibility("rate-limit"),
            ),
            # 2. AWS Common Rule Set — blocks common exploits (XSS, SQLi, etc.)
            #    Scoped down to exclude /github/ paths — those payloads contain HTML
            #    that triggers XSS rules, but are HMAC-signed by GitHub.
            wafv2.CfnWebACL.RuleProperty(
                name="AWSCommonRuleSet",
                priority=2,
                statement=wafv2.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                        vendor_name="AWS",
                        name="AWSManagedRulesCommonRuleSet",
                        excluded_rules=[
                            wafv2.CfnWebACL.ExcludedRuleProperty(name="SizeRestrictions_BODY"),
                        ],
                        scope_down_statement=wafv2.CfnWebACL.StatementProperty(
                            not_statement=wafv2.CfnWebACL.NotStatementProperty(
                                statement=wafv2.CfnWebACL.StatementProperty(
                                    byte_match_statement=wafv2.CfnWebACL.ByteMatchStatementProperty(
                                        field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(uri_path={}),
                                        positional_constraint="STARTS_WITH",
                                        search_string=f"/{self.env_name}/github/",
                                        text_transformations=[
                                            wafv2.CfnWebACL.TextTransformationProperty(priority=0, type="NONE")
                                        ],
                                    )
                                )
                            )
                        ),
                    )
                ),
                override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                visibility_config=_visibility("common-rules"),
            ),
            # 3. AWS Known Bad Inputs — scoped down to exclude /github/ paths
            wafv2.CfnWebACL.RuleProperty(
                name="AWSKnownBadInputs",
                priority=3,
                statement=wafv2.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                        vendor_name="AWS",
                        name="AWSManagedRulesKnownBadInputsRuleSet",
                        scope_down_statement=wafv2.CfnWebACL.StatementProperty(
                            not_statement=wafv2.CfnWebACL.NotStatementProperty(
                                statement=wafv2.CfnWebACL.StatementProperty(
                                    byte_match_statement=wafv2.CfnWebACL.ByteMatchStatementProperty(
                                        field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(uri_path={}),
                                        positional_constraint="STARTS_WITH",
                                        search_string=f"/{self.env_name}/github/",
                                        text_transformations=[
                                            wafv2.CfnWebACL.TextTransformationProperty(priority=0, type="NONE")
                                        ],
                                    )
                                )
                            )
                        ),
                    )
                ),
                override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                visibility_config=_visibility("known-bad-inputs"),
            ),
            # 4. Size constraint — reject request bodies > 8KB (Slack paths only).
            #    GitHub webhook payloads can be large and are HMAC-signed, so exempt them.
            wafv2.CfnWebACL.RuleProperty(
                name="BodySizeLimit",
                priority=4,
                statement=wafv2.CfnWebACL.StatementProperty(
                    and_statement=wafv2.CfnWebACL.AndStatementProperty(
                        statements=[
                            wafv2.CfnWebACL.StatementProperty(
                                not_statement=wafv2.CfnWebACL.NotStatementProperty(
                                    statement=wafv2.CfnWebACL.StatementProperty(
                                        byte_match_statement=wafv2.CfnWebACL.ByteMatchStatementProperty(
                                            field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(
                                                uri_path={}
                                            ),
                                            positional_constraint="STARTS_WITH",
                                            search_string=f"/{self.env_name}/github/",
                                            text_transformations=[
                                                wafv2.CfnWebACL.TextTransformationProperty(priority=0, type="NONE")
                                            ],
                                        )
                                    )
                                )
                            ),
                            wafv2.CfnWebACL.StatementProperty(
                                size_constraint_statement=wafv2.CfnWebACL.SizeConstraintStatementProperty(
                                    field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(body={}),
                                    comparison_operator="GT",
                                    size=self.WAF_MAX_BODY_SIZE,
                                    text_transformations=[
                                        wafv2.CfnWebACL.TextTransformationProperty(priority=0, type="NONE")
                                    ],
                                )
                            ),
                        ]
                    )
                ),
                action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                visibility_config=_visibility("body-size"),
            ),
        ]

        return wafv2.CfnWebACL(
            self, "OscarWafWebAcl",
            name=f"oscar-waf-{self.env_name}",
            scope="REGIONAL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            rules=rules,
            visibility_config=_visibility("overall"),
        )

    def _associate_waf(self) -> None:
        """Associate the WAF WebACL with the API Gateway stage."""
        wafv2.CfnWebACLAssociation(
            self, "OscarWafAssociation",
            resource_arn=self.api.deployment_stage.stage_arn,
            web_acl_arn=self.web_acl.attr_arn,
        )
