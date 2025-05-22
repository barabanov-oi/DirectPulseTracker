import logging
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required

from app import app, db
from models import User, YandexToken, ReportTemplate
from auth import admin_required

# Set up logging
logger = logging.getLogger(__name__)

# Create Blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/')
@login_required
@admin_required
def admin_dashboard():
    """Admin dashboard overview"""
    # Count statistics
    user_count = User.query.count()
    token_count = YandexToken.query.count()
    template_count = ReportTemplate.query.count()
    
    return render_template(
        'admin/dashboard.html',
        user_count=user_count,
        token_count=token_count,
        template_count=template_count
    )

@admin_bp.route('/users')
@login_required
@admin_required
def users_list():
    """List all users"""
    users = User.query.order_by(User.username).all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit user details"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        # Get form data
        username = request.form.get('username')
        email = request.form.get('email')
        is_admin = 'is_admin' in request.form
        timezone = request.form.get('timezone', 'UTC')
        
        # Validate form data
        if not username or not email:
            flash('Username and email are required', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))
        
        # Check if email or username already exists
        email_exists = User.query.filter(User.email == email, User.id != user_id).first()
        if email_exists:
            flash('Email already registered to another user', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))
        
        username_exists = User.query.filter(User.username == username, User.id != user_id).first()
        if username_exists:
            flash('Username already taken by another user', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))
        
        # Update user
        user.username = username
        user.email = email
        user.is_admin = is_admin
        user.timezone = timezone
        
        # Update password if provided
        new_password = request.form.get('new_password')
        if new_password:
            user.set_password(new_password)
        
        db.session.commit()
        
        flash('User updated successfully', 'success')
        return redirect(url_for('admin.users_list'))
    
    return render_template('admin/user_form.html', user=user)

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Delete a user"""
    user = User.query.get_or_404(user_id)
    
    # Check if trying to delete self
    from flask_login import current_user
    if user.id == current_user.id:
        flash('Cannot delete yourself', 'danger')
        return redirect(url_for('admin.users_list'))
    
    db.session.delete(user)
    db.session.commit()
    
    flash('User deleted successfully', 'success')
    return redirect(url_for('admin.users_list'))

@admin_bp.route('/tokens')
@login_required
@admin_required
def tokens_list():
    """List all Yandex Direct tokens"""
    tokens = YandexToken.query.join(User).order_by(User.username).all()
    return render_template('admin/tokens.html', tokens=tokens)

@admin_bp.route('/tokens/delete/<int:token_id>', methods=['POST'])
@login_required
@admin_required
def delete_token(token_id):
    """Delete a Yandex Direct token"""
    token = YandexToken.query.get_or_404(token_id)
    
    db.session.delete(token)
    db.session.commit()
    
    flash('Token deleted successfully', 'success')
    return redirect(url_for('admin.tokens_list'))

@admin_bp.route('/templates')
@login_required
@admin_required
def templates_list():
    """List all report templates"""
    templates = ReportTemplate.query.join(User).order_by(User.username, ReportTemplate.name).all()
    return render_template('admin/templates.html', templates=templates)

# Blueprint будет зарегистрирован в main.py
