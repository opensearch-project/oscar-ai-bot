import asyncio
import time
from typing import Dict, Callable
import threading

class AsyncSlackHandler:
    """Async handler for unlimited concurrency with resource limits"""
    
    def __init__(self, app, storage, oscar_agent):
        self.app = app
        self.storage = storage
        self.oscar_agent = oscar_agent
        self.client = app.client
        
        # Semaphore limits concurrent agent calls (not threads)
        self.agent_semaphore = asyncio.Semaphore(20)  # Max 20 concurrent agent calls
        self.active_queries = {}
        self.monitor_lock = threading.Lock()
        
        # Start timeout monitor
        self.timeout_monitor_task = None
        self._start_timeout_monitor()
    
    def _start_timeout_monitor(self):
        """Start async timeout monitor"""
        if self.timeout_monitor_task is None or self.timeout_monitor_task.done():
            self.timeout_monitor_task = asyncio.create_task(self._timeout_monitor_worker())
    
    async def _timeout_monitor_worker(self):
        """Async timeout monitor"""
        while True:
            await asyncio.sleep(30)  # Check every 30 seconds
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
                        await self._handle_timeout(query_info)
                        queries_to_remove.append(query_id)
                
                # Clean up timed out queries
                for query_id in queries_to_remove:
                    del self.active_queries[query_id]
    
    async def _handle_timeout(self, query_info):
        """Handle timeout for a specific query"""
        self._manage_reactions(query_info['channel'], query_info['reaction_ts'], 
                             add_reaction="x", 
                             remove_reaction=["thinking_face", "hourglass_flowing_sand"])
        query_info['say'](text="⏱️ Your request took too long and timed out.", 
                         thread_ts=query_info['thread_ts'])
        query_info['future'].cancel()
    
    async def _query_agent_async(self, query: str, session_id: str, context_summary: str, 
                                channel: str, reaction_ts: str, start_time: float,
                                say: Callable, thread_ts: str) -> tuple:
        """Async agent query with semaphore-based concurrency control"""
        query_id = f"{channel}_{thread_ts}_{int(start_time)}"
        
        # Check current load
        if len(self.active_queries) >= 100:  # Hard limit
            self._manage_reactions(channel, reaction_ts, add_reaction="x", remove_reaction="thinking_face")
            say(text="🚫 System is at capacity. Please try again later.", thread_ts=thread_ts)
            return None, None
        
        # Acquire semaphore (limits concurrent agent calls)
        async with self.agent_semaphore:
            # Register query for timeout monitoring
            future = asyncio.create_task(self._agent_worker_async(query, session_id, context_summary))
            
            with self.monitor_lock:
                self.active_queries[query_id] = {
                    'start_time': start_time,
                    'channel': channel,
                    'reaction_ts': reaction_ts,
                    'say': say,
                    'thread_ts': thread_ts,
                    'future': future,
                    'hourglass_added': False
                }
            
            try:
                # Wait for result
                response, new_session_id = await future
                
                # Clean up from monitoring
                with self.monitor_lock:
                    self.active_queries.pop(query_id, None)
                
                return response, new_session_id
                
            except asyncio.CancelledError:
                # Query was cancelled due to timeout
                with self.monitor_lock:
                    self.active_queries.pop(query_id, None)
                return None, None
            except Exception as e:
                # Clean up on error
                with self.monitor_lock:
                    self.active_queries.pop(query_id, None)
                raise e
    
    async def _agent_worker_async(self, query: str, session_id: str, context_summary: str):
        """Async worker that runs agent in thread pool"""
        loop = asyncio.get_event_loop()
        
        # Run blocking agent call in thread pool
        response, new_session_id = await loop.run_in_executor(
            None,  # Use default thread pool
            lambda: self.oscar_agent.query(query, session_id=session_id, context_summary=context_summary)
        )
        
        return response, new_session_id