from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from src.services.auth_service import AuthService
from src.services.google_auth_service import GoogleAuthService
from src.modules.calendar_module import CalendarModule
from src.utils.error_handler import handle_errors
from src.utils.logger import get_logger, console
from datetime import datetime
import re

logger = get_logger("calendar_handlers")


class CalendarHandlers:
    def __init__(
        self,
        auth_service: AuthService,
        google_auth_service: GoogleAuthService,
        calendar_module: CalendarModule
    ):
        self.auth_service = auth_service
        self.google_auth_service = google_auth_service
        self.calendar_module = calendar_module
    
    @handle_errors
    async def login_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"/login command received from user {update.effective_user.id}")
        console.print(f"[info]🔐 /login command from user {update.effective_user.id}[/info]")
        
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        telegram_user_id = update.effective_user.id
        
        if self.google_auth_service.has_valid_credentials(telegram_user_id):
            await update.message.reply_text(
                "✅ Ya estás autenticado con Google Calendar.\n\n"
                "Usa /logout para desconectar tu cuenta."
            )
            return
        
        auth_url = self.google_auth_service.generate_auth_url(telegram_user_id)
        
        message = (
            "🔐 <b>Conectar Google Calendar</b>\n\n"
            "Sigue estos pasos:\n\n"
            "1️⃣ Haz clic en este enlace:\n"
            f'<a href="{auth_url}">🔗 Autorizar Google Calendar</a>\n\n'
            "2️⃣ Acepta los permisos de Google\n\n"
            "3️⃣ Google te mostrará un código en pantalla\n\n"
            "4️⃣ Copia ese código y envíalo con:\n"
            "<code>/code TU_CODIGO</code>\n\n"
            "💡 <i>Tip:</i> Google mostrará el código directamente, no necesitas buscarlo en la URL"
        )
        
        await update.message.reply_text(message, parse_mode="HTML", disable_web_page_preview=True)
        logger.info(f"User {telegram_user_id} initiated Google OAuth flow")
    
    @handle_errors
    async def code_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        # Show typing indicator while exchanging code
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        telegram_user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "❌ Uso: `/code TU_CODIGO`\n\n"
                "Ejemplo: `/code 4/0AY0e-g7...`",
                parse_mode="Markdown"
            )
            return
        
        auth_code = " ".join(context.args).strip()
        
        url_match = re.search(r'code=([^&\s]+)', auth_code)
        if url_match:
            auth_code = url_match.group(1)
        
        await update.message.reply_text("⏳ Procesando código...")
        
        success = self.google_auth_service.exchange_code_for_tokens(telegram_user_id, auth_code)
        
        if success:
            await update.message.reply_text(
                "✅ *¡Autenticación exitosa!*\n\n"
                "Tu cuenta de Google Calendar está conectada.\n\n"
                "Ahora puedes:\n"
                "• `/add` - Crear eventos en tu calendario\n"
                "• `/list` - Ver tus próximos eventos\n"
                "• `/done` - Marcar evento como completado\n"
                "• `/delete` - Eliminar evento",
                parse_mode="Markdown"
            )
            logger.info(f"User {telegram_user_id} successfully authenticated with Google")
        else:
            await update.message.reply_text(
                "❌ Error al autenticar.\n\n"
                "Verifica que:\n"
                "• El código sea correcto\n"
                "• No haya expirado (válido 10 min)\n"
                "• No lo hayas usado antes\n\n"
                "Intenta de nuevo con /login"
            )
    
    @handle_errors
    async def logout_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        telegram_user_id = update.effective_user.id
        
        success = self.google_auth_service.revoke_credentials(telegram_user_id)
        
        if success:
            await update.message.reply_text(
                "✅ Desconectado de Google Calendar.\n\n"
                "Tus eventos en Google Calendar no se eliminaron.\n"
                "Usa /login para volver a conectar."
            )
            logger.info(f"User {telegram_user_id} logged out from Google")
        else:
            await update.message.reply_text(
                "⚠️ No estabas conectado a Google Calendar."
            )
    
    @handle_errors
    async def add_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        telegram_user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "📅 Uso: `/add <evento>`\n\n"
                "Ejemplos:\n"
                "• `/add Reunión mañana 3pm`\n"
                "• `/add Cena el viernes a las 8`\n"
                "• `/add Llamar a Juan el lunes`",
                parse_mode="Markdown"
            )
            return
        
        event_text = " ".join(context.args)
        
        # Show typing indicator while processing
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        # Generar mensaje dinámico de procesamiento
        processing_msg = await self.calendar_module.ollama_service.get_jarvis_response(
            "thinking",
            f"Procesando evento: {event_text}"
        )
        await update.message.reply_text(f"⏳ {processing_msg}", parse_mode="Markdown")
        
        result = await self.calendar_module.add_event(
            telegram_user_id=telegram_user_id,
            title=event_text,
            deadline_text=event_text
        )
        
        if result["success"]:
            # Formatear fecha de manera legible en español
            from datetime import datetime
            import locale
            
            start_time = result['start_time']
            
            # Nombres de días y meses en español
            dias_semana = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
            meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 
                    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            
            dia_semana = dias_semana[start_time.weekday()]
            mes = meses[start_time.month - 1]
            
            fecha_legible = f"{dia_semana} {start_time.day} de {mes} a las {start_time.strftime('%H:%M')}"
            
            # Generar confirmación dinámica con IA
            ai_confirmation = await self.calendar_module.ollama_service.get_jarvis_response(
                "event_created",
                f"He agendado: {result['title']} para el {fecha_legible}"
            )
            
            message = (
                f"✅ **{ai_confirmation}**\n\n"
                f"📌 {result['title']}\n"
                f"📅 {fecha_legible}\n"
                f"🗓️ {start_time.strftime('%Y-%m-%d %H:%M')}"
            )
            
            if result.get('html_link'):
                message += f"\n\n🔗 [Ver en Google Calendar]({result['html_link']})"
            
            # Enviar confirmación con botón de navegación
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await update.message.reply_text(
                message, 
                parse_mode="Markdown", 
                disable_web_page_preview=True,
                reply_markup=get_back_to_dashboard_keyboard()
            )
        else:
            await update.message.reply_text(result["message"])
    
    @handle_errors
    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        # Show typing indicator while fetching events
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        telegram_user_id = update.effective_user.id
        
        result = self.calendar_module.list_events(telegram_user_id, max_results=10)
        
        if not result["success"]:
            await update.message.reply_text(
                "❌ Primero debes autenticarte con /login"
            )
            return
        
        events = result["events"]
        
        if not events:
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await update.message.reply_text(
                "📅 No tienes eventos próximos en tu calendario.\n\n"
                "Usa /add para crear uno.",
                reply_markup=get_back_to_dashboard_keyboard()
            )
            return
        
        message = "📅 *Tus próximos eventos:*\n\n"
        
        for i, event in enumerate(events, 1):
            summary = event.get('summary', 'Sin título')
            start = event.get('start', {})
            event_id = event['id']
            
            # Debug: ver estructura real del evento
            logger.info(f"Event {i}: full event = {event}")
            logger.info(f"Event {i}: start = {start}")
            
            # Extracción robusta: primero dateTime, luego date
            date_time = start.get('dateTime')
            date_only = start.get('date')
            
            logger.info(f"Event {i}: dateTime = {date_time}, date = {date_only}")
            
            if date_time:
                # Evento con hora específica
                try:
                    start_dt = datetime.fromisoformat(date_time.replace('Z', '+00:00'))
                    formatted_date = start_dt.strftime('%d/%m %H:%M')
                except Exception as e:
                    logger.warning(f"Error parsing dateTime: {e}")
                    formatted_date = "Sin fecha"
            elif date_only:
                # Evento de todo el día
                try:
                    start_dt = datetime.fromisoformat(date_only)
                    formatted_date = start_dt.strftime('%d/%m') + " (Todo el día)"
                except Exception as e:
                    logger.warning(f"Error parsing date: {e}")
                    formatted_date = "Sin fecha"
            else:
                # Caso raro: sin fecha
                formatted_date = "Sin fecha"
            
            short_id = event_id[:8]
            
            message += f"{i}. [{formatted_date}] *{summary}*\n"
            message += f"   🔑 `{short_id}`\n\n"
        
        message += "\n💡 Usa `/done <id>` para marcar como completado\n"
        message += "💡 Usa `/delete <id>` para eliminar"
        
        from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
        await update.message.reply_text(
            message, 
            parse_mode="Markdown",
            reply_markup=get_back_to_dashboard_keyboard()
        )
    
    @handle_errors
    async def done_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        telegram_user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "✅ Uso: `/done <id>`\n\n"
                "Ejemplo: `/done a1b2c3d4`\n\n"
                "Obtén el ID con /list",
                parse_mode="Markdown"
            )
            return
        
        event_id_partial = context.args[0].strip()
        
        result = self.calendar_module.list_events(telegram_user_id, max_results=50)
        
        if not result["success"]:
            await update.message.reply_text("❌ Primero debes autenticarte con /login")
            return
        
        matching_event = None
        for event in result["events"]:
            if event['id'].startswith(event_id_partial):
                matching_event = event
                break
        
        if not matching_event:
            await update.message.reply_text(
                f"❌ No se encontró evento con ID: `{event_id_partial}`\n\n"
                "Usa /list para ver tus eventos.",
                parse_mode="Markdown"
            )
            return
        
        complete_result = self.calendar_module.mark_event_completed(
            telegram_user_id,
            matching_event['id']
        )
        
        if complete_result["success"]:
            await update.message.reply_text(
                f"✅ Evento marcado como completado:\n\n"
                f"*{matching_event.get('summary', 'Sin título')}*",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Error al marcar evento como completado")
    
    @handle_errors
    async def delete_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        telegram_user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "🗑️ Uso: `/delete <id>`\n\n"
                "Ejemplo: `/delete a1b2c3d4`\n\n"
                "Obtén el ID con /list",
                parse_mode="Markdown"
            )
            return
        
        event_id_partial = context.args[0].strip()
        
        result = self.calendar_module.list_events(telegram_user_id, max_results=50)
        
        if not result["success"]:
            await update.message.reply_text("❌ Primero debes autenticarte con /login")
            return
        
        matching_event = None
        for event in result["events"]:
            if event['id'].startswith(event_id_partial):
                matching_event = event
                break
        
        if not matching_event:
            await update.message.reply_text(
                f"❌ No se encontró evento con ID: `{event_id_partial}`\n\n"
                "Usa /list para ver tus eventos.",
                parse_mode="Markdown"
            )
            return
        
        delete_result = self.calendar_module.delete_event(
            telegram_user_id,
            matching_event['id']
        )
        
        if delete_result["success"]:
            await update.message.reply_text(
                f"🗑️ Evento eliminado:\n\n"
                f"*{matching_event.get('summary', 'Sin título')}*",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Error al eliminar evento")
    
    @handle_errors
    async def calendar_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        telegram_user_id = update.effective_user.id
        
        has_credentials = self.google_auth_service.has_valid_credentials(telegram_user_id)
        
        if has_credentials:
            message = (
                "✅ *Estado: Conectado*\n\n"
                "Tu cuenta de Google Calendar está activa.\n\n"
                "Comandos disponibles:\n"
                "• `/add` - Crear evento\n"
                "• `/list` - Ver eventos\n"
                "• `/done` - Marcar completado\n"
                "• `/delete` - Eliminar evento\n"
                "• `/logout` - Desconectar cuenta"
            )
        else:
            message = (
                "❌ *Estado: No conectado*\n\n"
                "No tienes una cuenta de Google Calendar conectada.\n\n"
                "Usa /login para conectar tu cuenta."
            )
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
    def get_handlers(self):
        from telegram.ext import CommandHandler
        
        return [
            CommandHandler("login", self.login_command),
            CommandHandler("code", self.code_command),
            CommandHandler("logout", self.logout_command),
            CommandHandler("calendar", self.calendar_status_command),
            CommandHandler("add", self.add_command),
            CommandHandler("list", self.list_command),
            CommandHandler("done", self.done_command),
            CommandHandler("delete", self.delete_command),
        ]
