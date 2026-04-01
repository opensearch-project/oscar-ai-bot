# Onboarding a New Agent to OSCAR

This guide walks through adding a new specialist agent to OSCAR. Before starting, read the [Developer Guide](DEVELOPER_GUIDE.md) for environment setup and deployment basics.

## What is an Agent?

An agent is a self-contained module that adds a new Bedrock collaborator agent to OSCAR. When registered, it automatically gets:
- An IAM Lambda execution role
- A Lambda function
- A Bedrock agent with action groups
- Wiring into the privileged and/or limited supervisor agents

## Prerequisites

- Working OSCAR development environment (see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md))
- AWS CDK CLI ≥ 2.1105.0 and `aws-cdk-lib==2.235.0`
- Python 3.12 with pipenv

## Step 1: Create the Agent Directory

Create your module under `agents/`:

```
agents/
└── new-agent/
    ├── __init__.py
    ├── agent.py
    ├── iam_policies.py
    ├── action_groups.py
    ├── instructions.py
    └── lambda/
        ├── lambda_function.py
        └── requirements.txt
```

## Step 2: Implement the Lambda Handler

Create `agents/new-agent/lambda/lambda_function.py` — the runtime code invoked by Bedrock:

```python
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    function_name = event.get('function', '')
    parameters = event.get('parameters', [])
    params = {p['name']: p['value'] for p in parameters}

    if function_name == 'my_function':
        result = handle_my_function(params)
    else:
        result = {'error': f'Unknown function: {function_name}'}

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get('actionGroup'),
            "function": function_name,
            "functionResponse": {
                "responseBody": {"TEXT": {"body": json.dumps(result)}}
            }
        }
    }
```

Add `requirements.txt` with any runtime dependencies. This project uses [`PythonFunction`](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_lambda_python_alpha/PythonFunction.html) which automatically bundles dependencies at synth time — just list them in `requirements.txt` and they will be installed into the Lambda package. You do not need to vendor or include the packages yourself.

```
# agents/new-agent/lambda/requirements.txt
requests==2.31.0
```

## Step 3: Define IAM Policies

Create `agents/new-agent/iam_policies.py` with the minimum permissions your Lambda needs:

```python
from typing import List
from aws_cdk import aws_iam as iam


def get_policies(account_id: str, region: str, env: str) -> List[iam.PolicyStatement]:
    return [
        iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=[f"arn:aws:secretsmanager:{region}:{account_id}:secret:oscar-central-env-{env}*"],
        ),
        # Add any additional permissions your Lambda needs
    ]
```

## Step 4: Define Action Groups

Create `agents/new-agent/action_groups.py` — this defines what functions the Bedrock agent can call:

```python
from typing import List
from aws_cdk import aws_bedrock as bedrock


def get_action_groups(lambda_arn: str) -> List[bedrock.CfnAgent.AgentActionGroupProperty]:
    return [
        bedrock.CfnAgent.AgentActionGroupProperty(
            action_group_name="newAgentActionGroup",
            description="Description of what this action group does",
            action_group_state="ENABLED",
            action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=lambda_arn),
            function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                functions=[
                    bedrock.CfnAgent.FunctionProperty(
                        name="my_function",
                        description="Description of what this function does",
                        parameters={
                            "version": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="OpenSearch version (e.g., '3.2.0')",
                                required=True,
                            )
                        },
                    )
                ]
            ),
        )
    ]
```

## Step 5: Write Agent Instructions

Create `agents/new-agent/instructions.py` — the system prompt for the Bedrock agent and the routing instruction for the supervisor:

```python
AGENT_INSTRUCTION = """You are a NewAgent Specialist for the OpenSearch project.
...
"""

COLLABORATOR_INSTRUCTION = (
    "This NewAgent-Specialist agent handles <domain>. "
    "Collaborate with this agent for <domain>-related queries."
)
```

## Step 6: Implement the Agent Class

Create `agents/new-agent/agent.py`:

```python
from agents.base_agent import OscarAgent, LambdaConfig
from agents.new_agent.action_groups import get_action_groups
from agents.new_agent.iam_policies import get_policies
from agents.new_agent.instructions import AGENT_INSTRUCTION, COLLABORATOR_INSTRUCTION


class NewAgent(OscarAgent):

    @property
    def name(self) -> str:
        return "new-agent"

    def get_lambda_config(self) -> LambdaConfig:
        return LambdaConfig(
            entry="agents/new-agent/lambda",
            timeout_seconds=60,
            memory_size=512,
            reserved_concurrency=10,
        )

    def get_iam_policies(self, account_id, region, env):
        return get_policies(account_id, region, env)

    def get_action_groups(self, lambda_arn):
        return get_action_groups(lambda_arn)

    def get_agent_instruction(self):
        return AGENT_INSTRUCTION

    def get_collaborator_instruction(self):
        return COLLABORATOR_INSTRUCTION

    def get_collaborator_name(self):
        return "NewAgent-Specialist"

    # Optional overrides:
    # def get_access_level(self): return "both"  # default is "limited"
    # def uses_knowledge_base(self): return False  # default is True
    # def get_managed_policies(self): return ["service-role/AWSLambdaBasicExecutionRole"]
```

Create `agents/new-agent/__init__.py`:

```python
from agents.new_agent.agent import NewAgent

__all__ = ["NewAgent"]
```

## Step 7: Register in `app.py`

Add your agent to the agents list in `app.py`:

```python
from agents.new_agent import NewAgent

agents = [
    JenkinsAgent(),
    MetricsAgent(),
    NewAgent(),  # <-- add here
]
```

That's the only file outside your agent directory you need to touch.

## Step 8: Verify

```bash
# Check for syntax/import errors
pipenv run python -c "from agents.new_agent import NewAgent; a = NewAgent(); print(a.name, a.get_access_level())"

# Lint
pipenv run flake8 agents/new-agent/

# Type check
pipenv run mypy agents/new-agent/

# Synthesize CDK (verify the new agent, Lambda, and IAM role appear)
pipenv run cdk synth
```

## Access Level Reference

| `get_access_level()` | Supervisor(s) that get this collaborator |
|---|---|
| `"limited"` (default) | Limited supervisor only |
| `"privileged"` | Privileged supervisor only |
| `"both"` | Both supervisors |

The **privileged supervisor** has access to Jenkins and messaging. The **limited supervisor** is read-only (metrics + knowledge base). New agents default to `"limited"` — override only if your agent needs privileged access.

## Shared Lambda (Advanced)

If your agent shares a Lambda with another agent (e.g., multiple agents sharing `agents/metrics/lambda/`), point `entry` to the shared path:

```python
def get_lambda_config(self):
    return LambdaConfig(entry="agents/metrics/lambda", ...)
```

The stack automatically deduplicates — only one Lambda is created for the shared entry path.
