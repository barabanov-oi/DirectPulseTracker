from datetime import datetime
from app import db
from flask_login import UserMixin
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
    access_token = db.Column(db.String(1024), nullable=False)
    refresh_token = db.Column(db.String(1024), nullable=False)
    token_type = db.Column(db.String(64), default='Bearer')
    expires_at = db.Column(db.DateTime, nullable=False)
    client_login = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<YandexToken {self.client_login}>'
    
    def is_expired(self):
        return datetime.utcnow() > self.expires_at

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

# Report model to store generated reports
class Report(db.Model):
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('report_templates.id'), nullable=False)
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
    schedule = db.relationship('Schedule', foreign_keys=[schedule_id])
    condition = db.relationship('Condition', foreign_keys=[condition_id])
    
    def __repr__(self):
        return f'<Report {self.title}>'
