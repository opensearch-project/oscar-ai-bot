#!/usr/bin/env python3

# Test the deduplication function locally
def deduplicate_integration_test_results(results):
    """Keep only most recent entry for each (component, version, rc_number) combination."""
    if not results:
        return results
    
    print(f"Deduplicating {len(results)} integration test results")
    
    # Group by (component, version, rc_number)
    groups = {}
    ungrouped = []
    
    for result in results:
        component = result.get('component')
        version = result.get('version')
        rc_number = result.get('rc_number')
        build_start_time = result.get('build_start_time')
        
        print(f"Processing: component={component}, version={version}, rc_number={rc_number}, time={build_start_time}")
        
        # Only group if we have required fields
        if component and version and rc_number is not None:
            key = (component, str(version), str(rc_number))
            
            if key not in groups:
                groups[key] = result
                print(f"  New group for {key}")
            else:
                # Compare by build_start_time (most recent wins)
                existing_time = groups[key].get('build_start_time')
                if build_start_time and existing_time:
                    if build_start_time > existing_time:
                        groups[key] = result
                        print(f"  Replaced with newer time: {build_start_time} > {existing_time}")
                    else:
                        print(f"  Kept existing with newer time: {existing_time} >= {build_start_time}")
                elif build_start_time and not existing_time:
                    # New result has timestamp, existing doesn't - prefer new
                    groups[key] = result
                    print(f"  Replaced (new has timestamp, existing doesn't)")
                else:
                    print(f"  Kept existing (no timestamp comparison possible)")
        else:
            # Keep results without proper grouping keys
            ungrouped.append(result)
            print(f"  Added to ungrouped (missing fields)")
    
    deduplicated_results = list(groups.values()) + ungrouped
    print(f"Deduplication complete: {len(results)} -> {len(deduplicated_results)} results")
    return deduplicated_results

# Test with sample data
test_data = [
    {'component': 'A', 'version': '3.2.0', 'rc_number': 6, 'build_start_time': '1755199176666'},
    {'component': 'A', 'version': '3.2.0', 'rc_number': 6, 'build_start_time': '1755192902707'},
    {'component': 'B', 'version': '3.2.0', 'rc_number': 6, 'build_start_time': '1755199176666'},
]

print("Testing deduplication function:")
result = deduplicate_integration_test_results(test_data)
print(f"Final result count: {len(result)}")
for r in result:
    print(f"  {r['component']}: {r['build_start_time']}")