# Release Metrics Field Updates

## Overview
Updated the metrics Lambda function to handle all available fields from the `opensearch_release_metrics` index based on the provided JSON structure.

## Changes Made

### 1. Updated `query_release_readiness()` function
- **Added new fields to `_source` array:**
  - `id` - Unique identifier for the record
  - `release_version` - Specific release version (may differ from version)
  - `release_issue` - URL to the release issue
  - `release_owner_exists` - Boolean indicating if release owner is assigned
  - `autocut_issues_open` - Count of open autocut issues

### 2. Enhanced `extract_release_results()` function
- **Comprehensive field extraction:** Now extracts all available fields from the index
- **Enhanced readiness scoring:** 
  - Core checks (5 points): `release_issue_exists`, `release_notes`, `version_increment`, `release_branch`, `release_owner_exists`
  - Bonus points (1.5 points max): Clean state bonuses for no open issues, PRs, or autocut issues
  - Total possible score: 6.5 points
  - Readiness threshold: 4+ points (was 3+ previously)
- **Additional calculated fields:**
  - `readiness_percentage` - Percentage of maximum possible readiness score
  - `readiness_checks_passed` - Array of passed readiness checks
  - `has_open_issues`, `has_open_pulls`, `has_autocut_issues` - Quality indicators
  - `clean_state` - Boolean indicating no open issues, PRs, or autocut issues

### 3. Enhanced `generate_release_summary()` function
- **Additional summary metrics:**
  - Average readiness score and percentage
  - Component counts by quality indicators
  - Clean state percentage
  - Release state breakdown
  - Total counts for issues, PRs, and autocut issues

## New Fields Available in Results

### Core Identification
- `id` - Unique record identifier
- `component` - Component name
- `repository` - Repository name
- `version` - Version string
- `release_version` - Specific release version
- `timestamp` - Current date of the record

### Release State Information
- `release_state` - Current state (open/closed)
- `release_branch` - Boolean indicating release branch exists
- `release_issue_exists` - Boolean indicating release issue exists
- `release_issue` - URL to the release issue
- `release_notes` - Boolean indicating release notes exist
- `version_increment` - Boolean indicating version was incremented
- `release_owner_exists` - Boolean indicating release owner assigned
- `release_owners` - Array of release owner usernames

### Issue and PR Metrics
- `issues_open` - Count of open issues
- `issues_closed` - Count of closed issues
- `pulls_open` - Count of open pull requests
- `pulls_closed` - Count of closed pull requests
- `autocut_issues_open` - Count of open autocut issues

### Calculated Readiness Metrics
- `readiness_score` - Numerical readiness score (0-6.5)
- `readiness_checks_passed` - Array of passed readiness checks
- `is_ready` - Boolean indicating overall readiness (score >= 4)
- `readiness_percentage` - Percentage of maximum possible score

### Quality Indicators
- `has_open_issues` - Boolean indicating open issues exist
- `has_open_pulls` - Boolean indicating open PRs exist
- `has_autocut_issues` - Boolean indicating open autocut issues exist
- `clean_state` - Boolean indicating no open issues, PRs, or autocut issues

## Testing
Created `test_release_metrics_fields.py` to verify the updated functionality works correctly with the provided data structure. The test confirms:
- All expected fields are extracted properly
- Readiness scoring works as intended
- Enhanced metrics provide valuable insights

## Backward Compatibility
All existing field names and structures are maintained, with new fields added alongside. This ensures existing integrations continue to work while providing access to the enhanced data.