# OSCAR Multi-Agent System - Manual Configuration Guide

## 📋 Prerequisites

Before configuring the agents, ensure you have:

### 1. Lambda Functions Deployed
Deploy your metrics Lambda functions in us-east-1 with VPC deployment for secure OpenSearch connectivity:

**All configuration is now loaded from your `.env` file automatically!**

```bash
# Deploy the Lambda functions within VPC for OpenSearch connectivity
./deploy_vpc_lambdas.sh
```

**Important Architecture Notes**: 
- Lambda functions are deployed **within your VPC** for secure OpenSearch access
- OpenSearch access is via VPC endpoint for cross-account connectivity
- All 6 subnets across availability zones are configured for high availability
- Security groups properly configured for VPC endpoint access

### 2. Get Lambda Function ARNs
After deployment, get the ARNs for your Lambda functions:

```bash
# Get the ARNs (you'll need these for agent configuration)
aws lambda get-function --function-name oscar-test-metrics-agent --region us-east-1 --query 'Configuration.FunctionArn'
aws lambda get-function --function-name oscar-build-metrics-agent --region us-east-1 --query 'Configuration.FunctionArn'
aws lambda get-function --function-name oscar-release-metrics-agent --region us-east-1 --query 'Configuration.FunctionArn'
aws lambda get-function --function-name oscar-deployment-metrics-agent --region us-east-1 --query 'Configuration.FunctionArn'
```

### 3. Test VPC Deployment and Connectivity
Verify your Lambda functions are properly deployed within the VPC and can execute:

```bash
# Test VPC deployment and connectivity
./test_vpc_deployment.sh

# Quick connectivity test
./test_vpc_connectivity.sh
```

### 4. Knowledge Base Information
- ✅ S3 Bucket: Already created
- ✅ Knowledge Base: Already created
- 📝 Note the Knowledge Base ID from the AWS Console

### 5. VPC Endpoint Configuration
- ✅ VPC Endpoint: Created in AWS Console under OpenSearch Service
- ✅ Cross-Account Access: Configured for metrics cluster access
- 📝 The VPC endpoint enables secure connectivity from your Lambda functions to the metrics cluster in the other AWS account

---

## 🤖 Agent Configuration Steps

### Step 1: Test Metrics Agent

**Navigate to**: AWS Console → Amazon Bedrock → Agents → Create Agent

#### Basic Information
- **Agent Name**: `test-metrics-agent`
- **Description**: `Specialized agent for analyzing test execution metrics, test coverage, and quality trends`
- **Foundation Model**: `Claude 3.5 Sonnet v2`

#### Agent Instructions
```
You are a specialized Test Metrics Agent focused on analyzing software testing data and quality metrics.

Your primary responsibilities:
1. Analyze test execution results, pass/fail rates, and test duration trends
2. Evaluate test coverage metrics across different code components
3. Identify patterns in test failures and flaky tests
4. Provide insights on testing efficiency and quality improvements
5. Generate reports on testing performance over time

When analyzing test metrics:
- Focus on test execution trends, coverage percentages, and failure patterns
- Identify areas with low test coverage or high failure rates
- Suggest improvements for test reliability and efficiency
- Correlate test results with code changes and deployment cycles

Always provide specific, actionable insights based on the test data available.
```

#### Action Groups Configuration
1. **Action Group Name**: `test-metrics-actions`
2. **Description**: `Actions for retrieving and analyzing test metrics`
3. **Action Group Type**: `Define with function details`
4. **Lambda Function**: `[Your test-metrics-function ARN from prerequisites]`

#### Function Details - Complete JSON Configuration
Copy and paste this complete JSON configuration for the action group function:

```json
{
  "name": "get_test_metrics",
  "description": "Retrieve test execution metrics and coverage data",
  "parameters": {
    "metric_type": {
      "type": "string",
      "description": "Type of test metric (execution, coverage, trends)",
      "required": true
    },
    "time_range": {
      "type": "string", 
      "description": "Time range for metrics (1d, 7d, 30d)",
      "required": false
    },
    "project_filter": {
      "type": "string",
      "description": "Filter by specific project or component",
      "required": false
    }
  },
  "requireConfirmation": "DISABLED"
}
```

---

### Step 2: Build Metrics Agent

#### Basic Information
- **Agent Name**: `build-metrics-agent`
- **Description**: `Specialized agent for analyzing build performance, success rates, and CI/CD pipeline metrics`
- **Foundation Model**: `Claude 3.5 Sonnet v2`

#### Agent Instructions
```
You are a specialized Build Metrics Agent focused on analyzing software build and CI/CD pipeline performance.

Your primary responsibilities:
1. Analyze build success rates, failure patterns, and build duration trends
2. Monitor CI/CD pipeline performance and bottlenecks
3. Evaluate build efficiency and resource utilization
4. Identify patterns in build failures and suggest optimizations
5. Track build performance across different branches and environments

When analyzing build metrics:
- Focus on build times, success rates, and failure root causes
- Identify slow or unreliable build steps
- Suggest optimizations for build performance and reliability
- Correlate build performance with code changes and team activities

Always provide specific recommendations for improving build efficiency and reliability.
```

#### Action Groups Configuration
1. **Action Group Name**: `build-metrics-actions`
2. **Description**: `Actions for retrieving and analyzing build metrics`
3. **Action Group Type**: `Define with function details`
4. **Lambda Function**: `[Your build-metrics-function ARN from prerequisites]`

#### Function Details - Complete JSON Configuration
Copy and paste this complete JSON configuration for the action group function:

```json
{
  "name": "get_build_metrics",
  "description": "Retrieve build performance and CI/CD pipeline metrics",
  "parameters": {
    "metric_type": {
      "type": "string",
      "description": "Type of build metric (performance, success_rate, pipeline)",
      "required": true
    },
    "time_range": {
      "type": "string",
      "description": "Time range for metrics (1d, 7d, 30d)", 
      "required": false
    },
    "branch_filter": {
      "type": "string",
      "description": "Filter by specific branch or environment",
      "required": false
    }
  },
  "requireConfirmation": "DISABLED"
}
```

---

### Step 3: Release Metrics Agent

#### Basic Information
- **Agent Name**: `release-metrics-agent`
- **Description**: `Specialized agent for analyzing release frequency, deployment success, and release quality metrics`
- **Foundation Model**: `Claude 3.5 Sonnet v2`

#### Agent Instructions
```
You are a specialized Release Metrics Agent focused on analyzing software release and deployment performance.

Your primary responsibilities:
1. Track release frequency, lead times, and deployment success rates
2. Analyze release quality metrics and post-deployment issues
3. Monitor rollback rates and deployment stability
4. Evaluate release process efficiency and bottlenecks
5. Provide insights on release planning and risk assessment

When analyzing release metrics:
- Focus on deployment success rates, rollback frequency, and release velocity
- Identify patterns in release failures and their impact
- Suggest improvements for release reliability and speed
- Correlate release performance with team practices and process changes

Always provide actionable insights for improving release processes and reducing deployment risks.
```

#### Action Groups Configuration
1. **Action Group Name**: `release-metrics-actions`
2. **Description**: `Actions for retrieving and analyzing release metrics`
3. **Action Group Type**: `Define with function details`
4. **Lambda Function**: `[Your release-metrics-function ARN from prerequisites]`

#### Function Details - Complete JSON Configuration
Copy and paste this complete JSON configuration for the action group function:

```json
{
  "name": "get_release_metrics",
  "description": "Retrieve release and deployment performance metrics",
  "parameters": {
    "metric_type": {
      "type": "string",
      "description": "Type of release metric (frequency, success_rate, quality)",
      "required": true
    },
    "time_range": {
      "type": "string",
      "description": "Time range for metrics (1d, 7d, 30d)",
      "required": false
    },
    "environment_filter": {
      "type": "string", 
      "description": "Filter by deployment environment (prod, staging, dev)",
      "required": false
    }
  },
  "requireConfirmation": "DISABLED"
}
```

---

### Step 4: Deployment Metrics Agent

#### Basic Information
- **Agent Name**: `deployment-metrics-agent`
- **Description**: `Specialized agent for analyzing deployment performance, infrastructure metrics, and operational health`
- **Foundation Model**: `Claude 3.5 Sonnet v2`

#### Agent Instructions
```
You are a specialized Deployment Metrics Agent focused on analyzing deployment performance and infrastructure health.

Your primary responsibilities:
1. Monitor deployment duration, success rates, and infrastructure performance
2. Analyze system health metrics during and after deployments
3. Track resource utilization and scaling patterns
4. Identify deployment bottlenecks and infrastructure issues
5. Provide insights on operational efficiency and system reliability

When analyzing deployment metrics:
- Focus on deployment times, system performance, and resource usage
- Identify infrastructure bottlenecks and scaling issues
- Suggest optimizations for deployment speed and system reliability
- Correlate deployment performance with infrastructure changes and load patterns

Always provide specific recommendations for improving deployment efficiency and system stability.
```

#### Action Groups Configuration
1. **Action Group Name**: `deployment-metrics-actions`
2. **Description**: `Actions for retrieving and analyzing deployment metrics`
3. **Action Group Type**: `Define with function details`
4. **Lambda Function**: `[Your deployment-metrics-function ARN from prerequisites]`

#### Function Details - Complete JSON Configuration
Copy and paste this complete JSON configuration for the action group function:

```json
{
  "name": "get_deployment_metrics",
  "description": "Retrieve deployment and infrastructure performance metrics",
  "parameters": {
    "metric_type": {
      "type": "string",
      "description": "Type of deployment metric (performance, infrastructure, health)",
      "required": true
    },
    "time_range": {
      "type": "string",
      "description": "Time range for metrics (1d, 7d, 30d)",
      "required": false
    },
    "service_filter": {
      "type": "string",
      "description": "Filter by specific service or component",
      "required": false
    }
  },
  "requireConfirmation": "DISABLED"
}
```

---

### Step 5: OSCAR Supervisor Agent (Main Agent)

#### Basic Information
- **Agent Name**: `oscar-supervisor-agent`
- **Description**: `Enhanced supervisor agent with integrated knowledge base access and metrics coordination capabilities`
- **Foundation Model**: `Claude 3.5 Sonnet v2`

#### Agent Instructions
```
You are OSCAR (Operational Software Continuous Analysis & Reporting), a comprehensive AI assistant for OpenSearch project management and software development insights.

Your enhanced capabilities include:

**Integrated Knowledge Base Access:**
- Answer questions about OpenSearch documentation, configuration, and best practices
- Provide guidance on installation, setup, and troubleshooting
- Explain OpenSearch features, APIs, and development practices
- Reference official documentation and community knowledge
- Handle static information queries directly through your knowledge base

**Advanced Metrics Coordination:**
- Coordinate with specialized metrics agents for real-time data analysis
- Synthesize insights from multiple metrics domains into cohesive reports
- Identify cross-functional patterns and correlations between different metrics
- Provide strategic recommendations based on holistic analysis
- Handle dynamic data queries through collaborator agent coordination

**Available Collaborator Agents:**
- Test Metrics Agent: Analyzes test execution, coverage, and quality metrics
- Build Metrics Agent: Analyzes build performance and CI/CD pipeline metrics  
- Release Metrics Agent: Analyzes release frequency and deployment success metrics
- Deployment Metrics Agent: Analyzes deployment performance and infrastructure metrics

**Enhanced Query Handling:**
1. **Documentation Queries**: Use integrated knowledge base for OpenSearch documentation, configuration guides, best practices, and troubleshooting
2. **Metrics Queries**: Collaborate with specialized agents for current performance data and analysis
3. **Hybrid Queries**: Seamlessly combine knowledge base information with real-time metrics for comprehensive responses
4. **Complex Analysis**: Synthesize findings from multiple sources into cohesive, actionable insights

**Response Guidelines:**
- Provide accurate, helpful responses whether drawing from documentation or real-time metrics
- When combining knowledge base and metrics data, clearly distinguish between static information and current data
- For metrics queries, provide specific numbers, trends, and actionable insights
- For documentation queries, reference specific configuration steps and best practices
- Always aim for comprehensive yet concise responses that directly address the user's question
```

#### Action Groups Configuration

**Enhanced Lambda Function Integration**
1. **Action Group Name**: `oscar-enhanced-actions`
2. **Description**: `Enhanced OSCAR actions with integrated knowledge base and metrics coordination`
3. **Action Group Type**: `Define with function details`
4. **Lambda Function**: `arn:aws:lambda:us-east-1:395380602281:function:oscar-supervisor-agent`

**Function Details - Complete JSON Configuration:**
```json
{
  "name": "process_oscar_query",
  "description": "Process comprehensive OSCAR queries with integrated knowledge base and metrics coordination",
  "parameters": {
    "query": {
      "type": "string",
      "description": "User query for OpenSearch documentation, metrics analysis, or hybrid requests",
      "required": true
    },
    "query_type": {
      "type": "string",
      "description": "Type of query: knowledge, metrics, hybrid, or auto (for automatic detection)",
      "required": false
    },
    "context": {
      "type": "string",
      "description": "Additional context or conversation history for better responses",
      "required": false
    }
  },
  "requireConfirmation": "DISABLED"
}
```

#### Enhanced Lambda Function Features

The `oscar-supervisor-agent` Lambda function provides:

**🧠 Intelligent Query Routing:**
- Automatic detection of query type (knowledge vs metrics vs hybrid)
- Smart routing to appropriate data sources
- Context-aware response generation

**📚 Knowledge Base Integration:**
- Direct access to OpenSearch documentation
- Configuration guides and best practices
- Troubleshooting and how-to information

**📊 Metrics Coordination:**
- Seamless integration with specialized metrics agents
- Cross-domain analysis and correlation
- Real-time data synthesis

**💾 Session Management:**
- DynamoDB-backed conversation context
- Session persistence across interactions
- Context summarization for long conversations

**🔄 Slack Integration:**
- Proper reaction management (thinking, success, error indicators)
- Threaded conversation support
- Asynchronous processing for better performance

#### Agent Collaborators Configuration
Add each of the 4 specialized agents as collaborators with the following detailed configuration:

**Collaborator 1: Test Metrics Agent**
- **Agent collaborator**: `test-metrics-agent`
- **Agent alias**: `initial-dev` (or your configured alias)
- **Collaborator name**: `TestAnalyzer`
- **Collaboration instruction**:
```
TestAnalyzer specializes in analyzing software testing data and quality metrics. Collaborate with TestAnalyzer when users ask about test execution results, test coverage analysis, failure patterns, or testing performance trends. TestAnalyzer can provide insights on test pass/fail rates, identify top failing test classes, analyze test execution trends over time, and recommend improvements for test reliability and efficiency. Use TestAnalyzer for queries involving test metrics, quality assurance data, or testing performance analysis across different repositories and time ranges.
```
- **Enable conversation history sharing**: ✅ Enabled

**Collaborator 2: Build Metrics Agent**
- **Agent collaborator**: `build-metrics-agent`
- **Agent alias**: `initial-dev` (or your configured alias)
- **Collaborator name**: `BuildAnalyzer`
- **Collaboration instruction**:
```
BuildAnalyzer specializes in analyzing build performance and CI/CD pipeline metrics. Collaborate with BuildAnalyzer when users ask about build success rates, build duration trends, pipeline bottlenecks, or development workflow efficiency. BuildAnalyzer can provide insights on build performance across different branches, identify slow or unreliable build steps, analyze build failure patterns, and recommend optimizations for build speed and reliability. Use BuildAnalyzer for queries involving build metrics, CI/CD pipeline analysis, or development workflow performance.
```
- **Enable conversation history sharing**: ✅ Enabled

**Collaborator 3: Release Metrics Agent**
- **Agent collaborator**: `release-metrics-agent`
- **Agent alias**: `initial-dev` (or your configured alias)
- **Collaborator name**: `ReleaseAnalyzer`
- **Collaboration instruction**:
```
ReleaseAnalyzer specializes in analyzing release frequency, deployment success, and release quality metrics. Collaborate with ReleaseAnalyzer when users ask about release readiness, version tracking, deployment success rates, or release planning insights. ReleaseAnalyzer can provide insights on component readiness across different versions, track release preparation status, analyze deployment patterns, and recommend improvements for release reliability and speed. Use ReleaseAnalyzer for queries involving release metrics, deployment planning, or version management analysis.
```
- **Enable conversation history sharing**: ✅ Enabled

**Collaborator 4: Deployment Metrics Agent**
- **Agent collaborator**: `deployment-metrics-agent`
- **Agent alias**: `initial-dev` (or your configured alias)
- **Collaborator name**: `DeploymentAnalyzer`
- **Collaboration instruction**:
```
DeploymentAnalyzer specializes in analyzing deployment performance, infrastructure health, and operational metrics. Collaborate with DeploymentAnalyzer when users ask about deployment success rates, infrastructure performance, system health during deployments, or operational efficiency. DeploymentAnalyzer can provide insights on deployment duration, resource utilization, scaling patterns, infrastructure bottlenecks, and recommend optimizations for deployment speed and system reliability. Use DeploymentAnalyzer for queries involving deployment metrics, infrastructure analysis, or operational performance monitoring.
```
- **Enable conversation history sharing**: ✅ Enabled

#### Knowledge Base Configuration
- **Knowledge Base**: `NBRUVWHAYY` (from your .env file)
- **Description**: `OpenSearch documentation, configuration guides, and best practices`

**Knowledge Base Instructions:**
```
Use the knowledge base to answer questions about:
- OpenSearch installation and configuration
- API documentation and usage examples
- Troubleshooting guides and common issues
- Best practices for deployment and optimization
- Feature explanations and tutorials

When a user asks about static information, documentation, or how-to questions, search the knowledge base first before considering metrics data.
```

---

## 🧪 Testing Your Configuration

### Individual Agent Tests

**Test Metrics Agent**:
```
"Show me test coverage trends for the last 30 days"
```

**Build Metrics Agent**:
```  
"Analyze build performance and identify bottlenecks in our CI/CD pipeline"
```

**Release Metrics Agent**:
```
"What's our deployment success rate and how often do we need rollbacks?"
```

**Deployment Metrics Agent**:
```
"Show me infrastructure performance during recent deployments"
```

### Multi-Agent Collaboration Tests

**OSCAR Supervisor Agent**:
```
"Provide a comprehensive analysis of our software development performance across all metrics"
```

```
"How do our test failures correlate with build issues and deployment problems?"
```

```
"Generate an executive summary of our development team's performance this month"
```

### Knowledge Base Integration Tests

**Pure Knowledge Base Queries**:
```
"How do I configure OpenSearch security?"
"What are the best practices for OpenSearch indexing?"
"How do I troubleshoot OpenSearch cluster connectivity issues?"
"What's the difference between OpenSearch and Elasticsearch?"
```

**Hybrid Knowledge + Metrics Queries**:
```
"Based on industry best practices, how do our current test metrics compare and what improvements should we prioritize?"
"Show me our current build performance and recommend optimizations based on OpenSearch best practices"
"What does our deployment health indicate about our system, and what does the documentation recommend for improvement?"
```

---

## ✅ Validation Checklist

- [ ] All 5 agents created successfully
- [ ] Lambda function ARNs configured correctly
- [ ] Action groups and functions defined properly
- [ ] Collaborator relationships established
- [ ] Knowledge base connected to supervisor agent
- [ ] Individual agent tests pass
- [ ] Multi-agent collaboration works
- [ ] Knowledge base integration functional

---

## 🚀 Next Steps

### Phase 1: Deploy Infrastructure
1. **✅ Deploy Metrics Lambda Functions** - Already completed with VPC deployment
2. **� Deeploy Enhanced Supervisor Agent**:
   ```bash
   ./deploy_oscar_supervisor.sh
   ```

### Phase 2: Configure Bedrock Agents
3. **🔧 Create specialized metrics agents** following steps 1-4 above
4. **🎯 Create enhanced supervisor agent** following step 5 above
5. **🔗 Configure collaborator relationships** between supervisor and specialized agents

### Phase 3: Testing & Validation
6. **🧪 Test individual agents** to ensure they work correctly
7. **🔗 Test multi-agent collaboration** through the supervisor agent
8. **📚 Validate knowledge base integration** for documentation queries
9. **📊 Test metrics coordination** for real-time data analysis

**Estimated Configuration Time**: ~60 minutes (12 minutes per agent + supervisor setup)

---

## 🔧 VPC Deployment Architecture

Your Lambda functions are now deployed within your VPC for secure OpenSearch access:

### VPC Configuration
- **VPC ID**: `vpc-0f2061a1321c2d669`
- **Subnets**: 6 subnets across all availability zones (us-east-1a through us-east-1f)
- **Security Group**: `sg-0e18a7fad124327c5` configured for VPC endpoint access
- **OpenSearch Access**: Via VPC endpoint for cross-account connectivity

### Security Benefits
- Lambda functions isolated within your VPC
- Direct, secure connectivity to OpenSearch cluster
- No internet access required for OpenSearch queries
- Cross-account access handled through VPC endpoint configuration

### Troubleshooting VPC Connectivity
If you encounter connectivity issues:

1. **Test VPC Deployment**: Run `./test_vpc_deployment.sh` for comprehensive testing
2. **Quick Connectivity Test**: Run `./test_vpc_connectivity.sh` for basic validation
3. **Check Security Groups**: Ensure Lambda security group allows HTTPS outbound (port 443)
4. **Verify VPC Endpoint**: Ensure it's properly configured for your OpenSearch domain
5. **IAM Permissions**: Ensure Lambda execution role has OpenSearch access permissions

### Cleanup and Redeployment
If you need to redeploy the Lambda functions:

```bash
# Clean up existing functions
./destroy_lambda_functions.sh

# Redeploy with VPC configuration
./deploy_vpc_lambdas.sh
```

**Estimated Configuration Time**: ~45 minutes (9 minutes per agent)