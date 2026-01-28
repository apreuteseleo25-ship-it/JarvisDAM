from telegram import Update
from telegram.ext import ContextTypes
from functools import wraps
from src.utils.logger import get_logger

logger = get_logger("error_handler")


def handle_errors(func):
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await func(self, update, context, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
            
            error_message = f"❌ Ocurrió un error: {str(e)[:100]}"
            
            try:
                if update.message:
                    await update.message.reply_text(error_message)
                elif update.callback_query:
                    await update.callback_query.message.reply_text(error_message)
            except Exception as send_error:
                logger.error(f"Failed to send error message to user: {send_error}", exc_info=True)
    
    return wrapper


def safe_execute(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
            return None
    
    return wrapper
