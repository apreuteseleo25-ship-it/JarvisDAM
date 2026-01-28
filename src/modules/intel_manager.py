"""
IntelManager - Sistema robusto de gestión de noticias con caché persistente.
Usa bot_data para almacenar noticias y evitar duplicados mediante hashing.
"""
from telegram.ext import ContextTypes
from src.models.database import DatabaseService, NewsSubscription
from src.services.ollama_service import OllamaService
from src.utils.logger import get_logger
from sqlalchemy import and_
import feedparser
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import asyncio

logger = get_logger("intel_manager")

# Dominio de operaciones - Categorías permitidas
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


class IntelManager:
    def __init__(self, db_service: DatabaseService, ollama_service: OllamaService):
        self.db_service = db_service
        self.ollama_service = ollama_service
        
        # RSS Feeds por categoría tecnológica
        # Incluye feeds con contenido histórico y popular (no solo últimas 24h)
        self.rss_feeds = {
            'technology': [
                'https://news.ycombinator.com/rss',
                'https://www.reddit.com/r/technology/.rss',
                'https://www.reddit.com/r/technology/top/.rss?t=week',  # Top semanal
                'https://www.reddit.com/r/technology/top/.rss?t=month',  # Top mensual
            ],
            'programming': [
                'https://www.reddit.com/r/programming/.rss',
                'https://www.reddit.com/r/programming/top/.rss?t=week',
                'https://www.reddit.com/r/programming/top/.rss?t=month',
                'https://news.ycombinator.com/rss',
            ],
            'ai': [
                'https://www.reddit.com/r/artificial/.rss',
                'https://www.reddit.com/r/MachineLearning/.rss',
                'https://www.reddit.com/r/artificial/top/.rss?t=week',
                'https://www.reddit.com/r/MachineLearning/top/.rss?t=month',
            ],
            'cybersecurity': [
                'https://www.reddit.com/r/cybersecurity/.rss',
                'https://www.reddit.com/r/netsec/.rss',
                'https://www.reddit.com/r/cybersecurity/top/.rss?t=week',
                'https://www.reddit.com/r/netsec/top/.rss?t=month',
            ],
            'default': [
                'https://news.ycombinator.com/rss',
                'https://www.reddit.com/r/technology/.rss',
                'https://www.reddit.com/r/technology/top/.rss?t=week',
            ]
        }
    
    def _generate_hash(self, title: str, link: str) -> str:
        """Genera hash único para detectar duplicados"""
        unique_string = f"{title}|{link}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
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
    
    def validate_topic(self, topic: str) -> bool:
        """Valida si un tema está dentro del dominio de operaciones permitido"""
        topic_lower = topic.lower().strip()
        
        for allowed_category in ALLOWED_TOPIC_CATEGORIES:
            if allowed_category in topic_lower or topic_lower in allowed_category:
                return True
        
        topic_words = topic_lower.split()
        for word in topic_words:
            if len(word) > 3:
                for allowed_category in ALLOWED_TOPIC_CATEGORIES:
                    if word in allowed_category or allowed_category in word:
                        return True
        
        return False
    
    async def _translate_and_prioritize_news(self, news_items: list) -> list:
        """
        Traduce títulos al español y asigna prioridad de importancia (1-5).
        Usa LLM para ambas tareas en una sola llamada.
        """
        if not news_items:
            return []
        
        try:
            # Procesar en lotes pequeños para mejor precisión
            for i, item in enumerate(news_items[:10]):
                try:
                    prompt = f"""Título: {item['titulo']}

Tareas:
1. Si está en inglés, tradúcelo al español (mantén términos técnicos)
2. Evalúa importancia con CRITERIO ESTRICTO:
   - 5: Solo vulnerabilidades críticas, lanzamientos revolucionarios (muy raro)
   - 4: Anuncios importantes de empresas grandes, tecnologías disruptivas
   - 3: Noticias interesantes, proyectos nuevos, tutoriales útiles (MAYORÍA)
   - 2: Noticias menores, actualizaciones pequeñas
   - 1: Trivial, off-topic

SÉ CONSERVADOR: La mayoría deben ser 2-3, muy pocas 4-5.

Responde EXACTAMENTE en este formato:
TITULO: [título en español]
PRIORIDAD: [número del 1-5]"""

                    response = await self.ollama_service.generate(
                        prompt,
                        system="Eres un analista crítico de noticias tech. SÉ ESTRICTO con las prioridades. La mayoría deben ser 2-3.",
                        timeout=15,
                        use_powerful_model=False  # Usar modelo rápido
                    )
                    
                    # Parsear respuesta
                    titulo_es = item['titulo']  # Default
                    prioridad = 3  # Default
                    
                    for line in response.strip().split('\n'):
                        if line.startswith('TITULO:'):
                            titulo_es = line.replace('TITULO:', '').strip()
                        elif line.startswith('PRIORIDAD:'):
                            try:
                                prioridad = int(line.replace('PRIORIDAD:', '').strip())
                                prioridad = max(1, min(5, prioridad))
                            except:
                                prioridad = 3
                    
                    item['titulo_es'] = titulo_es
                    item['prioridad'] = prioridad
                    
                    logger.info(f"Noticia {i+1}: '{titulo_es}' - Prioridad {prioridad}")
                    
                    await asyncio.sleep(0.2)  # Rate limiting
                    
                except Exception as e:
                    logger.warning(f"Error procesando noticia {i+1}: {e}")
                    item['titulo_es'] = item['titulo']
                    item['prioridad'] = 3
            
            # Asignar defaults a noticias no procesadas
            for item in news_items:
                if 'titulo_es' not in item:
                    item['titulo_es'] = item['titulo']
                if 'prioridad' not in item:
                    item['prioridad'] = 3
            
            # Ordenar por prioridad descendente
            news_items.sort(key=lambda x: x.get('prioridad', 3), reverse=True)
            
            logger.info(f"✅ Traducción completada. Prioridades: {[item['prioridad'] for item in news_items[:5]]}")
            
            return news_items
            
        except Exception as e:
            logger.error(f"Error en traducción/priorización: {e}", exc_info=True)
            # Fallback: usar títulos originales y prioridad 3
            for item in news_items:
                item['titulo_es'] = item['titulo']
                item['prioridad'] = 3
            return news_items
    
    async def update_topic_cache(self, context: ContextTypes.DEFAULT_TYPE, topic: str) -> int:
        """
        Actualiza el caché de noticias para un tema específico.
        Descarga RSS, detecta duplicados por hash, traduce títulos y ordena por importancia.
        
        Returns:
            Número de noticias nuevas añadidas
        """
        try:
            # Inicializar caché si no existe
            if 'news_cache' not in context.bot_data:
                context.bot_data['news_cache'] = {}
            
            category = self._get_feed_category(topic)
            feeds = self.rss_feeds.get(category, self.rss_feeds['default'])
            
            all_news = []
            
            for feed_url in feeds:
                try:
                    # Deshabilitar caché de feedparser
                    feed = await asyncio.to_thread(
                        feedparser.parse, 
                        feed_url,
                        agent='Mozilla/5.0 (compatible; JARVIS-Bot/1.0)',
                        request_headers={'Cache-Control': 'no-cache'}
                    )
                    
                    for entry in feed.entries[:15]:
                        title = entry.get('title', 'Sin título')
                        link = entry.get('link', '')
                        
                        # Generar hash para detectar duplicados
                        news_hash = self._generate_hash(title, link)
                        
                        # Extraer fecha de publicación
                        published_parsed = entry.get('published_parsed')
                        if published_parsed:
                            published_date = datetime(*published_parsed[:6])
                        else:
                            published_date = datetime.now()
                        
                        # Limpiar resumen de HTML
                        raw_summary = entry.get('summary', entry.get('description', title))
                        from bs4 import BeautifulSoup
                        clean_summary = BeautifulSoup(raw_summary, 'html.parser').get_text()[:500]
                        
                        # Calcular antigüedad de la noticia
                        age_hours = (datetime.now() - published_date).total_seconds() / 3600
                        age_days = age_hours / 24
                        
                        # Categorizar por fuente (estrategia híbrida)
                        # - Feeds normales (.rss) → breaking
                        # - Feeds top/week → recent
                        # - Feeds top/month → popular
                        if '/top/.rss?t=month' in feed_url:
                            category = 'popular'
                        elif '/top/.rss?t=week' in feed_url:
                            category = 'recent'
                        elif age_hours <= 48:
                            category = 'breaking'
                        elif age_days <= 14:
                            category = 'recent'
                        else:
                            category = 'popular'
                        
                        news_item = {
                            'titulo': title,
                            'link': link,
                            'resumen': clean_summary,
                            'hash': news_hash,
                            'fecha': published_date.isoformat(),
                            'fecha_obj': published_date,  # Para ordenar
                            'categoria': category,
                            'age_hours': age_hours
                        }
                        all_news.append(news_item)
                    
                    await asyncio.sleep(0.3)  # Rate limiting
                    
                except Exception as e:
                    logger.warning(f"Error fetching feed {feed_url}: {e}")
                    continue
            
            # Ordenar por fecha descendente (más recientes primero)
            all_news.sort(key=lambda x: x['fecha_obj'], reverse=True)
            
            # Traducir títulos y asignar prioridades con LLM
            all_news = await self._translate_and_prioritize_news(all_news)
            
            # Filtrar duplicados por hash
            seen_hashes = set()
            unique_news = []
            
            # Si ya existe caché para este tema, cargar hashes existentes
            if topic in context.bot_data['news_cache']:
                for existing_item in context.bot_data['news_cache'][topic]:
                    seen_hashes.add(existing_item['hash'])
            
            new_count = 0
            for item in all_news:
                if item['hash'] not in seen_hashes:
                    # Remover fecha_obj antes de guardar (no es serializable)
                    item_to_save = {k: v for k, v in item.items() if k != 'fecha_obj'}
                    unique_news.append(item_to_save)
                    seen_hashes.add(item['hash'])
                    new_count += 1
            
            # Combinar con noticias existentes y mantener solo las 10 más recientes
            if topic in context.bot_data['news_cache']:
                existing_news = context.bot_data['news_cache'][topic]
                all_combined = unique_news + existing_news
            else:
                all_combined = unique_news
            
            # Ordenar por fecha y mantener solo las 10 más recientes
            all_combined.sort(key=lambda x: x['fecha'], reverse=True)
            context.bot_data['news_cache'][topic] = all_combined[:10]
            
            logger.info(f"✅ Caché actualizado para '{topic}': {new_count} noticias nuevas, {len(context.bot_data['news_cache'][topic])} en total")
            
            return new_count
            
        except Exception as e:
            logger.error(f"❌ Error actualizando caché para '{topic}': {e}", exc_info=True)
            return 0
    
    def get_cached_news(self, context: ContextTypes.DEFAULT_TYPE, topic: str) -> List[Dict[str, Any]]:
        """Obtiene noticias del caché para un tema"""
        if 'news_cache' not in context.bot_data:
            return []
        
        return context.bot_data['news_cache'].get(topic, [])
    
    def is_cache_stale(self, context: ContextTypes.DEFAULT_TYPE, topic: str, max_age_hours: int = 1) -> bool:
        """Verifica si el caché está desactualizado (>1h)"""
        news = self.get_cached_news(context, topic)
        
        if not news:
            return True
        
        # Verificar fecha de la noticia más reciente
        try:
            latest_date = datetime.fromisoformat(news[0]['fecha'])
            age = datetime.now() - latest_date
            return age > timedelta(hours=max_age_hours)
        except:
            return True
    
    async def subscribe_topic(self, user_id: int, topic: str) -> tuple[bool, str]:
        """Suscribe a un usuario a un tema de noticias"""
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
        
        return True, "success"
    
    def unsubscribe_topic(self, user_id: int, topic: str) -> bool:
        """Desuscribe a un usuario de un tema"""
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
        """Obtiene las suscripciones de un usuario"""
        with self.db_service.get_session() as session:
            subscriptions = session.query(NewsSubscription).filter(
                NewsSubscription.user_id == user_id
            ).all()
            
            return [sub.topic for sub in subscriptions]
    
    async def get_all_subscribed_topics(self) -> List[str]:
        """Obtiene todos los temas a los que hay usuarios suscritos"""
        with self.db_service.get_session() as session:
            subscriptions = session.query(NewsSubscription.topic).distinct().all()
            return [sub.topic for sub in subscriptions]
