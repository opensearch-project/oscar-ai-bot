# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Base agent definition for OSCAR modules."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List

from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam

from utils.foundation_models import FoundationModels


@dataclass
class SecretConfig:
    """A secret that an agent needs created in AWS Secrets Manager.

    The full secret name is derived as: oscar-{agent.name}-{name_suffix}-{env}
    """
    name_suffix: str
    description: str
    env_var: str


@dataclass
class LambdaConfig:
    """Configuration for an agent's Lambda function."""
    entry: str
    index: str = "lambda_function.py"
    handler: str = "lambda_handler"
    timeout_seconds: int = 120
    memory_size: int = 512
    reserved_concurrency: int = 10
    environment_variables: Dict[str, str] = field(default_factory=dict)
    needs_vpc: bool = False


class OscarAgent(ABC):
    """Base class for all OSCAR agent modules.

    Each agent encapsulates everything needed for a Bedrock collaborator agent:
    IAM policies, Lambda config, action groups, and agent instructions.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique module name, e.g. 'jenkins', 'metrics'."""
        ...

    @abstractmethod
    def get_lambda_config(self) -> LambdaConfig:
        """Lambda function configuration."""
        ...

    @abstractmethod
    def get_iam_policies(self, account_id: str, region: str, env: str) -> List[iam.PolicyStatement]:
        """IAM policy statements for this module's Lambda role."""
        ...

    @abstractmethod
    def get_action_groups(self, lambda_arn: str) -> List[bedrock.CfnAgent.AgentActionGroupProperty]:
        """Bedrock action group definitions. Receives the Lambda ARN to wire up."""
        ...

    @abstractmethod
    def get_agent_instruction(self) -> str:
        """Bedrock agent instruction prompt."""
        ...

    @abstractmethod
    def get_collaborator_instruction(self) -> str:
        """Instruction the supervisor uses when routing to this collaborator."""
        ...

    @abstractmethod
    def get_collaborator_name(self) -> str:
        """Display name for the collaborator, e.g. 'Jenkins-Specialist'."""
        ...

    def get_access_level(self) -> str:
        """Which supervisor(s) get this collaborator: 'privileged', 'limited', or 'both'.
        Default: 'limited' (available to limited supervisor only).
        Override to 'privileged' for privileged-only or 'both' for both supervisors."""
        return "limited"

    def get_managed_policies(self) -> List[str]:
        """AWS managed policy names for the Lambda role."""
        return ["service-role/AWSLambdaBasicExecutionRole"]

    def uses_knowledge_base(self) -> bool:
        """Whether to attach the knowledge base to this agent."""
        return True

    def get_secrets(self) -> List[SecretConfig]:
        """Secrets this agent needs in AWS Secrets Manager.
        Override to declare agent-specific secrets. Default: none."""
        return []

    def get_foundation_model(self) -> str:
        """Foundation model ID."""
        return FoundationModels.CLAUDE_4_5_SONNET.value
