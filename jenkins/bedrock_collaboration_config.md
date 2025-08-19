# Jenkins Specialist Bedrock Collaboration Configuration

## For OSCAR Supervisor Agent Configuration

### Collaborator Agent Configuration:
```
Collaborator agent: JenkinsOperationsSpecialist
Alias: [Your Jenkins Agent Alias ID]
Instructions: This JenkinsOperationsSpecialist agent specializes in Jenkins job operations, build execution, and job parameter validation. It can execute Docker security scans, build jobs, release promotion pipelines, and provide comprehensive job information. Collaborate with this JenkinsOperationsSpecialist for all Jenkins-related operations and job execution requests.
Enable conversation history sharing: Enabled
```

### Integration Notes:
- The supervisor agent should route all Jenkins-related requests to this specialist
- The specialist handles technical execution while supervisor manages user confirmation
- Conversation history sharing ensures context is maintained across interactions
- The specialist provides job information, parameter validation, and execution capabilities

### Routing Keywords:
The supervisor should route to JenkinsOperationsSpecialist when users mention:
- Docker scan, security scan, vulnerability scan
- Jenkins job, build job, trigger job
- Release promotion, version promotion
- Pipeline central-release-promotion
- Any specific Jenkins job names