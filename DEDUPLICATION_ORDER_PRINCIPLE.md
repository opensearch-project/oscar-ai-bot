# Deduplication Order Principle

## Critical Rule: Always Deduplicate Before Filtering

### The Problem
When querying integration test results, we discovered a critical bug where filtering was applied **before** deduplication, leading to incorrect results:

**Buggy Flow:**
1. Query OpenSearch with `status_filter='failed'` → Get 20 failed results
2. Apply deduplication → Get 18 failed results  
3. Return 18 failed components ❌ **WRONG**

**Correct Flow:**
1. Query OpenSearch for ALL results → Get 377 total results
2. Apply deduplication → Get 336 deduplicated results
3. Filter for failed results → Get 4 failed components ✅ **CORRECT**

### Why This Matters
Integration test data contains multiple entries for the same component due to:
- Different build times/retries
- Historical data from previous runs
- Multiple test configurations

Deduplication keeps only the **most recent** result for each component/platform combination. If we filter before deduplication, we lose the recent passing results that should override older failing results.

### Implementation Rules

#### ✅ DO: Filter After Deduplication
```python
# 1. Get all raw results from OpenSearch
raw_results = query_opensearch(version, rc_number)

# 2. Apply deduplication first
deduplicated_results = deduplicate_integration_test_results(raw_results)

# 3. Then apply any filters
if status_filter:
    filtered_results = [r for r in deduplicated_results if r.get('status') == status_filter]
```

#### ❌ DON'T: Filter Before Deduplication
```python
# WRONG - This loses recent passing results
if status_filter:
    query_body["query"]["bool"]["must"].append({"match": {"status": status_filter}})
raw_results = query_opensearch(query_body)
deduplicated_results = deduplicate_integration_test_results(raw_results)
```

### Applied Fixes
1. **Removed OpenSearch-level status filtering** in `query_integration_test_results()`
2. **Kept post-deduplication filtering** in `handle_metrics_query()`
3. **Added fallback deduplication** for edge cases
4. **Enhanced logging** to track the deduplication process

### Testing
Always test both scenarios:
- **With status filter**: Should return only current failures (not historical)
- **Without status filter**: Should return all current results (deduplicated)

### Files Modified
- `metrics/lambda_function.py`: Removed OpenSearch-level status filtering
- Added comprehensive logging to track deduplication

### Verification
```bash
# Test that shows the difference
python test_status_filter_fix.py
```

This principle applies to **all metrics queries** - always deduplicate first, then filter.