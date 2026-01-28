from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot
from src.modules.hq import HQModule
from src.modules.intel import IntelModule
from src.models.database import DatabaseService
from src.utils.rate_limiter import TelegramRateLimiter
from src.utils.logger import get_logger
from datetime import datetime
import random
import asyncio
from typing import Dict, Any

logger = get_logger("scheduler_service")


class SchedulerService:
    def __init__(
        self,
        bot: Bot,
        hq_module: HQModule,
        intel_module: IntelModule,
        db_service: DatabaseService,
        config: Dict[str, Any]
    ):
        self.bot = bot
        self.hq_module = hq_module
        self.intel_module = intel_module
        self.db_service = db_service
        self.config = config
        self.scheduler = AsyncIOScheduler()
        self.telegram_rate_limiter = TelegramRateLimiter(max_messages_per_minute=20)
    
    def start(self):
        task_check_interval = self.config.get("scheduler", {}).get("task_check_interval", 15)
        
        self.scheduler.add_job(
            self._check_upcoming_tasks,
            trigger=IntervalTrigger(minutes=task_check_interval),
            id="check_upcoming_tasks",
            name="Check Upcoming Tasks",
            replace_existing=True
        )
        
        highlight_hour_min = self.config.get("scheduler", {}).get("news_highlight_hour_min", 9)
        highlight_hour_max = self.config.get("scheduler", {}).get("news_highlight_hour_max", 18)
        random_hour = random.randint(highlight_hour_min, highlight_hour_max)
        random_minute = random.randint(0, 59)
        
        self.scheduler.add_job(
            self._send_daily_highlights,
            trigger=CronTrigger(hour=random_hour, minute=random_minute),
            id="daily_news_highlight",
            name="Daily News Highlight",
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info(f"✅ Scheduler started")
        logger.info(f"   - Task check: Every {task_check_interval} minutes")
        logger.info(f"   - Daily highlight: {random_hour:02d}:{random_minute:02d}")
    
    async def _check_upcoming_tasks(self):
        logger.info(f"Checking upcoming tasks...")
        
        with self.db_service.get_session() as session:
            from src.models.database import User
            users = session.query(User).all()
            
            for user in users:
                try:
                    upcoming_tasks = self.hq_module.get_upcoming_tasks(user.id, hours_ahead=24)
                    
                    for task in upcoming_tasks:
                        await self._notify_task(user.telegram_id, task)
                        self.hq_module.mark_task_notified(task.id)
                        await asyncio.sleep(0.5)
                
                except Exception as e:
                    logger.error(f"Error checking tasks for user {user.id}: {e}", exc_info=True)
                
                await asyncio.sleep(0.2)
    
    async def _notify_task(self, telegram_id: int, task):
        await self.telegram_rate_limiter.wait_if_needed(telegram_id)
        
        time_left = task.deadline - datetime.utcnow()
        hours_left = int(time_left.total_seconds() / 3600)
        
        message = (
            f"⏰ *Recordatorio de Tarea*\n\n"
            f"📋 {task.title}\n"
        )
        
        if task.description:
            message += f"📝 {task.description}\n"
        
        message += f"\n⏳ Vence en {hours_left} horas"
        
        if task.deadline:
            message += f"\n📅 {task.deadline.strftime('%Y-%m-%d %H:%M')}"
        
        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error sending task notification to {telegram_id}: {e}", exc_info=True)
    
    async def _send_daily_highlights(self):
        logger.info(f"Sending daily news highlights...")
        
        with self.db_service.get_session() as session:
            from src.models.database import User
            users = session.query(User).all()
            
            for user in users:
                try:
                    highlight = self.intel_module.get_daily_highlight(user.id)
                    
                    if highlight:
                        await self._send_highlight(user.telegram_id, highlight)
                        self.intel_module.mark_as_read(user.id, highlight.id)
                
                except Exception as e:
                    logger.error(f"Error sending highlight to user {user.id}: {e}", exc_info=True)
                
                await asyncio.sleep(0.5)
    
    async def _send_highlight(self, telegram_id: int, news_item):
        await self.telegram_rate_limiter.wait_if_needed(telegram_id)
        
        priority_emoji = "🔥" * news_item.priority
        
        message = (
            f"📰 *Daily News Highlight*\n\n"
            f"{priority_emoji} *{news_item.title}*\n\n"
            f"🏷️ Tema: {news_item.topic}\n"
            f"🔗 {news_item.url}\n\n"
            f"_Prioridad: {news_item.priority}/5_"
        )
        
        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode="Markdown",
                disable_web_page_preview=False
            )
        except Exception as e:
            logger.error(f"Error sending highlight to {telegram_id}: {e}", exc_info=True)
    
    def stop(self):
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")
