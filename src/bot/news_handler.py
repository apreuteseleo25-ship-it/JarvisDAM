"""
News Handler - Maneja el comando /snipe con menú interactivo de noticias.
Sistema robusto con selección de titulares y lectura individual.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from src.services.auth_service import AuthService
from src.modules.intel_manager import IntelManager
from src.utils.error_handler import handle_errors
from src.utils.logger import get_logger

logger = get_logger("news_handler")


class NewsHandler:
    def __init__(self, auth_service: AuthService, intel_manager: IntelManager):
        self.auth_service = auth_service
        self.intel_manager = intel_manager
    
    @handle_errors
    async def snipe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Comando /snipe [tema] - Muestra menú interactivo con 5 titulares más recientes.
        Si no se especifica tema, usa el primer tema suscrito.
        """
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        # Determinar tema
        if context.args:
            topic = " ".join(context.args)
        else:
            # Usar primer tema suscrito
            subscriptions = self.intel_manager.get_user_subscriptions(user_id)
            if not subscriptions:
                await update.message.reply_text(
                    "⚠️ No tienes temas suscritos.\n\n"
                    "Usa `/subscribe <tema>` para suscribirte a un tema.",
                    parse_mode="Markdown"
                )
                return
            topic = subscriptions[0]
        
        # Validar tema
        if not self.intel_manager.validate_topic(topic):
            await update.message.reply_text(
                f"⚠️ El tema '{topic}' está fuera de mi dominio de operaciones.\n\n"
                "Solo puedo proporcionar noticias sobre tecnología, programación, IA, ciberseguridad, etc.",
                parse_mode="Markdown"
            )
            return
        
        # Verificar si el caché está desactualizado
        if self.intel_manager.is_cache_stale(context, topic):
            status_msg = await update.message.reply_text("🔄 Recopilando inteligencia reciente...")
            
            # Forzar actualización síncrona
            await self.intel_manager.update_topic_cache(context, topic)
            
            await status_msg.delete()
        
        # Obtener noticias del caché
        news = self.intel_manager.get_cached_news(context, topic)
        
        if not news:
            await update.message.reply_text(
                f"❌ No se encontraron noticias para '{topic}'.\n\n"
                "Intenta con otro tema o espera a que se actualice el caché.",
                parse_mode="Markdown"
            )
            return
        
        # Separar noticias por categoría
        breaking = [n for n in news if n.get('categoria') == 'breaking']
        recent = [n for n in news if n.get('categoria') == 'recent']
        popular = [n for n in news if n.get('categoria') == 'popular']
        
        # Mostrar menú de selección de categoría
        await self._show_category_selection(update, context, topic, breaking, recent, popular)
    
    async def _show_category_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str, breaking: list, recent: list, popular: list):
        """Muestra menú de selección de categoría temporal"""
        message_text = f"📡 **Radar de Noticias: {topic.upper()}**\n\n"
        message_text += "Selecciona una categoría:\n\n"
        
        # Mostrar estadísticas de cada categoría
        if breaking:
            message_text += f"🔴 **Última Hora** - {len(breaking)} noticias (últimas 24h)\n"
        else:
            message_text += f"🔴 **Última Hora** - Sin noticias recientes\n"
        
        if recent:
            message_text += f"🟡 **Esta Semana** - {len(recent)} noticias (últimos 7 días)\n"
        else:
            message_text += f"🟡 **Esta Semana** - Sin noticias\n"
        
        if popular:
            message_text += f"🟢 **Populares** - {len(popular)} noticias (último mes)\n"
        else:
            message_text += f"🟢 **Populares** - Sin noticias\n"
        
        # Crear botones de categoría (siempre mostrar todas las opciones)
        keyboard = [
            [InlineKeyboardButton(
                f"🔴 Última Hora ({len(breaking)})",
                callback_data=f"category_breaking|{topic}"
            )],
            [InlineKeyboardButton(
                f"🟡 Esta Semana ({len(recent)})",
                callback_data=f"category_recent|{topic}"
            )],
            [InlineKeyboardButton(
                f"🟢 Populares ({len(popular)})",
                callback_data=f"category_popular|{topic}"
            )],
            [InlineKeyboardButton("🏠 Panel Principal", callback_data="main_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        elif update.callback_query:
            await update.callback_query.edit_message_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    
    async def _show_news_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str, category: str, news: list):
        """Muestra menú interactivo con titulares de una categoría específica"""
        # Mapeo de categorías a nombres y emojis
        category_info = {
            'breaking': ('🔴 Última Hora', '🔴'),
            'recent': ('🟡 Esta Semana', '🟡'),
            'popular': ('🟢 Populares', '🟢')
        }
        
        category_name, category_emoji = category_info.get(category, ('Noticias', '📌'))
        
        message_text = f"📡 **{topic.upper()} - {category_name}**\n\n"
        message_text += f"Mostrando {len(news)} noticias:\n\n"
        
        # Crear teclado con titulares traducidos
        keyboard = []
        
        for i, item in enumerate(news):
            # Usar título traducido si existe, sino el original
            title = item.get('titulo_es', item['titulo'])
            
            # Emoji de prioridad solo si es alta
            priority = item.get('prioridad', 3)
            priority_emoji = "🔥" * priority if priority >= 4 else ""
            
            # Truncar título si es muy largo
            if len(title) > 50:
                title = title[:47] + "..."
            
            button = InlineKeyboardButton(
                text=f"{title} {priority_emoji}",
                callback_data=f"read_news|{i}|{topic}|{category}"
            )
            keyboard.append([button])
        
        # Botones de navegación
        keyboard.append([
            InlineKeyboardButton("🔙 Categorías", callback_data=f"back_to_categories|{topic}"),
            InlineKeyboardButton("🏠 Panel", callback_data="main_menu")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        elif update.callback_query:
            await update.callback_query.edit_message_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    
    @handle_errors
    async def handle_category_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja la selección de categoría temporal"""
        query = update.callback_query
        await query.answer()
        
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        try:
            _, category, topic = query.data.split("|", 2)
        except:
            await query.edit_message_text("❌ Error al procesar la solicitud.")
            return
        
        # Obtener todas las noticias del caché
        all_news = self.intel_manager.get_cached_news(context, topic)
        
        if not all_news:
            await query.edit_message_text("❌ No se encontraron noticias.")
            return
        
        # Filtrar por categoría seleccionada
        filtered_news = [n for n in all_news if n.get('categoria') == category]
        
        if not filtered_news:
            await query.edit_message_text(f"❌ No hay noticias en esta categoría.")
            return
        
        # Mostrar menú de noticias de la categoría
        await self._show_news_menu(update, context, topic, category, filtered_news[:10])
    
    @handle_errors
    async def handle_news_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja callbacks de selección de noticias"""
        query = update.callback_query
        await query.answer()
        
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        # Parsear callback_data: read_news|{index}|{topic}|{category}
        try:
            parts = query.data.split("|")
            index = int(parts[1])
            topic = parts[2]
            category = parts[3] if len(parts) > 3 else 'recent'
        except:
            await query.edit_message_text("❌ Error al procesar la solicitud.")
            return
        
        # Obtener noticia del caché
        all_news = self.intel_manager.get_cached_news(context, topic)
        
        # Filtrar por categoría
        news = [n for n in all_news if n.get('categoria') == category] if category else all_news
        
        if not news or index >= len(news):
            await query.edit_message_text("❌ Noticia no encontrada.")
            return
        
        news_item = news[index]
        
        # Usar título traducido si existe
        title = news_item.get('titulo_es', news_item['titulo'])
        priority = news_item.get('prioridad', 3)
        priority_text = "🔥" * priority if priority >= 4 else ""
        
        # Formatear mensaje de lectura
        message_text = f"📰 **{title}** {priority_text}\n\n"
        message_text += f"📝 {news_item['resumen']}\n\n"
        message_text += f"🗓️ {news_item['fecha'][:10]}"
        
        # Crear teclado con opciones
        keyboard = [
            [
                InlineKeyboardButton("⚡ Resumen Flash", callback_data=f"summary_flash|{index}|{topic}"),
                InlineKeyboardButton("🔍 Resumen Deep", callback_data=f"summary_deep|{index}|{topic}")
            ],
            [InlineKeyboardButton("🔗 Link Original", url=news_item['link'])],
            [InlineKeyboardButton("🔙 Categorías", callback_data=f"back_to_categories|{topic}")],
            [InlineKeyboardButton("🏠 Panel Principal", callback_data="main_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    
    @handle_errors
    async def handle_back_to_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Vuelve al menú de selección de categorías"""
        query = update.callback_query
        await query.answer()
        
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        try:
            _, topic = query.data.split("|", 1)
        except:
            await query.edit_message_text("❌ Error al procesar la solicitud.")
            return
        
        # Obtener noticias del caché
        news = self.intel_manager.get_cached_news(context, topic)
        
        if not news:
            await query.edit_message_text("❌ No se encontraron noticias.")
            return
        
        # Separar por categorías
        breaking = [n for n in news if n.get('categoria') == 'breaking']
        recent = [n for n in news if n.get('categoria') == 'recent']
        popular = [n for n in news if n.get('categoria') == 'popular']
        
        # Mostrar menú de categorías
        await self._show_category_selection(update, context, topic, breaking, recent, popular)
    
    @handle_errors
    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /subscribe <tema> - Suscribe a un tema de noticias"""
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        if not context.args:
            await update.message.reply_text(
                "📡 **Uso:** `/subscribe <tema>`\n\n"
                "**Ejemplos:**\n"
                "• `/subscribe ia`\n"
                "• `/subscribe programacion`\n"
                "• `/subscribe ciberseguridad`",
                parse_mode="Markdown"
            )
            return
        
        topic = " ".join(context.args)
        
        success, message = await self.intel_manager.subscribe_topic(user_id, topic)
        
        if success:
            # Forzar actualización inmediata del caché para este tema
            await update.message.reply_text("🔄 Recopilando inteligencia inicial...")
            await self.intel_manager.update_topic_cache(context, topic)
            
            await update.message.reply_text(
                f"✅ Suscrito a noticias de **{topic}**.\n\n"
                f"Usa `/snipe {topic}` para ver las últimas noticias.",
                parse_mode="Markdown"
            )
        elif message == "invalid_domain":
            await update.message.reply_text(
                f"⚠️ El tema '{topic}' está fuera de mi dominio de operaciones.\n\n"
                "Solo puedo proporcionar noticias sobre tecnología, programación, IA, ciberseguridad, etc."
            )
        elif message == "already_subscribed":
            await update.message.reply_text(f"ℹ️ Ya estás suscrito a '{topic}'.")
        else:
            await update.message.reply_text("❌ Error al procesar la suscripción.")
    
    @handle_errors
    async def unsubscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /unsubscribe <tema> - Desuscribe de un tema"""
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        if not context.args:
            await update.message.reply_text(
                "📡 **Uso:** `/unsubscribe <tema>`",
                parse_mode="Markdown"
            )
            return
        
        topic = " ".join(context.args)
        
        success = self.intel_manager.unsubscribe_topic(user_id, topic)
        
        if success:
            await update.message.reply_text(f"✅ Desuscrito de '{topic}'.")
        else:
            await update.message.reply_text(f"⚠️ No estabas suscrito a '{topic}'.")
    
    @handle_errors
    async def topics_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /topics - Lista temas suscritos"""
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        subscriptions = self.intel_manager.get_user_subscriptions(user_id)
        
        if not subscriptions:
            await update.message.reply_text(
                "ℹ️ No tienes temas suscritos.\n\n"
                "Usa `/subscribe <tema>` para suscribirte.",
                parse_mode="Markdown"
            )
            return
        
        message = "📡 **Tus Suscripciones:**\n\n"
        for topic in subscriptions:
            message += f"• {topic}\n"
        
        message += f"\n💡 Usa `/snipe <tema>` para ver noticias."
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
    @handle_errors
    async def handle_summary_flash(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Genera resumen ultra-corto (2-3 frases)"""
        query = update.callback_query
        await query.answer()
        
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        try:
            _, index_str, topic = query.data.split("|", 2)
            index = int(index_str)
        except:
            await query.edit_message_text("❌ Error al procesar la solicitud.")
            return
        
        news = self.intel_manager.get_cached_news(context, topic)
        if not news or index >= len(news):
            await query.edit_message_text("❌ Noticia no encontrada.")
            return
        
        news_item = news[index]
        
        await query.edit_message_text("⚡ Generando resumen flash...")
        
        # Generar resumen flash con LLM
        prompt = f"""Título: {news_item.get('titulo_es', news_item['titulo'])}
Contenido: {news_item['resumen']}

Resume en MÁXIMO 2-3 frases lo más importante."""
        
        try:
            summary = await self.intel_manager.ollama_service.generate(
                prompt,
                system="Eres un periodista conciso. Resume noticias en 2-3 frases máximo.",
                timeout=20,
                use_powerful_model=False
            )
            
            title = news_item.get('titulo_es', news_item['titulo'])
            priority = news_item.get('prioridad', 3)
            priority_text = "🔥" * priority if priority >= 4 else ""
            
            message_text = f"📰 **{title}** {priority_text}\n\n"
            message_text += f"⚡ **Resumen Flash:**\n{summary.strip()}\n\n"
            message_text += f"🗓️ {news_item['fecha'][:10]}"
            
            keyboard = [
                [InlineKeyboardButton("🔍 Resumen Deep", callback_data=f"summary_deep|{index}|{topic}")],
                [InlineKeyboardButton("🔗 Link Original", url=news_item['link'])],
                [InlineKeyboardButton("🔙 Categorías", callback_data=f"back_to_categories|{topic}")],
                [InlineKeyboardButton("🏠 Panel Principal", callback_data="main_menu")]
            ]
            
            await query.edit_message_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error generando resumen flash: {e}")
            await query.edit_message_text("❌ Error al generar resumen. Intenta de nuevo.")
    
    @handle_errors
    async def handle_summary_deep(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Genera resumen detallado con análisis"""
        query = update.callback_query
        await query.answer()
        
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        try:
            _, index_str, topic = query.data.split("|", 2)
            index = int(index_str)
        except:
            await query.edit_message_text("❌ Error al procesar la solicitud.")
            return
        
        news = self.intel_manager.get_cached_news(context, topic)
        if not news or index >= len(news):
            await query.edit_message_text("❌ Noticia no encontrada.")
            return
        
        news_item = news[index]
        
        await query.edit_message_text("🔍 Generando análisis profundo...")
        
        # Generar resumen deep con LLM potente
        prompt = f"""Título: {news_item.get('titulo_es', news_item['titulo'])}
Contenido: {news_item['resumen']}

Genera un análisis estructurado:
1. **Qué es:** Explicación clara
2. **Por qué importa:** Impacto y relevancia
3. **Contexto:** Información adicional útil

Máximo 6-8 frases en total."""
        
        try:
            summary = await self.intel_manager.ollama_service.generate(
                prompt,
                system="Eres un analista tech. Proporciona análisis claros y estructurados.",
                timeout=40,
                use_powerful_model=True  # Usar modelo potente para análisis
            )
            
            title = news_item.get('titulo_es', news_item['titulo'])
            priority = news_item.get('prioridad', 3)
            priority_text = "🔥" * priority if priority >= 4 else ""
            
            message_text = f"📰 **{title}** {priority_text}\n\n"
            message_text += f"🔍 **Análisis Profundo:**\n{summary.strip()}\n\n"
            message_text += f"🗓️ {news_item['fecha'][:10]}"
            
            keyboard = [
                [InlineKeyboardButton("⚡ Resumen Flash", callback_data=f"summary_flash|{index}|{topic}")],
                [InlineKeyboardButton("🔗 Link Original", url=news_item['link'])],
                [InlineKeyboardButton("🔙 Categorías", callback_data=f"back_to_categories|{topic}")],
                [InlineKeyboardButton("🏠 Panel Principal", callback_data="main_menu")]
            ]
            
            await query.edit_message_text(
                message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error generando resumen deep: {e}")
            await query.edit_message_text("❌ Error al generar análisis. Intenta de nuevo.")
    
    def get_handlers(self):
        """Retorna lista de handlers para registrar"""
        return [
            CommandHandler("snipe", self.snipe_command),
            CommandHandler("subscribe", self.subscribe_command),
            CommandHandler("unsubscribe", self.unsubscribe_command),
            CommandHandler("topics", self.topics_command),
            CallbackQueryHandler(self.handle_category_selection, pattern=r"^category_"),
            CallbackQueryHandler(self.handle_news_callback, pattern=r"^read_news\|"),
            CallbackQueryHandler(self.handle_summary_flash, pattern=r"^summary_flash\|"),
            CallbackQueryHandler(self.handle_summary_deep, pattern=r"^summary_deep\|"),
            CallbackQueryHandler(self.handle_back_to_categories, pattern=r"^back_to_categories\|"),
        ]
