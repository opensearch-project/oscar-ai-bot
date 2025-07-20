# Dependency Updates Summary

## Deployment Scripts

### deploy_lambda.sh
- Updated the script to copy individual Python files instead of the nested `oscar` directory
- Removed references to the old directory structure
- Updated verification checks to look for files in the new locations

### slack-bot/tests/run_tests.sh
- Updated the coverage command to use the current directory (`.`) instead of the `oscar` directory
- Added exclusion for the tests directory to avoid including test files in coverage reports

## Infrastructure as Code

### serverless.yml
- Updated the DynamoDB table structure to use `event_id` as the partition key for the sessions table instead of `session_key` to match the new code

### cdk/stacks/storage_stack.py
- Updated the DynamoDB table structure to use `event_id` as the partition key for the sessions table instead of `session_key` to match the new code

## Other Changes

- Removed the nested `oscar` directory and moved all files directly into the `slack-bot` directory
- Updated import statements in all files to use the new directory structure
- Moved the `MockKnowledgeBase` implementation from `bedrock.py` to `tests/test_bedrock.py`
- Updated references to the mock implementation in test files

These changes ensure that all dependencies are properly updated to work with the new directory structure and code organization.