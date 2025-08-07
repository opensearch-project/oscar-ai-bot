#!/usr/bin/env python3

import json
import sys
import os

# Load environment variables
from dotenv import load_dotenv
load_dotenv('/Users/divsen/Desktop/OSCAR/OSCAR/.env')

sys.path.append('/Users/divsen/Desktop/OSCAR/OSCAR/metrics')

from lambda_function import opensearch_request

def discover_all_indices():
    """Discover all available indices."""
    try:
        indices = opensearch_request('GET', '/_cat/indices?format=json')
        print("=== ALL AVAILABLE INDICES ===")
        for idx in indices:
            print(f"Index: {idx.get('index')}, Docs: {idx.get('docs.count', '0')}, Size: {idx.get('store.size', '0')}")
        return indices
    except Exception as e:
        print(f"Error getting indices: {e}")
        return []

def get_index_mapping(index_name):
    """Get mapping for a specific index."""
    try:
        mapping = opensearch_request('GET', f'/{index_name}/_mapping')
        return mapping
    except Exception as e:
        print(f"Error getting mapping for {index_name}: {e}")
        return None

def discover_metrics_indices():
    """Discover indices that might contain metrics data."""
    
    # Get all indices
    indices = discover_all_indices()
    
    # Filter for potential metrics indices
    metrics_keywords = ['test', 'build', 'release', 'deploy', 'ci', 'cd', 'pipeline', 'metrics', 'performance']
    
    potential_indices = []
    for idx in indices:
        index_name = idx.get('index', '').lower()
        if any(keyword in index_name for keyword in metrics_keywords):
            potential_indices.append(idx)
    
    print(f"\n=== POTENTIAL METRICS INDICES ({len(potential_indices)}) ===")
    for idx in potential_indices:
        print(f"Index: {idx.get('index')}")
    
    # Get mappings for each potential index
    print(f"\n=== INDEX MAPPINGS AND SAMPLE DATA ===")
    for idx in potential_indices:
        index_name = idx.get('index')
        print(f"\n--- {index_name} ---")
        
        # Get mapping
        mapping = get_index_mapping(index_name)
        if mapping:
            properties = mapping.get(index_name, {}).get('mappings', {}).get('properties', {})
            print(f"Fields: {list(properties.keys())}")
            
            # Get sample document
            try:
                sample = opensearch_request('POST', f'/{index_name}/_search', {
                    "size": 1,
                    "query": {"match_all": {}}
                })
                hits = sample.get('hits', {}).get('hits', [])
                if hits:
                    sample_doc = hits[0].get('_source', {})
                    print(f"Sample fields: {list(sample_doc.keys())}")
                    print(f"Sample data: {json.dumps(sample_doc, indent=2)[:300]}...")
                else:
                    print("No sample documents found")
            except Exception as e:
                print(f"Error getting sample: {e}")
    
    return potential_indices

def analyze_index_for_metrics_type(index_name, metrics_type):
    """Analyze if an index is suitable for a specific metrics type."""
    print(f"\n=== ANALYZING {index_name} FOR {metrics_type.upper()} METRICS ===")
    
    # Get mapping
    mapping = get_index_mapping(index_name)
    if not mapping:
        return False
    
    properties = mapping.get(index_name, {}).get('mappings', {}).get('properties', {})
    
    # Define expected fields for each metrics type
    expected_fields = {
        'test': ['test', 'result', 'status', 'coverage', 'failure', 'success', 'execution'],
        'build': ['build', 'pipeline', 'job', 'branch', 'commit', 'duration', 'status'],
        'release': ['release', 'version', 'deploy', 'environment', 'rollback', 'readiness'],
        'deployment': ['deploy', 'service', 'environment', 'health', 'uptime', 'performance']
    }
    
    # Check field relevance
    relevant_fields = []
    for field_name in properties.keys():
        field_lower = field_name.lower()
        if any(keyword in field_lower for keyword in expected_fields.get(metrics_type, [])):
            relevant_fields.append(field_name)
    
    print(f"Relevant fields for {metrics_type}: {relevant_fields}")
    
    # Get sample data to understand structure
    try:
        sample = opensearch_request('POST', f'/{index_name}/_search', {
            "size": 3,
            "query": {"match_all": {}},
            "sort": [{"@timestamp": {"order": "desc"}}] if "@timestamp" in properties else []
        })
        
        hits = sample.get('hits', {}).get('hits', [])
        print(f"Sample documents ({len(hits)}):")
        for i, hit in enumerate(hits):
            doc = hit.get('_source', {})
            print(f"  Doc {i+1}: {json.dumps(doc, indent=4)[:200]}...")
            
    except Exception as e:
        print(f"Error getting samples: {e}")
    
    return len(relevant_fields) > 0

if __name__ == "__main__":
    print("🔍 DISCOVERING METRICS INDICES AND MAPPINGS")
    print("=" * 60)
    
    # Discover all potential metrics indices
    potential_indices = discover_metrics_indices()
    
    # Analyze each index for different metrics types
    metrics_types = ['test', 'build', 'release', 'deployment']
    
    for metrics_type in metrics_types:
        print(f"\n{'='*60}")
        print(f"ANALYZING INDICES FOR {metrics_type.upper()} METRICS")
        print('='*60)
        
        for idx in potential_indices:
            index_name = idx.get('index')
            analyze_index_for_metrics_type(index_name, metrics_type)