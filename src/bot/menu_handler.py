from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction
from src.services.auth_service import AuthService
from src.services.google_auth_service import GoogleAuthService
from src.modules.calendar_module import CalendarModule
from src.utils.error_handler import handle_errors
from src.utils.logger import get_logger, console
import asyncio
from src.utils.google_token import is_google_token_valid

logger = get_logger("menu_handler")


def get_main_menu_keyboard(context=None):
    # 1. Lógica del botón de Google (Estado)
    # Asegúrate de importar la función de verificación de token correctamente
    is_connected = False
    try:
        # Aquí pon tu lógica real, ej: os.path.exists('token.json')
        is_connected = is_google_token_valid()
    except:
        is_connected = False # Fallback

    if is_connected:
        btn_google = InlineKeyboardButton("🔴 Desconectar", callback_data='google_logout')
    else:
        btn_google = InlineKeyboardButton("🔑 Conectar Google", callback_data='google_login')

    # 2. Definición ESTÁTICA del Teclado (Sin .appends posteriores)
    keyboard = [
        # Fila 1: Gestión de Tiempo
        [
            InlineKeyboardButton("📅 Ver Agenda", callback_data='list_events'),
            InlineKeyboardButton("➕ Añadir Evento", callback_data='add_event_instruction')
        ],
        # Fila 2: Gestión de Conocimiento (RAG e Ingesta)
        [
            InlineKeyboardButton("🧠 Consultar", callback_data='ask_instruction'),
            InlineKeyboardButton("📥 Ingestar (PDF/YT)", callback_data='ingest_menu') # Emoji: Inbox Tray
        ],
        # Fila 3: Generación y Noticias
        [
            InlineKeyboardButton("📑 Crear CheatSheet", callback_data='cheat_instruction'), # Emoji: Bookmark Tabs
            InlineKeyboardButton("📰 Noticias", callback_data='news_menu')
        ],
        # Fila 4: Aprendizaje y Sistema
        [
            InlineKeyboardButton("📝 Auto-Examen", callback_data='quiz_menu'),
            btn_google
        ],
        # Fila 5: Ayuda
        [
            InlineKeyboardButton("❓ Ayuda / Comandos", callback_data='help_command')
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_content(user_first_name: str, has_calendar: bool) -> tuple[str, InlineKeyboardMarkup]:
    """Genera el contenido del menú principal - ÚNICA FUENTE DE VERDAD para el mensaje de bienvenida"""
    calendar_status = "✅ Conectado" if has_calendar else "❌ No conectado"
    
    welcome_message = (
        f"🤖 <b>SISTEMA J.A.R.V.I.S. | EN LÍNEA</b>\n\n"
        f"Buenos días, <b>{user_first_name}</b>. Todos los sistemas operativos.\n\n"
        f"📊 <b>Estado de conexiones:</b>\n"
        f"  • Google Calendar: {calendar_status}\n"
        f"  • Base de Conocimiento: ✅ Activa\n"
        f"  • Módulo de Quizzes: ✅ Activo\n\n"
        f"💡 <i>¿En qué puedo asistirle hoy, Señor?</i>"
    )
    
    return welcome_message, get_main_menu_keyboard(has_calendar)


class MenuHandler:
    def __init__(
        self,
        auth_service: AuthService,
        google_auth_service: GoogleAuthService,
        calendar_module: CalendarModule,
        intel_module=None,
        bot_handlers=None
    ):
        self.auth_service = auth_service
        self.google_auth_service = google_auth_service
        self.calendar_module = calendar_module
        self.intel_module = intel_module
        self.bot_handlers = bot_handlers
    
    def get_main_menu_keyboard(self):
        """Genera el teclado del menú principal"""
        return get_main_menu_keyboard()
    
    @handle_errors
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start mejorado con menú interactivo"""
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        user = update.effective_user
        telegram_user_id = user.id
        
        # Verificar si tiene Google Calendar conectado
        has_calendar = self.google_auth_service.has_valid_credentials(telegram_user_id)
        
        # Usar función única para contenido del menú
        welcome_message, keyboard = get_main_menu_content(user.first_name, has_calendar)
        
        await update.message.reply_text(
            welcome_message,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
        console.print(f"[info]🏠 Menu displayed for user {telegram_user_id}[/info]")
    
    @handle_errors
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja los clics en los botones del menú"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        callback_data = query.data
        
        console.print(f"[info]🖱️  Button clicked: {callback_data} by user {user_id}[/info]")
        
        # Enrutar según el botón presionado (NUEVOS CALLBACK_DATA)
        if callback_data == "list_events":
            await self._handle_tasks(query, context, user_id)
        
        elif callback_data == "add_event_instruction":
            await self._handle_help_add_event(query, context)
        
        elif callback_data == "ask_instruction":
            await self._handle_help_ask(query, context)
        
        elif callback_data == "ingest_menu":
            await self._handle_ingest_menu(query, context)
        
        elif callback_data == "cheat_instruction":
            await self._handle_help_cheat(query, context)
        
        elif callback_data == "news_menu":
            await self._handle_news(query, context, user_id)
        
        elif callback_data == "quiz_menu":
            await self._handle_quiz(query, context, user_id)
        
        elif callback_data == "google_login":
            await self._handle_settings_login(query, context, user_id)
        
        elif callback_data == "google_logout":
            await self._handle_settings_logout(query, context, user_id)
        
        elif callback_data == "help_command":
            await self._handle_help(query, context)
        
        elif callback_data == "news_flash":
            await self._handle_news_briefing(query, context, user_id, density="flash")
        
        elif callback_data == "news_deep":
            await self._handle_news_briefing(query, context, user_id, density="deep")
        
        elif callback_data.startswith("snipe_select|"):
            if self.bot_handlers:
                await self.bot_handlers._handle_snipe_select(query, context, callback_data)
        
        elif callback_data.startswith("snipe_action|"):
            if self.bot_handlers:
                await self.bot_handlers._handle_snipe_action(query, context, callback_data)
        
        elif callback_data.startswith("snipe_list|"):
            if self.bot_handlers:
                await self.bot_handlers._handle_snipe_list(query, context, callback_data)
        
        elif callback_data == "back_to_menu" or callback_data == "main_menu":
            await self._handle_back_to_menu(query, context)
    
    async def _handle_tasks(self, query, context, user_id):
        """Muestra las tareas del usuario"""
        # Show typing indicator while fetching tasks
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
        
        # Verificar autenticación con Google Calendar
        if not self.google_auth_service.has_valid_credentials(user_id):
            keyboard = [
                [InlineKeyboardButton("� Conectar Google Calendar", callback_data="settings_login")],
                [InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]
            ]
            await query.edit_message_text(
                "❌ <b>No estás conectado a Google Calendar</b>\n\n"
                "Para ver tus tareas, primero debes conectar tu cuenta de Google Calendar.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Obtener eventos del calendario
        result = self.calendar_module.list_events(user_id, max_results=10)
        
        if not result["success"]:
            keyboard = [[InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]]
            await query.edit_message_text(
                f"❌ <b>Error al obtener tareas</b>\n\n{result.get('message', 'Error desconocido')}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        events = result.get("events", [])
        
        if not events:
            message = (
                "📅 <b>Tu Agenda</b>\n\n"
                "No tienes eventos próximos.\n\n"
                "➕ <b>Para añadir un evento:</b>\n"
                "Escribe directamente el comando <code>/add</code> seguido de los detalles.\n\n"
                "<i>Ejemplo:</i>\n"
                "<code>/add Reunión de equipo el martes a las 16:00</code>\n"
                "<code>/add Dentista mañana a las 10am</code>\n"
                "<code>/add Llamar a mamá el viernes</code>\n\n"
                "💡 El bot entiende lenguaje natural y extrae la fecha automáticamente."
            )
        else:
            message = "📅 <b>Tu Agenda - Próximos Eventos</b>\n\n"
            for i, event in enumerate(events[:10], 1):
                title = event.get('summary', 'Sin título')
                start_obj = event.get('start', {})
                
                # Extracción robusta: primero dateTime, luego date
                date_time = start_obj.get('dateTime')
                date_only = start_obj.get('date')
                
                if date_time:
                    # Evento con hora específica
                    try:
                        from datetime import datetime
                        start_dt = datetime.fromisoformat(date_time.replace('Z', '+00:00'))
                        start_str = start_dt.strftime('%d/%m %H:%M')
                    except:
                        start_str = "Sin fecha"
                elif date_only:
                    # Evento de todo el día
                    try:
                        from datetime import datetime
                        start_dt = datetime.fromisoformat(date_only)
                        start_str = start_dt.strftime('%d/%m') + " (Todo el día)"
                    except:
                        start_str = "Sin fecha"
                else:
                    start_str = "Sin fecha"
                
                message += f"{i}. {start_str} <b>{title}</b>\n   � <code>{event['id'][:8]}</code>\n\n"
            
            message += (
                "➕ <b>Para añadir un evento:</b>\n"
                "Usa el comando <code>/add</code> con lenguaje natural.\n"
                "<i>Ejemplo: /add Presentación el lunes a las 9am</i>"
            )
        
        keyboard = [
            [InlineKeyboardButton("➕ Añadir Tarea", callback_data="menu_add_quick")],
            [InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]
        ]
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _handle_add_quick(self, query, context, user_id):
        """Solicita al usuario que escriba una tarea"""
        # Verificar autenticación
        if not self.google_auth_service.has_valid_credentials(user_id):
            keyboard = [
                [InlineKeyboardButton("� Conectar Google Calendar", callback_data="settings_login")],
                [InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]
            ]
            await query.edit_message_text(
                "❌ <b>No estás conectado a Google Calendar</b>\n\n"
                "Para añadir tareas, primero debes conectar tu cuenta de Google Calendar.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        keyboard = [[InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]]
        
        message = (
            "➕ <b>Añadir Tarea Rápida</b>\n\n"
            "Escribe tu tarea en lenguaje natural. Ejemplos:\n\n"
            "• <code>Reunión mañana a las 3pm</code>\n"
            "• <code>Dentista el viernes a las 10am</code>\n"
            "• <code>Llamar a mamá el lunes</code>\n\n"
            "💡 Puedes especificar fecha y hora, y yo me encargo del resto."
        )
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Marcar que el usuario está en modo "añadir tarea"
        context.user_data['awaiting_task'] = True
    
    async def _handle_brain(self, query, context, user_id):
        """Muestra opciones del cerebro (biblioteca de conocimiento)"""
        keyboard = [
            [InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]
        ]
        
        message = (
            "🧠 <b>Cerebro - Tu Base de Conocimiento</b>\n\n"
            "Tu biblioteca de conocimiento personal con RAG.\n\n"
            "<b>Comandos disponibles:</b>\n"
            "• <code>/ingest</code> - Añadir PDF\n"
            "• <code>/ask [pregunta]</code> - Consultar documentos\n"
            "• <code>/quiz [tema]</code> - Generar examen\n\n"
            "💡 Envía un PDF directamente para guardarlo"
        )
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _handle_news(self, query, context, user_id):
        """Muestra opciones de noticias"""
        keyboard = [
            [InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]
        ]
        
        message = (
            "📰 <b>Noticias Personalizadas</b>\n\n"
            "Mantente informado con noticias relevantes.\n\n"
            "<b>Comandos disponibles:</b>\n"
            "• <code>/subscribe [tema]</code> - Seguir tema\n"
            "• <code>/topics</code> - Ver temas seguidos\n"
            "• <code>/snipe</code> - Obtener últimas noticias\n\n"
            "💡 Suscríbete a temas de tu interés para recibir actualizaciones"
        )
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _handle_quiz(self, query, context, user_id):
        """Muestra información sobre el sistema de quizzes"""
        keyboard = [
            [InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]
        ]
        
        message = (
            "📝 <b>Sistema de Quizzes Interactivos</b>\n\n"
            "Genera quizzes automáticos desde tus documentos guardados.\n\n"
            "<b>Cómo usar:</b>\n"
            "1. Primero guarda documentos con <code>/ingest</code>\n"
            "2. Luego genera un quiz: <code>/quiz [tema]</code>\n\n"
            "<b>Ejemplo:</b>\n"
            "• <code>/quiz SQL</code> - Quiz sobre SQL\n"
            "• <code>/quiz Python</code> - Quiz sobre Python\n\n"
            "💡 El bot buscará en tus documentos y generará preguntas tipo test con explicaciones"
        )
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _handle_help(self, query, context):
        """Muestra la ayuda con todos los comandos disponibles"""
        keyboard = [
            [InlineKeyboardButton("🔙 Volver", callback_data="main_menu")]
        ]
        
        message = (
            "❓ <b>Ayuda - Todos los Comandos</b>\n\n"
            "<b>📅 Calendario:</b>\n"
            "<code>/login</code> - Conectar Google Calendar\n"
            "<code>/add &lt;texto&gt;</code> - Crear evento\n"
            "  <i>Ejemplo: \"/add Dentista mañana 10am\"</i>\n"
            "<code>/list</code> - Ver próximos eventos\n"
            "<code>/delete &lt;id&gt;</code> - Borrar evento\n"
            "<code>/logout</code> - Desconectar Google Calendar\n\n"
            "<b>🧠 Cerebro &amp; Estudio:</b>\n"
            "<code>/ask &lt;pregunta&gt;</code> - Preguntar a tus documentos\n"
            "  <i>Ejemplo: \"/ask ¿Qué es SQL?\"</i>\n"
            "<code>/ingest</code> - Guardar documentos PDF\n"
            "<code>/ask &lt;pregunta&gt;</code> - Consultar base de conocimiento\n"
            "<code>/quiz &lt;tema&gt;</code> - Generar test interactivo\n"
            "  <i>Ejemplo: \"/quiz SQL\"</i>\n"
            "<code>/cheat &lt;tema&gt;</code> - Generar cheatsheet PDF\n\n"
            "<b>� &amp; 🛠 Otros:</b>\n"
            "<code>/subscribe &lt;tema&gt;</code> - Seguir tema de noticias\n"
            "  <i>Ejemplo: \"/subscribe Inteligencia Artificial\"</i>\n"
            "<code>/topics</code> - Ver temas seguidos\n"
            "<code>/start</code> - Volver al menú principal\n\n"
            "💡 <i>Tip: Puedes enviar PDFs directamente al chat para guardarlos automáticamente</i>"
        )
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _handle_back_to_menu(self, query, context):
        """Vuelve al menú principal"""
        user = query.from_user
        telegram_user_id = user.id
        
        # Verificar si tiene Google Calendar conectado
        has_calendar = self.google_auth_service.has_valid_credentials(telegram_user_id)
        
        # Usar la MISMA función que /start para consistencia
        welcome_message, keyboard = get_main_menu_content(user.first_name, has_calendar)
        
        await query.edit_message_text(
            welcome_message,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    
    async def _handle_settings_login(self, query, context, user_id):
        """Inicia el proceso de login de Google Calendar"""
        # Show typing indicator while generating auth URL
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
        
        auth_url = self.google_auth_service.generate_auth_url(user_id)
        
        keyboard = [[InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]]
        
        message = (
            "🔐 <b>Conectar Google Calendar</b>\n\n"
            "Haz clic en este enlace para autorizar:\n"
            f'<a href="{auth_url}">🔗 Autorizar Google Calendar</a>\n\n'
            "Después de aceptar los permisos, Google te mostrará un código.\n\n"
            "Copia ese código y envíalo con:\n"
            "<code>/code TU_CODIGO</code>"
        )
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
    
    async def _handle_settings_logout(self, query, context, user_id):
        """Desconecta la cuenta de Google Calendar"""
        # Show typing indicator while revoking credentials
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
        
        success = self.google_auth_service.revoke_credentials(user_id)
        
        if success:
            message = (
                "✅ <b>Desconectado Exitosamente</b>\n\n"
                "Tu cuenta de Google Calendar ha sido desconectada.\n\n"
                "Tus eventos en Google Calendar no se eliminaron.\n\n"
                "Puedes volver a conectarte cuando quieras."
            )
            console.print(f"[success]✅ User {user_id} disconnected from Google Calendar[/success]")
        else:
            message = (
                "⚠️ <b>No Estabas Conectado</b>\n\n"
                "No había ninguna cuenta de Google Calendar conectada."
            )
        
        keyboard = [[InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]]
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _handle_help_add_event(self, query, context):
        """Muestra ayuda para añadir eventos"""
        message = (
            "➕ <b>Añadir Evento al Calendario</b>\n\n"
            "<b>Comando:</b> <code>/add [descripción del evento]</code>\n\n"
            "<b>Ejemplos:</b>\n"
            "• <code>/add Reunión mañana a las 3pm</code>\n"
            "• <code>/add Dentista el viernes a las 10am</code>\n"
            "• <code>/add Presentación del proyecto el lunes a las 9</code>\n"
            "• <code>/add Llamar a Juan el martes por la tarde</code>\n\n"
            "💡 <b>Tip:</b> Usa lenguaje natural. JARVIS extrae automáticamente la fecha y hora."
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]]
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _handle_help_ask(self, query, context):
        """Muestra ayuda para consultas RAG"""
        message = (
            "🧠 <b>Consultar Base de Conocimiento (RAG)</b>\n\n"
            "<b>Comando:</b> <code>/ask [tu pregunta]</code>\n\n"
            "<b>Ejemplos:</b>\n"
            "• <code>/ask ¿Qué es machine learning?</code>\n"
            "• <code>/ask Explica las clases en Python</code>\n"
            "• <code>/ask ¿Cómo funcionan los decoradores?</code>\n\n"
            "📚 <b>Requisito:</b> Primero debes indexar documentos con <code>/ingest</code>\n\n"
            "💡 <b>Tip:</b> Las respuestas incluyen citas de las fuentes con números de página."
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]]
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _handle_help_cheat(self, query, context):
        """Muestra ayuda para generar cheatsheets"""
        message = (
            "📄 <b>Generar CheatSheet (Hoja de Referencia)</b>\n\n"
            "<b>Comando:</b> <code>/cheat [tema]</code>\n\n"
            "<b>Ejemplos:</b>\n"
            "• <code>/cheat Python Listas</code>\n"
            "• <code>/cheat SQL Joins</code>\n"
            "• <code>/cheat Git Comandos</code>\n"
            "• <code>/cheat Segunda Guerra Mundial</code>\n\n"
            "📂 <b>Resultado:</b> Recibirás un PDF profesional con:\n"
            "  • Definiciones clave\n"
            "  • Ejemplos prácticos\n"
            "  • Tabla de conceptos\n"
            "  • Best practices\n\n"
            "💡 <b>Tip:</b> Ideal para repasos rápidos antes de exámenes."
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]]
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _handle_news_briefing(self, query, context, user_id, density: str):
        """Procesa la generación de noticias con el nivel de densidad seleccionado"""
        if not self.intel_module:
            await query.edit_message_text(
                "⚠️ Módulo de noticias no disponible.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="main_menu")]])
            )
            return
        
        # Mostrar indicador de procesamiento
        await query.edit_message_text(
            f"{'⚡' if density == 'flash' else '🧐'} <b>Procesando informe...</b>\n\n"
            "Descargando noticias de las fuentes...",
            parse_mode="HTML"
        )
        
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
        
        try:
            # Descargar noticias
            count = await self.intel_module.snipe_news(user_id)
            
            if count == 0:
                from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
                await query.edit_message_text(
                    "📭 No se encontraron noticias nuevas.\n\n"
                    "Intenta nuevamente más tarde.",
                    reply_markup=get_back_to_dashboard_keyboard()
                )
                return
            
            # Generar resumen con densidad seleccionada
            await query.edit_message_text(
                f"{'⚡' if density == 'flash' else '🧐'} <b>Generando resumen...</b>\n\n"
                f"Procesando {count} noticias con IA...",
                parse_mode="HTML"
            )
            
            summary = await self.intel_module.generate_news_summary(user_id, density_level=density)
            
            if not summary:
                from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
                await query.edit_message_text(
                    "⚠️ No se pudo generar el resumen.\n\n"
                    "Intenta nuevamente.",
                    reply_markup=get_back_to_dashboard_keyboard()
                )
                return
            
            # Enviar resumen con botón de navegación
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            
            # Dividir mensaje si es muy largo
            if len(summary) > 4000:
                chunks = [summary[i:i+4000] for i in range(0, len(summary), 4000)]
                for i, chunk in enumerate(chunks):
                    if i == len(chunks) - 1:
                        # Último chunk con botón
                        await context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=chunk,
                            parse_mode="Markdown",
                            reply_markup=get_back_to_dashboard_keyboard()
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=chunk,
                            parse_mode="Markdown"
                        )
                        await asyncio.sleep(0.5)
            else:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=summary,
                    parse_mode="Markdown",
                    reply_markup=get_back_to_dashboard_keyboard()
                )
            
            # Eliminar mensaje de procesamiento
            await query.delete_message()
            
            console.print(f"[success]✅ News briefing ({density}) sent to user {user_id}[/success]")
            
        except Exception as e:
            logger.error(f"Error generating news briefing: {e}", exc_info=True)
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await query.edit_message_text(
                "⚠️ Error al generar el informe de noticias.\n\n"
                "Por favor, inténtalo nuevamente.",
                reply_markup=get_back_to_dashboard_keyboard()
            )
    
    async def _handle_ingest_menu(self, query, context):
        """Muestra el menú de ingesta de datos (PDF/YouTube)"""
        keyboard = [[InlineKeyboardButton("🏠 Volver al Panel", callback_data="main_menu")]]
        
        message = (
            "📂 <b>Protocolo de Ingesta de Datos.</b>\n\n"
            "Para añadir nueva información a mi base de conocimiento, proceda de una de las siguientes formas:\n\n"
            "<b>1. Archivos:</b> Envíe un PDF y escriba <code>/ingest</code> en el comentario (caption), o simplemente envíe el archivo.\n\n"
            "<b>2. YouTube:</b> Use el comando: <code>/ingest &lt;URL_DEL_VIDEO&gt;</code>\n\n"
            "<b>3. Directo:</b> Simplemente pegue el enlace de YouTube en el chat.\n\n"
            "<i>Sistemas de reconocimiento a la espera de datos...</i>"
        )
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _handle_system_status(self, query, context, user_id):
        """Muestra el estado del sistema y comandos disponibles"""
        # Verificar estado de Google Calendar
        has_calendar = self.google_auth_service.has_valid_credentials(user_id)
        calendar_status = "✅ Conectado" if has_calendar else "❌ No conectado"
        
        keyboard = [[InlineKeyboardButton("🔙 Volver al Menú", callback_data="back_to_menu")]]
        
        message = (
            "⚙️ <b>Estado del Sistema JARVIS</b>\n\n"
            "<b>📊 Módulos Activos:</b>\n"
            f"  • Google Calendar: {calendar_status}\n"
            "  • Base de Conocimiento: ✅ Activa\n"
            "  • Módulo de Noticias: ✅ Activo\n"
            "  • Generador de Quizzes: ✅ Activo\n"
            "  • Generador de CheatSheets: ✅ Activo\n\n"
            "<b>📝 Comandos Disponibles:</b>\n"
            "  • <code>/help</code> - Ver todos los comandos\n"
            "  • <code>/stats</code> - Estadísticas de biblioteca\n"
            "  • <code>/topics</code> - Ver temas de noticias\n"
            "  • <code>/set_daily</code> - Activar briefing diario\n\n"
            "💡 <i>Todos los sistemas operativos, Señor.</i>"
        )
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    def get_callback_handler(self):
        """Retorna el CallbackQueryHandler para registrar en main.py"""
        return CallbackQueryHandler(self.handle_callback)
