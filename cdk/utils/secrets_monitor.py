#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Secrets monitoring and alerting utilities for OSCAR CDK Automation.

This module provides monitoring capabilities for AWS Secrets Manager secrets
including CloudWatch metrics, alarms, and automated alerting for access failures.
"""

import boto3
import json
import logging
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from dataclasses import dataclass


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SecretMetrics:
    """Metrics for a specific secret."""
    secret_name: str
    access_count: int
    error_count: int
    last_accessed: Optional[datetime]
    last_error: Optional[datetime]
    error_rate: float


@dataclass
class AlertConfig:
    """Configuration for secret monitoring alerts."""
    secret_name: str
    error_threshold: int
    error_rate_threshold: float
    notification_topic_arn: str
    enabled: bool = True


class SecretsMonitor:
    """
    Monitoring and alerting utility for OSCAR secrets.
    
    This class provides methods to monitor secrets access patterns,
    create CloudWatch alarms, and send notifications for access failures.
    """
    
    def __init__(self, region: str = None):
        """
        Initialize the secrets monitor.
        
        Args:
            region: AWS region (defaults to environment variable or us-east-1)
        """
        self.region = region or os.environ.get('AWS_REGION', 'us-east-1')
        self.cloudwatch = None
        self.sns = None
        self.logs = None
        self._initialize_clients()
    
    def _initialize_clients(self) -> None:
        """Initialize AWS clients."""
        try:
            self.cloudwatch = boto3.client('cloudwatch', region_name=self.region)
            self.sns = boto3.client('sns', region_name=self.region)
            self.logs = boto3.client('logs', region_name=self.region)
            logger.info(f"Initialized monitoring clients for region: {self.region}")
        except Exception as e:
            logger.error(f"Failed to initialize monitoring clients: {e}")
            raise
    
    def create_secret_access_alarm(self, secret_name: str, error_threshold: int = 5, 
                                 notification_topic_arn: str = None) -> str:
        """
        Create CloudWatch alarm for secret access failures.
        
        Args:
            secret_name: Name of the secret to monitor
            error_threshold: Number of errors to trigger alarm
            notification_topic_arn: SNS topic ARN for notifications
            
        Returns:
            ARN of the created alarm
        """
        alarm_name = f"oscar-secret-access-failures-{secret_name}"
        
        try:
            # Create the alarm
            response = self.cloudwatch.put_metric_alarm(
                AlarmName=alarm_name,
                ComparisonOperator='GreaterThanThreshold',
                EvaluationPeriods=1,
                MetricName='Errors',
                Namespace='AWS/SecretsManager',
                Period=300,  # 5 minutes
                Statistic='Sum',
                Threshold=error_threshold,
                ActionsEnabled=True,
                AlarmActions=[notification_topic_arn] if notification_topic_arn else [],
                AlarmDescription=f'Monitor access failures for secret {secret_name}',
                Dimensions=[
                    {
                        'Name': 'SecretName',
                        'Value': secret_name
                    }
                ],
                Unit='Count',
                TreatMissingData='notBreaching'
            )
            
            logger.info(f"Created CloudWatch alarm: {alarm_name}")
            return f"arn:aws:cloudwatch:{self.region}:{boto3.client('sts').get_caller_identity()['Account']}:alarm:{alarm_name}"
        
        except ClientError as e:
            logger.error(f"Failed to create alarm for {secret_name}: {e}")
            raise
    
    def create_secret_usage_dashboard(self, secret_names: List[str]) -> str:
        """
        Create CloudWatch dashboard for secrets usage monitoring.
        
        Args:
            secret_names: List of secret names to include in dashboard
            
        Returns:
            Name of the created dashboard
        """
        dashboard_name = "oscar-secrets-monitoring"
        
        # Build dashboard widgets
        widgets = []
        
        # Access count widget
        access_metrics = []
        for secret_name in secret_names:
            access_metrics.append([
                "AWS/SecretsManager", "SuccessfulRequestLatency", "SecretName", secret_name
            ])
        
        widgets.append({
            "type": "metric",
            "x": 0,
            "y": 0,
            "width": 12,
            "height": 6,
            "properties": {
                "metrics": access_metrics,
                "period": 300,
                "stat": "Sum",
                "region": self.region,
                "title": "Secret Access Count",
                "yAxis": {
                    "left": {
                        "min": 0
                    }
                }
            }
        })
        
        # Error rate widget
        error_metrics = []
        for secret_name in secret_names:
            error_metrics.append([
                "AWS/SecretsManager", "Errors", "SecretName", secret_name
            ])
        
        widgets.append({
            "type": "metric",
            "x": 12,
            "y": 0,
            "width": 12,
            "height": 6,
            "properties": {
                "metrics": error_metrics,
                "period": 300,
                "stat": "Sum",
                "region": self.region,
                "title": "Secret Access Errors",
                "yAxis": {
                    "left": {
                        "min": 0
                    }
                }
            }
        })
        
        # Lambda function errors related to secrets
        widgets.append({
            "type": "log",
            "x": 0,
            "y": 6,
            "width": 24,
            "height": 6,
            "properties": {
                "query": f"SOURCE '/aws/lambda/oscar-agent'\n| fields @timestamp, @message\n| filter @message like /secretsmanager/\n| filter @message like /error/i\n| sort @timestamp desc\n| limit 100",
                "region": self.region,
                "title": "Recent Secrets-Related Lambda Errors",
                "view": "table"
            }
        })
        
        dashboard_body = {
            "widgets": widgets
        }
        
        try:
            self.cloudwatch.put_dashboard(
                DashboardName=dashboard_name,
                DashboardBody=json.dumps(dashboard_body)
            )
            
            logger.info(f"Created CloudWatch dashboard: {dashboard_name}")
            return dashboard_name
        
        except ClientError as e:
            logger.error(f"Failed to create dashboard: {e}")
            raise
    
    def get_secret_metrics(self, secret_name: str, hours: int = 24) -> SecretMetrics:
        """
        Get metrics for a specific secret over the specified time period.
        
        Args:
            secret_name: Name of the secret
            hours: Number of hours to look back
            
        Returns:
            SecretMetrics object with usage statistics
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        try:
            # Get access count
            access_response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/SecretsManager',
                MetricName='SuccessfulRequestLatency',
                Dimensions=[
                    {
                        'Name': 'SecretName',
                        'Value': secret_name
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,  # 1 hour
                Statistics=['SampleCount']
            )
            
            access_count = sum(point['SampleCount'] for point in access_response['Datapoints'])
            
            # Get error count
            error_response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/SecretsManager',
                MetricName='Errors',
                Dimensions=[
                    {
                        'Name': 'SecretName',
                        'Value': secret_name
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,  # 1 hour
                Statistics=['Sum']
            )
            
            error_count = sum(point['Sum'] for point in error_response['Datapoints'])
            
            # Calculate error rate
            total_requests = access_count + error_count
            error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0
            
            # Get last accessed time (approximate)
            last_accessed = None
            if access_response['Datapoints']:
                last_accessed = max(point['Timestamp'] for point in access_response['Datapoints'])
            
            # Get last error time
            last_error = None
            if error_response['Datapoints']:
                error_points = [point for point in error_response['Datapoints'] if point['Sum'] > 0]
                if error_points:
                    last_error = max(point['Timestamp'] for point in error_points)
            
            return SecretMetrics(
                secret_name=secret_name,
                access_count=int(access_count),
                error_count=int(error_count),
                last_accessed=last_accessed,
                last_error=last_error,
                error_rate=error_rate
            )
        
        except ClientError as e:
            logger.error(f"Failed to get metrics for {secret_name}: {e}")
            return SecretMetrics(
                secret_name=secret_name,
                access_count=0,
                error_count=0,
                last_accessed=None,
                last_error=None,
                error_rate=0.0
            )
    
    def check_lambda_secrets_access_logs(self, lambda_function_names: List[str], 
                                       hours: int = 1) -> Dict[str, List[str]]:
        """
        Check Lambda function logs for secrets access failures.
        
        Args:
            lambda_function_names: List of Lambda function names to check
            hours: Number of hours to look back
            
        Returns:
            Dictionary mapping function names to lists of error messages
        """
        end_time = int(datetime.utcnow().timestamp() * 1000)
        start_time = int((datetime.utcnow() - timedelta(hours=hours)).timestamp() * 1000)
        
        results = {}
        
        for function_name in lambda_function_names:
            log_group_name = f"/aws/lambda/{function_name}"
            errors = []
            
            try:
                # Query logs for secrets-related errors
                query = """
                fields @timestamp, @message
                | filter @message like /secretsmanager/
                | filter @message like /error/i or @message like /failed/i or @message like /exception/i
                | sort @timestamp desc
                """
                
                response = self.logs.start_query(
                    logGroupName=log_group_name,
                    startTime=start_time,
                    endTime=end_time,
                    queryString=query
                )
                
                query_id = response['queryId']
                
                # Wait for query to complete and get results
                import time
                while True:
                    result = self.logs.get_query_results(queryId=query_id)
                    if result['status'] == 'Complete':
                        break
                    elif result['status'] == 'Failed':
                        logger.error(f"Log query failed for {function_name}")
                        break
                    time.sleep(1)
                
                # Extract error messages
                for result_row in result.get('results', []):
                    message_field = next((field for field in result_row if field['field'] == '@message'), None)
                    if message_field:
                        errors.append(message_field['value'])
                
                results[function_name] = errors
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    logger.warning(f"Log group not found for {function_name}")
                    results[function_name] = []
                else:
                    logger.error(f"Failed to query logs for {function_name}: {e}")
                    results[function_name] = [f"Failed to query logs: {e}"]
        
        return results
    
    def send_alert_notification(self, topic_arn: str, secret_name: str, 
                              error_details: str) -> bool:
        """
        Send alert notification for secret access failure.
        
        Args:
            topic_arn: SNS topic ARN for notifications
            secret_name: Name of the affected secret
            error_details: Details of the error
            
        Returns:
            True if notification sent successfully
        """
        try:
            message = {
                "alert_type": "secret_access_failure",
                "secret_name": secret_name,
                "timestamp": datetime.utcnow().isoformat(),
                "error_details": error_details,
                "region": self.region
            }
            
            subject = f"OSCAR Secret Access Alert: {secret_name}"
            
            self.sns.publish(
                TopicArn=topic_arn,
                Message=json.dumps(message, indent=2),
                Subject=subject
            )
            
            logger.info(f"Sent alert notification for {secret_name}")
            return True
        
        except ClientError as e:
            logger.error(f"Failed to send notification: {e}")
            return False
    
    def monitor_all_secrets(self, alert_configs: List[AlertConfig]) -> Dict[str, Any]:
        """
        Monitor all configured secrets and send alerts if needed.
        
        Args:
            alert_configs: List of alert configurations
            
        Returns:
            Dictionary with monitoring results
        """
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "secrets_monitored": len(alert_configs),
            "alerts_sent": 0,
            "errors": [],
            "secret_status": {}
        }
        
        for config in alert_configs:
            if not config.enabled:
                continue
            
            try:
                # Get metrics for the secret
                metrics = self.get_secret_metrics(config.secret_name)
                results["secret_status"][config.secret_name] = {
                    "access_count": metrics.access_count,
                    "error_count": metrics.error_count,
                    "error_rate": metrics.error_rate,
                    "last_accessed": metrics.last_accessed.isoformat() if metrics.last_accessed else None,
                    "last_error": metrics.last_error.isoformat() if metrics.last_error else None
                }
                
                # Check if alert should be sent
                should_alert = False
                alert_reason = ""
                
                if metrics.error_count >= config.error_threshold:
                    should_alert = True
                    alert_reason = f"Error count ({metrics.error_count}) exceeded threshold ({config.error_threshold})"
                
                elif metrics.error_rate >= config.error_rate_threshold:
                    should_alert = True
                    alert_reason = f"Error rate ({metrics.error_rate:.2f}%) exceeded threshold ({config.error_rate_threshold}%)"
                
                if should_alert:
                    success = self.send_alert_notification(
                        config.notification_topic_arn,
                        config.secret_name,
                        alert_reason
                    )
                    if success:
                        results["alerts_sent"] += 1
                    else:
                        results["errors"].append(f"Failed to send alert for {config.secret_name}")
            
            except Exception as e:
                error_msg = f"Failed to monitor {config.secret_name}: {e}"
                results["errors"].append(error_msg)
                logger.error(error_msg)
        
        return results


def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Monitor OSCAR secrets and create alerts'
    )
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )
    parser.add_argument(
        '--create-alarms',
        action='store_true',
        help='Create CloudWatch alarms for secrets'
    )
    parser.add_argument(
        '--create-dashboard',
        action='store_true',
        help='Create CloudWatch dashboard'
    )
    parser.add_argument(
        '--check-metrics',
        action='store_true',
        help='Check current metrics for all secrets'
    )
    parser.add_argument(
        '--hours',
        type=int,
        default=24,
        help='Hours to look back for metrics (default: 24)'
    )
    
    args = parser.parse_args()
    
    try:
        monitor = SecretsMonitor(region=args.region)
        
        secret_names = ["oscar-central-env"]
        
        if args.create_alarms:
            print("Creating CloudWatch alarms...")
            for secret_name in secret_names:
                alarm_arn = monitor.create_secret_access_alarm(secret_name)
                print(f"Created alarm for {secret_name}: {alarm_arn}")
        
        if args.create_dashboard:
            print("Creating CloudWatch dashboard...")
            dashboard_name = monitor.create_secret_usage_dashboard(secret_names)
            print(f"Created dashboard: {dashboard_name}")
        
        if args.check_metrics:
            print(f"Checking metrics for the last {args.hours} hours...")
            for secret_name in secret_names:
                metrics = monitor.get_secret_metrics(secret_name, args.hours)
                print(f"\nMetrics for {secret_name}:")
                print(f"  Access Count: {metrics.access_count}")
                print(f"  Error Count: {metrics.error_count}")
                print(f"  Error Rate: {metrics.error_rate:.2f}%")
                print(f"  Last Accessed: {metrics.last_accessed}")
                print(f"  Last Error: {metrics.last_error}")
        
        return 0
    
    except Exception as e:
        logger.error(f"Monitoring failed: {e}")
        return 1


if __name__ == '__main__':
    exit(main())