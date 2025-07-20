# OSCAR Slack Bot PR Changes

This document outlines all the changes needed for the OSCAR Slack Bot PR based on feedback received.

## Critical Changes

- [ ] **Error Handling Improvements**
  - Replace stacktrace/detailed error descriptions with user-friendly error messages when retrieve and generate operations fail
  - Add emoji indicator for timeout situations (when bot doesn't respond within 60s)

- [ ] **Default Configuration Updates**
  - Change default model ARN to 3.5 haiku
  - Update default AWS region from `us-west-2` to `us-east-1`
  - Update context TTL from 48 hours (172800 seconds) to 7 days (604800 seconds)

- [ ] **Documentation Enhancement**
  - Add OSCAR documentation to the knowledge base to enable the bot to answer questions about OSCAR itself

- [ ] **Throttling Implementation**
  - Add throttling limits via API Gateway or appropriate service to prevent overuse

## Code Structure Changes

- [ ] **Directory Structure**
  - Simplify directory structure: remove nested `oscar/slack-bot/oscar` in favor of `oscar/slack-bot` directly

- [ ] **File Cleanup**
  - Remove `package.json` and `package-lock.json` since this is a Python codebase

- [ ] **Code Organization**
  - Extract common utilities into separate utility libraries
  - Move mock implementations from main code to test files

## Code Quality Improvements

- [ ] **Add to All Python Files**
  - Python shebang: `#!/usr/bin/env python`
  - SPDX License header:
    ```python
    # Copyright OpenSearch Contributors
    # SPDX-License-Identifier: Apache-2.0
    #
    # The OpenSearch Contributors require contributions made to
    # this file be licensed under the Apache-2.0 license or a
    # compatible open source license.
    ```

- [ ] **Function Definitions**
  - Add return type annotations to all function definitions

- [ ] **Import Statements**
  - Replace relative imports (e.g., `.config`) with absolute imports (e.g., `oscar.config`)
  - Move all imports to the top of files (e.g., fix the `import json` in bedrock.py)



## Code Refactoring

- [ ] **Bedrock Module**
  - Simplify conditional logic in `bedrock.py`:
    - Use `if not is_inference_profile` to avoid empty `pass` statement
    - Remove duplicate code in inference profile configuration

- [ ] **Config Module**
  - Add validation for required environment variables
  - Add appropriate defaults for optional environment variables
  - Remove Secret Manager code if environment variables are sufficient
  - Add TODO comment about potential improvements to deduplication solution

- [ ] **Test Scripts**
  - Update `run_tests.sh` to error out when dependencies are missing rather than installing them

## Documentation Updates

- [ ] **README.md**
  - Update title to "OpenSearch Conversational Automation for Releases (OSCAR) Slack Bot"
  - Clarify TTL mechanism description to avoid confusion between 1 hour and 7 days
  - Update file structure representation to use tree format
  - Format environment variables section similar to the automation-app repository
  - Remove detailed design decisions section from README
  - Add S3 to architecture diagram if it's used for knowledge base
  - Make READMEs more simple/don't delve into implementation detail as much

- [ ] **Socket App**
  - Evaluate if `socket_app.py` is still needed since it's described as legacy code

## Specific Code Changes

- [ ] **Config Module**
  - Update default region to `us-east-1`
  - Update context TTL to 7 days (604800 seconds)
  - Add note about future improvements for prompt templates (JSON/YAML configuration)
  - Remove Secret Manager code if environment variables are sufficient

- [ ] **Bedrock Module**
  - Fix conditional logic for inference profiles
  - Move mock implementation to test files

- [ ] **Slack Handler**
  - Add timeout handling with emoji indicator when bot doesn't respond within 60s

## Additional Notes

- The current TTL setup starts the countdown when a key is first created in DynamoDB
- Future improvement could include resetting the timer when the key is updated
- Consider allowing users to select default prompts through JSON or YAML configuration in the future