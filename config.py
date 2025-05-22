import os

class Config:
    """Base configuration class."""
    # Flask
    SECRET_KEY = os.environ.get('SESSION_SECRET', 'dev-secret-key')
    DEBUG = True
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Yandex Direct API
    YANDEX_CLIENT_ID = os.environ.get('YANDEX_CLIENT_ID')
    YANDEX_CLIENT_SECRET = os.environ.get('YANDEX_CLIENT_SECRET')
    YANDEX_REDIRECT_URI = os.environ.get('YANDEX_REDIRECT_URI', 'http://localhost:5000/auth/yandex/callback')
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    # APScheduler
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = "UTC"

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///test.db'
    WTF_CSRF_ENABLED = False

# Set config based on environment
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig
}

# Default to development config
config = config_by_name[os.getenv('FLASK_ENV', 'development')]
