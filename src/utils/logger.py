import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path
from rich.console import Console
from rich.theme import Theme

# Rich Console Setup
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "start": "bold magenta",
    "debug": "dim cyan"
})

console = Console(theme=custom_theme)


def setup_logger(name: str = "second_brain", log_file: str = "bot.log", level: int = logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if logger.handlers:
        return logger
    
    log_format = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)
    
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    file_handler = RotatingFileHandler(
        log_dir / log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str):
    return logging.getLogger(f"second_brain.{name}")
