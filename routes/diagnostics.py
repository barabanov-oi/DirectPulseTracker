from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError
from app import db
from models import YandexToken, YandexCampaign
from yandex_direct import YandexDirectAPI, get_user_client
from yandex_campaigns import sync_campaigns, get_account_status_summary, get_campaign_summary
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

diagnostics_bp = Blueprint('diagnostics', __name__)

@diagnostics_bp.route('/')
@login_required
def index():
    """Страница диагностики для проверки подключений к Яндекс Директу"""
    # Получаем информацию об аккаунтах
    summary = get_account_status_summary(current_user.id)
    
    return render_template('diagnostics/index.html', summary=summary)

@diagnostics_bp.route('/account/<int:token_id>')
@login_required
def account_details(token_id):
    """Подробная информация об аккаунте и его кампаниях"""
    token = YandexToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    # Получаем информацию о кампаниях
    campaign_data = get_campaign_summary(current_user.id, token_id)
    
    return render_template('diagnostics/account_details.html', 
                           token=token, 
                           campaign_data=campaign_data)

@diagnostics_bp.route('/sync/<int:token_id>', methods=['POST'])
@login_required
def sync_account_campaigns(token_id):
    """Синхронизировать кампании для указанного аккаунта"""
    token = YandexToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    result = sync_campaigns(token.id)
    
    if 'error' in result:
        flash(f'Ошибка синхронизации: {result["error"]}', 'danger')
    else:
        flash(f'Синхронизация успешно завершена. Добавлено: {result["added"]}, Обновлено: {result["updated"]}, '
              f'Неактивных: {result["inactive"]}, Всего: {result["total"]}', 'success')
    
    return redirect(url_for('diagnostics.account_details', token_id=token.id))

@diagnostics_bp.route('/account/toggle/<int:token_id>', methods=['POST'])
@login_required
def toggle_account_status(token_id):
    """Включить/выключить аккаунт"""
    token = YandexToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    token.is_active = not token.is_active
    db.session.commit()
    
    status = "активирован" if token.is_active else "деактивирован"
    flash(f'Аккаунт {token.account_name or token.client_login or token_id} {status}', 'success')
    
    return redirect(url_for('diagnostics.index'))

@diagnostics_bp.route('/account/default/<int:token_id>', methods=['POST'])
@login_required
def set_default_account(token_id):
    """Установить аккаунт по умолчанию"""
    token = YandexToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    # Сбрасываем флаг у всех аккаунтов пользователя
    YandexToken.query.filter_by(user_id=current_user.id).update({YandexToken.is_default: False})
    
    # Устанавливаем флаг у выбранного аккаунта
    token.is_default = True
    db.session.commit()
    
    flash(f'Аккаунт {token.account_name or token.client_login or token_id} установлен по умолчанию', 'success')
    
    return redirect(url_for('diagnostics.index'))

@diagnostics_bp.route('/account/edit/<int:token_id>', methods=['POST'])
@login_required
def edit_account(token_id):
    """Изменить название аккаунта"""
    token = YandexToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    account_name = request.form.get('account_name', '').strip()
    if account_name:
        token.account_name = account_name
        db.session.commit()
        flash(f'Название аккаунта изменено на "{account_name}"', 'success')
    else:
        flash('Название аккаунта не может быть пустым', 'danger')
    
    return redirect(url_for('diagnostics.index'))

@diagnostics_bp.route('/api/test/<int:token_id>')
@login_required
def test_api_connection(token_id):
    """Проверить соединение с API Яндекс Директа"""
    token = YandexToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    api_client = YandexDirectAPI(token)
    if not api_client:
        return jsonify({"success": False, "message": "Не удалось создать API-клиент"})
    
    try:
        # Проверяем, что токен не истек
        if token.is_expired():
            # Пробуем обновить токен
            refreshed = api_client.refresh_token(token.refresh_token)
            if not refreshed:
                return jsonify({
                    "success": False, 
                    "message": "Токен истек и не может быть обновлен"
                })
        
        # Пробуем получить список кампаний
        response = api_client.get_campaigns()
        
        if not response:
            return jsonify({
                "success": False, 
                "message": "Не удалось получить данные от API Яндекс Директа"
            })
        
        # Обновляем статус в базе
        token.last_status = "API-соединение проверено успешно"
        token.last_used = datetime.utcnow()
        db.session.commit()
        
        campaigns_count = len(response.get('Campaigns', []))
        return jsonify({
            "success": True,
            "message": f"API-соединение работает. Найдено кампаний: {campaigns_count}",
            "campaigns_count": campaigns_count
        })
    
    except Exception as e:
        logger.exception(f"Error testing API connection: {e}")
        # Обновляем статус в базе
        token.last_status = f"Ошибка API: {str(e)}"
        db.session.commit()
        
        return jsonify({
            "success": False,
            "message": f"Ошибка при проверке API: {str(e)}"
        })