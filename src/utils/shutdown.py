import signal
import asyncio
from typing import Callable, List
from src.utils.logger import get_logger

logger = get_logger("shutdown")


class GracefulShutdown:
    def __init__(self):
        self.shutdown_handlers: List[Callable] = []
        self.is_shutting_down = False
    
    def register_handler(self, handler: Callable):
        self.shutdown_handlers.append(handler)
        logger.info(f"Registered shutdown handler: {handler.__name__}")
    
    async def shutdown(self):
        if self.is_shutting_down:
            return
        
        self.is_shutting_down = True
        logger.info("🛑 Initiating graceful shutdown...")
        
        for handler in self.shutdown_handlers:
            try:
                logger.info(f"Executing shutdown handler: {handler.__name__}")
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
                logger.info(f"✅ Completed: {handler.__name__}")
            except Exception as e:
                logger.error(f"Error in shutdown handler {handler.__name__}: {e}", exc_info=True)
        
        logger.info("👋 Shutdown complete. Goodbye!")
    
    def setup_signal_handlers(self, loop):
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        logger.info("✅ Signal handlers configured")


shutdown_manager = GracefulShutdown()
