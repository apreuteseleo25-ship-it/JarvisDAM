from telegram import Update
from telegram.ext import ContextTypes
from src.models.database import DatabaseService
from typing import Optional


class AuthService:
    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
    
    async def authenticate_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
        if not update.effective_user:
            return None
        
        telegram_id = update.effective_user.id
        username = update.effective_user.username
        
        user = self.db_service.get_user_by_telegram_id(telegram_id)
        
        if not user:
            user = self.db_service.get_or_create_user(telegram_id, username)
            
            welcome_message = (
                f"👋 ¡Bienvenido a JARVIS System, {username or 'usuario'}!\n\n"
                "Tu cuenta ha sido creada automáticamente.\n\n"
                "Comandos disponibles:\n"
                "📚 *LIBRARY (Knowledge Vault)*\n"
                "  /ingest - Sube un PDF para indexar\n"
                "  /stash - Guarda un snippet de código\n"
                "  /ask - Pregunta sobre tus documentos\n"
                "  /quiz - Genera un quiz de tus documentos\n\n"
                "📰 *INTEL (News)*\n"
                "  /snipe - Descarga noticias de tus temas\n"
                "  /subscribe - Suscríbete a un tema\n"
                "  /unsubscribe - Cancela suscripción\n\n"
                "📅 *HQ (Tasks & Calendar)*\n"
                "  /add - Añade una tarea\n"
                "  /list - Lista tus tareas\n"
                "  /done - Marca tarea como completada\n\n"
                "ℹ️ /help - Muestra esta ayuda"
            )
            
            await update.message.reply_text(welcome_message, parse_mode="Markdown")
        
        return user.id
    
    def get_user_id(self, telegram_id: int) -> Optional[int]:
        user = self.db_service.get_user_by_telegram_id(telegram_id)
        return user.id if user else None
