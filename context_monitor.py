#!/usr/bin/env python3
"""
Context Preservation Monitoring Script for OSCAR Agent.

This script can be run periodically to check context preservation health.
"""

import json
import logging
import time
import boto3
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class ContextMonitor:
    """Monitor context preservation health."""
    
    def __init__(self, region: str = 'us-east-1'):
        self.region = region
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        
    def check_context_health(self, context_table_name: str = 'oscar-context') -> Dict[str, Any]:
        """Check the health of context storage."""
        try:
            table = self.dynamodb.Table(context_table_name)
            
            # Scan recent contexts (last hour)
            current_time = int(time.time())
            one_hour_ago = current_time - 3600
            
            response = table.scan(
                FilterExpression='updated_at > :timestamp',
                ExpressionAttributeValues={':timestamp': one_hour_ago},
                Limit=100
            )
            
            contexts = response.get('Items', [])
            
            # Analyze contexts
            stats = {
                'total_contexts': len(contexts),
                'contexts_with_history': 0,
                'contexts_with_sessions': 0,
                'average_history_length': 0,
                'contexts_with_empty_history': 0,
                'session_ids': set()
            }
            
            total_history_length = 0
            
            for item in contexts:
                context = item.get('context', {})
                history = context.get('history', [])
                session_id = context.get('session_id')
                
                if history:
                    stats['contexts_with_history'] += 1
                    total_history_length += len(history)
                else:
                    stats['contexts_with_empty_history'] += 1
                
                if session_id:
                    stats['contexts_with_sessions'] += 1
                    stats['session_ids'].add(session_id)
            
            if stats['contexts_with_history'] > 0:
                stats['average_history_length'] = total_history_length / stats['contexts_with_history']
            
            stats['unique_sessions'] = len(stats['session_ids'])
            del stats['session_ids']  # Remove set for JSON serialization
            
            return {
                'status': 'healthy' if stats['contexts_with_empty_history'] < stats['total_contexts'] * 0.5 else 'degraded',
                'timestamp': current_time,
                'stats': stats
            }
            
        except Exception as e:
            logger.error(f"Error checking context health: {e}")
            return {
                'status': 'error',
                'timestamp': current_time,
                'error': str(e)
            }
    
    def identify_problematic_contexts(self, context_table_name: str = 'oscar-context') -> List[Dict[str, Any]]:
        """Identify contexts that might have preservation issues."""
        try:
            table = self.dynamodb.Table(context_table_name)
            
            # Scan all contexts
            response = table.scan()
            contexts = response.get('Items', [])
            
            problematic = []
            
            for item in contexts:
                thread_key = item.get('thread_key')
                context = item.get('context', {})
                history = context.get('history', [])
                session_id = context.get('session_id')
                
                issues = []
                
                # Check for empty history in contexts that should have history
                if not history:
                    issues.append('empty_history')
                
                # Check for missing session ID
                if not session_id:
                    issues.append('missing_session_id')
                
                # Check for very old contexts with no recent activity
                if history:
                    latest_timestamp = max(entry.get('timestamp', 0) for entry in history)
                    if latest_timestamp < time.time() - 86400:  # 24 hours
                        issues.append('stale_context')
                
                if issues:
                    problematic.append({
                        'thread_key': thread_key,
                        'issues': issues,
                        'history_length': len(history),
                        'session_id': session_id
                    })
            
            return problematic
            
        except Exception as e:
            logger.error(f"Error identifying problematic contexts: {e}")
            return []

def main():
    """Run context monitoring."""
    monitor = ContextMonitor()
    
    print("OSCAR Context Preservation Health Check")
    print("=" * 50)
    
    # Check overall health
    health = monitor.check_context_health()
    print(f"Status: {health['status']}")
    print(f"Timestamp: {time.ctime(health['timestamp'])}")
    
    if 'stats' in health:
        stats = health['stats']
        print(f"Total contexts: {stats['total_contexts']}")
        print(f"Contexts with history: {stats['contexts_with_history']}")
        print(f"Contexts with sessions: {stats['contexts_with_sessions']}")
        print(f"Average history length: {stats['average_history_length']:.2f}")
        print(f"Contexts with empty history: {stats['contexts_with_empty_history']}")
        print(f"Unique sessions: {stats['unique_sessions']}")
    
    # Check for problematic contexts
    print("\nProblematic Contexts:")
    problematic = monitor.identify_problematic_contexts()
    
    if problematic:
        for context in problematic[:10]:  # Show first 10
            print(f"  {context['thread_key']}: {', '.join(context['issues'])}")
    else:
        print("  None found")
    
    print(f"\nTotal problematic contexts: {len(problematic)}")

if __name__ == "__main__":
    main()
