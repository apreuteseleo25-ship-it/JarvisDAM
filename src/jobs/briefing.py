from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime, time
from src.utils.logger import get_logger
from typing import Optional

logger = get_logger("briefing_job")

# Global storage for daily briefing chat IDs
# In production, this should be stored in database
DAILY_BRIEFING_CHATS = set()


async def send_daily_briefing(context: ContextTypes.DEFAULT_TYPE):
    """
    Envía el Daily Briefing matutino a todos los usuarios suscritos.
    Incluye: Agenda del día + Noticias prioritarias.
    """
    logger.info("Starting daily briefing job...")
    
    # Obtener módulos del contexto
    calendar_module = context.bot_data.get("calendar_module")
    intel_module = context.bot_data.get("intel_module")
    google_auth_service = context.bot_data.get("google_auth_service")
    
    if not calendar_module or not intel_module:
        logger.error("Required modules not found in bot_data")
        return
    
    # Enviar briefing a cada chat suscrito
    for chat_id in list(DAILY_BRIEFING_CHATS):
        try:
            await _send_briefing_to_chat(
                context=context,
                chat_id=chat_id,
                calendar_module=calendar_module,
                intel_module=intel_module,
                google_auth_service=google_auth_service
            )
            logger.info(f"Daily briefing sent to chat {chat_id}")
        except Exception as e:
            logger.error(f"Error sending briefing to chat {chat_id}: {e}", exc_info=True)


async def _send_briefing_to_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    calendar_module,
    intel_module,
    google_auth_service
):
    """Genera y envía el briefing para un chat específico"""
    
    # Obtener el user_id del telegram_id (chat_id)
    user_id = chat_id  # En este caso, telegram_id == user_id
    
    # === SECCIÓN 1: AGENDA DEL DÍA ===
    agenda_section = "📅 **Agenda para hoy:**\n"
    
    # Verificar si tiene Google Calendar conectado
    has_calendar = google_auth_service.has_valid_credentials(user_id)
    
    if has_calendar:
        try:
            # Obtener eventos de hoy
            today_events = await calendar_module.get_today_events(user_id)
            
            if today_events and len(today_events) > 0:
                for event in today_events:
                    event_time = event.get("start_time", "")
                    event_title = event.get("title", "Sin título")
                    agenda_section += f"• {event_time} - {event_title}\n"
            else:
                agenda_section += "• No hay eventos programados para hoy.\n"
        except Exception as e:
            logger.error(f"Error fetching calendar events: {e}")
            agenda_section += "• Error al obtener eventos del calendario.\n"
    else:
        agenda_section += "• Calendario no conectado.\n"
    
    # === SECCIÓN 2: RESUMEN DE INTELIGENCIA (NOTICIAS) ===
    news_section = "\n📰 **Resumen de Inteligencia:**\n"
    
    try:
        # Obtener las 3 noticias más prioritarias no leídas
        priority_news = intel_module.get_priority_news(user_id, priority=5)
        
        if not priority_news:
            # Si no hay prioridad 5, buscar prioridad 4
            priority_news = intel_module.get_priority_news(user_id, priority=4)
        
        if priority_news:
            # Limitar a 3 titulares
            top_news = priority_news[:3]
            for news_item in top_news:
                title = news_item.title
                url = news_item.url
                news_section += f"• [{title}]({url})\n"
        else:
            news_section += "• No hay noticias nuevas en este momento.\n"
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        news_section += "• Error al obtener noticias.\n"
    
    # === CONSTRUIR MENSAJE FINAL ===
    current_hour = datetime.now().hour
    greeting = "Buenos días" if current_hour < 12 else "Buenas tardes" if current_hour < 20 else "Buenas noches"
    
    briefing_message = (
        f"{greeting}, Señor. ☀️\n\n"
        f"{agenda_section}"
        f"{news_section}\n"
        f"Sistemas listos. ¿En qué procedemos?"
    )
    
    # Enviar el briefing
    await context.bot.send_message(
        chat_id=chat_id,
        text=briefing_message,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


def add_briefing_chat(chat_id: int) -> bool:
    """Añade un chat a la lista de briefings diarios"""
    if chat_id in DAILY_BRIEFING_CHATS:
        return False
    DAILY_BRIEFING_CHATS.add(chat_id)
    logger.info(f"Chat {chat_id} added to daily briefing list")
    return True


def remove_briefing_chat(chat_id: int) -> bool:
    """Elimina un chat de la lista de briefings diarios"""
    if chat_id not in DAILY_BRIEFING_CHATS:
        return False
    DAILY_BRIEFING_CHATS.discard(chat_id)
    logger.info(f"Chat {chat_id} removed from daily briefing list")
    return True


def is_briefing_enabled(chat_id: int) -> bool:
    """Verifica si un chat tiene el briefing activado"""
    return chat_id in DAILY_BRIEFING_CHATS


def setup_daily_briefing_job(application):
    """
    Configura el job diario para enviar briefings a las 08:00 AM.
    Debe ser llamado desde main.py después de inicializar la aplicación.
    """
    # Programar el job para las 08:00 AM todos los días
    job_queue = application.job_queue
    
    job_queue.run_daily(
        callback=send_daily_briefing,
        time=time(hour=8, minute=0, second=0),
        name="daily_briefing"
    )
    
    logger.info("Daily briefing job scheduled for 08:00 AM")
