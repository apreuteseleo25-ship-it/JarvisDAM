from dataclasses import dataclass
from typing import List


@dataclass
class CommandInfo:
    command: str
    description: str
    usage: str
    category: str


class CommandRegistry:
    def __init__(self):
        self.commands: List[CommandInfo] = []
    
    def register(self, command: str, description: str, usage: str = "", category: str = "General"):
        self.commands.append(CommandInfo(
            command=command,
            description=description,
            usage=usage or f"/{command}",
            category=category
        ))
    
    def get_help_text(self) -> str:
        categories = {}
        for cmd in self.commands:
            if cmd.category not in categories:
                categories[cmd.category] = []
            categories[cmd.category].append(cmd)
        
        help_text = "� *JARVIS System - Comandos*\n\n"
        
        category_emojis = {
            "General": "ℹ️",
            "LIBRARY": "📚",
            "INTEL": "📰",
            "HQ": "📅"
        }
        
        for category, commands in categories.items():
            emoji = category_emojis.get(category, "📌")
            help_text += f"{emoji} *{category}*\n"
            for cmd in commands:
                help_text += f"  {cmd.usage} - {cmd.description}\n"
            help_text += "\n"
        
        return help_text


command_registry = CommandRegistry()

command_registry.register("start", "Inicia el bot y registra tu cuenta", category="General")
command_registry.register("help", "Muestra esta ayuda", category="General")

command_registry.register("ingest", "Sube un PDF para indexar", category="LIBRARY")
command_registry.register("stash", "Guarda un snippet de código", "/stash <lenguaje>", category="LIBRARY")
command_registry.register("ask", "Pregunta sobre tus documentos", "/ask <pregunta>", category="LIBRARY")
command_registry.register("snippet", "Busca snippets de código", "/snippet <búsqueda>", category="LIBRARY")
command_registry.register("quiz", "Genera un quiz de tus documentos", category="LIBRARY")
command_registry.register("stats", "Estadísticas de tu biblioteca", category="LIBRARY")

command_registry.register("snipe", "Descarga noticias de tus temas", category="INTEL")
command_registry.register("subscribe", "Suscríbete a un tema", "/subscribe <tema>", category="INTEL")
command_registry.register("unsubscribe", "Cancela suscripción", "/unsubscribe <tema>", category="INTEL")
command_registry.register("topics", "Lista tus suscripciones", category="INTEL")

command_registry.register("add", "Crea evento en Google Calendar", "/add <evento>", category="CALENDAR")
command_registry.register("list", "Lista eventos de Google Calendar", category="CALENDAR")
command_registry.register("done", "Marca evento como completado", "/done <id>", category="CALENDAR")
command_registry.register("delete", "Elimina evento de Google Calendar", "/delete <id>", category="CALENDAR")
command_registry.register("code", "Ingresa código de autorización", "/code <codigo>", category="CALENDAR")
