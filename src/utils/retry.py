import asyncio
import functools
from typing import Callable, TypeVar, Any
from aiohttp import ClientResponseError
from src.utils.logger import get_logger

logger = get_logger("retry")
T = TypeVar('T')


def async_retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 5.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                
                except exceptions as e:
                    last_exception = e
                    
                    if hasattr(e, 'status') and e.status == 429:
                        logger.warning(f"⚠️ Rate limit hit (429) on attempt {attempt + 1}/{max_retries}")
                    else:
                        logger.warning(f"⚠️ Error on attempt {attempt + 1}/{max_retries}: {type(e).__name__}: {str(e)}")
                    
                    if attempt < max_retries - 1:
                        logger.info(f"⏳ Waiting {delay}s before retry (exponential backoff)...")
                        await asyncio.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(f"❌ Max retries ({max_retries}) reached. Aborting.")
            
            raise last_exception
        
        return wrapper
    return decorator


def sync_retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 5.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            import time
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                
                except exceptions as e:
                    last_exception = e
                    
                    if hasattr(e, 'status') and e.status == 429:
                        logger.warning(f"⚠️ Rate limit hit (429) on attempt {attempt + 1}/{max_retries}")
                    else:
                        logger.warning(f"⚠️ Error on attempt {attempt + 1}/{max_retries}: {type(e).__name__}: {str(e)}")
                    
                    if attempt < max_retries - 1:
                        logger.info(f"⏳ Waiting {delay}s before retry (exponential backoff)...")
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(f"❌ Max retries ({max_retries}) reached. Aborting.")
            
            raise last_exception
        
        return wrapper
    return decorator
