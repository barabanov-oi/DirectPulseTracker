from app import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# User model for authentication
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    telegram_chat_id = db.Column(db.String(64), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    timezone = db.Column(db.String(32), default='UTC')
    
    # Relationships
    yandex_tokens = db.relationship('YandexToken', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    report_templates = db.relationship('ReportTemplate', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    schedules = db.relationship('Schedule', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    conditions = db.relationship('Condition', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

# Yandex Direct OAuth token model
class YandexToken(db.Model):
    __tablename__ = 'yandex_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    account_name = db.Column(db.String(120), nullable=True)  # Название аккаунта для удобства пользователя
    access_token = db.Column(db.String(1024), nullable=False)
    refresh_token = db.Column(db.String(1024), nullable=False)
    token_type = db.Column(db.String(64), default='Bearer')
    expires_at = db.Column(db.DateTime, nullable=False)
    client_login = db.Column(db.String(120), nullable=True)
    is_active = db.Column(db.Boolean, default=True)  # Активен ли аккаунт
    is_default = db.Column(db.Boolean, default=False)  # Аккаунт по умолчанию
    last_used = db.Column(db.DateTime, nullable=True)  # Когда последний раз использовался
    last_status = db.Column(db.String(256), nullable=True)  # Результат последней проверки
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связь с кампаниями
    campaigns = db.relationship('YandexCampaign', backref='token', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        display_name = self.account_name or self.client_login or f"ID: {self.id}"
        return f'<YandexToken {display_name}>'
    
    def is_expired(self):
        return datetime.utcnow() > self.expires_at
        
    def get_status(self):
        """Возвращает текущий статус подключения к аккаунту"""
        if not self.is_active:
            return "Неактивен"
        if self.is_expired():
            return "Токен устарел"
        return "Активен"

# Report template model
class ReportTemplate(db.Model):
    __tablename__ = 'report_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    metrics = db.Column(db.Text, nullable=False)  # JSON string of metrics to include
    date_range = db.Column(db.String(32), default='LAST_7_DAYS')  # TODAY, YESTERDAY, LAST_7_DAYS, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ReportTemplate {self.name}>'

# Schedule model for timed reports
class Schedule(db.Model):
    __tablename__ = 'schedules'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('report_templates.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    cron_expression = db.Column(db.String(120), nullable=False)  # Cron-style schedule expression
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    template = db.relationship('ReportTemplate')
    
    def __repr__(self):
        return f'<Schedule {self.name}>'

# Condition model for conditional reports
class Condition(db.Model):
    __tablename__ = 'conditions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('report_templates.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    condition_json = db.Column(db.Text, nullable=False)  # JSON string of conditions
    check_interval = db.Column(db.Integer, default=3600)  # Seconds between checks
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    template = db.relationship('ReportTemplate')
    
    def __repr__(self):
        return f'<Condition {self.name}>'

# Модель для хранения информации о рекламных кампаниях Яндекс Директа
class YandexCampaign(db.Model):
    __tablename__ = 'yandex_campaigns'
    
    id = db.Column(db.Integer, primary_key=True)
    token_id = db.Column(db.Integer, db.ForeignKey('yandex_tokens.id'), nullable=False)
    campaign_id = db.Column(db.String(64), nullable=False)  # ID кампании в Яндекс Директе
    name = db.Column(db.String(256), nullable=False)  # Название кампании
    status = db.Column(db.String(64), nullable=False)  # Статус кампании (ON, OFF, SUSPENDED и т.д.)
    state = db.Column(db.String(64), nullable=True)  # Состояние кампании (ARCHIVED, ENDED и т.д.)
    type = db.Column(db.String(64), nullable=True)  # Тип кампании (TEXT, SMART, и т.д.)
    daily_budget = db.Column(db.Float, nullable=True)  # Дневной бюджет
    impressions = db.Column(db.Integer, nullable=True)  # Число показов
    clicks = db.Column(db.Integer, nullable=True)  # Число кликов
    cost = db.Column(db.Float, nullable=True)  # Стоимость
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<YandexCampaign {self.name} - {self.status}>'
    
    def get_status_display(self):
        """Возвращает удобочитаемый статус кампании"""
        status_map = {
            'ON': 'Активна',
            'OFF': 'Выключена',
            'SUSPENDED': 'Приостановлена',
            'ARCHIVED': 'В архиве',
            'ENDED': 'Завершена'
        }
        return status_map.get(self.status, self.status)

# Report model to store generated reports
class Report(db.Model):
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('report_templates.id'), nullable=False)
    token_id = db.Column(db.Integer, db.ForeignKey('yandex_tokens.id'), nullable=True)  # Добавляем связь с конкретным аккаунтом
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedules.id'), nullable=True)
    condition_id = db.Column(db.Integer, db.ForeignKey('conditions.id'), nullable=True)
    title = db.Column(db.String(256), nullable=False)
    summary = db.Column(db.Text, nullable=True)
    data_json = db.Column(db.Text, nullable=False)  # JSON string of report data
    date_from = db.Column(db.Date, nullable=False)
    date_to = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_to_telegram = db.Column(db.Boolean, default=False)
    
    # Relationships
    user = db.relationship('User')
    template = db.relationship('ReportTemplate')
    token = db.relationship('YandexToken', foreign_keys=[token_id])
    schedule = db.relationship('Schedule', foreign_keys=[schedule_id])
    condition = db.relationship('Condition', foreign_keys=[condition_id])
    
    def __repr__(self):
        return f'<Report {self.title}>'

# Таблица для хранения результатов оптимизации кампаний
class CampaignOptimization(db.Model):
    __tablename__ = 'campaign_optimizations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token_id = db.Column(db.Integer, db.ForeignKey('yandex_tokens.id'), nullable=False)
    campaign_ids = db.Column(db.Text, nullable=False)  # JSON-список ID кампаний
    recommendations = db.Column(db.Text, nullable=True)  # JSON-структура с рекомендациями
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Отношения
    user = db.relationship('User', backref=db.backref('optimizations', lazy=True))
    token = db.relationship('YandexToken', backref=db.backref('optimizations', lazy=True))
    
    def __repr__(self):
        return f'<CampaignOptimization id={self.id} user_id={self.user_id}>'
