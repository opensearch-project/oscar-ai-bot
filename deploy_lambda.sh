#!/bin/bash

# Exit on error
set -e

echo "=== Updating OSCAR Slack Bot Lambda Function ==="

# Get AWS region from environment or use default
AWS_REGION=${AWS_REGION:-us-west-2}
echo "Using AWS Region: $AWS_REGION"

# Create a temporary directory for the Lambda package
echo "Creating Lambda deployment package..."
mkdir -p lambda_package

# Copy the app.py file and other Python modules
echo "Copying application files..."
cp slack-bot/app.py lambda_package/
cp slack-bot/__init__.py lambda_package/
cp slack-bot/bedrock.py lambda_package/
cp slack-bot/config.py lambda_package/
cp slack-bot/slack_handler.py lambda_package/
cp slack-bot/storage.py lambda_package/

# Verify package structure
if [ ! -f "lambda_package/app.py" ] || [ ! -f "lambda_package/config.py" ]; then
    echo "Error: Application files are missing or incomplete!"
    echo "Please ensure the slack-bot directory contains all required modules."
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
pip install -r slack-bot/requirements.txt -t lambda_package/ --force-reinstall

# Create the zip file
echo "Creating zip file..."
cd lambda_package
zip -r ../lambda_package.zip .
cd ..

# Get Lambda function name from environment or use default
LAMBDA_FUNCTION_NAME=${LAMBDA_FUNCTION_NAME:-oscar-slack-bot}
echo "Updating Lambda function: $LAMBDA_FUNCTION_NAME"

# Update the Lambda function
echo "Updating Lambda function code..."
aws lambda update-function-code \
  --function-name $LAMBDA_FUNCTION_NAME \
  --zip-file fileb://lambda_package.zip \
  --region $AWS_REGION

# Verify Lambda update was successful
if [ $? -eq 0 ]; then
    echo "Lambda function code updated successfully!"
else
    echo "Error: Failed to update Lambda function code!"
    exit 1
fi

# Update Lambda environment variables if ENABLE_DM is set
if [ ! -z "$ENABLE_DM" ]; then
    echo "Setting ENABLE_DM environment variable to: $ENABLE_DM"
    
    # Get current environment variables
    ENV_VARS=$(aws lambda get-function-configuration \
        --function-name $LAMBDA_FUNCTION_NAME \
        --region $AWS_REGION \
        --query "Environment.Variables" \
        --output json)
    
    # If there are existing environment variables, update them
    if [ "$ENV_VARS" != "null" ]; then
        # Get current environment variables and add ENABLE_DM
        # Create a temporary file for the environment variables
        echo "{" > env_vars.json
        
        # Process each existing environment variable
        echo "$ENV_VARS" | jq -r 'to_entries | .[] | "\(.key)=\(.value)"' | while read -r line; do
            key=$(echo "$line" | cut -d= -f1)
            value=$(echo "$line" | cut -d= -f2-)
            
            # Skip ENABLE_DM if it already exists
            if [ "$key" != "ENABLE_DM" ]; then
                echo "\"$key\": \"$value\"," >> env_vars.json
            fi
        done
        
        # Add the ENABLE_DM variable
        echo "\"ENABLE_DM\": \"$ENABLE_DM\"" >> env_vars.json
        echo "}" >> env_vars.json
        
        # Format the JSON properly
        cat env_vars.json | jq '.' > env_vars_formatted.json
        
        # Update Lambda configuration with new environment variables
        # Convert the JSON to a compact format and escape it properly
        ENV_JSON=$(cat env_vars_formatted.json | jq -c '.')
        
        aws lambda update-function-configuration \
            --function-name $LAMBDA_FUNCTION_NAME \
            --region $AWS_REGION \
            --environment "{\"Variables\":$ENV_JSON}"
        
        # Clean up temporary files
        rm env_vars.json env_vars_formatted.json
    else
        # If no existing environment variables, create new ones
        aws lambda update-function-configuration \
            --function-name $LAMBDA_FUNCTION_NAME \
            --region $AWS_REGION \
            --environment "Variables={\"ENABLE_DM\":\"$ENABLE_DM\"}"
    fi
    
    echo "Lambda environment variables updated successfully!"
fi

# Clean up
echo "Cleaning up..."
rm -rf lambda_package
rm lambda_package.zip

echo "Lambda deployment completed successfully!"