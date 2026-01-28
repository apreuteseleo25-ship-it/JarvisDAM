from telegram import Update
from telegram.ext import ContextTypes
from src.models.database import DatabaseService, NewsSubscription, NewsItem
from src.services.ollama_service import OllamaService
from src.services.cache_service import CacheService
from src.utils.retry import async_retry_with_backoff
from src.utils.rate_limiter import APIRateLimiter
from src.utils.logger import get_logger
from sqlalchemy import and_
import aiohttp
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import random
import asyncio
import feedparser
from datetime import datetime

logger = get_logger("intel_module")

# Dominio de operaciones - Categorías permitidas basadas en fuentes disponibles
ALLOWED_TOPIC_CATEGORIES = [
    'tecnologia', 'technology', 'tech',
    'programacion', 'programming', 'desarrollo', 'development',
    'inteligencia artificial', 'ia', 'ai', 'machine learning', 'ml',
    'ciberseguridad', 'cybersecurity', 'seguridad', 'security',
    'startup', 'startups', 'emprendimiento',
    'software', 'hardware',
    'web', 'frontend', 'backend', 'fullstack',
    'python', 'javascript', 'java', 'rust', 'go', 'c++',
    'devops', 'cloud', 'aws', 'azure', 'docker', 'kubernetes',
    'blockchain', 'crypto', 'bitcoin',
    'datos', 'data', 'big data', 'analytics',
    'movil', 'mobile', 'android', 'ios',
    'ciencia', 'science', 'investigacion', 'research'
]


class IntelModule:
    def __init__(self, db_service: DatabaseService, ollama_service: OllamaService, cache_service: CacheService):
        self.db_service = db_service
        self.ollama_service = ollama_service
        self.cache_service = cache_service
        self.api_rate_limiter = APIRateLimiter(requests_per_minute=30)
        
        # NewsBuffer: Always-On Cache - Mantiene 15 noticias listas por tema
        self.news_buffer: Dict[str, List[Dict[str, Any]]] = {}
        
        # RSS Feeds por categoría tecnológica
        self.rss_feeds = {
            'technology': [
                'https://news.ycombinator.com/rss',
                'https://www.reddit.com/r/technology/.rss',
            ],
            'programming': [
                'https://www.reddit.com/r/programming/.rss',
                'https://news.ycombinator.com/rss',
            ],
            'ai': [
                'https://www.reddit.com/r/artificial/.rss',
                'https://www.reddit.com/r/MachineLearning/.rss',
            ],
            'cybersecurity': [
                'https://www.reddit.com/r/cybersecurity/.rss',
                'https://www.reddit.com/r/netsec/.rss',
            ],
            'default': [
                'https://news.ycombinator.com/rss',
            ]
        }
    
    def validate_topic(self, topic: str) -> bool:
        """
        Valida si un tema está dentro del dominio de operaciones permitido.
        Verifica coincidencia semántica con las categorías de tecnología disponibles.
        """
        topic_lower = topic.lower().strip()
        
        # Verificar coincidencia directa o parcial con categorías permitidas
        for allowed_category in ALLOWED_TOPIC_CATEGORIES:
            if allowed_category in topic_lower or topic_lower in allowed_category:
                return True
        
        # Verificar palabras clave individuales
        topic_words = topic_lower.split()
        for word in topic_words:
            if len(word) > 3:  # Ignorar palabras muy cortas
                for allowed_category in ALLOWED_TOPIC_CATEGORIES:
                    if word in allowed_category or allowed_category in word:
                        return True
        
        return False
    
    def _get_feed_category(self, topic: str) -> str:
        """Mapea un tema a una categoría de RSS feed"""
        topic_lower = topic.lower()
        
        if any(kw in topic_lower for kw in ['ai', 'inteligencia', 'machine learning', 'ml']):
            return 'ai'
        elif any(kw in topic_lower for kw in ['program', 'desarrollo', 'development', 'code']):
            return 'programming'
        elif any(kw in topic_lower for kw in ['security', 'ciberseguridad', 'seguridad']):
            return 'cybersecurity'
        elif any(kw in topic_lower for kw in ['tech', 'tecnologia']):
            return 'technology'
        else:
            return 'default'
    
    async def refresh_news_for_topic(self, topic: str) -> int:
        """
        Refresca el buffer de noticias para un tema específico.
        Descarga RSS feeds y mantiene las 15 noticias más recientes.
        
        Returns:
            Número de noticias añadidas al buffer
        """
        try:
            category = self._get_feed_category(topic)
            feeds = self.rss_feeds.get(category, self.rss_feeds['default'])
            
            all_news = []
            
            for feed_url in feeds:
                try:
                    # feedparser con timeout implícito
                    feed = await asyncio.to_thread(feedparser.parse, feed_url)
                    
                    for entry in feed.entries[:10]:  # Máximo 10 por feed
                        news_item = {
                            'title': entry.get('title', 'Sin título'),
                            'url': entry.get('link', ''),
                            'content': entry.get('summary', entry.get('title', ''))[:500],
                            'published': entry.get('published', datetime.now().isoformat()),
                            'topic': topic
                        }
                        all_news.append(news_item)
                    
                    await asyncio.sleep(0.5)  # Rate limiting
                    
                except Exception as e:
                    logger.warning(f"Error fetching feed {feed_url}: {e}")
                    continue
            
            # Filtrar duplicados por URL
            seen_urls = set()
            unique_news = []
            for item in all_news:
                if item['url'] not in seen_urls:
                    seen_urls.add(item['url'])
                    unique_news.append(item)
            
            # Mantener solo las 15 más recientes
            unique_news = unique_news[:15]
            
            # Actualizar buffer (no borrar si no hay nuevas noticias)
            if unique_news:
                self.news_buffer[topic] = unique_news
                logger.info(f"✅ Buffer actualizado para '{topic}': {len(unique_news)} noticias")
            else:
                # Si no hay noticias nuevas, mantener las viejas
                if topic not in self.news_buffer:
                    self.news_buffer[topic] = []
                logger.warning(f"⚠️ No se encontraron noticias nuevas para '{topic}', manteniendo buffer anterior")
            
            return len(unique_news)
            
        except Exception as e:
            logger.error(f"❌ Error refrescando noticias para '{topic}': {e}", exc_info=True)
            return 0
    
    async def subscribe_topic(self, user_id: int, topic: str) -> tuple[bool, str]:
        """
        Suscribe a un usuario a un tema de noticias.
        IMPORTANTE: Ahora inicia fetch inmediato de noticias.
        Returns: (success: bool, message: str)
        """
        # Validar que el tema esté dentro del dominio de operaciones
        if not self.validate_topic(topic):
            return False, "invalid_domain"
        
        with self.db_service.get_session() as session:
            existing = session.query(NewsSubscription).filter(
                and_(
                    NewsSubscription.user_id == user_id,
                    NewsSubscription.topic == topic
                )
            ).first()
            
            if existing:
                return False, "already_subscribed"
            
            subscription = NewsSubscription(user_id=user_id, topic=topic)
            session.add(subscription)
            session.commit()
        
        # ACCIÓN BLOQUEANTE: Iniciar fetch inmediato
        await self.refresh_news_for_topic(topic)
        
        return True, "success"
    
    async def unsubscribe_topic(self, user_id: int, topic: str) -> bool:
        with self.db_service.get_session() as session:
            subscription = session.query(NewsSubscription).filter(
                and_(
                    NewsSubscription.user_id == user_id,
                    NewsSubscription.topic == topic
                )
            ).first()
            
            if subscription:
                session.delete(subscription)
                session.commit()
                return True
            
            return False
    
    def get_user_subscriptions(self, user_id: int) -> List[str]:
        with self.db_service.get_session() as session:
            subscriptions = session.query(NewsSubscription).filter(
                NewsSubscription.user_id == user_id
            ).all()
            
            return [sub.topic for sub in subscriptions]
    
    @async_retry_with_backoff(
        max_retries=3,
        initial_delay=5.0,
        backoff_factor=2.0,
        exceptions=(aiohttp.ClientError, asyncio.TimeoutError)
    )
    async def _fetch_news_from_api(self, topic: str) -> List[Dict[str, Any]]:
        await self.api_rate_limiter.wait_if_needed()
        
        news_items = []
        search_url = f"https://news.ycombinator.com/search?q={topic}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, timeout=10) as response:
                if response.status == 429:
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=429,
                        message="Rate limit exceeded"
                    )
                
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    for item in soup.find_all('tr', class_='athing')[:5]:
                        title_elem = item.find('span', class_='titleline')
                        if title_elem and title_elem.find('a'):
                            title = title_elem.find('a').text
                            url = title_elem.find('a')['href']
                            
                            news_items.append({
                                'title': title,
                                'url': url,
                                'content': title
                            })
                        
                        await asyncio.sleep(0.1)
        
        return news_items
    
    async def fetch_news_for_topic(self, topic: str) -> List[Dict[str, Any]]:
        cached_news = self.cache_service.get_cached_news(topic)
        
        if cached_news is not None:
            return cached_news
        
        try:
            news_items = await self._fetch_news_from_api(topic)
            
            if news_items:
                self.cache_service.set_cached_news(topic, news_items)
            
            return news_items
        
        except Exception as e:
            logger.error(f"❌ Error fetching news for {topic}: {e}", exc_info=True)
            return []
    
    async def snipe_news(self, user_id: int) -> int:
        """
        Lee noticias del buffer (cache) en lugar de hacer fetch on-demand.
        Si el buffer está vacío, fuerza una actualización de emergencia.
        """
        topics = self.get_user_subscriptions(user_id)
        
        if not topics:
            return 0
        
        total_added = 0
        
        for topic in topics:
            # Leer del buffer (instantáneo)
            news_items = self.news_buffer.get(topic, [])
            
            # Si el buffer está vacío, actualización de emergencia
            if not news_items:
                logger.warning(f"⚠️ Buffer vacío para '{topic}', forzando actualización de emergencia")
                await self.refresh_news_for_topic(topic)
                news_items = self.news_buffer.get(topic, [])
            
            # Procesar noticias del buffer
            for item in news_items:
                priority = await self.ollama_service.prioritize_news(
                    item['title'],
                    item['content'],
                    topic
                )
                
                with self.db_service.get_session() as session:
                    existing = session.query(NewsItem).filter(
                        and_(
                            NewsItem.user_id == user_id,
                            NewsItem.url == item['url']
                        )
                    ).first()
                    
                    if not existing:
                        news_item = NewsItem(
                            user_id=user_id,
                            title=item['title'],
                            url=item['url'],
                            content=item.get('content', item['title']),
                            topic=topic,
                            priority=priority
                        )
                        session.add(news_item)
                        session.commit()
                        total_added += 1
                
                await asyncio.sleep(0.1)
            
            await asyncio.sleep(0.3)
        
        return total_added
    
    async def update_all_feeds(self) -> Dict[str, int]:
        """
        Actualiza el buffer de noticias para todos los temas suscritos.
        Usado por el background worker cada 30 minutos.
        
        Returns:
            Dict con el número de noticias actualizadas por tema
        """
        # Obtener todos los temas únicos de todos los usuarios
        with self.db_service.get_session() as session:
            all_subscriptions = session.query(NewsSubscription).all()
            unique_topics = list(set([sub.topic for sub in all_subscriptions]))
        
        results = {}
        
        for topic in unique_topics:
            try:
                count = await self.refresh_news_for_topic(topic)
                results[topic] = count
                await asyncio.sleep(1)  # Rate limiting entre temas
            except Exception as e:
                logger.error(f"❌ Error actualizando feed para '{topic}': {e}")
                results[topic] = 0
        
        logger.info(f"🔄 Actualización de feeds completada: {results}")
        return results
    
    def get_priority_news(self, user_id: int, priority: int = 5) -> List[NewsItem]:
        with self.db_service.get_session() as session:
            news = session.query(NewsItem).filter(
                and_(
                    NewsItem.user_id == user_id,
                    NewsItem.priority == priority,
                    NewsItem.read == False
                )
            ).all()
            
            return [
                NewsItem(
                    id=item.id,
                    user_id=item.user_id,
                    title=item.title,
                    url=item.url,
                    priority=item.priority,
                    topic=item.topic,
                    content=item.content,
                    read=item.read,
                    created_at=item.created_at
                ) for item in news
            ]
    
    def get_daily_highlight(self, user_id: int) -> NewsItem:
        with self.db_service.get_session() as session:
            unread_news = session.query(NewsItem).filter(
                and_(
                    NewsItem.user_id == user_id,
                    NewsItem.read == False
                )
            ).order_by(NewsItem.priority.desc()).all()
            
            if not unread_news:
                return None
            
            high_priority = [n for n in unread_news if n.priority >= 4]
            
            if high_priority:
                selected = random.choice(high_priority)
            else:
                selected = random.choice(unread_news)
            
            return NewsItem(
                id=selected.id,
                user_id=selected.user_id,
                title=selected.title,
                url=selected.url,
                priority=selected.priority,
                topic=selected.topic,
                content=selected.content,
                read=selected.read,
                created_at=selected.created_at
            )
    
    def mark_as_read(self, user_id: int, news_id: int) -> bool:
        with self.db_service.get_session() as session:
            news = session.query(NewsItem).filter(
                and_(
                    NewsItem.id == news_id,
                    NewsItem.user_id == user_id
                )
            ).first()
            
            if news:
                news.read = True
                session.commit()
                return True
            
            return False
    
    async def generate_news_summary(self, user_id: int, density_level: str = "flash") -> str:
        """
        Genera un resumen de noticias agrupado por temas con densidad variable.
        
        Args:
            user_id: ID del usuario
            density_level: "flash" para resumen conciso, "deep" para análisis profundo
        
        Returns:
            Resumen formateado en Markdown
        """
        # Obtener noticias no leídas del usuario
        with self.db_service.get_session() as session:
            news_items = session.query(NewsItem).filter(
                and_(
                    NewsItem.user_id == user_id,
                    NewsItem.read == False
                )
            ).order_by(NewsItem.priority.desc()).limit(20).all()
            
            if not news_items:
                return None
            
            # Agrupar noticias por tema
            news_by_topic = {}
            for item in news_items:
                topic = item.topic
                if topic not in news_by_topic:
                    news_by_topic[topic] = []
                news_by_topic[topic].append({
                    'title': item.title,
                    'content': item.content,
                    'url': item.url,
                    'priority': item.priority
                })
        
        # Construir prompt para Ollama según densidad
        if density_level == "flash":
            system_prompt = (
                "Eres JARVIS. Genera un resumen de noticias EXTREMADAMENTE CONCISO.\n\n"
                "FORMATO OBLIGATORIO:\n"
                "- Agrupa por tema con encabezados: ## 🔹 [TEMA]\n"
                "- Cada noticia: UN bullet point con título + 1 frase (máximo 15 palabras)\n"
                "- NO añadas contexto extra, solo lo esencial\n"
                "- Usa emojis relevantes para cada tema\n\n"
                "Ejemplo:\n"
                "## 🤖 Inteligencia Artificial\n"
                "• **OpenAI lanza GPT-5**: Nueva versión con capacidades multimodales mejoradas.\n"
                "• **Google anuncia Gemini 2.0**: Supera a GPT-4 en benchmarks clave.\n"
            )
        else:  # deep
            system_prompt = (
                "Eres JARVIS. Genera un análisis PROFUNDO de noticias.\n\n"
                "FORMATO OBLIGATORIO:\n"
                "- Agrupa por tema con encabezados: ## 🔹 [TEMA]\n"
                "- Cada noticia: Título en negrita + 2-3 párrafos explicativos\n"
                "- Incluye: Qué pasó, por qué importa, contexto relevante\n"
                "- Usa emojis relevantes para cada tema\n"
                "- Sé analítico y proporciona insights\n\n"
                "Ejemplo:\n"
                "## 🤖 Inteligencia Artificial\n\n"
                "**OpenAI lanza GPT-5**\n\n"
                "OpenAI ha anunciado el lanzamiento de GPT-5, su modelo de lenguaje más avanzado...\n"
            )
        
        # Construir el contenido de noticias para el prompt
        news_content = ""
        for topic, items in news_by_topic.items():
            news_content += f"\n\n=== TEMA: {topic.upper()} ===\n"
            for item in items[:5]:  # Limitar a 5 noticias por tema
                news_content += f"\nTítulo: {item['title']}\n"
                news_content += f"Contenido: {item['content'][:300]}...\n"
                news_content += f"Prioridad: {item['priority']}/5\n"
        
        prompt = (
            f"Genera un resumen de las siguientes noticias agrupadas por tema.\n"
            f"Nivel de detalle: {'MÍNIMO (Flash Briefing)' if density_level == 'flash' else 'MÁXIMO (Análisis Profundo)'}.\n\n"
            f"{news_content}\n\n"
            f"Resumen:"
        )
        
        try:
            summary = await self.ollama_service.generate(
                prompt=prompt,
                system=system_prompt,
                timeout=180
            )
            
            # Añadir encabezado
            header = (
                f"{'⚡' if density_level == 'flash' else '🧐'} **{'FLASH BRIEFING' if density_level == 'flash' else 'ANÁLISIS PROFUNDO'}**\n"
                f"📅 {len(news_items)} noticias procesadas\n\n"
                "---\n\n"
            )
            
            return header + summary.strip()
            
        except Exception as e:
            logger.error(f"Error generating news summary: {e}", exc_info=True)
            return None
