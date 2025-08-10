import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Callable
import queue

class OptimizedSlackHandler:
    """Optimized handler for high-concurrency scenarios"""
    
    def __init__(self, app, storage, oscar_agent):
        self.app = app
        self.storage = storage
        self.oscar_agent = oscar_agent
        self.client = app.client
        
        # Dynamic thread pool that scales with demand
        self.executor = ThreadPoolExecutor(
            max_workers=50,  # Higher limit for peak load
            thread_name_prefix="oscar-agent"
        )
        
        # Shared timeout monitor (single thread for all queries)
        self.active_queries = {}
        self.timeout_monitor_thread = None
        self.monitor_lock = threading.Lock()
        self._start_timeout_monitor()
    
    def _start_timeout_monitor(self):
        """Start single background thread to monitor all timeouts"""
        if self.timeout_monitor_thread is None or not self.timeout_monitor_thread.is_alive():
            self.timeout_monitor_thread = threading.Thread(target=self._timeout_monitor_worker, daemon=True)
            self.timeout_monitor_thread.start()
    
    def _timeout_monitor_worker(self):
        """Single thread monitors all active queries"""
        while True:
            time.sleep(30)  # Check every 30 seconds
            current_time = time.time()
            
            with self.monitor_lock:
                queries_to_remove = []
                for query_id, query_info in self.active_queries.items():
                    elapsed = current_time - query_info['start_time']
                    
                    # Add hourglass at 60s
                    if elapsed >= 60 and not query_info.get('hourglass_added'):
                        self._manage_reactions(query_info['channel'], query_info['reaction_ts'], 
                                             add_reaction="hourglass_flowing_sand")
                        query_info['hourglass_added'] = True
                    
                    # Timeout at 90s
                    if elapsed >= 90:
                        self._handle_timeout(query_info)
                        queries_to_remove.append(query_id)
                
                # Clean up timed out queries
                for query_id in queries_to_remove:
                    del self.active_queries[query_id]
    
    def _handle_timeout(self, query_info):
        """Handle timeout for a specific query"""
        self._manage_reactions(query_info['channel'], query_info['reaction_ts'], 
                             add_reaction="x", 
                             remove_reaction=["thinking_face", "hourglass_flowing_sand"])
        query_info['say'](text="⏱️ Your request took too long and timed out.", 
                         thread_ts=query_info['thread_ts'])
        query_info['result_queue'].put(("timeout", None, None))
    
    def _query_agent_optimized(self, query: str, session_id: str, context_summary: str, 
                              channel: str, reaction_ts: str, start_time: float,
                              say: Callable, thread_ts: str) -> tuple:
        """Optimized agent query with shared timeout monitoring"""
        result_queue = queue.Queue()
        query_id = f"{channel}_{thread_ts}_{int(start_time)}"
        
        # Rate limiting: max 3 concurrent queries per user
        user_queries = sum(1 for q in self.active_queries.values() if q.get('user_id') == user_id)
        if user_queries >= 3:
            self._manage_reactions(channel, reaction_ts, add_reaction="x", remove_reaction="thinking_face")
            say(text="🚫 You have too many active requests. Please wait for them to complete.", thread_ts=thread_ts)
            return None, None
        
        # System overload protection
        if len(self.active_queries) >= 45:
            self._manage_reactions(channel, reaction_ts, add_reaction="x", remove_reaction="thinking_face")
            say(text="🚫 System is currently overloaded. Please try again in a few minutes.", thread_ts=thread_ts)
            return None, None
        
        # Register query for timeout monitoring
        with self.monitor_lock:
            self.active_queries[query_id] = {
                'start_time': start_time,
                'channel': channel,
                'reaction_ts': reaction_ts,
                'say': say,
                'thread_ts': thread_ts,
                'result_queue': result_queue,
                'hourglass_added': False
            }
        
        # Submit to thread pool
        future = self.executor.submit(
            self._agent_worker, query, session_id, context_summary, result_queue
        )
        
        # Wait for result or timeout
        try:
            while True:
                try:
                    status, response, new_session_id = result_queue.get(timeout=30)
                    
                    # Clean up from monitoring
                    with self.monitor_lock:
                        self.active_queries.pop(query_id, None)
                    
                    if status == "success":
                        return response, new_session_id
                    elif status == "timeout":
                        return None, None
                    else:
                        raise Exception(response)
                        
                except queue.Empty:
                    # Continue waiting, timeout monitor will handle timeouts
                    continue
                    
        except Exception as e:
            # Clean up on error
            with self.monitor_lock:
                self.active_queries.pop(query_id, None)
            raise e
    
    def _agent_worker(self, query: str, session_id: str, context_summary: str, result_queue: queue.Queue):
        """Worker function for thread pool"""
        try:
            response, new_session_id = self.oscar_agent.query(
                query, session_id=session_id, context_summary=context_summary
            )
            result_queue.put(("success", response, new_session_id))
        except Exception as e:
            result_queue.put(("error", str(e), None))