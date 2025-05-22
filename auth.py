import logging
import requests
from functools import wraps
from datetime import datetime, timedelta
from flask import redirect, url_for, session, flash
from flask_login import current_user, login_required
from urllib.parse import urlencode

from app import app
from models import User
from yandex_direct import connection_manager

# Set up logging
logger = logging.getLogger(__name__)

def admin_required(f):
    """Decorator to require admin access for a route"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Admin access required', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def get_yandex_auth_url():
    """Generate the Yandex OAuth URL for user authentication using the connection manager"""
    # Используем глобальный менеджер подключений вместо переменных окружения
    return connection_manager.get_auth_url()

def process_yandex_callback(code):
    """
    Process the OAuth callback from Yandex and get tokens using the connection manager
    
    Args:
        code: The authorization code from the callback
        
    Returns:
        bool: Success status
    """
    try:
        # Получаем токен через менеджер подключений
        token_data = connection_manager.get_token(code)
        
        if not token_data:
            logger.error("Failed to get token from Yandex API")
            return False
        
        # Сохраняем токен для текущего пользователя
        token = connection_manager.store_token_for_user(current_user.id, token_data)
        
        if not token:
            logger.error("Failed to store token in database")
            return False
            
        logger.info(f"Successfully connected Yandex Direct account: {token.client_login}")
        return True
    except Exception as e:
        logger.exception(f"Exception processing Yandex callback: {e}")
        return False
