from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import Integer, String, DateTime, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
import json
from src.utils.logger import get_logger

logger = get_logger("cache_service")


class CacheBase(DeclarativeBase):
    pass


class NewsCache(CacheBase):
    __tablename__ = "news_cache"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    
    def __repr__(self):
        return f"<NewsCache(topic={self.topic}, expires_at={self.expires_at})>"


class CacheService:
    def __init__(self, db_path: str = "brain.db", cache_ttl_hours: int = 4):
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        CacheBase.metadata.create_all(self.engine)
        self.cache_ttl_hours = cache_ttl_hours
    
    def get_session(self) -> Session:
        return Session(self.engine)
    
    def get_cached_news(self, topic: str) -> Optional[List[Dict[str, Any]]]:
        with self.get_session() as session:
            now = datetime.utcnow()
            
            cache_entry = session.query(NewsCache).filter(
                NewsCache.topic == topic,
                NewsCache.expires_at > now
            ).order_by(NewsCache.created_at.desc()).first()
            
            if cache_entry:
                try:
                    data = json.loads(cache_entry.data)
                    age_minutes = int((now - cache_entry.created_at).total_seconds() / 60)
                    logger.info(f"✅ Cache HIT for '{topic}' (age: {age_minutes} min)")
                    return data
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Cache corrupted for '{topic}', will fetch fresh data")
                    return None
            
            logger.info(f"❌ Cache MISS for '{topic}', fetching fresh data")
            return None
    
    def set_cached_news(self, topic: str, news_data: List[Dict[str, Any]]) -> bool:
        try:
            with self.get_session() as session:
                now = datetime.utcnow()
                expires_at = now + timedelta(hours=self.cache_ttl_hours)
                
                cache_entry = NewsCache(
                    topic=topic,
                    data=json.dumps(news_data),
                    created_at=now,
                    expires_at=expires_at
                )
                
                session.add(cache_entry)
                session.commit()
                
                logger.info(f"💾 Cached {len(news_data)} news items for '{topic}' (TTL: {self.cache_ttl_hours}h)")
                return True
        except Exception as e:
            logger.error(f"❌ Error caching news for '{topic}': {e}", exc_info=True)
            return False
    
    def invalidate_cache(self, topic: Optional[str] = None) -> int:
        with self.get_session() as session:
            if topic:
                deleted = session.query(NewsCache).filter(NewsCache.topic == topic).delete()
            else:
                deleted = session.query(NewsCache).delete()
            
            session.commit()
            logger.info(f"🗑️ Invalidated {deleted} cache entries")
            return deleted
    
    def cleanup_expired(self) -> int:
        with self.get_session() as session:
            now = datetime.utcnow()
            deleted = session.query(NewsCache).filter(NewsCache.expires_at <= now).delete()
            session.commit()
            
            if deleted > 0:
                logger.info(f"🧹 Cleaned up {deleted} expired cache entries")
            
            return deleted
    
    def get_cache_stats(self) -> Dict[str, Any]:
        with self.get_session() as session:
            now = datetime.utcnow()
            
            total = session.query(NewsCache).count()
            valid = session.query(NewsCache).filter(NewsCache.expires_at > now).count()
            expired = total - valid
            
            return {
                "total": total,
                "valid": valid,
                "expired": expired
            }
