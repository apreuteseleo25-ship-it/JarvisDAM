import asyncio
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, Deque
from src.utils.logger import get_logger

logger = get_logger("rate_limiter")


class TelegramRateLimiter:
    def __init__(self, max_messages_per_minute: int = 20):
        self.max_messages_per_minute = max_messages_per_minute
        self.message_timestamps: Dict[int, Deque[datetime]] = defaultdict(deque)
        self._lock = asyncio.Lock()
    
    async def wait_if_needed(self, chat_id: int) -> float:
        async with self._lock:
            now = datetime.utcnow()
            one_minute_ago = now - timedelta(minutes=1)
            
            if chat_id in self.message_timestamps:
                while (self.message_timestamps[chat_id] and 
                       self.message_timestamps[chat_id][0] < one_minute_ago):
                    self.message_timestamps[chat_id].popleft()
            
            if len(self.message_timestamps[chat_id]) >= self.max_messages_per_minute:
                oldest_message = self.message_timestamps[chat_id][0]
                wait_until = oldest_message + timedelta(minutes=1)
                wait_seconds = (wait_until - now).total_seconds()
                
                if wait_seconds > 0:
                    logger.warning(f"⏳ Rate limit: waiting {wait_seconds:.1f}s for chat {chat_id}")
                    await asyncio.sleep(wait_seconds)
                    return wait_seconds
            
            self.message_timestamps[chat_id].append(now)
            return 0.0
    
    def get_stats(self, chat_id: int) -> Dict[str, int]:
        now = datetime.utcnow()
        one_minute_ago = now - timedelta(minutes=1)
        
        if chat_id not in self.message_timestamps:
            return {"messages_last_minute": 0, "limit": self.max_messages_per_minute}
        
        recent_messages = sum(
            1 for ts in self.message_timestamps[chat_id] 
            if ts > one_minute_ago
        )
        
        return {
            "messages_last_minute": recent_messages,
            "limit": self.max_messages_per_minute,
            "remaining": max(0, self.max_messages_per_minute - recent_messages)
        }
    
    def reset(self, chat_id: int = None):
        if chat_id:
            if chat_id in self.message_timestamps:
                self.message_timestamps[chat_id].clear()
        else:
            self.message_timestamps.clear()


class APIRateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.request_timestamps: Deque[datetime] = deque()
        self._lock = asyncio.Lock()
    
    async def wait_if_needed(self) -> float:
        async with self._lock:
            now = datetime.utcnow()
            one_minute_ago = now - timedelta(minutes=1)
            
            while self.request_timestamps and self.request_timestamps[0] < one_minute_ago:
                self.request_timestamps.popleft()
            
            if len(self.request_timestamps) >= self.requests_per_minute:
                oldest_request = self.request_timestamps[0]
                wait_until = oldest_request + timedelta(minutes=1)
                wait_seconds = (wait_until - now).total_seconds()
                
                if wait_seconds > 0:
                    logger.warning(f"⏳ API rate limit: waiting {wait_seconds:.1f}s")
                    await asyncio.sleep(wait_seconds)
                    return wait_seconds
            
            self.request_timestamps.append(now)
            return 0.0
    
    def get_stats(self) -> Dict[str, int]:
        now = datetime.utcnow()
        one_minute_ago = now - timedelta(minutes=1)
        
        recent_requests = sum(
            1 for ts in self.request_timestamps 
            if ts > one_minute_ago
        )
        
        return {
            "requests_last_minute": recent_requests,
            "limit": self.requests_per_minute,
            "remaining": max(0, self.requests_per_minute - recent_requests)
        }
