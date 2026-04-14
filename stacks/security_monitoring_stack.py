#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Security monitoring stack for OSCAR.

Creates CloudWatch metric filters and alarms from:
1. Core supervisor monitoring (unauthorized access, guardrail, prompt injection)
2. Agent-declared monitoring via get_monitoring_config()
"""

from typing import Any, List, Optional

from aws_cdk import Duration, Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sns as sns
from constructs import Construct

from agents.base_agent import MonitoringConfig

CORE_MONITORING = [
    MonitoringConfig(
        pattern="UNAUTHORIZED_DM_ATTEMPT",
        alarm_threshold=5,
        description="Multiple unauthorized DM attempts detected",
    ),
    MonitoringConfig(
        pattern="GUARDRAIL_INTERVENED",
        alarm_threshold=10,
        description="High rate of guardrail interventions",
    ),
    MonitoringConfig(
        pattern="PROMPT_INJECTION_DETECTED",
        alarm_threshold=3,
        description="Prompt injection attempts detected",
    ),
]


class OscarSecurityMonitoringStack(Stack):
    """CloudWatch metric filters and alarms for OSCAR security events."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment: str,
        agents: Optional[List[Any]] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = environment

        self.alert_topic = sns.Topic(
            self, "OscarSecurityAlerts",
            topic_name=f"oscar-security-alerts-{environment}",
            display_name="OSCAR Security Monitoring Alerts",
        )

        # Core supervisor monitoring
        supervisor_log_group = logs.LogGroup.from_log_group_name(
            self, "SupervisorLogs",
            f"/aws/lambda/oscar-supervisor-agent-{environment}",
        )
        for config in CORE_MONITORING:
            self._create_filter_and_alarm("core", supervisor_log_group, config)

        # Agent-declared monitoring
        for agent in (agents or []):
            monitoring_configs = agent.get_monitoring_config()
            if not monitoring_configs:
                continue
            log_group = logs.LogGroup.from_log_group_name(
                self, f"{agent.name.title()}Logs",
                f"/aws/lambda/oscar-{agent.name}-{environment}",
            )
            for config in monitoring_configs:
                self._create_filter_and_alarm(agent.name, log_group, config)

    def _create_filter_and_alarm(
        self, source: str, log_group: logs.ILogGroup, config: MonitoringConfig
    ) -> None:
        """Create a metric filter and alarm from a MonitoringConfig."""
        metric_name = f"{source}-{config.pattern.replace(' ', '-')}"
        construct_prefix = f"{source.title()}{config.pattern.replace(' ', '').replace('_', '')}"

        logs.MetricFilter(
            self, f"{construct_prefix}Filter",
            log_group=log_group,
            filter_pattern=logs.FilterPattern.literal(config.pattern),
            metric_namespace="OSCAR/Security",
            metric_name=metric_name,
            metric_value="1",
        )

        alarm = cloudwatch.Alarm(
            self, f"{construct_prefix}Alarm",
            alarm_name=f"oscar-{source}-{config.pattern.replace(' ', '-').lower()}-{self.env_name}",
            alarm_description=config.description,
            metric=cloudwatch.Metric(
                namespace="OSCAR/Security",
                metric_name=metric_name,
                statistic=cloudwatch.Stats.SUM,
                period=Duration.minutes(config.period_minutes),
            ),
            threshold=config.alarm_threshold,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        alarm.add_alarm_action(cw_actions.SnsAction(self.alert_topic))
