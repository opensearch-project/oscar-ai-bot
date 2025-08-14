#!/usr/bin/env python3
"""
Test that status_filter now works correctly after the fix.
"""

import json

def simulate_old_behavior(raw_results, status_filter=None):
    """Simulate the old buggy behavior - filter at OpenSearch level before deduplication."""
    print("=== OLD BUGGY BEHAVIOR ===")
    
    # Step 1: Filter at "OpenSearch level" (before deduplication)
    if status_filter:
        filtered_results = [r for r in raw_results if r.get('component_build_result') == status_filter]
        print(f"After OpenSearch filtering for '{status_filter}': {len(filtered_results)} results")
    else:
        filtered_results = raw_results
        print(f"No OpenSearch filtering: {len(filtered_results)} results")
    
    # Step 2: Apply deduplication to filtered results
    deduplicated = deduplicate_integration_test_results(filtered_results)
    print(f"After deduplication: {len(deduplicated)} results")
    
    return deduplicated

def simulate_new_behavior(raw_results, status_filter=None):
    """Simulate the new correct behavior - deduplicate first, then filter."""
    print("=== NEW CORRECT BEHAVIOR ===")
    
    # Step 1: Apply deduplication to all results
    deduplicated = deduplicate_integration_test_results(raw_results)
    print(f"After deduplication: {len(deduplicated)} results")
    
    # Step 2: Filter after deduplication
    if status_filter:
        filtered_results = [r for r in deduplicated if r.get('component_build_result') == status_filter]
        print(f"After filtering for '{status_filter}': {len(filtered_results)} results")
    else:
        filtered_results = deduplicated
        print(f"No filtering: {len(filtered_results)} results")
    
    return filtered_results

def deduplicate_integration_test_results(results):
    """Keep only most recent entry for each (component, version, rc_number) combination."""
    if not results:
        return results
    
    # Group by (component, version, rc_number, platform, architecture, distribution)
    groups = {}
    ungrouped = []
    
    for result in results:
        component = result.get('component')
        version = result.get('version')
        rc_number = result.get('rc_number')
        build_start_time = result.get('build_start_time')
        
        # Include platform/arch/distribution to keep legitimate different test configurations
        platform = result.get('platform')
        architecture = result.get('architecture') 
        distribution = result.get('distribution')
        
        if component and version and rc_number is not None:
            key = (component, str(version), str(rc_number), str(platform), str(architecture), str(distribution))
            
            if key not in groups:
                groups[key] = result
            else:
                # Compare by build_start_time (most recent wins)
                existing_time = groups[key].get('build_start_time')
                
                if build_start_time and existing_time:
                    try:
                        # Convert to int for proper numeric comparison
                        new_time_int = int(build_start_time) if isinstance(build_start_time, str) else build_start_time
                        existing_time_int = int(existing_time) if isinstance(existing_time, str) else existing_time
                        
                        if new_time_int > existing_time_int:
                            groups[key] = result
                    except (ValueError, TypeError) as e:
                        # If conversion fails, do string comparison
                        if build_start_time > existing_time:
                            groups[key] = result
                elif build_start_time and not existing_time:
                    # New result has timestamp, existing doesn't - prefer new
                    groups[key] = result
        else:
            # Keep results without proper grouping keys
            ungrouped.append(result)
    
    return list(groups.values()) + ungrouped

# Load the real data
with open('raw_integration_test_data_rc6_v3.2.0_20250814_124810.json', 'r') as f:
    data = json.load(f)

raw_results = data['raw_results']
print(f"Loaded {len(raw_results)} raw results")

print("\n" + "="*80)
print("TESTING STATUS_FILTER='failed'")
print("="*80)

# Test old behavior (buggy)
old_results = simulate_old_behavior(raw_results, status_filter='failed')
old_failed = [r for r in old_results if r.get('component_build_result') == 'failed']

# Test new behavior (correct)
new_results = simulate_new_behavior(raw_results, status_filter='failed')
new_failed = [r for r in new_results if r.get('component_build_result') == 'failed']

print(f"\nCOMPARISON:")
print(f"Old behavior (buggy): {len(old_failed)} failed components")
print(f"New behavior (correct): {len(new_failed)} failed components")

print(f"\nFailed components in old behavior:")
for r in old_failed:
    component = r.get('component')
    platform = r.get('platform')
    arch = r.get('architecture')
    dist = r.get('distribution')
    print(f"  - {component} ({platform}/{arch}/{dist})")

print(f"\nFailed components in new behavior:")
for r in new_failed:
    component = r.get('component')
    platform = r.get('platform')
    arch = r.get('architecture')
    dist = r.get('distribution')
    print(f"  - {component} ({platform}/{arch}/{dist})")

print("\n" + "="*80)
print("TESTING NO STATUS_FILTER (should be same for both)")
print("="*80)

# Test with no filter
old_all = simulate_old_behavior(raw_results, status_filter=None)
new_all = simulate_new_behavior(raw_results, status_filter=None)

old_all_failed = [r for r in old_all if r.get('component_build_result') == 'failed']
new_all_failed = [r for r in new_all if r.get('component_build_result') == 'failed']

print(f"\nCOMPARISON (no filter):")
print(f"Old behavior: {len(old_all)} total, {len(old_all_failed)} failed")
print(f"New behavior: {len(new_all)} total, {len(new_all_failed)} failed")