from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from src.services.auth_service import AuthService
from src.modules.library import LibraryModule
from src.utils.error_handler import handle_errors
from src.utils.logger import get_logger, console
import json

logger = get_logger("quiz_handler")


class QuizHandler:
    def __init__(self, auth_service: AuthService, library_module: LibraryModule):
        self.auth_service = auth_service
        self.library_module = library_module
    
    @handle_errors
    async def quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Genera un quiz interactivo basado en el conocimiento almacenado"""
        user_id = await self.auth_service.authenticate_user(update, context)
        if not user_id:
            return
        
        # Manejar tanto mensajes directos como callback queries
        if update.message:
            message = update.message
        elif update.callback_query:
            message = update.callback_query.message
        else:
            return
        
        if not context.args:
            await message.reply_text(
                "📝 <b>Uso:</b> <code>/quiz &lt;tema&gt;</code>\n\n"
                "<b>Ejemplos:</b>\n"
                "• <code>/quiz Python</code>\n"
                "• <code>/quiz Machine Learning</code>\n"
                "• <code>/quiz bases de datos</code>\n\n"
                "💡 Generaré una pregunta de examen basada en tus documentos guardados.",
                parse_mode="HTML"
            )
            return
        
        topic = " ".join(context.args)
        
        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        await message.reply_text(
            f"🔍 Accediendo a los archivos sobre <b>{topic}</b>...",
            parse_mode="HTML"
        )
        
        try:
            # Buscar en ChromaDB los 3 fragmentos más relevantes
            console.print(f"[info]📚 Searching ChromaDB for topic: {topic}[/info]")
            search_results = await self.library_module.search(user_id, topic, top_k=3)
            console.print(f"[debug]🔍 Found {len(search_results)} results[/debug]")
            
            if not search_results:
                await message.reply_text(
                    f"⚠️ <b>Me temo que no dispongo de información sobre '{topic}'</b>\n\n"
                    f"Le sugiero indexar documentos relacionados utilizando <code>/ingest</code>",
                    parse_mode="HTML"
                )
                return
            
            # Combinar los resultados en un contexto
            context_text = "\n\n".join([result["text"] for result in search_results])
            console.print(f"[debug]� Context length: {len(context_text)} chars[/debug]")
            
            # Generar mensaje dinámico de procesamiento
            processing_msg = await self.library_module.ollama_service.get_jarvis_response(
                "quiz_generated",
                f"Generando examen sobre {topic}"
            )
            await message.reply_text(
                f"🧠 {processing_msg}",
                parse_mode="HTML"
            )
            
            questions_list = await self._generate_quiz_with_ollama(context_text, topic)
            
            console.print(f"[debug]✅ Quiz data generated: {questions_list is not None}[/debug]")
            
            if not questions_list:
                await message.reply_text(
                    "⚠️ <b>Ha ocurrido un error al generar el examen</b>\n\n"
                    "No he podido crear un quiz válido. Le sugiero intentarlo nuevamente.",
                    parse_mode="HTML"
                )
                return
            
            # Mensaje dinámico antes de enviar las preguntas
            intro_msg = await self.library_module.ollama_service.get_jarvis_response(
                "quiz_generated",
                f"{len(questions_list)} preguntas de examen preparadas sobre {topic}"
            )
            await message.reply_text(
                f"🧐 {intro_msg}",
                parse_mode="HTML"
            )
            
            # Enviar cada pregunta como poll de Telegram
            import asyncio
            for i, quiz_data in enumerate(questions_list, 1):
                console.print(f"[info]📤 Sending question {i}/{len(questions_list)}[/info]")
                await self._send_quiz_poll(update, context, quiz_data, i, len(questions_list))
                # Pausa entre preguntas para asegurar orden
                if i < len(questions_list):
                    await asyncio.sleep(1.5)
            
            # Mensaje de cierre con botón de navegación
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await message.reply_text(
                "🎯 <b>Evaluación completada</b>\n\n"
                "💬 ¿Desea realizar otra operación?",
                parse_mode="HTML",
                reply_markup=get_back_to_dashboard_keyboard()
            )
            
            console.print(f"[success]✅ Quiz sent successfully for topic: {topic}[/success]")
            
        except asyncio.TimeoutError:
            logger.error("Timeout generating quiz")
            console.print("[error]❌ Timeout generating quiz[/error]")
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await message.reply_text(
                "⏱️ <b>Tiempo de espera agotado</b>\n\n"
                "La generación del examen está tomando más tiempo del esperado.\n\n"
                "💡 <b>Sugerencias:</b>\n"
                "• Intente con un tema más específico\n"
                "• Verifique que Ollama esté funcionando correctamente\n"
                "• El modelo puede estar sobrecargado, intente nuevamente en un momento",
                parse_mode="HTML",
                reply_markup=get_back_to_dashboard_keyboard()
            )
        except Exception as e:
            logger.error(f"Error generating quiz: {e}", exc_info=True)
            console.print(f"[error]❌ Error generating quiz: {e}[/error]")
            from src.utils.keyboard_helpers import get_back_to_dashboard_keyboard
            await message.reply_text(
                "⚠️ <b>Error al generar el quiz</b>\n\n"
                f"Ocurrió un error inesperado. Por favor, inténtalo de nuevo.",
                parse_mode="HTML",
                reply_markup=get_back_to_dashboard_keyboard()
            )
    
    async def _generate_quiz_with_ollama(self, context_text: str, topic: str) -> list:
        """Genera 3 preguntas de quiz usando Ollama con formato JSON Array"""
        try:
            # Limitar el contexto a 1200 caracteres para 3 preguntas
            if len(context_text) > 1200:
                context_text = context_text[:1200] + "..."
            
            from src.services.ollama_service import JARVIS_CORE_PROMPT
            
            system_prompt = (
                f"{JARVIS_CORE_PROMPT}\n\n"
                "IMPORTANTE: Responde SOLO con un JSON Array válido (una lista de objetos), sin texto antes ni después. "
                "No uses markdown, no uses ```json, solo el JSON puro.\n\n"
                "REGLAS PARA LAS PREGUNTAS:\n"
                "- Evita preguntas obvias o de simple definición\n"
                "- Crea preguntas que requieran razonamiento, análisis o aplicación de conceptos\n"
                "- Las opciones incorrectas deben ser plausibles y realistas\n"
                "- Enfócate en casos de uso, comparaciones o resolución de problemas\n"
                "- Cada pregunta debe ser independiente de las demás"
            )
            
            user_prompt = (
                f"Genera 3 preguntas de examen avanzadas sobre: {topic}\n\n"
                f"Contexto:\n{context_text}\n\n"
                f"Formato de respuesta (SOLO JSON Array):\n"
                f'['
                f'  {{"question": "pregunta 1", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "explicación"}},'
                f'  {{"question": "pregunta 2", "options": ["A", "B", "C", "D"], "correct_index": 1, "explanation": "explicación"}},'
                f'  {{"question": "pregunta 3", "options": ["A", "B", "C", "D"], "correct_index": 2, "explanation": "explicación"}}'
                f']'
            )
            
            # Llamar a Ollama con timeout extendido para generación de quiz
            console.print(f"[info]🤖 Calling Ollama to generate quiz...[/info]")
            response = await self.library_module.ollama_service.generate(
                prompt=user_prompt,
                system=system_prompt,
                timeout=240  # 4 minutos para generación de quiz con contexto largo
            )
            
            console.print(f"[debug]� Ollama raw response:\n{response}[/debug]")
            
            # Intentar parsear el JSON
            # Limpiar la respuesta de posibles markdown code blocks y texto extra
            response = response.strip()
            
            # Buscar el JSON Array en la respuesta (puede estar entre texto)
            import re
            # Buscar array JSON primero
            json_match = re.search(r'\[\s*\{[^\]]*\}\s*\]', response, re.DOTALL)
            if json_match:
                response = json_match.group(0)
            else:
                # Si no encuentra array, buscar objeto único
                json_match = re.search(r'\{[^{}]*"question"[^{}]*\}', response, re.DOTALL)
                if json_match:
                    response = json_match.group(0)
                else:
                    # Intentar limpiar markdown
                    if response.startswith("```json"):
                        response = response[7:]
                    if response.startswith("```"):
                        response = response[3:]
                    if response.endswith("```"):
                        response = response[:-3]
                    response = response.strip()
            
            console.print(f"[debug]🔧 Cleaned JSON:\n{response}[/debug]")
            
            quiz_data = json.loads(response)
            
            # Manejar caso de que devuelva un solo objeto en lugar de array
            if isinstance(quiz_data, dict):
                console.print(f"[warning]⚠️ Received single object instead of array, wrapping it[/warning]")
                quiz_data = [quiz_data]
            
            # Validar que sea una lista
            if not isinstance(quiz_data, list):
                console.print(f"[warning]⚠️ Response is not a list[/warning]")
                return None
            
            # Validar cada pregunta
            required_fields = ["question", "options", "correct_index", "explanation"]
            valid_questions = []
            
            for i, question_data in enumerate(quiz_data):
                # Validar campos requeridos
                if not all(field in question_data for field in required_fields):
                    console.print(f"[warning]⚠️ Question {i+1} missing required fields[/warning]")
                    continue
                
                # Validar que options tenga 4 elementos
                if len(question_data["options"]) != 4:
                    console.print(f"[warning]⚠️ Question {i+1} must have exactly 4 options[/warning]")
                    continue
                
                # Validar que correct_index esté entre 0 y 3
                if not (0 <= question_data["correct_index"] <= 3):
                    console.print(f"[warning]⚠️ Question {i+1} correct_index must be between 0 and 3[/warning]")
                    continue
                
                valid_questions.append(question_data)
            
            if not valid_questions:
                console.print(f"[warning]⚠️ No valid questions found[/warning]")
                return None
            
            console.print(f"[success]✅ Generated {len(valid_questions)} valid questions[/success]")
            return valid_questions
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Ollama response as JSON: {e}")
            console.print(f"[error]❌ Invalid JSON from Ollama: {response[:200]}[/error]")
            return None
        except Exception as e:
            logger.error(f"Error generating quiz with Ollama: {e}", exc_info=True)
            console.print(f"[error]❌ Error in _generate_quiz_with_ollama: {e}[/error]")
            return None
    
    async def _send_quiz_poll(self, update: Update, context: ContextTypes.DEFAULT_TYPE, quiz_data: dict, question_num: int = 1, total_questions: int = 1):
        """Envía el quiz como un poll de Telegram"""
        try:
            question = quiz_data["question"]
            options = quiz_data["options"]
            correct_option_id = quiz_data["correct_index"]
            explanation = quiz_data["explanation"]
            
            # Telegram limits: question max 300 chars, options max 100 chars each, explanation max 200 chars
            if len(question) > 300:
                question = question[:297] + "..."
                console.print(f"[warning]⚠️ Question truncated to 300 chars[/warning]")
            
            # Truncar opciones si son muy largas
            truncated_options = []
            for opt in options:
                if len(opt) > 100:
                    truncated_options.append(opt[:97] + "...")
                else:
                    truncated_options.append(opt)
            
            if len(explanation) > 200:
                explanation = explanation[:197] + "..."
                console.print(f"[warning]⚠️ Explanation truncated to 200 chars[/warning]")
            
            # Enviar el poll
            await context.bot.send_poll(
                chat_id=update.effective_chat.id,
                question=question,
                options=truncated_options,
                type="quiz",
                correct_option_id=correct_option_id,
                explanation=explanation,
                is_anonymous=False,
                allows_multiple_answers=False
            )
            
            logger.info(f"Quiz poll sent to user {update.effective_user.id}")
            
        except Exception as e:
            logger.error(f"Error sending quiz poll: {e}", exc_info=True)
            console.print(f"[error]❌ Error sending poll: {e}[/error]")
            raise
