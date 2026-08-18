# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Response builder for GitHub agent Lambda."""

import json
from typing import Any, Dict


def create_response(event: Dict[str, Any], result: Any) -> Dict[str, Any]:
    """Create a Bedrock action group response."""
    body = json.dumps(result) if not isinstance(result, str) else result
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "function": event.get("function", ""),
            "functionResponse": {
                "responseBody": {
                    "TEXT": {"body": body}
                }
            },
        },
    }
