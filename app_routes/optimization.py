import json
import logging
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, abort
from flask_login import login_required, current_user
import pandas as pd
import numpy as np

from app import db
from models import YandexToken, CampaignOptimization
from auth import admin_required
from yandex_direct import YandexDirectAPI, get_user_client

optimization_bp = Blueprint('optimization', __name__, url_prefix='/optimization')
logger = logging.getLogger(__name__)

@optimization_bp.route('/')
@login_required
def index():
    """Главная страница оптимизации - выбор аккаунта"""
    tokens = YandexToken.query.filter_by(user_id=current_user.id, is_active=True).all()
    optimizations = CampaignOptimization.query.filter_by(user_id=current_user.id).order_by(CampaignOptimization.created_at.desc()).limit(5).all()
    
    return render_template(
        'optimization/index.html',
        title='AI-оптимизация',
        tokens=tokens,
        optimizations=optimizations
    )

@optimization_bp.route('/analyze/<int:token_id>')
@login_required
def analyze_account(token_id):
    """Страница выбора кампаний для анализа"""
    # Проверяем, что токен принадлежит текущему пользователю
    token = YandexToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    # Получаем список кампаний для данного аккаунта
    try:
        yandex_client = get_user_client(token_id)
        campaigns = yandex_client.get_campaigns()
    except Exception as e:
        logger.error(f"Ошибка при получении кампаний: {e}")
        flash(f'Ошибка при получении кампаний: {str(e)}', 'danger')
        return redirect(url_for('optimization.index'))
    
    account_name = token.account_name or token.client_login or f'Аккаунт #{token.id}'
    
    return render_template(
        'optimization/analyze.html',
        title=f'Анализ аккаунта: {account_name}',
        token=token,
        account_name=account_name,
        campaigns=campaigns
    )

@optimization_bp.route('/generate/<int:token_id>', methods=['POST'])
@login_required
def generate_optimization(token_id):
    """Генерация рекомендаций по оптимизации для выбранных кампаний"""
    # Проверяем, что токен принадлежит текущему пользователю
    token = YandexToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    # Получаем ID выбранных кампаний
    campaign_ids = request.form.getlist('campaign_ids')
    
    if not campaign_ids:
        flash('Необходимо выбрать хотя бы одну кампанию для анализа', 'warning')
        return redirect(url_for('optimization.analyze_account', token_id=token_id))
    
    # Создаем запись об оптимизации
    optimization = CampaignOptimization(
        user_id=current_user.id,
        token_id=token_id,
        campaign_ids=json.dumps(campaign_ids),
        status='pending'
    )
    
    db.session.add(optimization)
    db.session.commit()
    
    # Запускаем анализ кампаний и генерацию рекомендаций
    try:
        recommendations = generate_campaign_recommendations(token_id, campaign_ids)
        
        # Обновляем запись с результатами
        optimization.recommendations = json.dumps(recommendations)
        optimization.status = 'completed'
        db.session.commit()
        
        flash('Рекомендации по оптимизации успешно сгенерированы', 'success')
    except Exception as e:
        logger.error(f"Ошибка при генерации рекомендаций: {e}")
        optimization.status = 'failed'
        db.session.commit()
        flash(f'Ошибка при генерации рекомендаций: {str(e)}', 'danger')
    
    return redirect(url_for('optimization.view_results', optimization_id=optimization.id))

@optimization_bp.route('/results/<int:optimization_id>')
@login_required
def view_results(optimization_id):
    """Просмотр результатов оптимизации"""
    # Проверяем, что оптимизация принадлежит текущему пользователю
    optimization = CampaignOptimization.query.filter_by(id=optimization_id, user_id=current_user.id).first_or_404()
    token = optimization.token
    
    account_name = token.account_name or token.client_login or f'Аккаунт #{token.id}'
    recommendations = []
    
    if optimization.recommendations:
        try:
            recommendations = json.loads(optimization.recommendations)
        except Exception as e:
            logger.error(f"Ошибка при парсинге рекомендаций: {e}")
            flash('Ошибка при загрузке рекомендаций', 'danger')
    
    return render_template(
        'optimization/results.html',
        title='Результаты оптимизации',
        optimization=optimization,
        token=token,
        account_name=account_name,
        recommendations=recommendations
    )

def generate_campaign_recommendations(token_id, campaign_ids):
    """
    Генерация рекомендаций по оптимизации для выбранных кампаний
    
    Args:
        token_id: ID токена Яндекс Директа
        campaign_ids: Список ID кампаний для анализа
        
    Returns:
        list: Список словарей с рекомендациями по кампаниям
    """
    yandex_client = get_user_client(token_id)
    
    # Получаем данные о кампаниях
    campaigns = yandex_client.get_campaigns()
    
    # Фильтруем кампании по выбранным ID
    selected_campaigns = [c for c in campaigns if str(c.get('id')) in campaign_ids]
    
    # Получаем статистику по кампаниям за последние 30 дней
    stats_data = []
    for campaign in selected_campaigns:
        try:
            campaign_stats = yandex_client.get_campaign_stats_dataframe(campaign['id'], date_range='LAST_30_DAYS')
            if not campaign_stats.empty:
                stats_data.append({
                    'campaign_id': campaign['id'],
                    'campaign_name': campaign['name'],
                    'stats': campaign_stats
                })
        except Exception as e:
            logger.error(f"Ошибка при получении статистики для кампании {campaign['id']}: {e}")
    
    # Генерируем рекомендации на основе полученных данных
    recommendations = []
    
    for campaign_data in stats_data:
        campaign_id = campaign_data['campaign_id']
        campaign_name = campaign_data['campaign_name']
        stats = campaign_data['stats']
        
        campaign_recommendations = analyze_campaign_data(campaign_id, campaign_name, stats)
        recommendations.append(campaign_recommendations)
    
    # Для кампаний без данных статистики добавляем базовые рекомендации
    campaign_ids_with_stats = [data['campaign_id'] for data in stats_data]
    for campaign in selected_campaigns:
        if campaign['id'] not in campaign_ids_with_stats:
            recommendations.append({
                'campaign_id': campaign['id'],
                'campaign_name': campaign['name'],
                'suggestions': [
                    "Недостаточно данных для детального анализа. Рекомендуется проверить настройки кампании и убедиться, что она активна.",
                    "Увеличьте период сбора статистики для более точного анализа.",
                    "Проверьте настройки таргетинга и ключевые слова на соответствие целевой аудитории."
                ]
            })
    
    return recommendations

def analyze_campaign_data(campaign_id, campaign_name, stats_df):
    """
    Анализ данных кампании и генерация рекомендаций
    
    Args:
        campaign_id: ID кампании
        campaign_name: Название кампании
        stats_df: DataFrame со статистикой кампании
        
    Returns:
        dict: Словарь с рекомендациями
    """
    suggestions = []
    
    # Базовый анализ эффективности кампании
    try:
        # Проверка CTR
        avg_ctr = stats_df['Ctr'].mean() if 'Ctr' in stats_df.columns else None
        if avg_ctr is not None and avg_ctr < 0.01:  # CTR менее 1%
            suggestions.append(
                "Низкий показатель CTR (менее 1%). Рекомендуется улучшить релевантность объявлений, "
                "пересмотреть заголовки и тексты для повышения привлекательности."
            )
        elif avg_ctr is not None and avg_ctr < 0.03:  # CTR менее 3%
            suggestions.append(
                "Средний показатель CTR может быть улучшен. Рассмотрите возможность A/B-тестирования различных "
                "вариантов заголовков и текстов объявлений."
            )
        
        # Проверка средней стоимости клика (CPC)
        avg_cpc = stats_df['AvgCpc'].mean() if 'AvgCpc' in stats_df.columns else None
        if avg_cpc is not None and avg_cpc > 50:  # Высокая стоимость клика
            suggestions.append(
                "Высокая средняя стоимость клика. Рекомендуется пересмотреть стратегию ставок, улучшить "
                "показатель качества объявлений и оптимизировать ключевые слова."
            )
        
        # Анализ динамики показов и кликов
        if 'Impressions' in stats_df.columns and len(stats_df) > 7:
            recent_impressions = stats_df['Impressions'].iloc[-7:].mean()
            older_impressions = stats_df['Impressions'].iloc[:-7].mean() if len(stats_df) > 14 else recent_impressions
            
            if recent_impressions < older_impressions * 0.7:  # Падение показов более чем на 30%
                suggestions.append(
                    "Наблюдается значительное снижение числа показов. Рекомендуется проверить настройки таргетинга, "
                    "бюджет кампании и актуальность ключевых слов."
                )
        
        # Анализ конверсий
        if 'Conversions' in stats_df.columns and 'Cost' in stats_df.columns:
            total_conversions = stats_df['Conversions'].sum()
            total_cost = stats_df['Cost'].sum()
            
            if total_conversions > 0:
                cost_per_conversion = total_cost / total_conversions
                if cost_per_conversion > 1000:  # Высокая стоимость конверсии
                    suggestions.append(
                        "Высокая стоимость конверсии. Рекомендуется пересмотреть целевую аудиторию, "
                        "оптимизировать посадочные страницы и улучшить релевантность объявлений."
                    )
            elif total_cost > 5000:  # Затраты без конверсий
                suggestions.append(
                    "Отсутствуют конверсии при значительных затратах. Рекомендуется проверить корректность "
                    "настройки целей, релевантность посадочных страниц и качество трафика."
                )
    except Exception as e:
        logger.error(f"Ошибка при анализе данных кампании {campaign_id}: {e}")
        suggestions.append(
            "При анализе данных кампании произошла ошибка. Рекомендуется повторить анализ позже или "
            "проверить корректность данных."
        )
    
    # Если рекомендаций нет, добавляем общие
    if not suggestions:
        suggestions.append(
            "Кампания демонстрирует хорошие показатели эффективности. Рекомендуется регулярно обновлять "
            "объявления и ключевые слова для поддержания результативности."
        )
        suggestions.append(
            "Рассмотрите возможность расширения списка ключевых слов для охвата новых сегментов аудитории."
        )
        suggestions.append(
            "Для повышения эффективности рекомендуется настроить расписание показов на основе анализа "
            "активности целевой аудитории."
        )
    
    # Добавляем общие рекомендации
    suggestions.append(
        "Регулярно анализируйте поисковые запросы и добавляйте неэффективные запросы в список минус-слов."
    )
    
    # Используем AI для дополнительных рекомендаций
    try:
        ai_suggestions = generate_ai_recommendations(campaign_name, stats_df)
        if ai_suggestions:
            suggestions.extend(ai_suggestions)
    except Exception as e:
        logger.error(f"Ошибка при генерации AI-рекомендаций: {e}")
    
    return {
        'campaign_id': campaign_id,
        'campaign_name': campaign_name,
        'suggestions': suggestions
    }

def generate_ai_recommendations(campaign_name, stats_df):
    """
    Генерация дополнительных рекомендаций с использованием AI
    
    Args:
        campaign_name: Название кампании
        stats_df: DataFrame со статистикой кампании
        
    Returns:
        list: Список рекомендаций
    """
    # Проверяем, настроен ли API-ключ
    openai_api_key = current_app.config.get('OPENAI_API_KEY')
    anthropic_api_key = current_app.config.get('ANTHROPIC_API_KEY')
    
    if not openai_api_key and not anthropic_api_key:
        logger.warning("API ключи для AI не настроены, используются только базовые рекомендации")
        return []
    
    # Подготовка данных для отправки в API
    stats_summary = {}
    
    if not stats_df.empty:
        for col in stats_df.columns:
            if col in ['Date', 'CampaignId', 'CampaignName']:
                continue
                
            try:
                stats_summary[col] = {
                    'mean': float(stats_df[col].mean()),
                    'min': float(stats_df[col].min()),
                    'max': float(stats_df[col].max()),
                    'sum': float(stats_df[col].sum()),
                    'trend': 'up' if stats_df[col].iloc[-1] > stats_df[col].iloc[0] else 'down'
                }
            except (TypeError, ValueError, IndexError):
                # Пропускаем колонки, которые нельзя агрегировать
                continue
    
    # Если есть API-ключ Anthropic, используем его (Claude более подходит для анализа)
    if anthropic_api_key:
        try:
            import anthropic
            from anthropic import Anthropic
            
            client = Anthropic(api_key=anthropic_api_key)
            
            prompt = f"""
            Проанализируй статистику рекламной кампании Яндекс Директ "{campaign_name}" и предложи 3 конкретные рекомендации 
            по её оптимизации. Вот агрегированные данные по кампании:
            
            {json.dumps(stats_summary, indent=2)}
            
            Предложи только конкретные, практические рекомендации, основанные на этих данных.
            Каждая рекомендация должна быть не более 2-3 предложений, понятной и полезной для маркетолога.
            """
            
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                temperature=0.5,
                system="Ты эксперт по оптимизации рекламных кампаний в Яндекс Директ. Даёшь только конкретные рекомендации на русском языке.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Разбиваем ответ на отдельные рекомендации
            text = message.content[0].text
            ai_recommendations = [line.strip() for line in text.split('\n') if line.strip() and not line.strip().startswith('Рекомендация')]
            
            # Ограничиваем количество рекомендаций
            return ai_recommendations[:3]
            
        except Exception as e:
            logger.error(f"Ошибка при использовании Anthropic API: {e}")
            return []
    
    # Если есть API-ключ OpenAI, используем его как запасной вариант
    elif openai_api_key:
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=openai_api_key)
            
            prompt = f"""
            Проанализируй статистику рекламной кампании Яндекс Директ "{campaign_name}" и предложи 3 конкретные рекомендации 
            по её оптимизации. Вот агрегированные данные по кампании:
            
            {json.dumps(stats_summary, indent=2)}
            
            Предложи только конкретные, практические рекомендации, основанные на этих данных.
            Каждая рекомендация должна быть не более 2-3 предложений, понятной и полезной для маркетолога.
            """
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Ты эксперт по оптимизации рекламных кампаний в Яндекс Директ. Даёшь только конкретные рекомендации на русском языке."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=1000
            )
            
            # Разбиваем ответ на отдельные рекомендации
            text = response.choices[0].message.content
            ai_recommendations = [line.strip() for line in text.split('\n') if line.strip() and not line.strip().startswith('Рекомендация')]
            
            # Ограничиваем количество рекомендаций
            return ai_recommendations[:3]
            
        except Exception as e:
            logger.error(f"Ошибка при использовании OpenAI API: {e}")
            return []
    
    return []