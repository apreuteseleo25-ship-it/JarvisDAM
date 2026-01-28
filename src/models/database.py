from sqlalchemy import create_engine, BigInteger, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session
from datetime import datetime
from typing import List, Optional


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    news_subscriptions: Mapped[List["NewsSubscription"]] = relationship("NewsSubscription", back_populates="user", cascade="all, delete-orphan")
    news_items: Mapped[List["NewsItem"]] = relationship("NewsItem", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"


class Task(Base):
    __tablename__ = "tasks"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notify_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    user: Mapped["User"] = relationship("User", back_populates="tasks")
    
    def __repr__(self):
        return f"<Task(id={self.id}, user_id={self.user_id}, title={self.title[:30]})>"


class NewsSubscription(Base):
    __tablename__ = "news_subscriptions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    user: Mapped["User"] = relationship("User", back_populates="news_subscriptions")
    
    def __repr__(self):
        return f"<NewsSubscription(id={self.id}, user_id={self.user_id}, topic={self.topic})>"


class NewsItem(Base):
    __tablename__ = "news_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    user: Mapped["User"] = relationship("User", back_populates="news_items")
    
    def __repr__(self):
        return f"<NewsItem(id={self.id}, user_id={self.user_id}, priority={self.priority}, title={self.title[:30]})>"


class UserToken(Base):
    __tablename__ = "user_tokens"
    
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_uri: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    client_secret: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    expiry: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<UserToken(user_id={self.user_id})>"


class DatabaseService:
    def __init__(self, db_path: str = "brain.db"):
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)
    
    def get_session(self) -> Session:
        return Session(self.engine)
    
    def get_or_create_user(self, telegram_id: int, username: Optional[str] = None) -> User:
        with self.get_session() as session:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            
            if not user:
                user = User(telegram_id=telegram_id, username=username)
                session.add(user)
                session.commit()
                session.refresh(user)
            elif username and user.username != username:
                user.username = username
                session.commit()
                session.refresh(user)
            
            return user
    
    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        with self.get_session() as session:
            return session.query(User).filter(User.telegram_id == telegram_id).first()
