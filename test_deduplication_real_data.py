#!/usr/bin/env python3
"""
Test deduplication logic with real data from the JSON file.
"""

import json
import sys

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
            
            print(f"🔄 DEDUP: Processing {component} - key: {key}, build_time: {build_start_time}")
            
            if key not in groups:
                groups[key] = result
                print(f"🔄 DEDUP: Added new entry for {component}")
            else:
                # Compare by build_start_time (most recent wins)
                existing_time = groups[key].get('build_start_time')
                existing_status = groups[key].get('component_build_result')
                new_status = result.get('component_build_result')
                
                print(f"🔄 DEDUP: Comparing {component} - existing_time: {existing_time} ({existing_status}) vs new_time: {build_start_time} ({new_status})")
                
                if build_start_time and existing_time:
                    try:
                        # Convert to int for proper numeric comparison
                        new_time_int = int(build_start_time) if isinstance(build_start_time, str) else build_start_time
                        existing_time_int = int(existing_time) if isinstance(existing_time, str) else existing_time
                        
                        if new_time_int > existing_time_int:
                            print(f"🔄 DEDUP: Replacing {component} - newer time {new_time_int} > {existing_time_int}")
                            groups[key] = result
                        else:
                            print(f"🔄 DEDUP: Keeping existing {component} - older time {new_time_int} <= {existing_time_int}")
                    except (ValueError, TypeError) as e:
                        print(f"🔄 DEDUP: Error comparing times for {component}: {e}")
                        # If conversion fails, do string comparison
                        if build_start_time > existing_time:
                            groups[key] = result
                elif build_start_time and not existing_time:
                    # New result has timestamp, existing doesn't - prefer new
                    print(f"🔄 DEDUP: Replacing {component} - new has timestamp, existing doesn't")
                    groups[key] = result
                # If neither has timestamp or existing is newer, keep existing
        else:
            # Keep results without proper grouping keys
            print(f"🔄 DEDUP: Adding to ungrouped - missing fields: component={component}, version={version}, rc_number={rc_number}")
            ungrouped.append(result)
    
    deduplicated_results = list(groups.values()) + ungrouped
    print(f"🔄 DEDUP: Deduplication complete: {len(results)} -> {len(deduplicated_results)} results")
    
    return deduplicated_results

# Load the real data
with open('raw_integration_test_data_rc6_v3.2.0_20250814_124810.json', 'r') as f:
    data = json.load(f)

raw_results = data['raw_results']
print(f"Loaded {len(raw_results)} raw results")

# Filter for alerting component only to see what happens
alerting_results = [r for r in raw_results if r.get('component') == 'alerting']
print(f"\nFound {len(alerting_results)} alerting results:")

for i, result in enumerate(alerting_results):
    platform = result.get('platform')
    arch = result.get('architecture')
    dist = result.get('distribution')
    status = result.get('component_build_result')
    build_time = result.get('build_start_time')
    with_sec = result.get('with_security')
    without_sec = result.get('without_security')
    
    print(f"{i+1}. {platform}/{arch}/{dist} - {status} - time: {build_time} - with_sec: {with_sec}, without_sec: {without_sec}")

print("\n" + "="*80)
print("TESTING DEDUPLICATION ON ALERTING RESULTS")
print("="*80)

deduplicated_alerting = deduplicate_integration_test_results(alerting_results)

print(f"\nAfter deduplication: {len(deduplicated_alerting)} alerting results:")
for i, result in enumerate(deduplicated_alerting):
    platform = result.get('platform')
    arch = result.get('architecture')
    dist = result.get('distribution')
    status = result.get('component_build_result')
    build_time = result.get('build_start_time')
    with_sec = result.get('with_security')
    without_sec = result.get('without_security')
    
    print(f"{i+1}. {platform}/{arch}/{dist} - {status} - time: {build_time} - with_sec: {with_sec}, without_sec: {without_sec}")

# Now test with all results
print("\n" + "="*80)
print("TESTING DEDUPLICATION ON ALL RESULTS")
print("="*80)

deduplicated_all = deduplicate_integration_test_results(raw_results)
print(f"All results: {len(raw_results)} -> {len(deduplicated_all)}")

# Count failures in deduplicated results
failed_results = [r for r in deduplicated_all if r.get('component_build_result') == 'failed']
print(f"Failed results after deduplication: {len(failed_results)}")

for result in failed_results:
    component = result.get('component')
    platform = result.get('platform')
    arch = result.get('architecture')
    dist = result.get('distribution')
    build_time = result.get('build_start_time')
    with_sec = result.get('with_security')
    without_sec = result.get('without_security')
    
    print(f"FAILED: {component} ({platform}/{arch}/{dist}) - time: {build_time} - with_sec: {with_sec}, without_sec: {without_sec}")