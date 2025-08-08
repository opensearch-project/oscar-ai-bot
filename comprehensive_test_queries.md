# OSCAR Comprehensive Test Queries

## Integration Test Agent Queries

### RC-Based Queries
```
@OSCAR Which components failed the integration tests for RC number 1 for version 3.2.0?
@OSCAR Show me integration test results for RC 2 and RC 3 for version 3.2.0
@OSCAR What OpenSearch components passed integration tests for RC 1 version 3.2.0?
@OSCAR Which OpenSearch-Dashboards components failed RC 1 for version 3.2.0?
```

### Build Number Queries
```
@OSCAR Which components failed integration tests for build number 11323 version 3.2.0?
@OSCAR Show me test results for build numbers 11323, 8585, and 9876 for version 3.2.0
@OSCAR What's the integration test status for build 11323?
```

### Component-Specific Queries
```
@OSCAR Show me OpenSearch integration test failures for version 3.2.0
@OSCAR What's the test status for OpenSearch-Dashboards components version 3.2.0?
@OSCAR Which knn and sql components failed integration tests for version 3.2.0?
```

### Platform/Architecture Queries
```
@OSCAR Show me ARM64 integration test failures for version 3.2.0
@OSCAR Which components failed on Windows platform for version 3.2.0?
@OSCAR What's the RPM distribution test status for version 3.2.0?
```

### General Queries
```
@OSCAR What's the overall integration test status for version 3.2.0?
@OSCAR Show me recent integration test failures
@OSCAR Give me integration test success rates for version 3.2.0
```

## Build Metrics Agent Queries

### Version-Based Queries
```
@OSCAR What's the build status for version 3.2.0?
@OSCAR Show me build failures for version 3.2.0
@OSCAR Give me build success rates for version 3.2.0
```

### Component Build Queries
```
@OSCAR What's the build status for OpenSearch components version 3.2.0?
@OSCAR Show me build failures for knn and sql repos
@OSCAR Which OpenSearch-Dashboards components have build issues?
```

### Build Number Queries
```
@OSCAR Show me build results for build numbers 11323 and 8585
@OSCAR What's the build status for build 11323?
@OSCAR Give me build details for recent build numbers
```

### Time-Based Queries
```
@OSCAR Show me build failures in the last 7 days
@OSCAR What's the build performance over the last 30 days?
@OSCAR Give me recent build trends
```

### General Build Queries
```
@OSCAR What's the current overall build status?
@OSCAR Show me all build failures
@OSCAR Give me build pipeline health summary
```

## Release Metrics Agent Queries

### Release Readiness Queries
```
@OSCAR What's the release readiness for version 3.2.0?
@OSCAR Show me release readiness scores for version 3.2.0
@OSCAR Which components are ready for release version 3.2.0?
@OSCAR What's blocking the release for version 3.2.0?
```

### Component Release Status
```
@OSCAR Show me OpenSearch release readiness for version 3.2.0
@OSCAR What's the release status for OpenSearch-Dashboards version 3.2.0?
@OSCAR Which components need attention for release 3.2.0?
```

### Release Owner Queries
```
@OSCAR Who are the release owners for version 3.2.0?
@OSCAR Show me release owners for OpenSearch components
@OSCAR Give me contact information for release coordination
```

### Release Issues Queries
```
@OSCAR Show me open release issues for version 3.2.0
@OSCAR What release blockers exist for version 3.2.0?
@OSCAR Give me release notes status for version 3.2.0
```

### General Release Queries
```
@OSCAR What's the overall release health for version 3.2.0?
@OSCAR Show me release pipeline status
@OSCAR Give me release readiness summary
```

## Cross-Agent Complex Queries

### Multi-Strategy Queries
```
@OSCAR Analyze integration test and build failures for version 3.2.0
@OSCAR Show me the complete pipeline health for version 3.2.0
@OSCAR Which components have both build and test issues?
```

### Executive Summary Queries
```
@OSCAR Give me an executive summary of version 3.2.0 readiness
@OSCAR What's the overall development pipeline health?
@OSCAR Show me critical issues blocking release 3.2.0
```

### Comparative Queries
```
@OSCAR Compare OpenSearch vs OpenSearch-Dashboards test results
@OSCAR Show me ARM64 vs x64 performance differences
@OSCAR Compare current vs previous release readiness
```

## Edge Case and Error Handling Tests

### Invalid Parameters
```
@OSCAR Show me results for version 99.99.99
@OSCAR What's the status for build number 999999?
@OSCAR Give me results for RC 999
```

### Missing Parameters
```
@OSCAR Show me integration test results
@OSCAR What's the build status?
@OSCAR Give me release readiness
```

### Ambiguous Queries
```
@OSCAR What's broken?
@OSCAR Show me failures
@OSCAR Give me status
```

## Knowledge Base Test Queries

### Build Commands
```
@OSCAR How can I build an x64 tarball?
@OSCAR What are the steps to build OpenSearch from source?
@OSCAR How do I set up the build environment?
```

### Configuration Questions
```
@OSCAR How do I configure OpenSearch for production?
@OSCAR What are the recommended JVM settings?
@OSCAR How do I set up cluster security?
```

### Troubleshooting
```
@OSCAR How do I debug build failures?
@OSCAR What should I do if integration tests fail?
@OSCAR How do I resolve dependency issues?
```