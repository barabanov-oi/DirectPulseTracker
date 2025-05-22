from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from app import db
from models import YandexToken, YandexCampaign
from yandex_direct import YandexDirectAPI, get_user_client
from datetime import datetime
import logging
import numpy as np

logger = logging.getLogger(__name__)

def sync_campaigns(token_id):
    """
    Синхронизировать список кампаний для указанного токена
    
    Args:
        token_id: ID токена Яндекс Директа
        
    Returns:
        dict: Результат синхронизации с количеством добавленных, обновленных и неактивных кампаний
    """
    token = YandexToken.query.get(token_id)
    if not token:
        return {"error": "Токен не найден"}
    
    # Создаем API-клиент
    api_client = YandexDirectAPI(token)
    if not api_client:
        return {"error": "Не удалось создать API-клиент"}
    
    # Проверяем, что токен не истек
    if token.is_expired():
        # Пробуем обновить токен
        refreshed = api_client.refresh_token(token.refresh_token)
        if not refreshed:
            return {"error": "Токен истек и не может быть обновлен"}
    
    try:
        # Получаем список кампаний
        response = api_client.get_campaigns()
        if not response:
            return {"error": "Не удалось получить список кампаний"}
        
        campaigns = response.get('Campaigns', [])
        if not campaigns:
            token.last_status = "Кампании не найдены"
            token.last_used = datetime.utcnow()
            db.session.commit()
            return {"error": "В аккаунте нет кампаний"}
        
        # Получаем статистику по кампаниям
        campaign_ids = [str(c['Id']) for c in campaigns]
        stats_response = api_client.get_campaign_stats(campaign_ids)
        stats_data = {}
        
        if stats_response and 'data' in stats_response:
            for row in stats_response['data']:
                camp_id = str(row.get('CampaignId'))
                if camp_id:
                    stats_data[camp_id] = {
                        'impressions': int(row.get('Impressions', 0)),
                        'clicks': int(row.get('Clicks', 0)),
                        'cost': float(row.get('Cost', 0))
                    }
        
        # Подготавливаем результат
        result = {
            "added": 0,
            "updated": 0,
            "inactive": 0,
            "total": len(campaigns)
        }
        
        # Обрабатываем каждую кампанию
        for campaign in campaigns:
            campaign_id = str(campaign['Id'])
            
            # Получаем данные статистики для кампании
            stats = stats_data.get(campaign_id, {
                'impressions': 0,
                'clicks': 0,
                'cost': 0
            })
            
            # Проверяем, есть ли уже такая кампания в базе
            db_campaign = YandexCampaign.query.filter_by(
                token_id=token.id,
                campaign_id=campaign_id
            ).first()
            
            # Вычисляем дневной бюджет
            daily_budget = None
            if 'DailyBudget' in campaign:
                daily_budget = float(campaign['DailyBudget']['Amount']) / 1000000
            
            # Определяем, активна ли кампания
            is_active = campaign['State'] != 'ARCHIVED' and campaign['Status'] == 'ON'
            
            if db_campaign:
                # Обновляем существующую кампанию
                db_campaign.name = campaign['Name']
                db_campaign.status = campaign['Status']
                db_campaign.state = campaign['State']
                db_campaign.type = campaign['Type']
                db_campaign.daily_budget = daily_budget
                db_campaign.impressions = stats['impressions']
                db_campaign.clicks = stats['clicks']
                db_campaign.cost = stats['cost']
                db_campaign.last_updated = datetime.utcnow()
                
                result["updated"] += 1
                if not is_active:
                    result["inactive"] += 1
            else:
                # Создаем новую кампанию
                db_campaign = YandexCampaign(
                    token_id=token.id,
                    campaign_id=campaign_id,
                    name=campaign['Name'],
                    status=campaign['Status'],
                    state=campaign['State'],
                    type=campaign['Type'],
                    daily_budget=daily_budget,
                    impressions=stats['impressions'],
                    clicks=stats['clicks'],
                    cost=stats['cost'],
                    last_updated=datetime.utcnow()
                )
                db.session.add(db_campaign)
                
                result["added"] += 1
                if not is_active:
                    result["inactive"] += 1
        
        # Обновляем статус в токене
        token.last_status = f"Синхронизировано кампаний: {result['total']}"
        token.last_used = datetime.utcnow()
        db.session.commit()
        
        return result
    
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.exception(f"Database error during campaign sync: {e}")
        return {"error": f"Ошибка базы данных: {str(e)}"}
    except Exception as e:
        logger.exception(f"Error syncing campaigns: {e}")
        token.last_status = f"Ошибка синхронизации: {str(e)}"
        db.session.commit()
        return {"error": str(e)}

def get_account_status_summary(user_id):
    """
    Получить сводку по статусам всех аккаунтов пользователя
    
    Args:
        user_id: ID пользователя
        
    Returns:
        dict: Сводка по аккаунтам с информацией о кампаниях
    """
    tokens = YandexToken.query.filter_by(user_id=user_id).all()
    
    summary = {
        "accounts_count": len(tokens),
        "active_accounts": 0,
        "accounts": []
    }
    
    for token in tokens:
        # Статус аккаунта
        status = token.get_status()
        is_active = status == "Активен"
        
        # Получаем информацию о кампаниях
        campaigns = YandexCampaign.query.filter_by(token_id=token.id).all()
        active_campaigns = sum(1 for c in campaigns if c.status == "ON")
        
        account_info = {
            "id": token.id,
            "name": token.account_name or token.client_login or f"Аккаунт #{token.id}",
            "status": status,
            "is_active": token.is_active,
            "is_default": token.is_default,
            "campaigns_count": len(campaigns),
            "active_campaigns": active_campaigns,
            "last_updated": token.last_used.strftime("%Y-%m-%d %H:%M") if token.last_used else "Никогда",
            "last_status": token.last_status
        }
        
        summary["accounts"].append(account_info)
        if is_active and token.is_active:
            summary["active_accounts"] += 1
    
    # Сортируем аккаунты: сначала по умолчанию, затем по статусу, затем по имени
    summary["accounts"] = sorted(
        summary["accounts"], 
        key=lambda x: (not x["is_default"], not x["is_active"], x["name"])
    )
    
    return summary

def get_campaign_summary(user_id, token_id=None):
    """
    Получить сводку по кампаниям для указанного пользователя и аккаунта
    
    Args:
        user_id: ID пользователя
        token_id: ID токена (если None, то используется аккаунт по умолчанию)
        
    Returns:
        dict: Сводка по кампаниям
    """
    # Если token_id не указан, используем аккаунт по умолчанию
    if token_id is None:
        token = YandexToken.query.filter_by(user_id=user_id, is_default=True).first()
        if not token:
            # Если нет аккаунта по умолчанию, берем первый активный
            token = YandexToken.query.filter_by(user_id=user_id, is_active=True).first()
        
        if token:
            token_id = token.id
        else:
            # Если нет активных аккаунтов, возвращаем пустую сводку
            return {
                "campaigns_total": 0,
                "active_campaigns": 0,
                "paused_campaigns": 0,
                "off_campaigns": 0,
                "total_impressions": 0,
                "total_clicks": 0,
                "total_cost": 0,
                "ctr": 0.0,
                "avg_cpc": 0.0,
                "campaigns": [],
                "last_updated": "Нет данных"
            }
    
    # Получаем кампании для указанного аккаунта
    campaigns = YandexCampaign.query.filter_by(token_id=token_id).all()
    
    # Подготавливаем результат
    result = {
        "campaigns_total": len(campaigns),
        "active_campaigns": 0,
        "paused_campaigns": 0,
        "off_campaigns": 0,
        "total_impressions": 0,
        "total_clicks": 0,
        "total_cost": 0.0,
        "ctr": 0.0,
        "avg_cpc": 0.0,
        "campaigns": [],
        "last_updated": "Нет данных" if not campaigns else max(c.last_updated for c in campaigns).strftime("%Y-%m-%d %H:%M")
    }
    
    # Собираем статистику
    for campaign in campaigns:
        # Добавляем кампанию в список
        ctr = 0.0
        if campaign.impressions > 0:
            ctr = (campaign.clicks / campaign.impressions) * 100
        
        # Рассчитываем процент от общей стоимости
        cost_percentage = 0.0
        if result["total_cost"] > 0:
            cost_percentage = (campaign.cost / result["total_cost"]) * 100
            
        campaign_data = {
            "id": campaign.id,
            "campaign_id": campaign.campaign_id,
            "name": campaign.name,
            "status": campaign.status,
            "status_display": campaign.get_status_display(),
            "state": campaign.state,
            "type": campaign.type,
            "daily_budget": campaign.daily_budget or 0.0,
            "impressions": campaign.impressions or 0,
            "clicks": campaign.clicks or 0,
            "cost": campaign.cost or 0.0,
            "ctr": ctr,
            "cost_percentage": cost_percentage
        }
        
        result["campaigns"].append(campaign_data)
        
        # Обновляем общую статистику
        result["total_impressions"] += campaign.impressions or 0
        result["total_clicks"] += campaign.clicks or 0
        result["total_cost"] += campaign.cost or 0.0
        
        # Считаем кампании по статусам
        if campaign.status == "ON":
            result["active_campaigns"] += 1
        elif campaign.status == "SUSPENDED":
            result["paused_campaigns"] += 1
        else:
            result["off_campaigns"] += 1
    
    # Рассчитываем общие метрики
    if result["total_impressions"] > 0:
        result["ctr"] = (result["total_clicks"] / result["total_impressions"]) * 100
    
    if result["total_clicks"] > 0:
        result["avg_cpc"] = result["total_cost"] / result["total_clicks"]
    
    # Обновляем проценты стоимости
    for campaign in result["campaigns"]:
        if result["total_cost"] > 0:
            campaign["cost_percentage"] = (campaign["cost"] / result["total_cost"]) * 100
    
    # Сортируем кампании по статусу и имени
    result["campaigns"] = sorted(
        result["campaigns"], 
        key=lambda x: (x["status"] != "ON", x["status"] != "SUSPENDED", x["name"])
    )
    
    return result