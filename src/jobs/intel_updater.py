"""
Background job para actualizar el caché de noticias cada 30 minutos.
Sistema robusto con actualización inmediata al iniciar.
"""
from telegram.ext import ContextTypes
from src.utils.logger import get_logger

logger = get_logger("intel_updater")


async def update_intel_cache(context: ContextTypes.DEFAULT_TYPE):
    """
    Job que actualiza el caché de noticias para todos los temas suscritos.
    Mantiene las 10 noticias más recientes por tema, ordenadas por fecha.
    """
    try:
        intel_manager = context.bot_data.get('intel_manager')
        
        if not intel_manager:
            logger.error("❌ IntelManager no encontrado en bot_data")
            return
        
        logger.info("🔄 Iniciando actualización automática de caché de noticias...")
        
        # Obtener todos los temas suscritos
        topics = await intel_manager.get_all_subscribed_topics()
        
        if not topics:
            logger.info("ℹ️ No hay temas suscritos, saltando actualización")
            return
        
        # Actualizar caché para cada tema
        total_new = 0
        for topic in topics:
            new_count = await intel_manager.update_topic_cache(context, topic)
            total_new += new_count
            logger.info(f"  • {topic}: {new_count} noticias nuevas")
        
        logger.info(f"✅ Actualización completada: {total_new} noticias nuevas en {len(topics)} temas")
        
    except Exception as e:
        logger.error(f"❌ Error en background job de intel: {e}", exc_info=True)


def setup_intel_updater(application):
    """
    Configura el job de actualización de caché.
    Se ejecuta INMEDIATAMENTE al iniciar y luego cada 30 minutos.
    """
    job_queue = application.job_queue
    
    # Ejecutar inmediatamente al iniciar (first=0) y luego cada 30 minutos
    job_queue.run_repeating(
        update_intel_cache,
        interval=1800,  # 30 minutos en segundos
        first=0,  # Ejecutar INMEDIATAMENTE al iniciar
        name="intel_cache_updater"
    )
    
    logger.info("✅ Background job 'intel_cache_updater' configurado (inmediato + cada 30 min)")
