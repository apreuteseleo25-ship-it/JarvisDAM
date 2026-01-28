import aiohttp
from typing import Optional, Dict, Any
import json
from src.utils.retry import async_retry_with_backoff
from src.utils.logger import get_logger
import asyncio

logger = get_logger("ollama_service")

# JARVIS - Sistema de Inteligencia Artificial Avanzado
JARVIS_CORE_PROMPT = (
    "Eres JARVIS, un sistema de inteligencia artificial avanzado y leal. "
    "Tu objetivo es asistir al usuario con máxima eficiencia y precisión.\n\n"
    "TONO: Formal, elegante, conciso y ligeramente ingenioso.\n"
    "IDIOMA: Español neutro y culto.\n\n"
    "REGLAS:\n"
    "- Cuando se te pida realizar una acción (Calendar), confirma la ejecución con brevedad y profesionalidad.\n"
    "- Cuando expliques conceptos (RAG/Quiz), sé pedagógico pero no condescendiente. Demuestra un dominio absoluto del tema.\n"
    "- Si debes generar JSON, hazlo estrictamente sin añadir 'conversación' fuera del JSON.\n"
    "- Nunca rompas el personaje. No menciones que eres un modelo de lenguaje.\n"
    "- Mantén un tono de mayordomo británico: servicial, competente, con humor seco muy sutil."
)


class OllamaService:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self.base_url = base_url
        self.model = model  # Modelo rápido por defecto
        self.fast_model = "qwen2.5:7b"  # Modelo rápido para tareas comunes
        self.powerful_model = "gpt-oss:20b"  # Modelo potente para análisis profundo
        self.timeout = 60  # Timeout por defecto para modelo rápido
        self.timeout_powerful = 240  # Timeout para modelo potente (4 minutos)
        self.fallback_models = ["llama3.2", "qwen2.5:7b", "phi3.5"]  # Modelos de respaldo
        
        # Verificar disponibilidad del modelo al iniciar
        print(f"🤖 Inicializando OllamaService - Modelo rápido: {self.fast_model}, Modelo potente: {self.powerful_model}")
        logger.info(f"Inicializando OllamaService - Modelo rápido: {self.fast_model}, Modelo potente: {self.powerful_model}")
        try:
            # Nota: La verificación real se hará en la primera llamada
            # para no bloquear el inicio del bot
            pass
        except Exception as e:
            logger.warning(f"No se pudo verificar modelos: {e}")
    
    async def get_jarvis_response(self, context_type: str, details: str) -> str:
        """
        Genera respuestas dinámicas de JARVIS para mensajes de estado.
        
        Args:
            context_type: Tipo de situación (event_created, error_found, boot_sequence, thinking, etc.)
            details: Detalles específicos de la situación
        
        Returns:
            Respuesta corta y única generada por la IA (1-2 frases)
        """
        system_prompt = (
            "Eres J.A.R.V.I.S. Tu tarea es generar una frase de respuesta CORTA (máximo 1-2 frases) para el usuario.\n"
            "IDIOMA: Español neutro y culto.\n"
            "Tono: Servicial, eficiente, leal y con un toque de ingenio británico sutil.\n"
            "NO ofrezcas ayuda extra, solo confirma la acción o informa del estado.\n"
            "NO uses comillas ni prefijos.\n"
            "Responde SOLO con la frase en ESPAÑOL, sin añadir nada más."
        )
        
        # Mapeo de contextos a instrucciones específicas
        context_instructions = {
            "event_created": "Confirma que has agendado el evento de forma elegante y breve.",
            "event_error": "Informa del error al crear el evento con profesionalismo.",
            "document_indexed": "Confirma que has indexado el documento exitosamente.",
            "document_error": "Informa del error al procesar el documento.",
            "query_processing": "Indica que estás procesando la consulta del usuario.",
            "query_complete": "Confirma que has completado la búsqueda.",
            "briefing_activated": "Confirma que has activado el briefing diario.",
            "briefing_deactivated": "Confirma que has desactivado el briefing diario.",
            "subscription_added": "Confirma la suscripción a noticias.",
            "subscription_invalid": "Explica que el tema está fuera de tu rango operativo.",
            "quiz_generated": "Indica que has generado el examen.",
            "thinking": "Indica que estás procesando información.",
            "boot_sequence": "Saludo inicial al activarse.",
            "error_found": "Informa de un error genérico con elegancia."
        }
        
        instruction = context_instructions.get(context_type, "Responde apropiadamente a la situación.")
        
        prompt = f"{instruction}\n\nDetalles: {details}\n\nRespuesta:"
        
        try:
            # Llamada optimizada con límite de tokens para respuesta rápida
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
                "options": {
                    "num_predict": 50,  # Máximo 50 tokens para respuesta rápida
                    "temperature": 0.8,  # Un poco de variación para respuestas únicas
                    "top_p": 0.9
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        data = await response.json()
                        ai_response = data.get("response", "").strip()
                        
                        # Limpiar respuesta de posibles artefactos
                        ai_response = ai_response.replace('"', '').replace("'", "").strip()
                        
                        return ai_response if ai_response else details
                    else:
                        logger.warning(f"Ollama API error in get_jarvis_response: {response.status}")
                        return details
        except Exception as e:
            logger.error(f"Error generating JARVIS response: {e}")
            # Fallback a mensaje básico si falla la IA
            return details
    
    async def _verify_model_availability(self) -> bool:
        """Verifica si el modelo está disponible, intenta con fallback si no"""
        try:
            url = f"{self.base_url}/api/tags"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        available_models = [m['name'] for m in data.get('models', [])]
                        
                        if self.model in available_models:
                            logger.info(f"✅ Modelo {self.model} disponible")
                            return True
                        else:
                            logger.warning(f"⚠️ Modelo {self.model} no encontrado. Modelos disponibles: {available_models}")
                            
                            # Intentar con modelos de respaldo
                            for fallback in self.fallback_models:
                                if fallback in available_models:
                                    logger.info(f"🔄 Usando modelo de respaldo: {fallback}")
                                    self.model = fallback
                                    return True
                            
                            logger.error(f"❌ No hay modelos disponibles. Ejecute: ollama pull {self.model}")
                            return False
        except Exception as e:
            logger.error(f"Error verificando modelos: {e}")
            return False
    
    @async_retry_with_backoff(
        max_retries=3,
        initial_delay=5.0,
        backoff_factor=2.0,
        exceptions=(aiohttp.ClientError, asyncio.TimeoutError)
    )
    async def generate(self, prompt: str, system: Optional[str] = None, timeout: int = None, use_powerful_model: bool = False) -> str:
        # Seleccionar modelo según parámetro
        model_to_use = self.powerful_model if use_powerful_model else self.model
        
        # Usar timeout configurado si no se especifica
        if timeout is None:
            timeout = self.timeout_powerful if use_powerful_model else self.timeout
        
        logger.info(f"Usando modelo: {model_to_use} (timeout: {timeout}s)")
        
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": model_to_use,
            "prompt": prompt,
            "stream": False
        }
        
        if system:
            payload["system"] = system
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status == 429:
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=429,
                        message="Rate limit exceeded"
                    )
                
                if response.status == 200:
                    data = await response.json()
                    return data.get("response", "")
                else:
                    raise aiohttp.ClientError(f"Ollama API error: {response.status}")
    
    async def extract_date_from_text(self, text: str) -> Optional[str]:
        """Extrae fecha usando IA + dateparser para máxima precisión"""
        from datetime import datetime, timedelta
        import dateparser
        import calendar
        
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        
        # Calcular próximos días de la semana en español
        weekdays_es = {
            0: 'lunes', 1: 'martes', 2: 'miércoles', 3: 'jueves',
            4: 'viernes', 5: 'sábado', 6: 'domingo'
        }
        
        current_weekday = now.weekday()
        current_weekday_name = weekdays_es[current_weekday]
        
        # Información de contexto temporal completa
        current_date = now.strftime("%Y-%m-%d %H:%M:%S")
        current_day = now.strftime("%d")
        current_month = now.strftime("%m")
        current_year = now.strftime("%Y")
        tomorrow_date = tomorrow.strftime("%Y-%m-%d")
        
        system_prompt = (
            "Eres un asistente experto en extraer fechas de texto en español. "
            "Devuelve SOLO la fecha y hora en formato ISO 8601 (YYYY-MM-DD HH:MM:SS). "
            "Si no hay hora específica, usa 09:00:00 por defecto. "
            "No añadas explicaciones, SOLO la fecha.\n\n"
            f"REFERENCIA TEMPORAL:\n"
            f"- HOY es: {current_date} ({current_weekday_name})\n"
            f"- MAÑANA es: {tomorrow_date}\n"
            f"- Día actual: {current_day}, Mes: {current_month}, Año: {current_year}\n\n"
            "REGLAS IMPORTANTES:\n"
            f"- 'mañana' = {tomorrow_date}\n"
            f"- 'hoy' = {current_date[:10]}\n"
            "- 'el jueves', 'el viernes', etc. = PRÓXIMO día de esa semana (futuro)\n"
            "- 'pasado mañana' = 2 días después de hoy\n"
            "- '3pm' o '15h' = 15:00:00\n"
            "- '8am' o '8h' = 08:00:00\n"
            "- Si dice 'de X a Y', extrae SOLO la hora de inicio X\n"
            "- SIEMPRE usa fechas FUTURAS, nunca pasadas\n\n"
            "Ejemplos:\n"
            f"- 'mañana a las 3pm' -> {tomorrow_date} 15:00:00\n"
            f"- 'hoy a las 5pm' -> {now.strftime('%Y-%m-%d')} 17:00:00"
        )
        
        prompt = f"Texto del usuario: '{text}'\n\nFecha de inicio en formato ISO 8601:"
        
        # Obtener respuesta de Ollama
        response = await self.generate(prompt, system=system_prompt)
        response = response.strip()
        
        if response.upper() == "NONE" or not response:
            return None
        
        # Post-procesamiento con dateparser para validar y corregir
        try:
            # Intentar parsear con dateparser (preferir fechas futuras)
            parsed_date = dateparser.parse(
                response,
                settings={
                    'PREFER_DATES_FROM': 'future',
                    'TIMEZONE': 'Europe/Madrid',
                    'RETURN_AS_TIMEZONE_AWARE': False
                }
            )
            
            if parsed_date:
                # Validar que la fecha sea futura
                if parsed_date < now:
                    # Si la fecha es pasada, intentar parsear el texto original directamente
                    parsed_from_text = dateparser.parse(
                        text,
                        languages=['es'],
                        settings={
                            'PREFER_DATES_FROM': 'future',
                            'TIMEZONE': 'Europe/Madrid',
                            'RETURN_AS_TIMEZONE_AWARE': False
                        }
                    )
                    if parsed_from_text and parsed_from_text >= now:
                        return parsed_from_text.strftime("%Y-%m-%d %H:%M:%S")
                
                return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
            
        except Exception as e:
            # Si dateparser falla, usar la respuesta de Ollama tal cual
            pass
        
        return response
    
    async def extract_event_structure(self, event_text: str) -> Optional[Dict[str, str]]:
        """Extrae el título del evento y el contexto temporal por separado usando NLP"""
        from datetime import datetime
        
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d %H:%M:%S")
        
        weekdays_es = {
            0: 'lunes', 1: 'martes', 2: 'miércoles', 3: 'jueves',
            4: 'viernes', 5: 'sábado', 6: 'domingo'
        }
        current_weekday = weekdays_es[now.weekday()]
        
        system_prompt = (
            f"{JARVIS_CORE_PROMPT}\n\n"
            "Tu objetivo es estructurar la petición del usuario en un formato JSON estricto para la API de Google Calendar.\n\n"
            "DATOS DE CONTEXTO:\n"
            f"- Fecha y hora actual: {current_date}\n"
            f"- Día de la semana actual: {current_weekday}\n\n"
            "INSTRUCCIONES DE EXTRACCIÓN:\n"
            "1. CAMPO 'summary' (El título del evento):\n"
            "   - DEBE incluir: La actividad (Examen, Cita, Reunión), el tema específico (Tema 6, Proyecto X) y personas involucradas.\n"
            "   - DEBE ELIMINAR: Cualquier referencia temporal (hoy, mañana, el lunes, a las 5, next week, 16:00).\n"
            "   - Formato: Capitalizado y gramaticalmente correcto.\n\n"
            "2. CAMPO 'date_context' (La referencia temporal):\n"
            "   - Extrae todo el texto relacionado con CUÁNDO ocurre el evento para que pueda ser procesado por un parser de fechas.\n\n"
            "EJEMPLOS DE COMPORTAMIENTO (Few-Shot):\n"
            "Input: \"reunión con carlos el martes a las 10 sobre el presupuesto\"\n"
            "Output: {\"summary\": \"Reunión con Carlos sobre el presupuesto\", \"date_context\": \"el martes a las 10\"}\n\n"
            "Input: \"add examen el martes a las 16 de programacion del tema 6\"\n"
            "Output: {\"summary\": \"Examen de programación del tema 6\", \"date_context\": \"el martes a las 16\"}\n\n"
            "Input: \"ir al dentista mañana\"\n"
            "Output: {\"summary\": \"Ir al dentista\", \"date_context\": \"mañana\"}\n\n"
            "Input: \"llamar a juan el viernes por la tarde\"\n"
            "Output: {\"summary\": \"Llamar a Juan\", \"date_context\": \"el viernes por la tarde\"}\n\n"
            "Input: \"presentación del proyecto final el próximo lunes a las 9\"\n"
            "Output: {\"summary\": \"Presentación del proyecto final\", \"date_context\": \"el próximo lunes a las 9\"}\n\n"
            "Responde ÚNICAMENTE con el objeto JSON. No añadas markdown ni explicaciones extra."
        )
        
        prompt = f"Input: \"{event_text}\"\nOutput:"
        
        try:
            response = await self.generate(prompt, system=system_prompt)
            response = response.strip()
            
            # Limpiar markdown si existe
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            # Parsear JSON
            import re
            json_match = re.search(r'\{[^{}]*"summary"[^{}]*"date_context"[^{}]*\}', response, re.DOTALL)
            if json_match:
                response = json_match.group(0)
            
            result = json.loads(response)
            
            # Validar campos requeridos
            if "summary" in result and "date_context" in result:
                return result
            else:
                logger.warning(f"Missing required fields in event structure: {result}")
                return None
                
        except Exception as e:
            logger.error(f"Error extracting event structure: {e}")
            return None
    
    async def generate_quiz(self, context: str, num_questions: int = 5) -> str:
        system_prompt = (
            "Eres un profesor que genera preguntas de quiz basadas en el contexto proporcionado. "
            "Genera preguntas claras y concisas con sus respuestas."
        )
        
        prompt = (
            f"Genera {num_questions} preguntas de quiz basadas en este contexto:\n\n"
            f"{context}\n\n"
            f"Formato: Q1: [pregunta]\nA1: [respuesta]\n"
        )
        
        return await self.generate(prompt, system=system_prompt)
    
    async def answer_question(self, question: str, context: str) -> str:
        system_prompt = (
            f"{JARVIS_CORE_PROMPT}\n\n"
            "Responde preguntas basándote en el contexto proporcionado. "
            "Si la respuesta no está en el contexto, indica claramente que no tienes suficiente información "
            "y sugiere cómo el usuario podría obtenerla."
        )
        
        prompt = (
            f"Contexto:\n{context}\n\n"
            f"Pregunta: {question}\n\n"
            f"Respuesta:"
        )
        
        return await self.generate_response(prompt, system_prompt=system_prompt)
    
    async def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Genera una respuesta usando el modelo de lenguaje"""
        return await self.generate(prompt, system=system_prompt)
    
    async def check_model_status(self) -> Dict[str, Any]:
        """Verifica el estado del modelo y retorna información de diagnóstico"""
        try:
            is_available = await self._verify_model_availability()
            return {
                "available": is_available,
                "current_model": self.model,
                "timeout": self.timeout,
                "fallback_models": self.fallback_models
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "current_model": self.model
            }
    
    async def prioritize_news(self, title: str, content: str, topic: str) -> int:
        system_prompt = (
            f"{JARVIS_CORE_PROMPT}\n\n"
            "Evalúa la prioridad de noticias del 1 al 5. "
            "5 = Urgente/Crítico, 1 = Informativo. "
            "Devuelve SOLO un número del 1 al 5."
        )
        
        prompt = (
            f"Evalúa la prioridad de esta noticia sobre '{topic}':\n"
            f"Título: {title}\n"
            f"Contenido: {content[:500]}\n"
        )
        
        try:
            # Usar modelo potente para análisis de noticias (mejor criterio)
            response = await self.generate(prompt, system=system_prompt, use_powerful_model=True)
            priority = int(response.strip())
            return max(1, min(5, priority))
        except Exception as e:
            logger.warning(f"⚠️ Error prioritizing news, using default priority 3: {e}")
            return 3
