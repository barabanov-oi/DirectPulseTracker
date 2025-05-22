import logging
from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app import app, db
from models import User
from auth import get_yandex_auth_url, process_yandex_callback

# Set up logging
logger = logging.getLogger(__name__)

# Create Blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login route"""
    # If user is already logged in, redirect to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = 'remember' in request.form
        
        # Find user by email
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            flash('Invalid email or password', 'danger')
            return render_template('login.html')
        
        # Log in the user
        login_user(user, remember=remember)
        flash('Login successful', 'success')
        
        # Redirect to the next page or dashboard
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('main.dashboard'))
    
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route"""
    # If user is already logged in, redirect to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        # Get form data
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate form data
        if not username or not email or not password:
            flash('All fields are required', 'danger')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('register.html')
        
        # Check if email or username already exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'danger')
            return render_template('register.html')
        
        # Create new user
        new_user = User(
            username=username,
            email=email
        )
        new_user.set_password(password)
        
        # Make the first user an admin
        if User.query.count() == 0:
            new_user.is_admin = True
        
        # Save the user to the database
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful. You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """User logout route"""
    logout_user()
    flash('You have been logged out', 'success')
    return redirect(url_for('auth.login'))

@auth_bp.route('/yandex/authorize')
@login_required
def yandex_authorize():
    """Show page with Yandex Direct connection options"""
    auth_url = get_yandex_auth_url()
    
    if not auth_url:
        # Создаем URL для ручного получения токена, даже если клиент не настроен
        auth_url = "https://oauth.yandex.ru/authorize?response_type=token&client_id=18bd059cacd948faaa3fd34d622eeab7"
        flash('Автоматическая авторизация недоступна, используйте ручной ввод токена', 'warning')
    
    return render_template('auth/yandex_token_form.html', oauth_url=auth_url)

@auth_bp.route('/yandex/callback')
@login_required
def yandex_callback():
    """Handle the callback from Yandex OAuth"""
    code = request.args.get('code')
    
    if not code:
        flash('Авторизация не удалась', 'danger')
        return redirect(url_for('main.dashboard'))
    
    success = process_yandex_callback(code)
    
    if success:
        flash('Аккаунт Яндекс Директа успешно подключен', 'success')
    else:
        flash('Не удалось подключить аккаунт Яндекс Директа', 'danger')
    
    return redirect(url_for('main.dashboard'))

@auth_bp.route('/yandex/save-token', methods=['POST'])
@login_required
def save_yandex_token():
    """Save manually entered Yandex Direct token"""
    from datetime import datetime, timedelta
    from yandex_direct import store_token_for_user
    
    # Получаем данные из формы
    access_token = request.form.get('access_token')
    client_login = request.form.get('client_login')
    
    if not access_token:
        flash('Необходимо указать токен доступа', 'danger')
        return redirect(url_for('auth.yandex_authorize'))
    
    # Создаем данные токена
    token_data = {
        'access_token': access_token,
        'refresh_token': 'manual_entry_no_refresh',  # При ручном вводе нет refresh_token
        'expires_in': 31536000,  # 1 год в секундах (стандартный срок для токенов Яндекса)
        'token_type': 'bearer'
    }
    
    try:
        # Сохраняем токен в базе данных
        token = store_token_for_user(current_user.id, token_data, client_login)
        
        if token:
            flash('Токен Яндекс Директа успешно сохранен', 'success')
        else:
            flash('Не удалось сохранить токен', 'danger')
            
    except Exception as e:
        logger.exception(f'Ошибка при сохранении токена: {e}')
        flash(f'Произошла ошибка при сохранении токена: {str(e)}', 'danger')
    
    return redirect(url_for('main.dashboard'))

# Register Blueprint with app
app.register_blueprint(auth_bp)
