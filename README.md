# 🤖 J.A.R.V.I.S. - Just A Rather Very Intelligent System

**Asistente Personal Inteligente con IA Local**

Sistema de productividad basado en Telegram que integra gestión de conocimiento (RAG), noticias tecnológicas, calendario y utilidades mediante inteligencia artificial ejecutada localmente con Ollama.

---

## 📋 Información Académica

**Proyecto:** Sistema de Asistente Personal con IA  
**Asignatura:** Desarrollo de Aplicaciones con Inteligencia Artificial  
**Tecnologías:** Python, Telegram Bot API, Ollama (LLM Local), ChromaDB, Google Calendar API  
**Año:** 2026

---

## ✨ Características Principales

### 🎯 Módulos Funcionales

- **📚 LIBRARY (Knowledge Vault)**: Sistema RAG para consultas sobre documentos PDF y videos de YouTube
- **📰 INTEL (News Intelligence)**: Agregador de noticias tecnológicas con traducción y priorización automática
- **📅 HQ (Headquarters)**: Gestión de tareas con integración a Google Calendar y extracción de fechas NLP
- **⚡ UTILITIES**: Generador de cheatsheets, quizzes interactivos y menú de navegación

### 🔑 Características Técnicas

- ✅ **Arquitectura Asíncrona**: Manejo concurrente de múltiples usuarios sin bloqueo
- ✅ **Sistema Híbrido de Modelos**: Modelo rápido (qwen2.5:7b) y potente (gpt-oss:20b)
- ✅ **RAG Completo**: Búsqueda semántica con ChromaDB y chunking inteligente
- ✅ **Caché Inteligente**: Actualización automática de noticias cada 30 minutos
- ✅ **Error Handling Robusto**: Retry con backoff exponencial, timeouts configurables
- ✅ **Privacidad**: Ejecución completamente local (excepto Telegram API)

---

## 🚀 Tech Stack

| Componente | Tecnología | Propósito |
|------------|------------|-----------|
| **Bot Framework** | python-telegram-bot 20.7 | Interfaz de usuario asíncrona |
| **LLM Local** | Ollama (qwen2.5:7b, gpt-oss:20b) | Procesamiento de lenguaje natural |
| **Vector DB** | ChromaDB 0.4.18 | Búsqueda semántica (RAG) |
| **Database** | SQLAlchemy + SQLite | Persistencia de usuarios/tareas |
| **Calendar** | Google Calendar API | Sincronización de eventos |
| **RSS Parser** | feedparser 6.0.10 | Agregación de noticias |
| **PDF Processing** | PyPDF2 3.0.1 | Extracción de texto |

---

## 📦 Instalación

### 1. Requisitos Previos

- **Python 3.11+**
- **Ollama** instalado y ejecutándose ([ollama.ai](https://ollama.ai))
- **Token de Telegram Bot** (obtener de [@BotFather](https://t.me/BotFather))
- **Credenciales de Google Calendar** (opcional, para módulo HQ)

### 2. Clonar Repositorio

```bash
git clone https://github.com/tu-usuario/JarvisDAM.git
cd JarvisDAM
```

### 3. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar Ollama

```bash
# Descargar modelos necesarios
ollama pull qwen2.5:7b
ollama pull gpt-oss:20b

# Iniciar servidor Ollama
ollama serve
```

### 5. Configuración

Copia el archivo de ejemplo y edita con tus credenciales:

```bash
cp config.example.yaml config.yaml
```

Edita `config.yaml`:

```yaml
telegram:
  bot_token: "TU_TOKEN_DE_TELEGRAM"

database:
  path: "brain.db"

chromadb:
  persist_directory: "./chroma_db"
  collection_name: "jarvis_knowledge"

ollama:
  base_url: "http://localhost:11434"
  model: "qwen2.5:7b"
```

### 6. Ejecutar

```bash
python main.py
```

---

## 📚 Comandos Disponibles

### LIBRARY (Knowledge Vault)
- `/ingest [url]` - Ingesta PDF o video de YouTube
- `/ask <pregunta>` - Consulta sobre documentos indexados
- `/quiz` - Genera examen basado en documentos
- `/stats` - Estadísticas de la biblioteca

### INTEL (News Intelligence)
- `/snipe [tema]` - Noticias categorizadas (Última Hora, Esta Semana, Populares)
- `/subscribe <tema>` - Suscribirse a tema (technology, ai, programming, cybersecurity)
- `/unsubscribe <tema>` - Cancelar suscripción
- `/topics` - Listar temas suscritos

### HQ (Tasks & Calendar)
- `/login` - Iniciar autenticación con Google Calendar
- `/code <código>` - Completar OAuth con código de Google
- `/logout` - Cerrar sesión de Google
- `/add <tarea>` - Crear evento (extrae fecha automáticamente)
- `/list` - Listar próximos eventos
- `/done <id>` - Marcar tarea como completada
- `/delete <id>` - Eliminar tarea

### UTILITIES
- `/start` - Menú principal interactivo
- `/help` - Manual de usuario completo
- `/cheat <tema>` - Generar cheatsheet técnica

---

## 🏗️ Arquitectura del Sistema

### Flujo de Datos

```
Usuario (Telegram) 
    ↓
Telegram API
    ↓
Middleware Python (main.py)
    ↓
AuthService → Verificación de usuario
    ↓
Router (CommandHandler) → Enruta a módulo correspondiente
    ↓
┌─────────────┬──────────────┬─────────────┬──────────────┐
│   Library   │    Intel     │     HQ      │  Utilities   │
│   Module    │   Manager    │   Module    │   Handler    │
└──────┬──────┴──────┬───────┴──────┬──────┴──────┬───────┘
       │             │              │             │
       ↓             ↓              ↓             ↓
   ChromaDB      RSS Feeds    Google Cal     Ollama API
   (Vectors)     (Cache)      (OAuth)        (LLM Local)
       │             │              │             │
       └─────────────┴──────────────┴─────────────┘
                          ↓
                   Respuesta al Usuario
```

### Componentes Clave

**1. Middleware (main.py, ollama_service.py)**
- Orquestador principal que conecta Telegram con Ollama
- Manejo de errores: retry con backoff exponencial, timeouts diferenciados
- Sistema de fallback a modelos alternativos

**2. Sistema RAG (library.py, chroma_service.py)**
- Chunking inteligente: 1000 caracteres con overlap de 200
- Búsqueda semántica: Top-3 chunks más relevantes
- Metadata enriquecida para trazabilidad

**3. Sistema de Noticias (intel_manager.py)**
- Caché persistente en `bot_data`
- Background job: actualización cada 30 minutos
- Procesamiento LLM: traducción y priorización automática
- Categorización híbrida por fuente y tiempo

**4. Integración Calendar (calendar_module.py)**
- OAuth 2.0 completo con Google
- Extracción de fechas en lenguaje natural mediante LLM
- Sincronización bidireccional

---

## 🔧 Decisiones de Diseño

### ¿Por qué python-telegram-bot?
- **Asincronía nativa**: Maneja múltiples usuarios sin bloqueo (crítico con latencias de 5-60s en LLM)
- **Handlers modulares**: Separación clara de responsabilidades
- **Inline keyboards**: UX superior para navegación de noticias

### ¿Por qué sistema híbrido de modelos?
- **qwen2.5:7b (rápido)**: 3-8s para traducción, extracción de fechas, respuestas cortas
- **gpt-oss:20b (potente)**: 15-40s para análisis profundo, priorización crítica
- **Optimización GPU**: Modelo 7B usa ~6GB VRAM, 20B usa ~16GB. Usar 20B solo cuando sea necesario

### ¿Por qué ChromaDB para RAG?
- **Búsqueda semántica**: Encuentra contenido por significado, no solo palabras exactas
- **Persistencia local**: Privacidad total, sin servicios cloud
- **Chunking con overlap**: Preserva contexto entre fragmentos

---

## 🎯 Retos Técnicos Resueltos

### 1. Latencia en Cold Start de Ollama
**Problema**: Primera inferencia tarda 15-30s (carga de modelo en VRAM)  
**Solución**:
- Keep-alive en requests (mantiene modelo 10 min)
- Mensajes de estado progresivos
- Retry con backoff exponencial
- Timeouts diferenciados (60s rápido, 240s potente)

### 2. Contexto Limitado en Videos Largos
**Problema**: Videos de 2h generan 50K tokens, Ollama soporta 8K  
**Solución**:
- RAG con chunking inteligente (1000 chars, overlap 200)
- Búsqueda semántica Top-3 (~3K tokens relevantes)
- Metadata con timestamps para trazabilidad

### 3. Persistencia de Noticias
**Problema**: Descargar RSS en cada comando (5-15s de latencia)  
**Solución**:
- Caché persistente en `bot_data` (lectura <100ms)
- Background job cada 30 min
- Deduplicación por hash MD5
- Procesamiento LLM en background (traducción + priorización)

---

## 📊 Estructura del Proyecto

```
JarvisDAM/
├── main.py                          # Punto de entrada
├── config.yaml                      # Configuración (gitignored)
├── config.example.yaml              # Ejemplo de configuración
├── requirements.txt                 # Dependencias
├── README.md                        # Este archivo
├── DOCUMENTACION_TECNICA_JARVIS.md  # Documentación técnica completa
├── DOCUMENTACION_TECNICA_JARVIS.docx # Memoria para entrega académica
├── .gitignore
├── setup.sh / setup.bat             # Scripts de instalación
├── src/
│   ├── bot/
│   │   ├── handlers.py              # Comandos principales
│   │   ├── news_handler.py          # Sistema de noticias
│   │   ├── calendar_handlers.py     # Google Calendar
│   │   ├── menu_handler.py          # Menú interactivo
│   │   ├── quiz_handler.py          # Generador de quizzes
│   │   └── generator_handler.py     # Cheatsheets
│   ├── services/
│   │   ├── ollama_service.py        # API Ollama (middleware)
│   │   ├── chroma_service.py        # ChromaDB
│   │   ├── auth_service.py          # Autenticación
│   │   ├── google_auth_service.py   # OAuth Google
│   │   └── cache_service.py         # Sistema de caché
│   ├── modules/
│   │   ├── library.py               # RAG
│   │   ├── intel_manager.py         # Noticias
│   │   ├── calendar_module.py       # Calendar
│   │   └── hq.py                    # Tareas
│   ├── models/
│   │   └── database.py              # SQLAlchemy models
│   ├── jobs/
│   │   └── intel_updater.py         # Background jobs
│   └── utils/
│       ├── logger.py                # Logging
│       └── retry.py                 # Retry logic
├── chroma_db/                       # Vector database (auto-generada)
├── data/
│   └── jarvis.db                    # SQLite database (auto-generada)
└── logs/                            # Logs (gitignored)
```

---

## 🔒 Seguridad

- ✅ **Sin tokens hardcodeados**: Configuración en `config.yaml` (protegido por `.gitignore`)
- ✅ **Autenticación obligatoria**: Todos los comandos verifican usuario
- ✅ **Logging completo**: Trazabilidad de operaciones (INFO, WARNING, ERROR)
- ✅ **Ejecución local**: Datos permanecen en tu máquina (excepto Telegram API)

---

## 🐛 Troubleshooting

### Error: "Ollama connection failed"
```bash
# Asegúrate de que Ollama esté ejecutándose
ollama serve
```

### Error: "Model not found"
```bash
# Descarga los modelos necesarios
ollama pull qwen2.5:7b
ollama pull gpt-oss:20b
```

### Error: "Bot token invalid"
```bash
# Verifica tu token en config.yaml
# Obtén uno nuevo de @BotFather si es necesario
```

### ChromaDB no persiste datos
```bash
# Verifica permisos de escritura
chmod -R 755 ./chroma_db
```

---

## 📄 Documentación Adicional

- **[DOCUMENTACION_TECNICA_JARVIS.md](DOCUMENTACION_TECNICA_JARVIS.md)**: Documentación técnica completa con diagramas Mermaid
- **DOCUMENTACION_TECNICA_JARVIS.docx**: Memoria técnica en formato Word para entrega académica

---

## 📈 Cumplimiento de Requisitos Académicos

| Requisito | Cumplimiento | Evidencia |
|-----------|--------------|-----------|
| Middleware Python | ✅ 100% | `main.py` + `ollama_service.py` |
| Manejo de Errores | ✅ 100% | Retry, timeouts, fallbacks |
| Variables de Entorno | ✅ 100% | `config.yaml` protegido |
| Mensaje de Bienvenida | ✅ 100% | `/start` con menú interactivo |
| Manual de Usuario | ✅ 100% | `/help` con 18 comandos |
| 5+ Comandos | ✅ 360% | **18 comandos** implementados |
| System Prompt | ✅ 100% | `JARVIS_CORE_PROMPT` personalizado |
| Hardening | ✅ 100% | Sin tokens hardcodeados, logs |
| Documentación | ✅ 100% | README + memoria técnica |

---

## 🎓 Créditos Académicos

**Desarrollado por:** Leonardo  
**Asignatura:** Desarrollo de Aplicaciones con Inteligencia Artificial  
**Año:** 2026

---

## 📝 Licencia

MIT License - Proyecto académico de código abierto.

---

**Desarrollado con ❤️ usando Python, Telegram y Ollama**
