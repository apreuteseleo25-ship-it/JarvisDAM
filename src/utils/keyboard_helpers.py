"""
Keyboard helpers for consistent navigation across the bot
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_back_to_dashboard_keyboard() -> InlineKeyboardMarkup:
    """
    Genera un teclado con un único botón para volver al menú principal.
    Usar en todos los mensajes finales para evitar "dead ends" en la navegación.
    
    Returns:
        InlineKeyboardMarkup con botón "🏠 Volver al Panel"
    """
    keyboard = [[InlineKeyboardButton("🏠 Volver al Panel", callback_data="main_menu")]]
    return InlineKeyboardMarkup(keyboard)


def get_back_button_only() -> InlineKeyboardMarkup:
    """
    Alias de get_back_to_dashboard_keyboard() para compatibilidad.
    """
    return get_back_to_dashboard_keyboard()
