#!/usr/bin/env python3
"""
Test different query parameters to see if they affect deduplication.
"""

import json

def deduplicate_integration_test_results(results):
    """Keep only most recent entry for each (component, version, rc_number) combination."""
    if not results:
        return results
    
    print(f"🔄 DEDUP: Starting deduplication of {len(results)} integration test results")
    
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
    
    deduplicated_results = list(groups.values()) + ungrouped
    print(f"🔄 DEDUP: Deduplication complete: {len(results)} -> {len(deduplicated_results)} results")
    return deduplicated_results

# Load the real data
with open('raw_integration_test_data_rc6_v3.2.0_20250814_124810.json', 'r') as f:
    data = json.load(f)

raw_results = data['raw_results']
print(f"Loaded {len(raw_results)} raw results")

# Test 1: Get all results and deduplicate
print("\n" + "="*80)
print("TEST 1: All results with deduplication")
print("="*80)

deduplicated_all = deduplicate_integration_test_results(raw_results)
failed_all = [r for r in deduplicated_all if r.get('component_build_result') == 'failed']
print(f"All results after deduplication: {len(deduplicated_all)}")
print(f"Failed results after deduplication: {len(failed_all)}")

# Test 2: Filter for failed results BEFORE deduplication (this might be what's happening)
print("\n" + "="*80)
print("TEST 2: Filter failed BEFORE deduplication (potential bug)")
print("="*80)

failed_raw = [r for r in raw_results if r.get('component_build_result') == 'failed']
print(f"Failed results before deduplication: {len(failed_raw)}")

# Show the failed components before deduplication
failed_components = {}
for r in failed_raw:
    component = r.get('component')
    platform = r.get('platform')
    arch = r.get('architecture')
    dist = r.get('distribution')
    build_time = r.get('build_start_time')
    
    key = f"{component}_{platform}_{arch}_{dist}"
    if key not in failed_components:
        failed_components[key] = []
    failed_components[key].append(build_time)

print(f"Unique failed component/platform combinations: {len(failed_components)}")
for key, times in failed_components.items():
    print(f"  - {key}: {len(times)} entries, times: {times}")

# Now deduplicate the failed results
deduplicated_failed = deduplicate_integration_test_results(failed_raw)
print(f"Failed results after deduplication: {len(deduplicated_failed)}")

# Test 3: Check if there are any results with 'with_security' or 'without_security' failures
print("\n" + "="*80)
print("TEST 3: Check security test failures")
print("="*80)

security_failures = []
for r in raw_results:
    with_sec = r.get('with_security')
    without_sec = r.get('without_security')
    component = r.get('component')
    
    if with_sec == 'fail' or without_sec == 'fail':
        security_failures.append(r)

print(f"Results with security test failures: {len(security_failures)}")

# Deduplicate security failures
deduplicated_security = deduplicate_integration_test_results(security_failures)
print(f"Security failures after deduplication: {len(deduplicated_security)}")

for r in deduplicated_security:
    component = r.get('component')
    platform = r.get('platform')
    arch = r.get('architecture')
    dist = r.get('distribution')
    build_time = r.get('build_start_time')
    with_sec = r.get('with_security')
    without_sec = r.get('without_security')
    build_result = r.get('component_build_result')
    print(f"  - {component} ({platform}/{arch}/{dist}) - build_result: {build_result}, with_sec: {with_sec}, without_sec: {without_sec}, time: {build_time}")