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

import logging
import os
from typing import Dict, List, Optional, Any
from aws_cdk import (
    Duration,
    Stack,
    RemovalPolicy,
    aws_apigateway as apigateway,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
    CfnOutput
)
from constructs import Construct

# Configure logging
logger = logging.getLogger(__name__)

class OscarApiGatewayStack(Stack):
    """
    API Gateway stack for OSCAR Slack Bot.
    
    This stack creates and configures the REST API Gateway with Slack webhook
    endpoints, security features, and monitoring capabilities.
    """
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str,
        lambda_stack: Any,
        permissions_stack: Any,
        **kwargs
    ) -> None:
        """
        Initialize API Gateway stack.
        
        Args:
            scope: The CDK construct scope
            construct_id: The ID of the construct
            lambda_stack: The Lambda stack with functions
            permissions_stack: The permissions stack with IAM roles
            **kwargs: Additional keyword arguments for Stack
        """
        super().__init__(scope, construct_id, **kwargs)
        
        self.lambda_stack = lambda_stack
        self.permissions_stack = permissions_stack
        
        # Get the main Lambda function and API Gateway role
        self.lambda_function = lambda_stack.lambda_functions["main_agent"]
        self.api_gateway_role = permissions_stack.api_gateway_role
        
        # Create CloudWatch log group for API Gateway
        self.log_group = self._create_log_group()
        
        # Create the REST API Gateway
        self.api = self._create_rest_api()
        
        # Configure Slack webhook endpoints
        self._configure_slack_endpoints()
        
        # Add outputs for important resources
        self._add_outputs()
    
    def _create_log_group(self) -> logs.LogGroup:
        """
        Create CloudWatch log group for API Gateway access logs.
        
        Returns:
            The created CloudWatch log group
        """
        return logs.LogGroup(
            self, "ApiGatewayLogGroup",
            log_group_name="/aws/apigateway/oscar-slack-bot-cdk",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY
        )
    
    def _create_rest_api(self) -> apigateway.RestApi:
        """
        Create the REST API Gateway with security and monitoring configuration.
        
        Returns:
            The created REST API Gateway
        """
        # Configure CORS origins with security in mind
        cors_origins = self._get_cors_origins()
        
        api = apigateway.RestApi(
            self, "OscarSlackBotApi",
            rest_api_name="oscar-slack-bot-api-cdk",
            description="OSCAR Slack Bot API Gateway for webhook endpoints",
            
            # Enable CloudWatch logging
            cloud_watch_role=True,
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                logging_level=apigateway.MethodLoggingLevel.INFO,
                access_log_destination=apigateway.LogGroupLogDestination(self.log_group),
                access_log_format=apigateway.AccessLogFormat.json_with_standard_fields(
                    caller=True,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=True
                ),
                
                # Enable throttling and abuse protection
                throttling_rate_limit=100,  # requests per second
                throttling_burst_limit=200,  # burst capacity
                
                # Enable detailed metrics
                metrics_enabled=True,
                data_trace_enabled=False  # Disable for security (contains request/response data)
            ),
            
            # Default CORS configuration
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=cors_origins,
                allow_methods=["POST", "OPTIONS"],
                allow_headers=[
                    "Content-Type",
                    "X-Slack-Request-Timestamp", 
                    "X-Slack-Signature",
                    "X-Slack-Retry-Num",
                    "X-Slack-Retry-Reason"
                ],
                max_age=Duration.hours(1)
            ),
            
            # Security configuration
            endpoint_configuration=apigateway.EndpointConfiguration(
                types=[apigateway.EndpointType.REGIONAL]
            ),
            
            # Disable execute API endpoint for security
            disable_execute_api_endpoint=True
        )
        
        # Add additional security and monitoring
        self._add_security_features(api)
        self._add_monitoring_features(api)
        
        return api
    
    def _configure_slack_endpoints(self) -> None:
        """
        Configure Slack webhook endpoints with proper methods and integration.
        """
        # Create /slack resource
        slack_resource = self.api.root.add_resource("slack")
        
        # Create request validator once and reuse
        request_validator = self._create_request_validator()
        
        # Create Lambda integration
        lambda_integration = apigateway.LambdaIntegration(
            self.lambda_function,
            proxy=False,
            integration_responses=[
                apigateway.IntegrationResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": "'*'"
                    }
                ),
                apigateway.IntegrationResponse(
                    status_code="400",
                    selection_pattern="4\\d{2}"
                ),
                apigateway.IntegrationResponse(
                    status_code="500",
                    selection_pattern="5\\d{2}"
                )
            ]
        )
        
        # Method response configuration
        method_responses = [
            apigateway.MethodResponse(
                status_code="200",
                response_parameters={
                    "method.response.header.Access-Control-Allow-Origin": True
                }
            ),
            apigateway.MethodResponse(status_code="400"),
            apigateway.MethodResponse(status_code="500")
        ]
        
        # Create /slack/events endpoint
        events_resource = slack_resource.add_resource("events")
        events_resource.add_method(
            "POST",
            lambda_integration,
            method_responses=method_responses,
            request_validator=request_validator,
            authorization_type=apigateway.AuthorizationType.NONE
        )
        
        # Create /slack/interactive endpoint
        interactive_resource = slack_resource.add_resource("interactive")
        interactive_resource.add_method(
            "POST", 
            lambda_integration,
            method_responses=method_responses,
            request_validator=request_validator,
            authorization_type=apigateway.AuthorizationType.NONE
        )
    
    def _create_request_validator(self) -> apigateway.RequestValidator:
        """
        Create request validator for API Gateway endpoints.
        
        Returns:
            The created request validator
        """
        return apigateway.RequestValidator(
            self, "SlackRequestValidator",
            rest_api=self.api,
            request_validator_name="slack-request-validator-cdk",
            validate_request_body=True,
            validate_request_parameters=True
        )
    
    def _get_cors_origins(self) -> List[str]:
        """
        Get CORS origins configuration with security best practices.
        
        Returns:
            List of allowed CORS origins
        """
        # Default secure origins for Slack bot
        default_origins = [
            "https://slack.com",
            "https://*.slack.com", 
            "https://api.slack.com",
            "https://hooks.slack.com"
        ]
        
        # Allow users to specify additional origins via environment variable
        custom_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "")
        if custom_origins:
            # Parse comma-separated origins and add to defaults
            additional_origins = [origin.strip() for origin in custom_origins.split(",") if origin.strip()]
            default_origins.extend(additional_origins)
            logger.info(f"Added custom CORS origins: {additional_origins}")
        
        logger.info(f"Configured CORS origins: {default_origins}")
        return default_origins
    
    def _add_security_features(self, api: apigateway.RestApi) -> None:
        """
        Add additional security features to the API Gateway.
        
        Args:
            api: The REST API Gateway to enhance
        """
        # Create usage plan for rate limiting and quotas
        usage_plan = api.add_usage_plan(
            "SlackBotUsagePlan",
            name="oscar-slack-bot-usage-plan-cdk",
            description="Usage plan for OSCAR Slack Bot API with rate limiting",
            throttle=apigateway.ThrottleSettings(
                rate_limit=50,  # requests per second per API key
                burst_limit=100  # burst capacity per API key
            ),
            quota=apigateway.QuotaSettings(
                limit=10000,  # requests per period
                period=apigateway.Period.DAY
            )
        )
        
        # Create API key for additional security (optional, can be used for monitoring)
        api_key = api.add_api_key(
            "SlackBotApiKey",
            api_key_name="oscar-slack-bot-api-key-cdk",
            description="API key for OSCAR Slack Bot"
        )
        
        # Associate API key with usage plan
        usage_plan.add_api_key(api_key)
        
        # Add WAF web ACL for additional protection (if needed)
        # Note: This would require additional configuration and is optional
        
    def _add_monitoring_features(self, api: apigateway.RestApi) -> None:
        """
        Add monitoring and alerting features to the API Gateway.
        
        Args:
            api: The REST API Gateway to monitor
        """
        from aws_cdk import aws_cloudwatch as cloudwatch
        from aws_cdk import aws_cloudwatch_actions as cw_actions
        from aws_cdk import aws_sns as sns
        
        # Create SNS topic for alerts (optional)
        alert_topic = sns.Topic(
            self, "ApiGatewayAlerts",
            topic_name="oscar-api-gateway-alerts-cdk"
        )
        
        # Create CloudWatch alarms for monitoring
        
        # High error rate alarm
        error_rate_alarm = cloudwatch.Alarm(
            self, "HighErrorRateAlarm",
            alarm_name="oscar-api-gateway-high-error-rate-cdk",
            alarm_description="High error rate detected in API Gateway",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGateway",
                metric_name="4XXError",
                dimensions_map={
                    "ApiName": api.rest_api_name
                },
                statistic="Sum",
                period=Duration.minutes(5)
            ),
            threshold=10,  # 10 errors in 5 minutes
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
        )
        
        # High latency alarm
        latency_alarm = cloudwatch.Alarm(
            self, "HighLatencyAlarm", 
            alarm_name="oscar-api-gateway-high-latency-cdk",
            alarm_description="High latency detected in API Gateway",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGateway",
                metric_name="Latency",
                dimensions_map={
                    "ApiName": api.rest_api_name
                },
                statistic="Average",
                period=Duration.minutes(5)
            ),
            threshold=5000,  # 5 seconds
            evaluation_periods=3,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
        )
        
        # Throttling alarm
        throttle_alarm = cloudwatch.Alarm(
            self, "ThrottlingAlarm",
            alarm_name="oscar-api-gateway-throttling-cdk",
            alarm_description="API Gateway throttling detected",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGateway", 
                metric_name="ThrottledRequests",
                dimensions_map={
                    "ApiName": api.rest_api_name
                },
                statistic="Sum",
                period=Duration.minutes(1)
            ),
            threshold=5,  # 5 throttled requests in 1 minute
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD
        )
        
        # Add SNS actions to alarms (optional)
        error_rate_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))
        latency_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))
        throttle_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))
        
        # Store references for outputs
        self.alert_topic = alert_topic
        self.error_rate_alarm = error_rate_alarm
        self.latency_alarm = latency_alarm
        self.throttle_alarm = throttle_alarm

    def _add_outputs(self) -> None:
        """
        Add CloudFormation outputs for important resources.
        """
        CfnOutput(
            self, "ApiGatewayUrl",
            value=self.api.url,
            description="Base URL of the API Gateway"
        )
        
        CfnOutput(
            self, "SlackEventsUrl", 
            value=f"{self.api.url}slack/events",
            description="URL for Slack Events API webhook"
        )
        
        CfnOutput(
            self, "SlackInteractiveUrl",
            value=f"{self.api.url}slack/interactive", 
            description="URL for Slack Interactive Components webhook"
        )
        
        CfnOutput(
            self, "ApiGatewayId",
            value=self.api.rest_api_id,
            description="ID of the API Gateway"
        )
        
        CfnOutput(
            self, "ApiGatewayLogGroupName",
            value=self.log_group.log_group_name,
            description="Name of the API Gateway CloudWatch log group"
        )
        
        # Add monitoring outputs
        if hasattr(self, 'alert_topic'):
            CfnOutput(
                self, "AlertTopicArn",
                value=self.alert_topic.topic_arn,
                description="ARN of the SNS topic for API Gateway alerts"
            )