import logging
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from app import db
from models import YandexToken, YandexCampaign
from yandex_direct import YandexDirectAPI

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
        logger.error(f"Token with ID {token_id} not found")
        return {"error": "Токен не найден"}
    
    # Обновляем время последнего использования
    token.last_used = datetime.utcnow()
    
    api_client = YandexDirectAPI(token)
    
    # Проверяем, что API-клиент инициализирован успешно
    if not api_client or not api_client.ensure_fresh_token():
        token.last_status = "Ошибка инициализации API-клиента или истек срок токена"
        db.session.commit()
        return {"error": token.last_status}
    
    try:
        # Получаем детальную информацию о кампаниях
        campaign_details = api_client.get_campaign_details()
        
        if not campaign_details:
            token.last_status = "Не удалось получить список кампаний или кампании отсутствуют"
            db.session.commit()
            return {"error": token.last_status, "campaigns_count": 0}
        
        # Результаты для отчета
        results = {
            "added": 0,
            "updated": 0,
            "inactive": 0,
            "total": len(campaign_details)
        }
        
        # Получаем текущие кампании из базы
        existing_campaigns = {c.campaign_id: c for c in YandexCampaign.query.filter_by(token_id=token.id).all()}
        
        # Обновляем или создаем кампании
        for campaign_data in campaign_details:
            campaign_id = str(campaign_data.get('Id'))
            
            if campaign_id in existing_campaigns:
                # Обновляем существующую кампанию
                campaign = existing_campaigns[campaign_id]
                campaign.name = campaign_data.get('Name', '')
                campaign.status = campaign_data.get('Status', '')
                campaign.state = campaign_data.get('State', '')
                campaign.type = campaign_data.get('Type', '')
                campaign.daily_budget = float(campaign_data.get('DailyBudget', 0))
                campaign.impressions = int(campaign_data.get('Impressions', 0))
                campaign.clicks = int(campaign_data.get('Clicks', 0))
                campaign.cost = float(campaign_data.get('Cost', 0))
                campaign.last_updated = datetime.utcnow()
                results["updated"] += 1
            else:
                # Создаем новую кампанию
                campaign = YandexCampaign(
                    token_id=token.id,
                    campaign_id=campaign_id,
                    name=campaign_data.get('Name', ''),
                    status=campaign_data.get('Status', ''),
                    state=campaign_data.get('State', ''),
                    type=campaign_data.get('Type', ''),
                    daily_budget=float(campaign_data.get('DailyBudget', 0)),
                    impressions=int(campaign_data.get('Impressions', 0)),
                    clicks=int(campaign_data.get('Clicks', 0)),
                    cost=float(campaign_data.get('Cost', 0)),
                    last_updated=datetime.utcnow()
                )
                db.session.add(campaign)
                results["added"] += 1
            
            # Считаем неактивные кампании
            if campaign.status != 'ON' or campaign.state != 'ON':
                results["inactive"] += 1
        
        # Обновляем статус синхронизации в токене
        token.last_status = f"Успешно синхронизировано {results['total']} кампаний"
        db.session.commit()
        
        return results
    
    except SQLAlchemyError as e:
        logger.exception(f"Database error during campaign sync: {e}")
        db.session.rollback()
        token.last_status = f"Ошибка базы данных: {str(e)}"
        db.session.commit()
        return {"error": "Ошибка базы данных при синхронизации кампаний"}
    
    except Exception as e:
        logger.exception(f"Error syncing campaigns: {e}")
        token.last_status = f"Ошибка синхронизации: {str(e)}"
        db.session.commit()
        return {"error": f"Ошибка синхронизации кампаний: {str(e)}"}

def get_account_status_summary(user_id):
    """
    Получить сводку по статусам всех аккаунтов пользователя
    
    Args:
        user_id: ID пользователя
        
    Returns:
        dict: Сводка по аккаунтам с информацией о кампаниях
    """
    tokens = YandexToken.query.filter_by(user_id=user_id).all()
    
    if not tokens:
        return {
            "accounts_count": 0,
            "active_accounts": 0,
            "accounts": []
        }
    
    accounts = []
    active_accounts = 0
    
    for token in tokens:
        # Получаем статистику по кампаниям
        campaigns = YandexCampaign.query.filter_by(token_id=token.id).all()
        
        active_campaigns = sum(1 for c in campaigns if c.status == 'ON' and c.state == 'ON')
        
        # Считаем активные аккаунты
        if token.is_active and not token.is_expired():
            active_accounts += 1
        
        account_info = {
            "id": token.id,
            "name": token.account_name or token.client_login or f"Аккаунт #{token.id}",
            "status": token.get_status(),
            "is_active": token.is_active,
            "is_default": token.is_default,
            "campaigns_count": len(campaigns),
            "active_campaigns": active_campaigns,
            "last_updated": token.last_used.strftime("%Y-%m-%d %H:%M") if token.last_used else "Нет данных",
            "last_status": token.last_status or "Нет данных",
        }
        
        accounts.append(account_info)
    
    return {
        "accounts_count": len(tokens),
        "active_accounts": active_accounts,
        "accounts": accounts
    }

def get_campaign_summary(user_id, token_id=None):
    """
    Получить сводку по кампаниям для указанного пользователя и аккаунта
    
    Args:
        user_id: ID пользователя
        token_id: ID токена (если None, то используется аккаунт по умолчанию)
        
    Returns:
        dict: Сводка по кампаниям
    """
    if token_id:
        token = YandexToken.query.filter_by(id=token_id, user_id=user_id).first()
    else:
        # Ищем аккаунт по умолчанию
        token = YandexToken.query.filter_by(user_id=user_id, is_default=True).first()
        if not token:
            # Если нет аккаунта по умолчанию, берем первый активный
            token = YandexToken.query.filter_by(user_id=user_id, is_active=True).first()
    
    if not token:
        return {
            "error": "Аккаунт не найден",
            "campaigns": []
        }
    
    campaigns = YandexCampaign.query.filter_by(token_id=token.id).order_by(YandexCampaign.status, YandexCampaign.name).all()
    
    # Формируем статистику
    active_count = sum(1 for c in campaigns if c.status == 'ON')
    paused_count = sum(1 for c in campaigns if c.status == 'SUSPENDED')
    off_count = sum(1 for c in campaigns if c.status == 'OFF')
    other_count = len(campaigns) - active_count - paused_count - off_count
    
    total_impressions = sum(c.impressions or 0 for c in campaigns)
    total_clicks = sum(c.clicks or 0 for c in campaigns)
    total_cost = sum(c.cost or 0 for c in campaigns)
    
    # CTR вычисляем только если есть показы
    ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
    
    return {
        "account_name": token.account_name or token.client_login or f"Аккаунт #{token.id}",
        "account_status": token.get_status(),
        "campaigns_total": len(campaigns),
        "active_campaigns": active_count,
        "paused_campaigns": paused_count,
        "off_campaigns": off_count,
        "other_campaigns": other_count,
        "total_impressions": total_impressions,
        "total_clicks": total_clicks,
        "total_cost": total_cost,
        "ctr": ctr,
        "last_updated": token.last_used.strftime("%Y-%m-%d %H:%M") if token.last_used else "Нет данных",
        "campaigns": [
            {
                "id": c.id,
                "campaign_id": c.campaign_id,
                "name": c.name,
                "status": c.status,
                "status_display": c.get_status_display(),
                "type": c.type,
                "daily_budget": c.daily_budget,
                "impressions": c.impressions,
                "clicks": c.clicks,
                "cost": c.cost,
                "ctr": (c.clicks / c.impressions * 100) if c.impressions and c.impressions > 0 else 0,
                "last_updated": c.last_updated.strftime("%Y-%m-%d %H:%M") if c.last_updated else "Нет данных"
            }
            for c in campaigns
        ]
    }