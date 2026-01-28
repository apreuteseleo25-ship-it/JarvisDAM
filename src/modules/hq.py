from telegram import Update
from telegram.ext import ContextTypes
from src.models.database import DatabaseService, Task
from src.services.ollama_service import OllamaService
from src.utils.logger import get_logger
from sqlalchemy import and_
from datetime import datetime, timedelta
from dateutil import parser
from typing import List, Optional, Dict, Any

logger = get_logger("hq_module")


class HQModule:
    def __init__(
        self,
        db_service: DatabaseService,
        ollama_service: OllamaService
    ):
        self.db_service = db_service
        self.ollama_service = ollama_service
    
    async def add_task(
        self,
        user_id: int,
        title: str,
        description: Optional[str] = None,
        deadline_text: Optional[str] = None,
        notify_enabled: bool = False
    ) -> Task:
        deadline = None
        
        if deadline_text:
            deadline = await self._parse_deadline(deadline_text)
        
        with self.db_service.get_session() as session:
            task = Task(
                user_id=user_id,
                title=title,
                description=description,
                deadline=deadline,
                notify_enabled=notify_enabled
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            
            return Task(
                id=task.id,
                user_id=task.user_id,
                title=task.title,
                description=task.description,
                deadline=task.deadline,
                notify_enabled=task.notify_enabled,
                notified=task.notified,
                completed=task.completed,
                created_at=task.created_at
            )
    
    async def _parse_deadline(self, deadline_text: str) -> Optional[datetime]:
        try:
            date_str = await self.ollama_service.extract_date_from_text(deadline_text)
            
            if date_str and date_str.upper() != "NONE":
                return parser.parse(date_str)
        except Exception as e:
            print(f"Error parsing deadline with Ollama: {e}")
        
        try:
            return parser.parse(deadline_text, fuzzy=True)
        except:
            pass
        
        return None
    
    def list_tasks(self, user_id: int, include_completed: bool = False) -> List[Task]:
        with self.db_service.get_session() as session:
            query = session.query(Task).filter(Task.user_id == user_id)
            
            if not include_completed:
                query = query.filter(Task.completed == False)
            
            tasks = query.order_by(Task.deadline.asc().nullslast()).all()
            
            return [
                Task(
                    id=task.id,
                    user_id=task.user_id,
                    title=task.title,
                    description=task.description,
                    deadline=task.deadline,
                    notify_enabled=task.notify_enabled,
                    notified=task.notified,
                    completed=task.completed,
                    created_at=task.created_at
                ) for task in tasks
            ]
    
    def mark_task_completed(self, user_id: int, task_id: int) -> bool:
        with self.db_service.get_session() as session:
            task = session.query(Task).filter(
                and_(
                    Task.id == task_id,
                    Task.user_id == user_id
                )
            ).first()
            
            if task:
                task.completed = True
                session.commit()
                return True
            
            return False
    
    def delete_task(self, user_id: int, task_id: int) -> bool:
        with self.db_service.get_session() as session:
            task = session.query(Task).filter(
                and_(
                    Task.id == task_id,
                    Task.user_id == user_id
                )
            ).first()
            
            if task:
                session.delete(task)
                session.commit()
                return True
            
            return False
    
    def get_upcoming_tasks(self, user_id: int, hours_ahead: int = 24) -> List[Task]:
        with self.db_service.get_session() as session:
            now = datetime.utcnow()
            threshold = now + timedelta(hours=hours_ahead)
            
            tasks = session.query(Task).filter(
                and_(
                    Task.user_id == user_id,
                    Task.completed == False,
                    Task.notify_enabled == True,
                    Task.notified == False,
                    Task.deadline != None,
                    Task.deadline <= threshold,
                    Task.deadline >= now
                )
            ).all()
            
            return [
                Task(
                    id=task.id,
                    user_id=task.user_id,
                    title=task.title,
                    description=task.description,
                    deadline=task.deadline,
                    notify_enabled=task.notify_enabled,
                    notified=task.notified,
                    completed=task.completed,
                    created_at=task.created_at
                ) for task in tasks
            ]
    
    def mark_task_notified(self, task_id: int) -> bool:
        with self.db_service.get_session() as session:
            task = session.query(Task).filter(Task.id == task_id).first()
            
            if task:
                task.notified = True
                session.commit()
                return True
            
            return False
    
    def get_task_stats(self, user_id: int) -> Dict[str, int]:
        with self.db_service.get_session() as session:
            total = session.query(Task).filter(Task.user_id == user_id).count()
            completed = session.query(Task).filter(
                and_(Task.user_id == user_id, Task.completed == True)
            ).count()
            pending = total - completed
            
            return {
                "total": total,
                "completed": completed,
                "pending": pending
            }
