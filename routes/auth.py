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
    """Redirect user to Yandex OAuth authorization page"""
    auth_url = get_yandex_auth_url()
    
    if not auth_url:
        flash('Yandex Direct integration is not configured correctly', 'danger')
        return redirect(url_for('main.dashboard'))
    
    return redirect(auth_url)

@auth_bp.route('/yandex/callback')
@login_required
def yandex_callback():
    """Handle the callback from Yandex OAuth"""
    code = request.args.get('code')
    
    if not code:
        flash('Authorization failed', 'danger')
        return redirect(url_for('main.dashboard'))
    
    success = process_yandex_callback(code)
    
    if success:
        flash('Yandex Direct account connected successfully', 'success')
    else:
        flash('Failed to connect Yandex Direct account', 'danger')
    
    return redirect(url_for('main.dashboard'))

# Register Blueprint with app
app.register_blueprint(auth_bp)
