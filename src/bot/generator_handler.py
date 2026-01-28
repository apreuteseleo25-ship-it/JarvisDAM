from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from src.services.auth_service import AuthService
from src.services.ollama_service import OllamaService
from src.utils.error_handler import handle_errors
from src.utils.logger import get_logger
from fpdf import FPDF
from datetime import datetime
import os
import tempfile
import re

logger = get_logger("generator_handler")


class CheatSheetPDF(FPDF):
    """Custom PDF class for JARVIS-branded cheatsheets"""
    
    def header(self):
        """Add JARVIS header to each page"""
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'J.A.R.V.I.S. | KNOWLEDGE DOSSIER', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 5, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}', 0, 1, 'C')
        self.ln(5)
    
    def footer(self):
        """Add page number footer"""
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')
    
    def chapter_title(self, title):
        """Add a chapter title"""
        self.set_font('Arial', 'B', 14)
        self.set_fill_color(200, 220, 255)
        self.cell(0, 10, title, 0, 1, 'L', 1)
        self.ln(2)
    
    def chapter_body(self, body):
        """Add chapter body text"""
        self.set_font('Arial', '', 11)
        self.multi_cell(0, 6, body)
        self.ln()


class GeneratorHandler:
    def __init__(self, auth_service: AuthService, ollama_service: OllamaService):
        self.auth_service = auth_service
        self.ollama_service = ollama_service
    
    @handle_errors
    async def cheat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Genera una cheatsheet en PDF sobre un tema específico"""
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        if not context.args:
            await update.message.reply_text(
                "📚 **Uso:** `/cheat <tema>`\n\n"
                "**Ejemplos:**\n"
                "• `/cheat Python Listas`\n"
                "• `/cheat SQL Joins`\n"
                "• `/cheat Segunda Guerra Mundial`\n\n"
                "Generaré un dossier técnico en PDF sobre el tema solicitado.",
                parse_mode="Markdown"
            )
            return
        
        topic = " ".join(context.args)
        
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        # Mensaje dinámico de procesamiento
        processing_msg = await self.ollama_service.get_jarvis_response(
            "thinking",
            f"Compilando dossier sobre {topic}"
        )
        await update.message.reply_text(f"📋 {processing_msg}")
        
        try:
            # Paso 1: Generar contenido con Ollama
            logger.info(f"Generating cheatsheet for topic: {topic}")
            markdown_content = await self._generate_cheatsheet_content(topic)
            
            if not markdown_content:
                await update.message.reply_text(
                    "⚠️ No he podido generar el contenido del dossier. Intente nuevamente."
                )
                return
            
            # Paso 2: Convertir Markdown a PDF
            logger.info("Converting markdown to PDF")
            pdf_path = await self._markdown_to_pdf(topic, markdown_content)
            
            if not pdf_path:
                await update.message.reply_text(
                    "⚠️ Error al generar el archivo PDF."
                )
                return
            
            # Paso 3: Enviar PDF al usuario
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT)
            
            with open(pdf_path, 'rb') as pdf_file:
                # Mensaje dinámico de entrega
                delivery_msg = await self.ollama_service.get_jarvis_response(
                    "document_indexed",
                    f"Dossier sobre {topic} completado"
                )
                
                from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
                await update.message.reply_document(
                    document=pdf_file,
                    filename=f"JARVIS_Cheatsheet_{topic.replace(' ', '_')}.pdf",
                    caption=f"📂 **{delivery_msg}**",
                    parse_mode="Markdown",
                    reply_markup=get_back_to_dashboard_keyboard()
                )
            
            # Limpiar archivo temporal
            os.remove(pdf_path)
            logger.info(f"Cheatsheet sent successfully for topic: {topic}")
            
        except Exception as e:
            logger.error(f"Error generating cheatsheet: {e}", exc_info=True)
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await update.message.reply_text(
                "⚠️ Ha ocurrido un error al generar el dossier. Por favor, inténtelo nuevamente.",
                reply_markup=get_back_to_dashboard_keyboard()
            )
    
    async def _generate_cheatsheet_content(self, topic: str) -> str:
        """Genera el contenido de la cheatsheet usando Ollama"""
        system_prompt = (
            "Eres JARVIS. Genera una 'Cheatsheet' (Hoja de Referencia) técnica y densa sobre el tema solicitado.\n"
            "Usa formato Markdown limpio y estructurado.\n\n"
            "ESTRUCTURA OBLIGATORIA:\n"
            "1. # Título del tema\n"
            "2. ## Definiciones Clave (bullet points)\n"
            "3. ## Conceptos Fundamentales (tabla o lista)\n"
            "4. ## Ejemplos Prácticos (código si aplica)\n"
            "5. ## Best Practices / Tips\n\n"
            "REGLAS:\n"
            "- Sé conciso y esquemático\n"
            "- Usa tablas cuando sea apropiado\n"
            "- Incluye ejemplos de código si el tema es técnico\n"
            "- Máximo 2 páginas de contenido\n"
            "- NO uses emojis\n"
            "- NO añadas conversación, solo el contenido Markdown"
        )
        
        prompt = f"Genera una cheatsheet completa sobre: {topic}"
        
        try:
            response = await self.ollama_service.generate(
                prompt, 
                system=system_prompt,
                timeout=240  # 4 minutos para generación de cheatsheet
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating content with Ollama: {e}")
            return ""
    
    async def _markdown_to_pdf(self, topic: str, markdown_content: str) -> str:
        """Convierte contenido Markdown a PDF con branding de JARVIS"""
        try:
            pdf = CheatSheetPDF()
            pdf.add_page()
            
            # Título principal del tema
            pdf.set_font('Arial', 'B', 18)
            pdf.cell(0, 15, topic.upper(), 0, 1, 'C')
            pdf.ln(5)
            
            # Procesar el contenido Markdown
            lines = markdown_content.split('\n')
            
            for line in lines:
                line = line.strip()
                
                if not line:
                    pdf.ln(3)
                    continue
                
                # Títulos H1
                if line.startswith('# '):
                    title = line[2:].strip()
                    pdf.chapter_title(title)
                
                # Títulos H2
                elif line.startswith('## '):
                    subtitle = line[3:].strip()
                    pdf.set_font('Arial', 'B', 12)
                    pdf.cell(0, 8, subtitle, 0, 1, 'L')
                    pdf.ln(1)
                
                # Títulos H3
                elif line.startswith('### '):
                    subsubtitle = line[4:].strip()
                    pdf.set_font('Arial', 'B', 11)
                    pdf.cell(0, 7, subsubtitle, 0, 1, 'L')
                
                # Bullet points
                elif line.startswith('- ') or line.startswith('* '):
                    text = line[2:].strip()
                    # Limpiar markdown de negritas y cursivas
                    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
                    text = re.sub(r'\*(.*?)\*', r'\1', text)
                    text = re.sub(r'`(.*?)`', r'\1', text)
                    
                    pdf.set_font('Arial', '', 10)
                    pdf.cell(10, 6, chr(149), 0, 0)  # Bullet character
                    pdf.multi_cell(0, 6, text)
                
                # Bloques de código
                elif line.startswith('```'):
                    continue  # Skip code fence markers
                
                # Texto normal
                else:
                    # Limpiar markdown
                    text = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
                    text = re.sub(r'\*(.*?)\*', r'\1', text)
                    text = re.sub(r'`(.*?)`', r'\1', text)
                    
                    if text:
                        pdf.set_font('Arial', '', 10)
                        pdf.multi_cell(0, 6, text)
            
            # Guardar PDF en archivo temporal
            temp_dir = tempfile.gettempdir()
            pdf_filename = f"jarvis_cheatsheet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            pdf_path = os.path.join(temp_dir, pdf_filename)
            
            pdf.output(pdf_path)
            logger.info(f"PDF generated at: {pdf_path}")
            
            return pdf_path
            
        except Exception as e:
            logger.error(f"Error creating PDF: {e}", exc_info=True)
            return ""
    
    def get_handlers(self):
        """Retorna los handlers de comandos"""
        from telegram.ext import CommandHandler
        return [
            CommandHandler("cheat", self.cheat_command),
            CommandHandler("resumen", self.cheat_command),  # Alias
        ]
