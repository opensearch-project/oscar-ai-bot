# Onboarding a New Plugin to OSCAR

This guide walks through adding a new specialist agent (plugin) to OSCAR. Before starting, read the [Developer Guide](DEVELOPER_GUIDE.md) for environment setup and deployment basics.

## What is a Plugin?

A plugin is a self-contained module that adds a new Bedrock collaborator agent to OSCAR. When registered, it automatically gets:
- An IAM Lambda execution role
- A Lambda function
- A Bedrock agent with action groups
- Wiring into the privileged and/or limited supervisor agents

## Prerequisites

- Working OSCAR development environment (see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md))
- AWS CDK CLI ≥ 2.1105.0 and `aws-cdk-lib==2.235.0`
- Python 3.12 with pipenv

## Step 1: Create the Plugin Directory

Create your module under `plugins/`:

```
plugins/
└── new-plugin/
    ├── __init__.py
    ├── plugin.py
    ├── iam_policies.py
    ├── action_groups.py
    ├── instructions.py
    └── lambda/
        ├── lambda_function.py
        └── requirements.txt
```

## Step 2: Implement the Lambda Handler

Create `plugins/new-plugin/lambda/lambda_function.py` — the runtime code invoked by Bedrock:

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
# plugins/new-plugin/lambda/requirements.txt
requests==2.31.0
```

## Step 3: Define IAM Policies

Create `plugins/new-plugin/iam_policies.py` with the minimum permissions your Lambda needs:

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

Create `plugins/new-plugin/action_groups.py` — this defines what functions the Bedrock agent can call:

```python
from typing import List
from aws_cdk import aws_bedrock as bedrock


def get_action_groups(lambda_arn: str) -> List[bedrock.CfnAgent.AgentActionGroupProperty]:
    return [
        bedrock.CfnAgent.AgentActionGroupProperty(
            action_group_name="newPluginActionGroup",
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

Create `plugins/new-plugin/instructions.py` — the system prompt for the Bedrock agent and the routing instruction for the supervisor:

```python
AGENT_INSTRUCTION = """You are a NewPlugin Specialist for the OpenSearch project.
...
"""

COLLABORATOR_INSTRUCTION = (
    "This NewPlugin-Specialist agent handles <domain>. "
    "Collaborate with this agent for <domain>-related queries."
)
```

## Step 6: Implement the Plugin Class

Create `plugins/new-plugin/plugin.py`:

```python
from plugins.base_plugin import OscarPlugin, LambdaConfig
from plugins.new_plugin.action_groups import get_action_groups
from plugins.new_plugin.iam_policies import get_policies
from plugins.new_plugin.instructions import AGENT_INSTRUCTION, COLLABORATOR_INSTRUCTION


class NewPlugin(OscarPlugin):

    @property
    def name(self) -> str:
        return "new-plugin"

    def get_lambda_config(self) -> LambdaConfig:
        return LambdaConfig(
            entry="plugins/new-plugin/lambda",
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
        return "NewPlugin-Specialist"

    # Optional overrides:
    # def get_access_level(self): return "both"  # default is "limited"
    # def uses_knowledge_base(self): return False  # default is True
    # def get_managed_policies(self): return ["service-role/AWSLambdaBasicExecutionRole"]
```

Create `plugins/new-plugin/__init__.py`:

```python
from plugins.new_plugin.plugin import NewPlugin

__all__ = ["NewPlugin"]
```

## Step 7: Register in `app.py`

Add your plugin to the plugins list in `app.py`:

```python
from plugins.new_plugin import NewPlugin

plugins = [
    JenkinsPlugin(),
    MetricsBuildPlugin(),
    MetricsTestPlugin(),
    MetricsReleasePlugin(),
    NewPlugin(),  # <-- add here
]
```

That's the only file outside your plugin directory you need to touch.

## Step 8: Verify

```bash
# Check for syntax/import errors
pipenv run python -c "from plugins.new_plugin import NewPlugin; p = NewPlugin(); print(p.name, p.get_access_level())"

# Lint
pipenv run flake8 plugins/new-plugin/

# Type check
pipenv run mypy plugins/new-plugin/

# Synthesize CDK (verify the new agent, Lambda, and IAM role appear)
pipenv run cdk synth
```

## Access Level Reference

| `get_access_level()` | Supervisor(s) that get this collaborator |
|---|---|
| `"limited"` (default) | Limited supervisor only |
| `"privileged"` | Privileged supervisor only |
| `"both"` | Both supervisors |

The **privileged supervisor** has access to Jenkins and messaging. The **limited supervisor** is read-only (metrics + knowledge base). New plugins default to `"limited"` — override only if your plugin needs privileged access.

## Shared Lambda (Advanced)

If your plugin shares a Lambda with another plugin (like the 3 metrics sub-plugins share `plugins/metrics/lambda/`), point `entry` to the shared path:

```python
def get_lambda_config(self):
    return LambdaConfig(entry="plugins/metrics/lambda", ...)
```

The stack automatically deduplicates — only one Lambda is created for the shared entry path.
