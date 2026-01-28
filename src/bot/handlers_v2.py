from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ChatAction
from src.services.auth_service import AuthService
from src.modules.library import LibraryModule
from src.modules.intel import IntelModule
from src.modules.hq import HQModule
from src.utils.rate_limiter import TelegramRateLimiter
from src.utils.error_handler import handle_errors
from src.utils.logger import get_logger
from src.bot.command_registry import command_registry
from typing import Optional
import asyncio

logger = get_logger("bot_handlers")


class BotHandlers:
    def __init__(
        self,
        auth_service: AuthService,
        library_module: LibraryModule,
        intel_module: IntelModule,
        hq_module: HQModule
    ):
        self.auth_service = auth_service
        self.library_module = library_module
        self.intel_module = intel_module
        self.hq_module = hq_module
        self.telegram_rate_limiter = TelegramRateLimiter(max_messages_per_minute=20)
    
    @handle_errors
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"User {update.effective_user.id} started the bot")
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            await update.message.reply_text("❌ Error de autenticación.")
    
    @handle_errors
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        help_text = command_registry.get_help_text()
        await update.message.reply_text(help_text, parse_mode="Markdown")
        logger.info(f"Help command sent to user {update.effective_user.id}")
    
    @handle_errors
    async def ingest_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Comando unificado de ingesta. Maneja 4 casos:
        1. URL en argumentos: /ingest <URL>
        2. Archivo adjunto: PDF con /ingest en caption
        3. Referencia (reply): /ingest respondiendo a mensaje con archivo/link
        4. Sin datos: Muestra ayuda
        """
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        # CASO 1: URL en argumentos
        if context.args:
            url = " ".join(context.args)
            
            # Detectar si es una URL de YouTube
            if "youtube.com" in url or "youtu.be" in url:
                await self._process_youtube_url(update, context, user_id, url)
                return
            else:
                await update.message.reply_text(
                    "⚠️ <b>URL no reconocida.</b>\n\n"
                    "Actualmente solo soporto URLs de YouTube.\n\n"
                    "<b>Formato correcto:</b>\n"
                    "<code>/ingest https://youtube.com/watch?v=...</code>",
                    parse_mode="HTML"
                )
                return
        
        # CASO 2: Archivo adjunto en el mismo mensaje
        if update.message.document:
            await self.handle_document(update, context)
            return
        
        # CASO 3: Referencia (reply) a mensaje anterior
        if update.message.reply_to_message:
            replied_msg = update.message.reply_to_message
            
            # Verificar si el mensaje tiene archivo
            if replied_msg.document:
                # Procesar el documento del mensaje referenciado
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
                
                document = replied_msg.document
                if document.mime_type == "application/pdf":
                    await update.message.reply_text("📥 Descargando y procesando PDF...")
                    logger.info(f"Processing PDF from reply: {document.file_name} for user {update.effective_user.id}")
                    
                    file = await context.bot.get_file(document.file_id)
                    file_bytes = await file.download_as_bytearray()
                    
                    result = await self.library_module.ingest_pdf(
                        user_id=user_id,
                        file_bytes=bytes(file_bytes),
                        filename=document.file_name
                    )
                    
                    if result["success"]:
                        await update.message.reply_text(
                            f"✅ <b>Documento procesado.</b>\n\n"
                            f"� {result['filename']}\n"
                            f"📖 {result['pages']} páginas procesadas\n"
                            f"🔢 {result['chunks']} fragmentos indexados",
                            parse_mode="HTML"
                        )
                    else:
                        await update.message.reply_text(
                            f"❌ Error al procesar documento: {result.get('error')}",
                            parse_mode="HTML"
                        )
                    return
            
            # Verificar si el mensaje tiene texto con URL de YouTube
            if replied_msg.text:
                text = replied_msg.text
                if "youtube.com" in text or "youtu.be" in text:
                    await self._process_youtube_url(update, context, user_id, text)
                    return
            
            # Si no tiene ni archivo ni URL
            await update.message.reply_text(
                "⚠️ <b>Mensaje sin datos procesables.</b>\n\n"
                "El mensaje al que respondes no contiene un PDF ni una URL de YouTube.",
                parse_mode="HTML"
            )
            return
        
        # CASO 4: Sin datos - Mostrar ayuda
        await update.message.reply_text(
            "⚠️ <b>Datos insuficientes.</b>\n\n"
            "Por favor, adjunte un archivo o indique una URL después del comando.\n\n"
            "<b>Ejemplos de uso:</b>\n"
            "• <code>/ingest</code> + adjuntar PDF\n"
            "• <code>/ingest https://youtube.com/watch?v=...</code>\n"
            "• Responder a un mensaje con <code>/ingest</code>\n\n"
            "<b>O simplemente:</b>\n"
            "• Envíe un PDF directamente\n"
            "• Pegue un enlace de YouTube",
            parse_mode="HTML"
        )
        logger.info(f"User {update.effective_user.id} requested ingest help")
    
    @handle_errors
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        # Show typing indicator while processing document
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        if not update.message.document:
            return
        
        document = update.message.document
        
        if document.mime_type == "application/pdf":
            await update.message.reply_text("📥 Descargando y procesando PDF...")
            logger.info(f"Processing PDF: {document.file_name} for user {update.effective_user.id}")
            
            file = await context.bot.get_file(document.file_id)
            file_bytes = await file.download_as_bytearray()
            
            result = await self.library_module.ingest_pdf(
                user_id=user_id,
                file_bytes=bytes(file_bytes),
                filename=document.file_name
            )
            
            if result["success"]:
                # Generar confirmación dinámica
                ai_confirmation = await self.library_module.ollama_service.get_jarvis_response(
                    "document_indexed",
                    f"Documento {result['filename']} con {result['pages']} páginas indexado"
                )
                await update.message.reply_text(
                    f"✅ **{ai_confirmation}**\n\n"
                    f"📄 {result['filename']}\n"
                    f"📖 {result['pages']} páginas procesadas\n"
                    f"🔢 {result['chunks']} fragmentos indexados"
                )
                logger.info(f"PDF indexed successfully: {document.file_name}")
                
                # Enviar menú principal para continuar navegando
                from src.bot.menu_handler import get_main_menu_keyboard
                # Mensaje dinámico para el menú
                menu_msg = await self.library_module.ollama_service.get_jarvis_response(
                    "query_complete",
                    "Documento procesado"
                )
                await update.message.reply_text(
                    f"🏠 {menu_msg}",
                    parse_mode="Markdown",
                    reply_markup=get_main_menu_keyboard()
                )
            else:
                # Generar mensaje de error dinámico
                ai_error = await self.library_module.ollama_service.get_jarvis_response(
                    "document_error",
                    f"Error al procesar documento: {result['error']}"
                )
                await update.message.reply_text(
                    f"❌ {ai_error}"
                )
                logger.error(f"PDF processing failed: {result.get('error')}")
        else:
            await update.message.reply_text(
                "⚠️ Por favor, envía un archivo PDF válido."
            )
    
    async def _process_youtube_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, url: str):
        """Procesa una URL de YouTube y la ingesta en la base de conocimiento"""
        # Mensaje inicial estilo JARVIS
        await update.message.reply_text(
            "🎬 <b>Enlace visual detectado.</b>\n\n"
            "Iniciando extracción de datos del flujo de vídeo...",
            parse_mode="HTML"
        )
        
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        logger.info(f"Processing YouTube URL: {url} for user {update.effective_user.id}")
        
        # Procesar el video
        result = await self.library_module.ingest_youtube_video(user_id, url)
        
        if result["success"]:
            # Mensaje de éxito estilo JARVIS (diferente para videos largos)
            if result.get("is_long", False):
                message = (
                    "✅ <b>Video extenso procesado.</b>\n\n"
                    f"He fragmentado la transcripción en <b>{result['chunks']} partes</b> y las he almacenado en la memoria.\n\n"
                    f"📺 <b>Título:</b> {result.get('title', 'Sin título')}\n"
                    f"🎬 <b>Video ID:</b> <code>{result['video_id']}</code>\n\n"
                    f"💬 Puede interrogarme sobre él usando <code>/ask</code>"
                )
            else:
                message = (
                    "✅ <b>Video asimilado.</b>\n\n"
                    f"El contenido ha sido transcrito y añadido a su base de conocimiento.\n\n"
                    f"📺 <b>Título:</b> {result.get('title', 'Sin título')}\n"
                    f"🎬 <b>Video ID:</b> <code>{result['video_id']}</code>\n"
                    f"📊 {result['chunks']} fragmentos procesados\n\n"
                    f"💬 Puede interrogarme sobre él usando <code>/ask</code>"
                )
            
            await update.message.reply_text(message, parse_mode="HTML")
            logger.info(f"YouTube video indexed successfully: {result['video_id']} ({result['chunks']} chunks)")
            
            # Enviar botón de navegación
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await update.message.reply_text(
                "💡 ¿Desea realizar otra operación?",
                reply_markup=get_back_to_dashboard_keyboard()
            )
        else:
            # Manejo de errores específicos
            if result.get("error") == "no_transcript":
                await update.message.reply_text(
                    "⚠️ <b>Imposible procesar.</b>\n\n"
                    "Este video carece de subtítulos accesibles para mi sistema actual.\n\n"
                    "💡 Intente con otro video que tenga transcripciones disponibles.",
                    parse_mode="HTML"
                )
            elif result.get("error") == "invalid_url":
                await update.message.reply_text(
                    "❌ <b>URL inválida.</b>\n\n"
                    f"{result['message']}\n\n"
                    "💡 Asegúrese de enviar una URL válida de YouTube.",
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    f"❌ <b>Error al procesar video.</b>\n\n"
                    f"{result['message']}",
                    parse_mode="HTML"
                )
            logger.error(f"YouTube processing failed: {result.get('error')}")
            
            # Botón de navegación incluso en error
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await update.message.reply_text(
                "💡 ¿Desea intentar con otro contenido?",
                reply_markup=get_back_to_dashboard_keyboard()
            )
    
    @handle_errors
    async def ask_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        # Show typing indicator while searching and generating answer
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        if not context.args:
            await update.message.reply_text(
                "❓ Uso: /ask <tu pregunta>\n"
                "Ejemplo: /ask ¿Qué es machine learning?"
            )
            return
        
        question = " ".join(context.args)
        
        # Generar mensaje dinámico de procesamiento
        processing_msg = await self.library_module.ollama_service.get_jarvis_response(
            "query_processing",
            f"Consultando sobre: {question}"
        )
        await update.message.reply_text(f"🔍 {processing_msg}")
        logger.info(f"User {update.effective_user.id} asked: {question}")
        
        answer = await self.library_module.ask(user_id, question)
        
        # Enviar respuesta con botón de navegación
        from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
        await update.message.reply_text(
            answer, 
            parse_mode="Markdown",
            reply_markup=get_back_to_dashboard_keyboard()
        )
    
    @handle_errors
    async def quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        await update.message.reply_text("🎯 Generando quiz...")
        logger.info(f"Generating quiz for user {update.effective_user.id}")
        
        quiz = await self.library_module.generate_quiz(user_id)
        
        await update.message.reply_text(quiz)
    
    @handle_errors
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        stats = self.library_module.get_library_stats(user_id)
        
        message = (
            "📊 *Estadísticas de tu Biblioteca*\n\n"
            f"📄 Documentos: {stats['documents']}\n"
            f"📚 Total: {stats['total']}"
        )
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
    @handle_errors
    async def snipe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Herramienta de precisión quirúrgica para noticias.
        Flujo: /snipe <tema> -> Selector de objetivos -> Selector de formato -> Ejecución
        """
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        # Verificar que tenga suscripciones
        topics = self.intel_module.get_user_subscriptions(user_id)
        if not topics:
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await update.message.reply_text(
                "⚠️ No tienes temas suscritos.\n\n"
                "Usa `/subscribe <tema>` para suscribirte a temas de interés.",
                parse_mode="Markdown",
                reply_markup=get_back_to_dashboard_keyboard()
            )
            return
        
        # Determinar tema objetivo
        if context.args:
            target_topic = " ".join(context.args).lower()
            # Buscar tema que coincida
            matching_topic = None
            for topic in topics:
                if target_topic in topic.lower() or topic.lower() in target_topic:
                    matching_topic = topic
                    break
            
            if not matching_topic:
                await update.message.reply_text(
                    f"⚠️ <b>Objetivo no encontrado.</b>\n\n"
                    f"Tema '<i>{target_topic}</i>' no está en sus suscripciones.\n\n"
                    f"<b>Temas disponibles:</b>\n" + "\n".join([f"  • {t}" for t in topics]),
                    parse_mode="HTML"
                )
                return
            
            topic = matching_topic
        else:
            # Usar primer tema por defecto
            topic = topics[0]
        
        # Obtener noticias del cache
        news_items = self.intel_module.news_buffer.get(topic, [])
        
        if not news_items:
            await update.message.reply_text(
                f"⚠️ <b>Buffer vacío.</b>\n\n"
                f"No hay noticias cargadas para '<i>{topic}</i>'.\n\n"
                f"Intente con <code>/subscribe {topic}</code> para recargar.",
                parse_mode="HTML"
            )
            return
        
        # Mostrar top 5 noticias
        await self._show_snipe_targets(update, topic, news_items[:5])
        logger.info(f"User {update.effective_user.id} initiated snipe for topic: {topic}")
    
    async def _show_snipe_targets(self, update, topic: str, news_items: list):
        """Paso 1: Mostrar selector de objetivos (titulares)"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = []
        for i, item in enumerate(news_items):
            # Recortar título a 60 chars para que quepa en botón
            title = item['title'][:60] + "..." if len(item['title']) > 60 else item['title']
            keyboard.append([
                InlineKeyboardButton(
                    f"🎯 {i+1}. {title}",
                    callback_data=f"snipe_select|{i}|{topic}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="main_menu")])
        
        message = (
            f"🎯 <b>Blancos detectados en sector [{topic.upper()}]:</b>\n\n"
            f"<i>Señor, seleccione el objetivo para adquisición de datos.</i>\n\n"
            f"📊 <b>{len(news_items)} objetivos disponibles</b>"
        )
        
        await update.message.reply_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _handle_snipe_select(self, query, context, callback_data: str):
        """Paso 2: Mostrar selector de formato (munición)"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        # Parsear callback_data: snipe_select|{index}|{topic}
        parts = callback_data.split("|")
        if len(parts) != 3:
            await query.edit_message_text("❌ Error al procesar selección.")
            return
        
        index = int(parts[1])
        topic = parts[2]
        
        # Obtener noticia del buffer
        news_items = self.intel_module.news_buffer.get(topic, [])
        if index >= len(news_items):
            await query.edit_message_text("❌ Objetivo no disponible.")
            return
        
        news_item = news_items[index]
        
        # Mostrar selector de formato
        keyboard = [
            [
                InlineKeyboardButton("🔗 Solo Link", callback_data=f"snipe_action|link|{index}|{topic}"),
                InlineKeyboardButton("⚡ Resumen Flash", callback_data=f"snipe_action|flash|{index}|{topic}")
            ],
            [
                InlineKeyboardButton("🧐 Informe Decente", callback_data=f"snipe_action|deep|{index}|{topic}")
            ],
            [
                InlineKeyboardButton("🔙 Volver a Lista", callback_data=f"snipe_list|{topic}")
            ]
        ]
        
        message = (
            f"🔒 <b>Objetivo fijado:</b>\n\n"
            f"<i>{news_item['title']}</i>\n\n"
            f"🎯 Seleccione calibre de extracción:"
        )
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def _handle_snipe_action(self, query, context, callback_data: str):
        """Paso 3: Ejecutar acción según formato seleccionado"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
        
        # Parsear callback_data: snipe_action|{format}|{index}|{topic}
        parts = callback_data.split("|")
        if len(parts) != 4:
            await query.edit_message_text("❌ Error al procesar acción.")
            return
        
        format_type = parts[1]
        index = int(parts[2])
        topic = parts[3]
        
        # Obtener noticia del buffer
        news_items = self.intel_module.news_buffer.get(topic, [])
        if index >= len(news_items):
            await query.edit_message_text("❌ Objetivo no disponible.")
            return
        
        news_item = news_items[index]
        
        # Mostrar indicador de procesamiento
        await query.edit_message_text(
            f"🔄 <b>Extrayendo datos...</b>\n\n"
            f"<i>Procesando objetivo con calibre '{format_type.upper()}'</i>",
            parse_mode="HTML"
        )
        
        # Ejecutar según formato
        if format_type == "link":
            result = (
                f"🔗 <b>Enlace establecido:</b>\n\n"
                f"<b>{news_item['title']}</b>\n\n"
                f"🌐 {news_item['url']}"
            )
        
        elif format_type == "flash":
            # Generar resumen flash con LLM
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
            
            prompt = (
                f"Genera un resumen ultra-conciso (máximo 2 frases o 3 bullet points) de esta noticia:\n\n"
                f"Título: {news_item['title']}\n"
                f"Contenido: {news_item.get('content', news_item['title'])}"
            )
            
            summary = await self.intel_module.ollama_service.generate_response(prompt)
            
            result = (
                f"⚡ <b>Resumen Flash:</b>\n\n"
                f"<b>{news_item['title']}</b>\n\n"
                f"{summary}\n\n"
                f"🔗 {news_item['url']}"
            )
        
        elif format_type == "deep":
            # Generar informe profundo con LLM
            await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
            
            prompt = (
                f"Genera un análisis detallado (2-3 párrafos bien estructurados) de esta noticia. "
                f"Incluye contexto, implicaciones y por qué es relevante:\n\n"
                f"Título: {news_item['title']}\n"
                f"Contenido: {news_item.get('content', news_item['title'])}"
            )
            
            analysis = await self.intel_module.ollama_service.generate_response(prompt)
            
            result = (
                f"🧐 <b>Informe Decente:</b>\n\n"
                f"<b>{news_item['title']}</b>\n\n"
                f"{analysis}\n\n"
                f"🔗 {news_item['url']}"
            )
        
        # Botones de navegación
        keyboard = [
            [
                InlineKeyboardButton("🔙 Otra noticia de " + topic[:15], callback_data=f"snipe_list|{topic}"),
                InlineKeyboardButton("🏠 Volver al Panel", callback_data="main_menu")
            ]
        ]
        
        await query.edit_message_text(
            result,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
    
    async def _handle_snipe_list(self, query, context, callback_data: str):
        """Volver a mostrar lista de objetivos para un tema"""
        # Parsear callback_data: snipe_list|{topic}
        parts = callback_data.split("|")
        if len(parts) != 2:
            await query.edit_message_text("❌ Error al procesar.")
            return
        
        topic = parts[1]
        
        # Obtener noticias del cache
        news_items = self.intel_module.news_buffer.get(topic, [])
        
        if not news_items:
            await query.edit_message_text(
                f"⚠️ No hay noticias disponibles para '{topic}'.",
                parse_mode="HTML"
            )
            return
        
        # Mostrar lista de nuevo
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = []
        for i, item in enumerate(news_items[:5]):
            title = item['title'][:60] + "..." if len(item['title']) > 60 else item['title']
            keyboard.append([
                InlineKeyboardButton(
                    f"🎯 {i+1}. {title}",
                    callback_data=f"snipe_select|{i}|{topic}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="main_menu")])
        
        message = (
            f"🎯 <b>Blancos detectados en sector [{topic.upper()}]:</b>\n\n"
            f"<i>Señor, seleccione el objetivo para adquisición de datos.</i>\n\n"
            f"📊 <b>{len(news_items[:5])} objetivos disponibles</b>"
        )
        
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    @handle_errors
    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        if not context.args:
            await update.message.reply_text(
                "📰 **Uso correcto:** `/subscribe <tema>`\n\n"
                "**Ejemplo:** `/subscribe python`\n\n"
                "**Temas disponibles:** Tecnología, Programación, IA, Ciberseguridad, Startups",
                parse_mode="Markdown"
            )
            return
        
        topic = " ".join(context.args)
        
        # Feedback inmediato: Calibrando sensores
        calibration_msg = await update.message.reply_text(
            f"🔄 <b>Calibrando sensores...</b>\n\n"
            f"Iniciando barrido inicial de información sobre '<i>{topic}</i>'.\n"
            f"Espere un momento, Señor...",
            parse_mode="HTML"
        )
        
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        # ACCIÓN BLOQUEANTE: subscribe_topic ahora hace fetch inmediato
        success, message = await self.intel_module.subscribe_topic(user_id, topic)
        
        if success:
            # Generar confirmación dinámica
            ai_confirmation = await self.intel_module.ollama_service.get_jarvis_response(
                "subscription_added",
                f"Suscripción a {topic} configurada y noticias cargadas"
            )
            
            # Obtener número de noticias en buffer
            buffer_count = len(self.intel_module.news_buffer.get(topic, []))
            
            await calibration_msg.edit_text(
                f"✅ <b>Configuración completada.</b>\n\n"
                f"<b>Tema:</b> {topic}\n"
                f"<b>Noticias en buffer:</b> {buffer_count}\n\n"
                f"💬 {ai_confirmation}",
                parse_mode="HTML"
            )
            logger.info(f"User {update.effective_user.id} subscribed to: {topic} ({buffer_count} news cached)")
        elif message == "invalid_domain":
            # Mensaje de JARVIS cuando el tema está fuera del dominio de operaciones
            await update.message.reply_text(
                f"⚠️ **Fuera de rango operativo.**\n\n"
                f"Me temo que mis protocolos de vigilancia están limitados actualmente a fuentes de "
                f"**Tecnología, Desarrollo y Ciencia**.\n\n"
                f"No dispongo de acceso a feeds de datos sobre '{topic}'.\n\n"
                f"**Temas disponibles:**\n"
                f"• Inteligencia Artificial y Machine Learning\n"
                f"• Programación y Desarrollo de Software\n"
                f"• Ciberseguridad y Protección de Datos\n"
                f"• Startups y Emprendimiento Tecnológico\n"
                f"• Cloud Computing y DevOps\n"
                f"• Blockchain y Criptomonedas\n"
                f"• Ciencia e Investigación\n\n"
                f"¿Desea que configure alertas sobre alguno de estos temas en su lugar, Señor?",
                parse_mode="Markdown"
            )
            logger.warning(f"User {update.effective_user.id} attempted to subscribe to invalid topic: {topic}")
        elif message == "already_subscribed":
            await update.message.reply_text(
                f"ℹ️ **Suscripción existente.**\n\n"
                f"Ya está suscrito a: **{topic}**",
                parse_mode="Markdown"
            )
    
    @handle_errors
    async def unsubscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        if not context.args:
            await update.message.reply_text(
                "📰 Uso: /unsubscribe <tema>\n"
                "Ejemplo: /unsubscribe python"
            )
            return
        
        topic = " ".join(context.args)
        
        success = await self.intel_module.unsubscribe_topic(user_id, topic)
        
        if success:
            await update.message.reply_text(f"✅ Desuscrito de: {topic}")
            logger.info(f"User {update.effective_user.id} unsubscribed from: {topic}")
        else:
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await update.message.reply_text(
                f"⚠️ No estás suscrito a: {topic}",
                reply_markup=get_back_to_dashboard_keyboard()
            )
    
    @handle_errors
    async def topics_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        topics = self.intel_module.get_user_subscriptions(user_id)
        
        if not topics:
            await update.message.reply_text(
                "📰 No tienes suscripciones activas.\n"
                "Usa /subscribe <tema> para suscribirte."
            )
            return
        
        message = "📰 *Tus Suscripciones:*\n\n" + "\n".join([f"• {topic}" for topic in topics])
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
    @handle_errors
    async def add_task_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        if not context.args:
            await update.message.reply_text(
                "📝 Uso: /add <tarea>\n"
                "Ejemplo: /add Reunión mañana a las 3pm"
            )
            return
        
        task_text = " ".join(context.args)
        
        await update.message.reply_text("⏳ Procesando tarea...")
        logger.info(f"User {update.effective_user.id} adding task: {task_text}")
        
        task = await self.hq_module.add_task(
            user_id=user_id,
            title=task_text,
            deadline_text=task_text,
            notify_enabled=True
        )
        
        message = f"✅ Tarea añadida: {task.title}"
        
        if task.deadline:
            message += f"\n📅 Fecha límite: {task.deadline.strftime('%Y-%m-%d %H:%M')}"
        
        await update.message.reply_text(message)
    
    @handle_errors
    async def list_tasks_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        tasks = self.hq_module.list_tasks(user_id)
        
        if not tasks:
            await update.message.reply_text(
                "📋 No tienes tareas pendientes.\n"
                "Usa /add para añadir una tarea."
            )
            return
        
        message = "📋 *Tus Tareas:*\n\n"
        
        for task in tasks:
            status = "✅" if task.completed else "⏳"
            message += f"{status} *[{task.id}]* {task.title}\n"
            
            if task.deadline:
                message += f"   📅 {task.deadline.strftime('%Y-%m-%d %H:%M')}\n"
            
            message += "\n"
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
    @handle_errors
    async def done_task_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        if not context.args:
            await update.message.reply_text(
                "✅ Uso: /done <id>\n"
                "Ejemplo: /done 1"
            )
            return
        
        try:
            task_id = int(context.args[0])
        except ValueError:
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await update.message.reply_text(
                "❌ ID de tarea inválido.",
                reply_markup=get_back_to_dashboard_keyboard()
            )
            return
        
        success = self.hq_module.mark_task_completed(user_id, task_id)
        
        if success:
            await update.message.reply_text("✅ Tarea completada!")
            logger.info(f"User {update.effective_user.id} completed task {task_id}")
        else:
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await update.message.reply_text(
                "❌ Tarea no encontrada.",
                reply_markup=get_back_to_dashboard_keyboard()
            )
    
    @handle_errors
    async def delete_task_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        if not context.args:
            await update.message.reply_text(
                "🗑️ Uso: /delete <id>\n"
                "Ejemplo: /delete 1"
            )
            return
        
        try:
            task_id = int(context.args[0])
        except ValueError:
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await update.message.reply_text(
                "❌ ID de tarea inválido.",
                reply_markup=get_back_to_dashboard_keyboard()
            )
            return
        
        success = self.hq_module.delete_task(user_id, task_id)
        
        if success:
            await update.message.reply_text("🗑️ Tarea eliminada!")
            logger.info(f"User {update.effective_user.id} deleted task {task_id}")
        else:
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await update.message.reply_text(
                "❌ Tarea no encontrada.",
                reply_markup=get_back_to_dashboard_keyboard()
            )
    
    @handle_errors
    async def set_daily_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Activa el Daily Briefing matutino para el usuario"""
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        from src.jobs.briefing import add_briefing_chat, is_briefing_enabled
        
        chat_id = update.effective_chat.id
        
        # Verificar si ya está activado
        if is_briefing_enabled(chat_id):
            await update.message.reply_text(
                "ℹ️ **Daily Briefing ya configurado.**\n\n"
                "Su informe diario está programado para las 08:00 horas.\n\n"
                "Si desea desactivarlo, use `/cancel_daily`.",
                parse_mode="Markdown"
            )
            return
        
        # Activar el briefing
        success = add_briefing_chat(chat_id)
        
        if success:
            # Generar confirmación dinámica
            ai_confirmation = await self.library_module.ollama_service.get_jarvis_response(
                "briefing_activated",
                "Briefing diario programado para las 08:00 horas"
            )
            await update.message.reply_text(
                f"⏰ **{ai_confirmation}**\n\n"
                "El briefing incluirá:\n"
                "• 📅 Eventos de su agenda del día\n"
                "• 📰 Resumen de noticias prioritarias",
                parse_mode="Markdown"
            )
            logger.info(f"Daily briefing enabled for chat {chat_id}")
        else:
            await update.message.reply_text(
                "❌ Error al configurar el briefing diario."
            )
    
    @handle_errors
    async def cancel_daily_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Desactiva el Daily Briefing matutino"""
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        from src.jobs.briefing import remove_briefing_chat, is_briefing_enabled
        
        chat_id = update.effective_chat.id
        
        if not is_briefing_enabled(chat_id):
            await update.message.reply_text(
                "ℹ️ **No hay briefing configurado.**\n\n"
                "Use `/set_daily` para activar el informe matutino.",
                parse_mode="Markdown"
            )
            return
        
        success = remove_briefing_chat(chat_id)
        
        if success:
            # Generar confirmación dinámica
            ai_confirmation = await self.library_module.ollama_service.get_jarvis_response(
                "briefing_deactivated",
                "Briefing diario desactivado"
            )
            await update.message.reply_text(
                f"✅ {ai_confirmation}",
                parse_mode="Markdown"
            )
            logger.info(f"Daily briefing disabled for chat {chat_id}")
        else:
            await update.message.reply_text(
                "❌ Error al desactivar el briefing."
            )
    
    @handle_errors
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        text = update.message.text
        
        # Detectar URLs de YouTube
        if "youtube.com" in text or "youtu.be" in text:
            # Feedback de JARVIS
            await update.message.reply_text(
                "🎥 <b>Enlace detectado.</b>\n\n"
                "Descargando transcripción y vectorizando contenido...\n"
                "<i>(Esto puede tomar unos segundos)</i>",
                parse_mode="HTML"
            )
            
            # Procesar URL de YouTube
            await self._process_youtube_url(update, context, user_id, text)
            return
        
        # Si no es YouTube, ignorar (placeholder para futuras funcionalidades)
        pass
    
    def get_handlers(self):
        return [
            CommandHandler("start", self.start_command),
            CommandHandler("help", self.help_command),
            CommandHandler("ingest", self.ingest_command),
            CommandHandler("ask", self.ask_command),
            CommandHandler("stats", self.stats_command),
            CommandHandler("snipe", self.snipe_command),
            CommandHandler("subscribe", self.subscribe_command),
            CommandHandler("unsubscribe", self.unsubscribe_command),
            CommandHandler("topics", self.topics_command),
            CommandHandler("set_daily", self.set_daily_command),
            CommandHandler("cancel_daily", self.cancel_daily_command),
            MessageHandler(filters.Document.ALL, self.handle_document),
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message),
        ]
