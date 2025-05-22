import logging
import json
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user

from app import db
from models import User, YandexToken, CampaignOptimization
from auth import admin_required
from yandex_direct import get_user_client, get_client_for_token

# Настройка логирования
logger = logging.getLogger(__name__)

# Создаем Blueprint
optimization_bp = Blueprint('optimization', __name__, url_prefix='/optimization')

@optimization_bp.route('/')
@login_required
def index():
    """Страница с выбором аккаунта для оптимизации"""
    # Получаем токены пользователя
    if current_user.is_admin:
        # Администраторы видят все токены
        tokens = YandexToken.query.all()
    else:
        # Обычные пользователи видят только свои токены
        tokens = YandexToken.query.filter_by(user_id=current_user.id).all()
    
    # Получаем предыдущие оптимизации
    optimizations = CampaignOptimization.query.filter_by(user_id=current_user.id).order_by(
        CampaignOptimization.created_at.desc()).limit(10).all()
    
    return render_template('optimization/index.html', 
                          tokens=tokens,
                          optimizations=optimizations,
                          title='AI-оптимизация кампаний')

@optimization_bp.route('/analyze/<int:token_id>')
@login_required
def analyze_account(token_id):
    """Страница анализа аккаунта"""
    # Получаем токен
    token = YandexToken.query.get_or_404(token_id)
    
    # Проверяем доступ
    if not current_user.is_admin and token.user_id != current_user.id:
        flash('У вас нет доступа к этому аккаунту', 'danger')
        return redirect(url_for('optimization.index'))
    
    # Получаем клиент Яндекс Директа
    client = get_client_for_token(token_id)
    
    if not client:
        flash('Не удалось подключиться к аккаунту Яндекс Директа', 'danger')
        return redirect(url_for('optimization.index'))
    
    # Получаем кампании
    campaigns_data = client.get_campaigns()
    
    if not campaigns_data or not campaigns_data.get('Campaigns'):
        flash('Не удалось получить данные о кампаниях', 'danger')
        return redirect(url_for('optimization.index'))
    
    # Получаем статистику за последние 30 дней
    today = datetime.now()
    date_from = (today - timedelta(days=30)).strftime('%Y-%m-%d')
    date_to = today.strftime('%Y-%m-%d')
    
    try:
        campaign_stats = client.get_campaign_stats(date_from=date_from, date_to=date_to)
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        campaign_stats = []
    
    # Подготавливаем данные для отображения
    campaigns = []
    for campaign in campaigns_data.get('Campaigns', []):
        campaign_id = campaign.get('Id')
        campaign_info = {
            'id': campaign_id,
            'name': campaign.get('Name', ''),
            'status': campaign.get('Status', {}).get('value', '') if isinstance(campaign.get('Status'), dict) else campaign.get('Status', ''),
            'state': campaign.get('State', {}).get('value', '') if isinstance(campaign.get('State'), dict) else campaign.get('State', ''),
            'type': campaign.get('Type', {}).get('value', '') if isinstance(campaign.get('Type'), dict) else campaign.get('Type', ''),
            'daily_budget': campaign.get('DailyBudget', {}).get('Amount', 0) if campaign.get('DailyBudget') else 0,
        }
        campaigns.append(campaign_info)
    
    return render_template('optimization/analyze.html',
                          token=token,
                          campaigns=campaigns,
                          account_name=token.account_name or token.client_login,
                          title='Анализ аккаунта')

@optimization_bp.route('/generate/<int:token_id>', methods=['POST'])
@login_required
def generate_optimization(token_id):
    """Генерация рекомендаций по оптимизации"""
    # Получаем токен
    token = YandexToken.query.get_or_404(token_id)
    
    # Проверяем доступ
    if not current_user.is_admin and token.user_id != current_user.id:
        flash('У вас нет доступа к этому аккаунту', 'danger')
        return redirect(url_for('optimization.index'))
    
    # Получаем список ID кампаний для анализа
    campaign_ids = request.form.getlist('campaign_ids')
    
    if not campaign_ids:
        flash('Выберите хотя бы одну кампанию для анализа', 'warning')
        return redirect(url_for('optimization.analyze_account', token_id=token_id))
    
    # Получаем клиент Яндекс Директа
    client = get_client_for_token(token_id)
    
    if not client:
        flash('Не удалось подключиться к аккаунту Яндекс Директа', 'danger')
        return redirect(url_for('optimization.index'))
    
    # Получаем данные о кампаниях
    try:
        campaign_details = client.get_campaign_details(campaign_ids=campaign_ids)
    except Exception as e:
        logger.error(f"Ошибка при получении деталей кампаний: {e}")
        flash('Ошибка при получении данных о кампаниях', 'danger')
        return redirect(url_for('optimization.analyze_account', token_id=token_id))
    
    # Получаем статистику за последние 30 дней
    today = datetime.now()
    date_from = (today - timedelta(days=30)).strftime('%Y-%m-%d')
    date_to = today.strftime('%Y-%m-%d')
    
    try:
        stats_df = client.get_campaign_stats_dataframe(
            campaign_ids=campaign_ids,
            date_from=date_from,
            date_to=date_to
        )
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        stats_df = None
    
    # Генерируем рекомендации на основе данных
    recommendations = generate_ai_recommendations(campaign_details, stats_df)
    
    # Сохраняем рекомендации в базу данных
    optimization = CampaignOptimization(
        user_id=current_user.id,
        token_id=token_id,
        campaign_ids=json.dumps(campaign_ids),
        recommendations=json.dumps(recommendations, ensure_ascii=False),
        status='completed',
        created_at=datetime.now()
    )
    
    db.session.add(optimization)
    db.session.commit()
    
    # Перенаправляем на страницу с результатами
    return redirect(url_for('optimization.view_results', optimization_id=optimization.id))

@optimization_bp.route('/results/<int:optimization_id>')
@login_required
def view_results(optimization_id):
    """Просмотр результатов оптимизации"""
    # Получаем оптимизацию
    optimization = CampaignOptimization.query.get_or_404(optimization_id)
    
    # Проверяем доступ
    if not current_user.is_admin and optimization.user_id != current_user.id:
        flash('У вас нет доступа к этой оптимизации', 'danger')
        return redirect(url_for('optimization.index'))
    
    # Получаем токен
    token = YandexToken.query.get(optimization.token_id)
    
    # Получаем рекомендации
    recommendations = json.loads(optimization.recommendations)
    
    return render_template('optimization/results.html',
                          optimization=optimization,
                          token=token,
                          recommendations=recommendations,
                          account_name=token.account_name or token.client_login if token else "Неизвестный аккаунт",
                          title='Результаты оптимизации')

def generate_ai_recommendations(campaign_details, stats_df):
    """
    Генерация рекомендаций по оптимизации с использованием AI
    
    Args:
        campaign_details: Список с подробностями о кампаниях
        stats_df: DataFrame со статистикой
        
    Returns:
        list: Список рекомендаций по оптимизации
    """
    try:
        # Импортируем OpenAI или Anthropic для генерации рекомендаций
        import os
        import anthropic
        from anthropic import Anthropic
        
        # Проверяем, есть ли ключ API
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY')
        if not anthropic_key:
            # Если ключа нет, возвращаем базовые рекомендации
            return generate_basic_recommendations(campaign_details, stats_df)
        
        client = Anthropic(api_key=anthropic_key)
        
        # Подготавливаем данные для отправки в API
        campaign_data = []
        
        for campaign in campaign_details:
            campaign_info = {
                'id': campaign.get('Id'),
                'name': campaign.get('Name'),
                'status': campaign.get('Status'),
                'type': campaign.get('Type'),
                'dailyBudget': campaign.get('DailyBudget'),
                'impressions': campaign.get('Impressions'),
                'clicks': campaign.get('Clicks'),
                'ctr': campaign.get('Clicks') / campaign.get('Impressions') * 100 if campaign.get('Impressions', 0) > 0 else 0,
                'cost': campaign.get('Cost'),
                'avgCpc': campaign.get('Cost') / campaign.get('Clicks') if campaign.get('Clicks', 0) > 0 else 0,
            }
            campaign_data.append(campaign_info)
        
        # Формируем запрос к AI
        prompt = f"""
        Я специалист по Яндекс Директу и хочу получить рекомендации по оптимизации рекламных кампаний. 
        Вот данные по кампаниям за последние 30 дней:
        
        {json.dumps(campaign_data, ensure_ascii=False, indent=2)}
        
        Пожалуйста, проанализируй эти данные и предложи конкретные рекомендации для улучшения эффективности каждой кампании.
        Обрати внимание на:
        1. CTR (показатель кликабельности)
        2. Средняя стоимость клика
        3. Дневной бюджет
        4. Общие расходы
        5. Состояние кампании
        
        Для каждой кампании дай 2-3 конкретные рекомендации по оптимизации.
        Ответ должен быть структурирован по кампаниям и содержать точные шаги для улучшения результатов.
        Пиши на русском языке.
        """
        
        # Делаем запрос к API
        # the newest Anthropic model is "claude-3-5-sonnet-20241022" which was released October 22, 2024
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            temperature=0.3,
            system="Ты - эксперт по оптимизации рекламных кампаний в Яндекс Директе.",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Получаем результат
        ai_response = message.content[0].text
        
        # Обрабатываем ответ и форматируем рекомендации
        recommendations = parse_ai_response(ai_response, campaign_details)
        
        return recommendations
    
    except Exception as e:
        logger.exception(f"Ошибка при генерации AI-рекомендаций: {e}")
        # В случае ошибки используем базовый метод
        return generate_basic_recommendations(campaign_details, stats_df)

def parse_ai_response(ai_response, campaign_details):
    """
    Обработка ответа от AI и форматирование рекомендаций
    
    Args:
        ai_response: Текстовый ответ от AI
        campaign_details: Список с подробностями о кампаниях
        
    Returns:
        list: Отформатированный список рекомендаций
    """
    recommendations = []
    
    # Создаем словарь с именами кампаний для сопоставления
    campaign_names = {campaign.get('Id'): campaign.get('Name') for campaign in campaign_details}
    
    # Простая обработка: разбиваем на абзацы и форматируем
    # В реальном приложении здесь должна быть более сложная логика
    paragraphs = ai_response.split('\n\n')
    
    current_campaign = None
    campaign_recommendations = []
    
    for paragraph in paragraphs:
        # Ищем заголовки кампаний
        if any(name in paragraph for name in campaign_names.values()):
            # Если нашли новую кампанию, сохраняем предыдущие рекомендации
            if current_campaign and campaign_recommendations:
                recommendations.append({
                    'campaign_id': current_campaign[0],
                    'campaign_name': current_campaign[1],
                    'suggestions': campaign_recommendations
                })
                campaign_recommendations = []
            
            # Определяем текущую кампанию
            for campaign_id, name in campaign_names.items():
                if name in paragraph:
                    current_campaign = (campaign_id, name)
                    break
        
        # Добавляем рекомендации
        elif paragraph.strip() and current_campaign:
            # Если параграф содержит числа, скорее всего это детали статистики, пропускаем
            if not any(char.isdigit() for char in paragraph) and len(paragraph.strip()) > 20:
                # Ищем конкретные рекомендации с маркерами списка
                if "• " in paragraph or "- " in paragraph or ". " in paragraph:
                    items = paragraph.split("• ") if "• " in paragraph else paragraph.split("- ") if "- " in paragraph else [paragraph]
                    for item in items:
                        if item.strip() and not item.strip().startswith(current_campaign[1]):
                            campaign_recommendations.append(item.strip())
    
    # Добавляем последнюю кампанию
    if current_campaign and campaign_recommendations:
        recommendations.append({
            'campaign_id': current_campaign[0],
            'campaign_name': current_campaign[1],
            'suggestions': campaign_recommendations
        })
    
    return recommendations

def generate_basic_recommendations(campaign_details, stats_df):
    """
    Генерация базовых рекомендаций без использования AI
    
    Args:
        campaign_details: Список с подробностями о кампаниях
        stats_df: DataFrame со статистикой
        
    Returns:
        list: Список рекомендаций по оптимизации
    """
    recommendations = []
    
    for campaign in campaign_details:
        campaign_id = campaign.get('Id')
        campaign_name = campaign.get('Name', '')
        impressions = campaign.get('Impressions', 0)
        clicks = campaign.get('Clicks', 0)
        cost = campaign.get('Cost', 0)
        
        campaign_recs = []
        
        # Низкий CTR
        ctr = (clicks / impressions * 100) if impressions > 0 else 0
        if ctr < 1.0:
            campaign_recs.append(
                "Низкий показатель CTR (меньше 1%). Рекомендуется пересмотреть тексты объявлений, "
                "ключевые слова и настройки таргетинга для повышения релевантности."
            )
        
        # Высокая стоимость клика
        avg_cpc = cost / clicks if clicks > 0 else 0
        if avg_cpc > 50:  # Пример порога для высокой стоимости клика
            campaign_recs.append(
                f"Высокая стоимость клика ({avg_cpc:.2f} руб). Рекомендуется оптимизировать ставки, "
                "улучшить показатель качества и пересмотреть стратегию назначения ставок."
            )
        
        # Низкая конверсия показов в клики
        if impressions > 1000 and clicks < 10:
            campaign_recs.append(
                "Низкая конверсия показов в клики. Рекомендуется улучшить привлекательность объявлений, "
                "проверить соответствие объявлений поисковым запросам и оптимизировать выбор ключевых слов."
            )
        
        # Отсутствие бюджета
        daily_budget = campaign.get('DailyBudget', 0)
        if daily_budget < 300:  # Пример порога для низкого дневного бюджета
            campaign_recs.append(
                f"Низкий дневной бюджет ({daily_budget} руб). Рекомендуется увеличить бюджет для "
                "повышения видимости и получения более стабильных результатов."
            )
        
        # Если кампания не активна
        status = campaign.get('Status', '')
        if status != 'ACCEPTED' or campaign.get('State', '') != 'ON':
            campaign_recs.append(
                f"Кампания неактивна (статус: {status}). Рекомендуется проверить настройки и активировать "
                "кампанию для возобновления показов."
            )
        
        # Если нет конкретных рекомендаций, добавляем общие
        if not campaign_recs:
            campaign_recs.append(
                "Рекомендуется регулярно проверять эффективность ключевых слов, удалять неэффективные "
                "и добавлять новые релевантные ключевые слова."
            )
            campaign_recs.append(
                "Периодически обновляйте тексты объявлений для поддержания интереса аудитории и "
                "улучшения показателей кликабельности."
            )
        
        recommendations.append({
            'campaign_id': campaign_id,
            'campaign_name': campaign_name,
            'suggestions': campaign_recs
        })
    
    return recommendations