import asyncio
import yaml
import os
from telegram.ext import Application

# Disable ChromaDB telemetry to avoid warnings
os.environ["ANONYMIZED_TELEMETRY"] = "False"
from src.models.database import DatabaseService
from src.services.chroma_service import ChromaService
from src.services.cache_service import CacheService
from src.services.auth_service import AuthService
from src.services.google_auth_service import GoogleAuthService
from src.services.ollama_service import OllamaService
from src.services.scheduler_service import SchedulerService
from src.modules.library import LibraryModule
from src.modules.intel import IntelModule
from src.modules.intel_manager import IntelManager
from src.modules.hq import HQModule
from src.modules.calendar_module import CalendarModule
from src.bot.handlers import BotHandlers
from src.bot.calendar_handlers import CalendarHandlers
from src.bot.menu_handler import MenuHandler
from src.bot.quiz_handler import QuizHandler
from src.bot.generator_handler import GeneratorHandler
from src.bot.news_handler import NewsHandler
from src.utils.logger import console
from rich.panel import Panel


def load_config(config_path: str = "config.yaml"):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


async def main():
    console.print(Panel.fit(
        "[start]� JARVIS System Online[/start]",
        border_style="magenta",
        padding=(1, 2)
    ))
    
    config = load_config()
    
    db_service = DatabaseService(config['database']['path'])
    console.print("[success]✅ Database initialized[/success]")
    
    chroma_service = ChromaService(
        persist_directory=config['chromadb']['persist_directory'],
        collection_name=config['chromadb']['collection_name']
    )
    console.print("[success]✅ ChromaDB initialized[/success]")
    
    cache_service = CacheService(
        db_path=config['database']['path'],
        cache_ttl_hours=config.get('cache', {}).get('ttl_hours', 4)
    )
    console.print("[success]✅ Cache service initialized[/success] [info](TTL: 4 hours)[/info]")
    
    auth_service = AuthService(db_service)
    # Sistema híbrido: modelo rápido por defecto, modelo potente para análisis
    ollama_service = OllamaService(
        base_url=config['ollama'].get('base_url', 'http://localhost:11434'),
        model=config['ollama'].get('model', 'qwen2.5:7b')  # Modelo rápido por defecto
    )
    
    google_auth_service = GoogleAuthService(db_service)
    calendar_module = CalendarModule(google_auth_service, ollama_service)
    console.print("[success]✅ Google Calendar services initialized[/success]")
    
    library_module = LibraryModule(chroma_service, ollama_service)
    intel_module = IntelModule(db_service, ollama_service, cache_service)  # Mantener para compatibilidad
    intel_manager = IntelManager(db_service, ollama_service)  # Nuevo sistema robusto
    hq_module = HQModule(db_service, ollama_service)
    
    console.print("[success]✅ Modules initialized[/success]")
    
    application = Application.builder().token(config['telegram']['bot_token']).build()
    
    bot_handlers = BotHandlers(
        auth_service=auth_service,
        library_module=library_module,
        intel_module=intel_module,
        hq_module=hq_module
    )
    
    calendar_handlers = CalendarHandlers(
        auth_service=auth_service,
        google_auth_service=google_auth_service,
        calendar_module=calendar_module
    )
    
    menu_handler = MenuHandler(
        auth_service=auth_service,
        google_auth_service=google_auth_service,
        calendar_module=calendar_module,
        intel_module=intel_module,
        bot_handlers=bot_handlers
    )
    
    quiz_handler = QuizHandler(
        auth_service=auth_service,
        library_module=library_module
    )
    
    generator_handler = GeneratorHandler(
        auth_service=auth_service,
        ollama_service=ollama_service
    )
    
    news_handler = NewsHandler(
        auth_service=auth_service,
        intel_manager=intel_manager
    )
    
    # Register menu handlers FIRST (interactive menu with buttons)
    from telegram.ext import CommandHandler
    application.add_handler(CommandHandler("start", menu_handler.start_command))
    
    # Register news handlers BEFORE menu callbacks (specific patterns first)
    for handler in news_handler.get_handlers():
        application.add_handler(handler)
    
    # Register menu callback handler (catches remaining callbacks)
    application.add_handler(menu_handler.get_callback_handler())
    
    # Register quiz handler
    application.add_handler(CommandHandler("quiz", quiz_handler.quiz_command))
    
    # Register generator handlers
    for handler in generator_handler.get_handlers():
        application.add_handler(handler)
    
    # Register calendar handlers to give them priority
    for handler in calendar_handlers.get_handlers():
        application.add_handler(handler)
    
    for handler in bot_handlers.get_handlers():
        application.add_handler(handler)
    
    console.print("[success]✅ Bot handlers registered[/success] [info](including Google Calendar)[/info]")
    
    # Store modules in bot_data for jobs and handlers
    application.bot_data["calendar_module"] = calendar_module
    application.bot_data["intel_module"] = intel_module  # Mantener para compatibilidad
    application.bot_data["intel_manager"] = intel_manager  # Nuevo sistema
    application.bot_data["google_auth_service"] = google_auth_service
    application.bot_data["news_cache"] = {}  # Inicializar caché de noticias
    
    # Setup daily briefing job
    from src.jobs.briefing import setup_daily_briefing_job
    setup_daily_briefing_job(application)
    console.print("[success]✅ Daily briefing job scheduled[/success] [info](08:00 AM)[/info]")
    
    # Setup intel feed updater (Always-On Cache)
    from src.jobs.intel_updater import setup_intel_updater
    setup_intel_updater(application)
    console.print("[success]✅ Intel feed updater scheduled[/success] [info](every 30 min)[/info]")
    
    scheduler_service = SchedulerService(
        bot=application.bot,
        hq_module=hq_module,
        intel_module=intel_module,
        db_service=db_service,
        config=config
    )
    
    scheduler_service.start()
    
    console.print("\n[start]🚀 JARVIS System is running![/start]")
    console.print("[info]ℹ️  Press Ctrl+C to stop[/info]\n")
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        console.print("\n[warning]⏹️  Stopping JARVIS System...[/warning]")
        scheduler_service.stop()
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        console.print("[success]👋 Goodbye![/success]")


if __name__ == "__main__":
    asyncio.run(main())
