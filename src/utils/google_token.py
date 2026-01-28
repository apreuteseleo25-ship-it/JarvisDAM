"""
Utilidad para verificar el estado del token de Google Calendar.
"""
import os


def is_google_token_valid() -> bool:
    """
    Verifica si existe un token válido de Google Calendar.
    
    Returns:
        bool: True si el token existe, False en caso contrario
    """
    token_path = "token.json"
    return os.path.exists(token_path)
