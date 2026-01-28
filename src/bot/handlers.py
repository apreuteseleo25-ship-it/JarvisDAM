from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from src.services.auth_service import AuthService
from src.modules.library import LibraryModule
from src.modules.intel import IntelModule
from src.modules.hq import HQModule
from src.utils.rate_limiter import TelegramRateLimiter
from typing import Optional
import asyncio


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
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            await update.message.reply_text("Error de autenticación.")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        help_text = (
            "🤖 *JARVIS System - Comandos*\n\n"
            "📚 *LIBRARY (Knowledge Vault)*\n"
            "  /ingest - Sube un PDF para indexar\n"
            "  /ask <pregunta> - Pregunta sobre tus documentos\n"
            "  /quiz - Genera un quiz de tus documentos\n"
            "  /stats - Estadísticas de tu biblioteca\n\n"
            "📰 *INTEL (News)*\n"
            "  /snipe - Descarga noticias de tus temas\n"
            "  /subscribe <tema> - Suscríbete a un tema\n"
            "  /unsubscribe <tema> - Cancela suscripción\n"
            "  /topics - Lista tus suscripciones\n\n"
            "📅 *HQ (Tasks & Calendar)*\n"
            "  /add <tarea> - Añade una tarea\n"
            "  /list - Lista tus tareas\n"
            "  /done <id> - Marca tarea como completada\n"
            "  /delete <id> - Elimina una tarea\n\n"
            "ℹ️ /help - Muestra esta ayuda"
        )
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def ingest_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        # Si hay argumentos, verificar si es una URL de YouTube
        if context.args:
            url = " ".join(context.args)
            
            # Detectar URLs de YouTube
            if "youtube.com" in url or "youtu.be" in url:
                await update.message.reply_text(
                    "🎥 <b>Enlace de YouTube detectado.</b>\n\n"
                    "Descargando transcripción y vectorizando contenido...\n"
                    "<i>(Esto puede tomar unos segundos)</i>",
                    parse_mode="HTML"
                )
                
                try:
                    result = await self.library_module.ingest_youtube_video(
                        user_id=user_id,
                        url=url
                    )
                    
                    if result["success"]:
                        await update.message.reply_text(
                            f"✅ Video transcrito y añadido a la base de conocimiento.\n\n"
                            f"🎥 {result['title']}\n"
                            f"📊 {result['chunks']} fragmentos indexados\n\n"
                            f"Ahora puedes hacer preguntas sobre este contenido con /ask"
                        )
                    else:
                        await update.message.reply_text(
                            f"❌ Error al procesar video: {result['error']}"
                        )
                except Exception as e:
                    logger.error(f"Error ingesting YouTube video: {e}", exc_info=True)
                    await update.message.reply_text(
                        f"❌ Error al procesar el video de YouTube: {str(e)}"
                    )
                return
            else:
                await update.message.reply_text(
                    "⚠️ URL no reconocida. Solo se soportan URLs de YouTube.\n\n"
                    "**Uso:**\n"
                    "• `/ingest <URL_de_YouTube>`\n"
                    "• `/ingest` (luego envía un PDF)",
                    parse_mode="Markdown"
                )
                return
        
        # Si no hay argumentos, solicitar PDF
        await update.message.reply_text(
            "📄 Por favor, envía el archivo PDF que deseas indexar.\n\n"
            "O usa: `/ingest <URL_de_YouTube>`",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_pdf"] = True
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        if not update.message.document:
            return
        
        document = update.message.document
        
        if document.mime_type == "application/pdf":
            await update.message.reply_text("📥 Descargando y procesando PDF...")
            
            file = await context.bot.get_file(document.file_id)
            file_bytes = await file.download_as_bytearray()
            
            result = await self.library_module.ingest_pdf(
                user_id=user_id,
                file_bytes=bytes(file_bytes),
                filename=document.file_name
            )
            
            if result["success"]:
                await update.message.reply_text(
                    f"✅ PDF indexado exitosamente!\n\n"
                    f"📄 Archivo: {result['filename']}\n"
                    f"📖 Páginas: {result['pages']}\n"
                    f"🔢 Chunks: {result['chunks']}"
                )
            else:
                await update.message.reply_text(
                    f"❌ Error al procesar PDF: {result['error']}"
                )
        else:
            await update.message.reply_text(
                "⚠️ Por favor, envía un archivo PDF válido."
            )
    
    async def ask_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        if not context.args:
            await update.message.reply_text(
                "❓ Uso: /ask <tu pregunta>\n"
                "Ejemplo: /ask ¿Qué es machine learning?"
            )
            return
        
        question = " ".join(context.args)
        
        await update.message.reply_text("🔍 Buscando en tus documentos...")
        
        try:
            answer = await self.library_module.ask(user_id, question)
            await update.message.reply_text(answer, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error in ask_command: {e}", exc_info=True)
            await update.message.reply_text(
                "⚠️ El modelo está tardando demasiado en responder.\n\n"
                "Esto puede deberse a que el modelo gpt-oss:20b es muy grande.\n\n"
                "💡 Recomendaciones:\n"
                "• Espera unos segundos y vuelve a intentar\n"
                "• O usa un modelo más ligero (edita el código para usar qwen2.5:7b)\n\n"
                f"Error técnico: {str(e)}"
            )
    
    async def quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        await update.message.reply_text("🎯 Generando quiz...")
        
        quiz = await self.library_module.generate_quiz(user_id)
        
        await update.message.reply_text(quiz)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        stats = self.library_module.get_library_stats(user_id)
        
        message = (
            "📊 *Estadísticas de tu Biblioteca*\n\n"
            f"📄 Documentos: {stats['documents']}\n"
            f"💾 Snippets: {stats['snippets']}\n"
            f"📚 Total: {stats['total']}"
        )
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
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
            await update.message.reply_text("❌ ID de tarea inválido.")
            return
        
        success = self.hq_module.mark_task_completed(user_id, task_id)
        
        if success:
            await update.message.reply_text("✅ Tarea completada!")
        else:
            await update.message.reply_text("❌ Tarea no encontrada.")
    
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
            await update.message.reply_text("❌ ID de tarea inválido.")
            return
        
        success = self.hq_module.delete_task(user_id, task_id)
        
        if success:
            await update.message.reply_text("🗑️ Tarea eliminada!")
        else:
            await update.message.reply_text("❌ Tarea no encontrada.")
    
    def get_handlers(self):
        return [
            CommandHandler("start", self.start_command),
            CommandHandler("help", self.help_command),
            CommandHandler("ingest", self.ingest_command),
            CommandHandler("ask", self.ask_command),
            CommandHandler("quiz", self.quiz_command),
            CommandHandler("stats", self.stats_command),
            CommandHandler("add", self.add_task_command),
            CommandHandler("list", self.list_tasks_command),
            CommandHandler("done", self.done_task_command),
            CommandHandler("delete", self.delete_task_command),
            MessageHandler(filters.Document.ALL, self.handle_document),
        ]
