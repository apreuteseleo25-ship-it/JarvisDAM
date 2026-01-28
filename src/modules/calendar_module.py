from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from src.services.google_auth_service import GoogleAuthService
from src.services.ollama_service import OllamaService
from src.utils.logger import get_logger
from datetime import datetime, timedelta
from dateutil import parser
from typing import List, Dict, Any, Optional

logger = get_logger("calendar_module")


class CalendarModule:
    def __init__(self, auth_service: GoogleAuthService, ollama_service: OllamaService):
        self.auth_service = auth_service
        self.ollama_service = ollama_service
    
    def _get_calendar_service(self, telegram_user_id: int):
        credentials = self.auth_service.get_credentials(telegram_user_id)
        
        if not credentials:
            raise ValueError("No valid credentials found. Please authenticate with /login first.")
        
        return build('calendar', 'v3', credentials=credentials)
    
    async def add_event(
        self,
        telegram_user_id: int,
        title: str,
        description: Optional[str] = None,
        deadline_text: Optional[str] = None
    ) -> Dict[str, Any]:
        service = self._get_calendar_service(telegram_user_id)
        
        if not service:
            return {
                "success": False,
                "error": "not_authenticated",
                "message": "❌ Primero debes autenticarte con /login"
            }
        
        # Extraer estructura del evento (título limpio + contexto temporal)
        event_structure = await self.ollama_service.extract_event_structure(title)
        
        if event_structure:
            clean_title = event_structure["summary"]
            date_context = event_structure["date_context"]
            logger.info(f"Extracted event structure - Title: '{clean_title}', Date context: '{date_context}'")
        else:
            # Fallback: usar el título original
            clean_title = title
            date_context = deadline_text or title
            logger.warning(f"Failed to extract event structure, using original title")
        
        start_time = None
        end_time = None
        
        if date_context:
            start_time = await self._parse_deadline(date_context)
            # Intentar extraer hora de fin si el texto contiene "hasta" o "a"
            end_time = await self._parse_end_time(date_context, start_time)
        
        if not start_time:
            start_time = datetime.utcnow() + timedelta(days=1)
        
        if not end_time:
            end_time = start_time + timedelta(hours=1)
        
        event = {
            'summary': clean_title,
            'description': description or '',
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'Europe/Madrid',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'Europe/Madrid',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 30},
                    {'method': 'popup', 'minutes': 10},
                ],
            },
        }
        
        try:
            created_event = service.events().insert(
                calendarId='primary',
                body=event
            ).execute()
            
            logger.info(f"Created calendar event for Telegram user {telegram_user_id}: {title}")
            
            return {
                "success": True,
                "event_id": created_event['id'],
                "title": title,
                "start_time": start_time,
                "html_link": created_event.get('htmlLink')
            }
        
        except HttpError as e:
            logger.error(f"HTTP error creating event for user {telegram_user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": "api_error",
                "message": f"❌ Error de Google Calendar: {e.reason}"
            }
        except Exception as e:
            logger.error(f"Error creating event for user {telegram_user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": "unknown",
                "message": f"❌ Error inesperado: {str(e)}"
            }
    
    async def _parse_deadline(self, deadline_text: str) -> Optional[datetime]:
        """Parse deadline con validación mejorada usando Ollama + dateparser"""
        import dateparser
        
        try:
            # Primero intentar con Ollama (ya incluye dateparser internamente)
            date_str = await self.ollama_service.extract_date_from_text(deadline_text)
            
            if date_str and date_str.upper() != "NONE":
                parsed = parser.parse(date_str)
                
                # Validar que la fecha sea futura
                now = datetime.now()
                if parsed and parsed >= now:
                    return parsed
                else:
                    logger.warning(f"Parsed date {parsed} is in the past, trying dateparser fallback")
        except Exception as e:
            logger.warning(f"Error parsing deadline with Ollama: {e}")
        
        # Fallback: usar dateparser directamente en español
        try:
            parsed = dateparser.parse(
                deadline_text,
                languages=['es'],
                settings={
                    'PREFER_DATES_FROM': 'future',
                    'TIMEZONE': 'Europe/Madrid',
                    'RETURN_AS_TIMEZONE_AWARE': False
                }
            )
            if parsed:
                return parsed
        except Exception as e:
            logger.warning(f"Error with dateparser: {e}")
        
        # Último fallback: python-dateutil
        try:
            return parser.parse(deadline_text, fuzzy=True)
        except:
            pass
        
        return None
    
    async def _parse_end_time(self, text: str, start_time: Optional[datetime]) -> Optional[datetime]:
        """Extrae la hora de fin si el texto contiene 'hasta', 'a las' después de una hora"""
        if not start_time:
            return None
        
        import re
        
        # Buscar patrones como "hasta las 8pm", "a las 8pm", "de 3pm a 8pm"
        patterns = [
            r'hasta\s+(?:las\s+)?(\d{1,2})\s*([ap]m)?',
            r'de\s+\d{1,2}\s*[ap]m\s+a\s+(?:las\s+)?(\d{1,2})\s*([ap]m)?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                hour = int(match.group(1))
                am_pm = match.group(2)
                
                # Convertir a formato 24h
                if am_pm == 'pm' and hour != 12:
                    hour += 12
                elif am_pm == 'am' and hour == 12:
                    hour = 0
                
                # Crear datetime con la misma fecha que start_time pero con la hora de fin
                end_time = start_time.replace(hour=hour, minute=0, second=0)
                
                # Si la hora de fin es menor que la de inicio, probablemente sea del día siguiente
                if end_time <= start_time:
                    end_time = end_time + timedelta(days=1)
                
                return end_time
        
        return None
    
    async def get_today_events(self, telegram_user_id: int) -> List[Dict[str, Any]]:
        """
        Obtiene los eventos de hoy para el daily briefing.
        Returns: Lista de eventos con formato simplificado {title, start_time}
        """
        try:
            service = self._get_calendar_service(telegram_user_id)
        except ValueError:
            return []
        
        # Definir inicio y fin del día de hoy
        now = datetime.now()
        start_of_day = datetime(now.year, now.month, now.day, 0, 0, 0)
        end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59)
        
        try:
            events_result = service.events().list(
                calendarId='primary',
                timeMin=start_of_day.isoformat() + 'Z',
                timeMax=end_of_day.isoformat() + 'Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Formatear eventos para el briefing
            formatted_events = []
            for event in events:
                start = event.get('start', {})
                start_time_str = start.get('dateTime', start.get('date', ''))
                
                if start_time_str:
                    try:
                        start_dt = parser.parse(start_time_str)
                        time_formatted = start_dt.strftime('%H:%M')
                    except:
                        time_formatted = "Todo el día"
                else:
                    time_formatted = "Todo el día"
                
                formatted_events.append({
                    'title': event.get('summary', 'Sin título'),
                    'start_time': time_formatted
                })
            
            return formatted_events
        
        except Exception as e:
            logger.error(f"Error getting today's events: {e}", exc_info=True)
            return []
    
    def list_events(
        self,
        telegram_user_id: int,
        max_results: int = 10,
        time_min: Optional[datetime] = None
    ) -> Dict[str, Any]:
        try:
            service = self._get_calendar_service(telegram_user_id)
        except ValueError as e:
            logger.warning(f"User {telegram_user_id} not authenticated: {e}")
            return {
                "success": False,
                "error": "not_authenticated",
                "events": []
            }
        
        if not time_min:
            time_min = datetime.utcnow()
        
        try:
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min.isoformat() + 'Z',
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            logger.info(f"Retrieved {len(events)} events for Telegram user {telegram_user_id}")
            
            return {
                "success": True,
                "events": events
            }
        
        except HttpError as e:
            logger.error(f"HTTP error listing events for user {telegram_user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": "api_error",
                "events": []
            }
        except Exception as e:
            logger.error(f"Error listing events for user {telegram_user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": "unknown",
                "events": []
            }
    
    def mark_event_completed(self, telegram_user_id: int, event_id: str) -> Dict[str, Any]:
        try:
            service = self._get_calendar_service(telegram_user_id)
        except ValueError as e:
            logger.warning(f"User {telegram_user_id} not authenticated: {e}")
            return {
                "success": False,
                "error": "not_authenticated"
            }
        
        try:
            event = service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            event['summary'] = f"✅ {event['summary']}"
            event['colorId'] = '10'
            
            updated_event = service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event
            ).execute()
            
            logger.info(f"Marked event {event_id} as completed for user {telegram_user_id}")
            
            return {
                "success": True,
                "event_id": event_id
            }
        
        except HttpError as e:
            logger.error(f"HTTP error marking event completed for user {telegram_user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": "api_error"
            }
        except Exception as e:
            logger.error(f"Error marking event completed for user {telegram_user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": "unknown"
            }
    
    def delete_event(self, telegram_user_id: int, event_id: str) -> Dict[str, Any]:
        try:
            service = self._get_calendar_service(telegram_user_id)
        except ValueError as e:
            logger.warning(f"User {telegram_user_id} not authenticated: {e}")
            return {
                "success": False,
                "error": "not_authenticated"
            }
        
        try:
            service.events().delete(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            logger.info(f"Deleted event {event_id} for user {telegram_user_id}")
            
            return {
                "success": True,
                "event_id": event_id
            }
        
        except HttpError as e:
            logger.error(f"HTTP error deleting event for user {telegram_user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": "api_error"
            }
        except Exception as e:
            logger.error(f"Error deleting event for user {telegram_user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": "unknown"
            }
    
    def get_upcoming_events(
        self,
        telegram_user_id: int,
        hours_ahead: int = 24
    ) -> List[Dict[str, Any]]:
        time_min = datetime.utcnow()
        time_max = time_min + timedelta(hours=hours_ahead)
        
        try:
            service = self._get_calendar_service(telegram_user_id)
        except ValueError:
            return []
        
        try:
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min.isoformat() + 'Z',
                timeMax=time_max.isoformat() + 'Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            logger.info(f"Retrieved {len(events)} upcoming events for user {telegram_user_id}")
            
            return events
        
        except Exception as e:
            logger.error(f"Error getting upcoming events for user {telegram_user_id}: {e}", exc_info=True)
            return []
