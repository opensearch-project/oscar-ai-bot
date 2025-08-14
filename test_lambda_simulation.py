#!/usr/bin/env python3
"""
Simulate what the Lambda function does when called by the agent.
"""

import json
import sys
import os

# Add the metrics directory to the path so we can import the Lambda function
sys.path.append('metrics')

# Import the Lambda function
from lambda_function import handle_metrics_query

def test_lambda_call():
    """Test what happens when we call the Lambda function like the agent does."""
    
    # Simulate the parameters that the agent would send
    params = {
        'version': '3.2.0',
        'rc_numbers': ['6'],  # This should be an array based on action group config
        'build_numbers': [],
        'integ_test_build_numbers': [],
        'components': [],
        'status_filter': None,
        'distribution': None,
        'architecture': None,
        'platform': None,
        'with_security': None,
        'without_security': None
    }
    
    print("Testing Lambda function call simulation...")
    print(f"Parameters: {params}")
    
    # Call the handle_metrics_query function directly
    try:
        result = handle_metrics_query(
            agent_type='integration-test',
            function_name='get_integration_test_metrics', 
            params=params,
            request_id='test-123'
        )
        
        print(f"\nResult keys: {list(result.keys())}")
        print(f"Total results: {result.get('total_results', 'N/A')}")
        
        # Check if we have results
        if 'results' in result:
            results = result['results']
            print(f"Actual results count: {len(results)}")
            
            # Count failed results
            failed_results = [r for r in results if r.get('component_build_result') == 'failed' or r.get('status') == 'failed']
            print(f"Failed results: {len(failed_results)}")
            
            # Show failed components
            if failed_results:
                print("\nFailed components:")
                for r in failed_results:
                    component = r.get('component')
                    platform = r.get('platform')
                    arch = r.get('architecture')
                    dist = r.get('distribution')
                    build_time = r.get('build_start_time')
                    with_sec = r.get('with_security')
                    without_sec = r.get('without_security')
                    print(f"  - {component} ({platform}/{arch}/{dist}) - time: {build_time} - with_sec: {with_sec}, without_sec: {without_sec}")
            
            # Check for alerting specifically
            alerting_results = [r for r in results if r.get('component') == 'alerting']
            print(f"\nAlerting results: {len(alerting_results)}")
            for r in alerting_results:
                platform = r.get('platform')
                arch = r.get('architecture')
                dist = r.get('distribution')
                status = r.get('component_build_result')
                build_time = r.get('build_start_time')
                with_sec = r.get('with_security')
                without_sec = r.get('without_security')
                print(f"  - {platform}/{arch}/{dist} - {status} - time: {build_time} - with_sec: {with_sec}, without_sec: {without_sec}")
        
        return result
        
    except Exception as e:
        print(f"Error calling Lambda function: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_lambda_call()