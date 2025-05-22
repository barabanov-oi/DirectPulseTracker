import os
import logging
import requests
from functools import wraps
from datetime import datetime, timedelta
from flask import redirect, url_for, session, flash
from flask_login import current_user, login_required
from urllib.parse import urlencode

from app import app
from models import User
from yandex_direct import YandexDirectAPI, store_token_for_user

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
    """Generate the Yandex OAuth URL for user authentication"""
    client_id = os.environ.get('YANDEX_CLIENT_ID')
    redirect_uri = os.environ.get('YANDEX_REDIRECT_URI', 'http://localhost:5000/auth/yandex/callback')
    
    if not client_id:
        logger.error("YANDEX_CLIENT_ID environment variable is not set")
        return None
    
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'force_confirm': 'yes',
        'scope': 'direct'
    }
    
    return f"https://oauth.yandex.ru/authorize?{urlencode(params)}"

def process_yandex_callback(code):
    """
    Process the OAuth callback from Yandex and get tokens
    
    Args:
        code: The authorization code from the callback
        
    Returns:
        bool: Success status
    """
    client_id = os.environ.get('YANDEX_CLIENT_ID')
    client_secret = os.environ.get('YANDEX_CLIENT_SECRET')
    redirect_uri = os.environ.get('YANDEX_REDIRECT_URI', 'http://localhost:5000/auth/yandex/callback')
    
    if not client_id or not client_secret:
        logger.error("YANDEX_CLIENT_ID or YANDEX_CLIENT_SECRET environment variables are not set")
        return False
    
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri
    }
    
    try:
        response = requests.post('https://oauth.yandex.ru/token', data=data)
        
        if response.status_code != 200:
            logger.error(f"Error getting Yandex token: {response.text}")
            return False
        
        token_data = response.json()
        
        # Store the token for the current user
        store_token_for_user(current_user.id, token_data)
        
        return True
    except Exception as e:
        logger.exception(f"Exception processing Yandex callback: {e}")
        return False
