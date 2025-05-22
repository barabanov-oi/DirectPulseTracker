import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from models import YandexToken, User
from auth import admin_required
from yandex_direct import connection_manager

# Настройка логирования
logger = logging.getLogger(__name__)

# Создаем Blueprint для страниц управления аккаунтами
account_manager = Blueprint('account_manager', __name__, url_prefix='/account-manager')

@account_manager.route('/')
@login_required
def index():
    """Главная страница менеджера аккаунтов"""
    # Если пользователь не админ, показываем только его аккаунты
    if not current_user.is_admin:
        users = [current_user]
    else:
        # Админы видят все аккаунты
        users = User.query.all()
    
    # Собираем информацию об аккаунтах
    account_data = []
    for user in users:
        user_tokens = YandexToken.query.filter_by(user_id=user.id).all()
        for token in user_tokens:
            account_data.append({
                'id': token.id,
                'user_id': user.id,
                'username': user.username,
                'account_name': token.account_name or token.client_login or f"Аккаунт #{token.id}",
                'client_login': token.client_login,
                'status': token.get_status(),
                'is_default': token.is_default,
                'last_used': token.last_used,
                'created_at': token.created_at
            })
    
    return render_template('account_manager/index.html', 
                          accounts=account_data, 
                          users=users, 
                          title='Менеджер аккаунтов')

@account_manager.route('/account/<int:token_id>')
@login_required
def account_details(token_id):
    """Страница с детальной информацией об аккаунте"""
    token = YandexToken.query.get_or_404(token_id)
    user = User.query.get(token.user_id)
    
    # Проверяем, что пользователь имеет доступ к этому аккаунту
    if token.user_id != current_user.id and not current_user.is_admin:
        flash('У вас нет доступа к этому аккаунту', 'danger')
        return redirect(url_for('account_manager.index'))
    
    # Получаем информацию о кампаниях
    campaigns = []
    try:
        # Получаем API-клиент для этого токена
        api_client = connection_manager.get_connection(token.id)
        if api_client:
            campaigns_data = api_client.get_campaign_details()
            campaigns = campaigns_data if campaigns_data else []
    except Exception as e:
        logger.exception(f"Error getting campaign details: {e}")
        flash('Ошибка при получении данных о кампаниях', 'danger')
    
    return render_template('account_manager/account_details.html',
                          token=token,
                          user=user,
                          campaigns=campaigns,
                          title=f'Аккаунт: {token.account_name or token.client_login}')

@account_manager.route('/set-default/<int:token_id>', methods=['POST'])
@login_required
def set_default_account(token_id):
    """Установить аккаунт по умолчанию для пользователя"""
    token = YandexToken.query.get_or_404(token_id)
    user_id = token.user_id
    
    # Сбрасываем флаг у всех токенов пользователя
    user_tokens = YandexToken.query.filter_by(user_id=user_id).all()
    for t in user_tokens:
        t.is_default = False
    
    # Устанавливаем флаг у выбранного токена
    token.is_default = True
    db.session.commit()
    
    flash(f'Аккаунт {token.account_name or token.client_login} установлен по умолчанию', 'success')
    return redirect(url_for('account_manager.index'))

@account_manager.route('/rename/<int:token_id>', methods=['POST'])
@login_required
def rename_account(token_id):
    """Переименовать аккаунт"""
    token = YandexToken.query.get_or_404(token_id)
    new_name = request.form.get('account_name', '').strip()
    
    if new_name:
        token.account_name = new_name
        db.session.commit()
        flash('Название аккаунта обновлено', 'success')
    else:
        flash('Название аккаунта не может быть пустым', 'warning')
        
    return redirect(url_for('account_manager.account_details', token_id=token.id))

@account_manager.route('/toggle-active/<int:token_id>', methods=['POST'])
@login_required
def toggle_active(token_id):
    """Включить/выключить аккаунт"""
    token = YandexToken.query.get_or_404(token_id)
    token.is_active = not token.is_active
    
    # Если деактивируем аккаунт по умолчанию, нужно выбрать другой
    if not token.is_active and token.is_default:
        token.is_default = False
        # Ищем другой активный токен и делаем его токеном по умолчанию
        other_token = YandexToken.query.filter_by(user_id=token.user_id, is_active=True).first()
        if other_token:
            other_token.is_default = True
            
    db.session.commit()
    
    status = 'активирован' if token.is_active else 'деактивирован'
    flash(f'Аккаунт {token.account_name or token.client_login} {status}', 'success')
    return redirect(url_for('account_manager.index'))

@account_manager.route('/delete/<int:token_id>', methods=['POST'])
@login_required
def delete_account(token_id):
    """Удалить аккаунт"""
    token = YandexToken.query.get_or_404(token_id)
    account_name = token.account_name or token.client_login or f"Аккаунт #{token.id}"
    user_id = token.user_id
    
    # Если удаляем аккаунт по умолчанию, нужно выбрать другой
    if token.is_default:
        # Ищем другой активный токен и делаем его токеном по умолчанию
        other_token = YandexToken.query.filter(
            YandexToken.user_id == user_id,
            YandexToken.id != token_id,
            YandexToken.is_active == True
        ).first()
        
        if other_token:
            other_token.is_default = True
    
    # Удаляем токен
    db.session.delete(token)
    db.session.commit()
    
    # Сбрасываем соединение в менеджере подключений
    connection_manager.refresh_connection(token_id)
    
    flash(f'Аккаунт {account_name} удален', 'success')
    return redirect(url_for('account_manager.index'))