import json
import logging
import requests
from datetime import datetime, timedelta
from urllib.parse import urlencode
import pandas as pd
from models import YandexToken, User
from app import db

# Импортируем tapi для Яндекс Директа
from tapi_yandex_direct import YandexDirect
from tapi_yandex_direct.exceptions import YandexDirectApiError

logger = logging.getLogger(__name__)

class YandexDirectConnectionManager:
    """Менеджер для управления подключениями к аккаунтам Яндекс Директа"""
    
    # API endpoints для OAuth
    AUTH_URL = 'https://oauth.yandex.ru/authorize'
    TOKEN_URL = 'https://oauth.yandex.ru/token'
    
    # Настройки OAuth по умолчанию
    DEFAULT_CLIENT_ID = '736c506b2b1a4c5588e9e8ea8c4054a4'  # Замените на ваш ID при необходимости
    DEFAULT_CLIENT_SECRET = 'f84cc9e2411841c39bc844a47e9ca57f'  # Замените на ваш секрет при необходимости
    DEFAULT_REDIRECT_URI = 'http://localhost:5000/auth/yandex/callback'
    
    def __init__(self):
        """Инициализация менеджера подключений"""
        self.connections = {}  # Словарь активных подключений {token_id: YandexDirectAPI}
        self.config = {
            'client_id': self.DEFAULT_CLIENT_ID,
            'client_secret': self.DEFAULT_CLIENT_SECRET,
            'redirect_uri': self.DEFAULT_REDIRECT_URI
        }
    
    def set_oauth_config(self, client_id=None, client_secret=None, redirect_uri=None):
        """Установка OAuth конфигурации для Яндекс Директа"""
        if client_id:
            self.config['client_id'] = client_id
        if client_secret:
            self.config['client_secret'] = client_secret
        if redirect_uri:
            self.config['redirect_uri'] = redirect_uri
    
    def get_connection(self, token_id):
        """
        Получение или создание подключения для указанного токена
        
        Args:
            token_id: ID токена в базе данных
            
        Returns:
            YandexDirectAPI: Экземпляр API клиента
        """
        # Проверяем, есть ли уже активное подключение
        if token_id in self.connections:
            return self.connections[token_id]
        
        # Получаем токен из базы данных
        token = YandexToken.query.get(token_id)
        if not token:
            logger.error(f"Token with ID {token_id} not found")
            return None
        
        # Создаем новое подключение
        connection = YandexDirectAPI(token, self.config)
        self.connections[token_id] = connection
        return connection
    
    def get_connection_for_user(self, user_id, default_only=True):
        """
        Получение подключения для указанного пользователя
        
        Args:
            user_id: ID пользователя
            default_only: Искать только токен по умолчанию
            
        Returns:
            YandexDirectAPI: Экземпляр API клиента
        """
        # Ищем токен пользователя
        if default_only:
            token = YandexToken.query.filter_by(user_id=user_id, is_default=True, is_active=True).first()
            if not token:
                # Если токен по умолчанию не найден или не активен, попробуем найти любой активный
                token = YandexToken.query.filter_by(user_id=user_id, is_active=True).first()
        else:
            token = YandexToken.query.filter_by(user_id=user_id, is_active=True).first()
        
        if not token:
            logger.warning(f"No active Yandex token found for user {user_id}")
            return None
        
        # Получаем или создаем подключение
        return self.get_connection(token.id)
    
    def refresh_connection(self, token_id):
        """
        Обновить подключение (например, после изменения токена)
        
        Args:
            token_id: ID токена
            
        Returns:
            YandexDirectAPI: Обновленный экземпляр API клиента
        """
        # Удаляем существующее подключение из кэша
        if token_id in self.connections:
            del self.connections[token_id]
        
        # Создаем новое подключение
        return self.get_connection(token_id)
    
    def get_auth_url(self):
        """
        Генерировать URL для OAuth авторизации
        
        Returns:
            str: URL для авторизации пользователя
        """
        params = {
            'client_id': self.config['client_id'],
            'redirect_uri': self.config['redirect_uri'],
            'response_type': 'code',
            'force_confirm': 'yes',
            'scope': 'direct'
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"
    
    def get_token(self, code):
        """
        Обмен кода авторизации на токен доступа
        
        Args:
            code: Код авторизации из callback
            
        Returns:
            dict: Ответ с токеном или None при ошибке
        """
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': self.config['client_id'],
            'client_secret': self.config['client_secret'],
            'redirect_uri': self.config['redirect_uri']
        }
        
        response = requests.post(self.TOKEN_URL, data=data)
        
        if response.status_code != 200:
            logger.error(f"Error getting token: {response.text}")
            return None
        
        return response.json()
    
    def refresh_token(self, refresh_token):
        """
        Обновление истекшего токена доступа
        
        Args:
            refresh_token: Токен обновления
            
        Returns:
            dict: Новый ответ с токеном или None при ошибке
        """
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.config['client_id'],
            'client_secret': self.config['client_secret']
        }
        
        response = requests.post(self.TOKEN_URL, data=data)
        
        if response.status_code != 200:
            logger.error(f"Error refreshing token: {response.text}")
            return None
        
        return response.json()
    
    def store_token_for_user(self, user_id, token_data, client_login=None, is_default=None):
        """
        Сохранение или обновление OAuth токена для пользователя
        
        Args:
            user_id: ID пользователя
            token_data: Ответ с токеном от API
            client_login: Логин клиента (для ручного ввода токена)
            is_default: Установить как токен по умолчанию
        
        Returns:
            YandexToken: Сохраненный объект токена
        """
        # Проверяем, есть ли у пользователя токены
        user_tokens = YandexToken.query.filter_by(user_id=user_id).all()
        
        # Определяем, должен ли этот токен быть токеном по умолчанию
        if is_default is None:
            # Если это первый токен пользователя, делаем его токеном по умолчанию
            is_default = len(user_tokens) == 0
        
        # Проверяем, есть ли у пользователя такой токен (по client_login)
        existing_token = None
        if client_login:
            existing_token = YandexToken.query.filter_by(
                user_id=user_id, 
                client_login=client_login
            ).first()
        
        expires_at = datetime.utcnow() + timedelta(seconds=token_data['expires_in'])
        
        if existing_token:
            # Обновляем существующий токен
            existing_token.access_token = token_data['access_token']
            existing_token.refresh_token = token_data.get('refresh_token', existing_token.refresh_token)
            existing_token.expires_at = expires_at
            existing_token.updated_at = datetime.utcnow()
            
            # Если нужно установить как токен по умолчанию
            if is_default:
                # Сбрасываем флаг у всех токенов пользователя
                for token in user_tokens:
                    token.is_default = False
                existing_token.is_default = True
                
            token = existing_token
        else:
            # Если нужно установить как токен по умолчанию, сбрасываем флаг у всех токенов
            if is_default:
                for token in user_tokens:
                    token.is_default = False
            
            # Создаем новый токен
            token = YandexToken(
                user_id=user_id,
                access_token=token_data['access_token'],
                refresh_token=token_data['refresh_token'],
                expires_at=expires_at,
                token_type=token_data.get('token_type', 'Bearer'),
                client_login=client_login,
                is_active=True,
                is_default=is_default
            )
            db.session.add(token)
        
        # Сохраняем изменения
        db.session.commit()
        
        # Получаем логин клиента через API, если он не задан
        if not client_login and token:
            # Создаем временное подключение для получения информации о клиенте
            connection = YandexDirectAPI(token, self.config)
            if connection._init_api_client():
                try:
                    # Получаем информацию о клиенте
                    clients_info = connection.api_client.clients().get(
                        FieldNames=['Login']
                    )
                    
                    if clients_info and 'Clients' in clients_info and clients_info['Clients']:
                        token.client_login = clients_info['Clients'][0]['Login']
                        # Используем логин клиента как название аккаунта, если оно не задано
                        if not token.account_name:
                            token.account_name = token.client_login
                        db.session.commit()
                except Exception as e:
                    logger.exception(f"Error getting client info: {e}")
            
            # Обновляем подключение в кэше менеджера
            self.refresh_connection(token.id)
        
        return token


# Создаем глобальный экземпляр менеджера подключений
connection_manager = YandexDirectConnectionManager()

# Вспомогательные функции для работы с Яндекс Директом

def get_user_client(user_id):
    """
    Get a YandexDirectAPI client for a specific user
    
    Args:
        user_id: User ID
        
    Returns:
        YandexDirectAPI: Configured API client or None
    """
    return connection_manager.get_connection_for_user(user_id)
    
def get_client_for_token(token_id):
    """
    Get a YandexDirectAPI client for a specific token
    
    Args:
        token_id: Token ID
        
    Returns:
        YandexDirectAPI: Configured API client or None
    """
    return connection_manager.get_connection(token_id)


class YandexDirectAPI:
    """Class to interact with Yandex Direct API using tapi_yandex_direct"""
    
    def __init__(self, token=None, config=None):
        """
        Initialize with a token object and OAuth config
        
        Args:
            token: YandexToken model instance (optional)
            config: OAuth configuration dictionary (optional)
        """
        self.token = token
        self.config = config or {}
        self.api_client = None
        
        if token and token.access_token:
            self._init_api_client()
    
    def _init_api_client(self):
        """Инициализация API клиента tapi_yandex_direct"""
        if not self.token:
            return False
            
        # Если токен истек, пытаемся обновить его
        if self.token.is_expired():
            if not self.ensure_fresh_token():
                return False
        
        # Создаем API клиент с доступом к нужным сервисам
        try:
            self.api_client = YandexDirect(
                access_token=self.token.access_token,
                login=self.token.client_login,
                is_sandbox=False,
                # Использовать язык по умолчанию
                language='ru'
            )
            return True
        except Exception as e:
            logger.exception(f"Error initializing YandexDirect API client: {e}")
            return False
    
    def ensure_fresh_token(self):
        """
        Проверяет, не истек ли токен, и обновляет его при необходимости
        
        Returns:
            bool: True, если токен валиден, False - в противном случае
        """
        if not self.token:
            logger.error("No token available")
            return False
        
        # Проверяем, истек ли токен
        if self.token.is_expired():
            logger.info(f"Token for {self.token.client_login} is expired, refreshing...")
            
            # Обновляем токен через менеджер подключений
            token_data = connection_manager.refresh_token(self.token.refresh_token)
            if not token_data:
                return False
            
            # Обновляем токен в базе данных
            self.token.access_token = token_data['access_token']
            self.token.refresh_token = token_data.get('refresh_token', self.token.refresh_token)
            self.token.expires_at = datetime.utcnow() + timedelta(seconds=token_data['expires_in'])
            self.token.updated_at = datetime.utcnow()
            
            db.session.commit()
            logger.info(f"Token refreshed successfully for {self.token.client_login}")
        
        return True
    
    def get_campaigns(self, include_archived=False):
        """
        Получить список кампаний пользователя
        
        Args:
            include_archived: Включать ли архивные кампании
            
        Returns:
            dict: Ответ API с данными о кампаниях
        """
        if not self._init_api_client():
            return None
            
        try:
            # Для tapi_yandex_direct версии 2 параметры указываются по-другому
            # Создаем запрос в правильном формате
            states = ['ON', 'OFF', 'SUSPENDED', 'ENDED'] if not include_archived else None
            
            # Получаем кампании через tapi_yandex_direct
            # Создаем правильный запрос с SelectionCriteria
            params = {}
            if states:
                params = {
                    "SelectionCriteria": {"States": states}
                }
            
            # Выполняем запрос
            campaigns = self.api_client.campaigns().get(params)
            
            # Возвращаем результат в ожидаемом формате
            if campaigns and 'result' in campaigns and 'Campaigns' in campaigns['result']:
                return campaigns['result']['Campaigns']
            else:
                return []
            
        except YandexDirectApiError as e:
            logger.error(f"Yandex Direct API error: {e}")
            return None
        except Exception as e:
            logger.exception(f"Error getting campaigns: {e}")
            return None
    
    def get_campaign_details(self, campaign_ids=None):
        """
        Получить подробную информацию о кампаниях со статистикой
        
        Args:
            campaign_ids: Список ID кампаний (если None, получаем все кампании)
            
        Returns:
            list: Список деталей о кампаниях со статистикой
        """
        # Получаем кампании сначала
        campaigns_response = self.get_campaigns(include_archived=True)
        if not campaigns_response:
            return []
            
        campaigns = campaigns_response.get('Campaigns', [])
        
        # Фильтруем по ID, если указаны
        if campaign_ids:
            campaigns = [c for c in campaigns if str(c.get('Id')) in [str(cid) for cid in campaign_ids]]
            
        # Получаем статистику за сегодня, если доступна
        today = datetime.now().strftime('%Y-%m-%d')
        stats_df = self._get_stats_report(
            report_type='CAMPAIGN_PERFORMANCE_REPORT',
            date_range_type='TODAY',
            campaign_ids=[c.get('Id') for c in campaigns] if campaigns else None
        )
        
        # Создаем подробные объекты кампаний
        result = []
        for campaign in campaigns:
            campaign_id = str(campaign.get('Id'))
            
            # Находим статистику по кампании за сегодня
            campaign_stats = {}
            if not stats_df.empty and 'CampaignId' in stats_df.columns:
                campaign_row = stats_df[stats_df['CampaignId'] == campaign_id]
                if not campaign_row.empty:
                    for col in stats_df.columns:
                        campaign_stats[col] = campaign_row.iloc[0][col]
            
            # Формируем детальный объект кампании
            campaign_detail = {
                'Id': campaign_id,
                'Name': campaign.get('Name', ''),
                'Status': campaign.get('Status', {}).get('value', '') if isinstance(campaign.get('Status'), dict) else campaign.get('Status', ''),
                'State': campaign.get('State', {}).get('value', '') if isinstance(campaign.get('State'), dict) else campaign.get('State', ''),
                'Type': campaign.get('Type', {}).get('value', '') if isinstance(campaign.get('Type'), dict) else campaign.get('Type', ''),
                'DailyBudget': campaign.get('DailyBudget', {}).get('Amount', 0) if campaign.get('DailyBudget') else 0,
                'Impressions': campaign_stats.get('Impressions', 0),
                'Clicks': campaign_stats.get('Clicks', 0),
                'Cost': campaign_stats.get('Cost', 0),
                'LastUpdated': datetime.now().isoformat()
            }
            
            result.append(campaign_detail)
            
        return result
    
    def _get_stats_report(self, report_type, date_range_type='LAST_7_DAYS', date_from=None, date_to=None, campaign_ids=None, field_names=None):
        """
        Получает отчет по статистике через tapi_yandex_direct
        
        Args:
            report_type: Тип отчета (CAMPAIGN_PERFORMANCE_REPORT и т.д.)
            date_range_type: Тип диапазона дат (TODAY, YESTERDAY, LAST_7_DAYS и т.д.)
            date_from: Дата начала в формате YYYY-MM-DD (если указан CUSTOM_DATE)
            date_to: Дата окончания в формате YYYY-MM-DD (если указан CUSTOM_DATE)
            campaign_ids: Список ID кампаний для фильтрации
            field_names: Список полей для отчета
            
        Returns:
            pandas.DataFrame: DataFrame с данными отчета
        """
        if not self._init_api_client():
            return pd.DataFrame()
        
        if not field_names:
            field_names = [
                'CampaignId', 'CampaignName', 'Impressions', 'Clicks', 'Ctr', 
                'Cost', 'AvgCpc', 'Conversions', 'ConversionRate', 'CostPerConversion'
            ]
            
        # Для tapi_yandex_direct версии 2 используется другой формат запроса
        try:
            # Настраиваем параметры отчета
            report_options = {
                'report_type': report_type,
                'fields': field_names,
                'period': date_range_type
            }
            
            # Если указан CUSTOM_DATE, добавляем даты
            if date_range_type == 'CUSTOM_DATE':
                if date_from and date_to:
                    report_options['date_from'] = date_from
                    report_options['date_to'] = date_to
                else:
                    logger.error("For CUSTOM_DATE range both date_from and date_to must be specified")
                    return pd.DataFrame()
                    
            # Добавляем фильтр по кампаниям, если указан
            if campaign_ids:
                report_options['filter'] = {'CampaignId': campaign_ids}
                
            # В библиотеке tapi_yandex_direct отчеты получаются по-другому
            # Нам нужно использовать метод reports().get() и правильно форматировать запрос
            from tapi_yandex_direct.exceptions import YandexDirectApiError
            
            # Форматируем запрос в формате JSON/dict, как ожидает API
            report_params = {
                'ReportDefinition': {
                    'ReportName': f'Report {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                    'ReportType': report_type,
                    'DateRangeType': date_range_type,
                    'Format': 'TSV',
                    'FieldNames': field_names,
                }
            }
            
            # Добавляем SelectionCriteria если есть фильтры
            if campaign_ids:
                report_params['ReportDefinition']['SelectionCriteria'] = {
                    'CampaignIds': campaign_ids
                }
                
            # Если указан CUSTOM_DATE, добавляем даты
            if date_range_type == 'CUSTOM_DATE':
                if date_from and date_to:
                    report_params['ReportDefinition']['DateFrom'] = date_from
                    report_params['ReportDefinition']['DateTo'] = date_to
                    
            # Обходим ошибки с нестандартными методами API
            # Используем прямой доступ к API через requests, так как библиотека может не поддерживать текущий интерфейс
            import requests
            
            # Подготавливаем заголовки и данные запроса
            headers = {
                "Authorization": f"Bearer {self.token.access_token}",
                "Accept-Language": "ru",
                "Content-Type": "application/json; charset=utf-8",
                "Client-Login": self.token.client_login if hasattr(self.token, 'client_login') else None
            }
            
            # Формируем запрос к API статистики
            stats_url = "https://api.direct.yandex.com/json/v5/reports"
            
            # Получаем данные через прямой HTTP запрос
            try:
                response = requests.post(stats_url, headers=headers, json=report_params, timeout=60)
                
                if response.status_code == 200:
                    # Успешно получили данные, преобразуем в DataFrame
                    import io
                    # Создаем DataFrame из TSV данных
                    df = pd.read_csv(io.StringIO(response.text), sep='\t', skiprows=1)
                    report_result = df
                else:
                    logger.error(f"Error getting report: {response.status_code} - {response.text}")
                    return pd.DataFrame()
            except Exception as e:
                logger.exception(f"Exception during direct API call: {e}")
                return pd.DataFrame()
                
            # Результат уже в виде DataFrame
            report_result = df
            
            # Проверяем результат
            if not report_result or not isinstance(report_result, pd.DataFrame) or report_result.empty:
                logger.warning("Empty report received from Yandex Direct API")
                return pd.DataFrame()
                
            # В tapi_yandex_direct v2 отчет сразу возвращается как DataFrame
            df = report_result
            
            # Форматируем данные если DataFrame не пустой
            if not df.empty:
                # Преобразуем числовые поля
                for col in ['Impressions', 'Clicks']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # В версии 2 библиотеки Cost может возвращаться уже в правильном формате
                # Проверяем, нужно ли делить на 1,000,000
                if 'Cost' in df.columns:
                    # Преобразуем в числовой формат
                    df['Cost'] = pd.to_numeric(df['Cost'], errors='coerce')
                    # Проверим первое значение, если оно очень большое, значит нужно делить
                    if not df.empty and df['Cost'].iloc[0] > 10000:
                        df['Cost'] = df['Cost'] / 1000000
                
                # Для CTR тоже проверяем формат
                if 'Ctr' in df.columns:
                    df['Ctr'] = pd.to_numeric(df['Ctr'], errors='coerce')
                    # Если CTR меньше 1, значит это доля, нужно умножить на 100 для процентов
                    if not df.empty and df['Ctr'].iloc[0] < 1:
                        df['Ctr'] = df['Ctr'] * 100
                    
            return df
            
        except YandexDirectApiError as e:
            logger.error(f"Yandex Direct API error: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.exception(f"Error getting stats report: {e}")
            return pd.DataFrame()
    
    def get_campaign_stats(self, campaign_ids=None, date_from=None, date_to=None):
        """
        Получить статистику по кампаниям
        
        Args:
            campaign_ids: Список ID кампаний (опционально)
            date_from: Дата начала (YYYY-MM-DD)
            date_to: Дата окончания (YYYY-MM-DD)
            
        Returns:
            dict: Статистика по кампаниям или None при ошибке
        """
        # Если даты указаны, используем CUSTOM_DATE
        if date_from and date_to:
            df = self._get_stats_report(
                report_type='CAMPAIGN_PERFORMANCE_REPORT',
                date_range_type='CUSTOM_DATE',
                date_from=date_from,
                date_to=date_to,
                campaign_ids=campaign_ids
            )
        else:
            # Иначе используем последние 7 дней по умолчанию
            df = self._get_stats_report(
                report_type='CAMPAIGN_PERFORMANCE_REPORT',
                date_range_type='LAST_7_DAYS',
                campaign_ids=campaign_ids
            )
        
        if df.empty:
            return None
            
        # Преобразуем DataFrame в структуру, совместимую с предыдущей версией API
        try:
            rows = []
            for _, row in df.iterrows():
                row_dict = {}
                for col in df.columns:
                    row_dict[col] = row[col]
                rows.append(row_dict)
                
            return {
                'Rows': rows,
                'data': rows  # для совместимости со старым кодом
            }
        except Exception as e:
            logger.exception(f"Error processing campaign stats: {e}")
            return None
    
    def get_campaign_stats_dataframe(self, campaign_ids=None, date_from=None, date_to=None, date_range=None):
        """
        Получить статистику по кампаниям в виде pandas DataFrame
        
        Args:
            campaign_ids: ID кампании или список ID кампаний
            date_from: Дата начала в формате YYYY-MM-DD
            date_to: Дата окончания в формате YYYY-MM-DD
            date_range: Предопределенный период (TODAY, YESTERDAY, LAST_7_DAYS и т.д.)
            
        Returns:
            pandas.DataFrame: Статистика по кампаниям
        """
        # Если указан date_range, используем его
        if date_range:
            return self._get_stats_report(
                report_type='CAMPAIGN_PERFORMANCE_REPORT',
                date_range_type=date_range,
                campaign_ids=campaign_ids
            )
        # Если даты указаны, используем CUSTOM_DATE
        elif date_from and date_to:
            return self._get_stats_report(
                report_type='CAMPAIGN_PERFORMANCE_REPORT',
                date_range_type='CUSTOM_DATE',
                date_from=date_from,
                date_to=date_to,
                campaign_ids=campaign_ids
            )
        else:
            # Иначе используем последние 7 дней по умолчанию
            return self._get_stats_report(
                report_type='CAMPAIGN_PERFORMANCE_REPORT',
                date_range_type='LAST_7_DAYS',
                campaign_ids=campaign_ids
            )
            
    def get_top_active_campaigns(self, limit=10, days=7):
        """
        Получить ТОП-N активных кампаний с наибольшими расходами за последние X дней
        
        Args:
            limit: Количество кампаний для вывода (по умолчанию 10)
            days: Количество дней для анализа (по умолчанию 7)
            
        Returns:
            list: Список словарей с данными по кампаниям
        """
        # Получаем все кампании
        all_campaigns = self.get_campaigns(include_archived=False)
        if not all_campaigns:
            return []
            
        # Определяем период для статистики
        date_range = 'LAST_7_DAYS'
        if days != 7:
            if days == 1:
                date_range = 'TODAY'
            elif days == 30:
                date_range = 'LAST_30_DAYS'
            elif days == 90:
                date_range = 'LAST_90_DAYS'
        
        # Получаем статистику за указанный период
        stats_df = self.get_campaign_stats_dataframe(date_range=date_range)
        
        # Если статистика пустая, возвращаем кампании без статистики
        if stats_df.empty:
            # Возвращаем первые N кампаний
            result = []
            for i, campaign in enumerate(all_campaigns):
                if i >= limit:
                    break
                result.append({
                    'id': campaign.get('Id', '0'),
                    'name': campaign.get('Name', 'Неизвестная кампания'),
                    'state': campaign.get('State', 'UNKNOWN'),
                    'cost': 0.0,
                    'clicks': 0,
                    'impressions': 0,
                    'ctr': 0.0
                })
            return result
            
        # Группируем статистику по кампаниям и считаем суммарные показатели
        try:
            # Формируем результат
            result = []
            
            # Создаем словарь кампаний для быстрого доступа
            campaign_dict = {}
            for campaign in all_campaigns:
                campaign_id = campaign.get('Id')
                if campaign_id:
                    campaign_dict[campaign_id] = campaign
            
            # Обрабатываем данные статистики по кампаниям
            campaign_stats = {}
            
            # Определяем имена колонок
            campaign_id_col = next((col for col in stats_df.columns if 'campaign' in col.lower() and 'id' in col.lower()), None)
            if not campaign_id_col:
                logger.warning("CampaignId column not found in stats dataframe")
                return []
                
            # Агрегируем данные по кампаниям
            for _, row in stats_df.iterrows():
                try:
                    campaign_id = str(row[campaign_id_col])
                    
                    if campaign_id not in campaign_stats:
                        campaign_stats[campaign_id] = {
                            'cost': 0.0,
                            'clicks': 0,
                            'impressions': 0
                        }
                    
                    # Добавляем показатели
                    if 'Cost' in row:
                        campaign_stats[campaign_id]['cost'] += float(row['Cost'])
                    if 'Clicks' in row:
                        campaign_stats[campaign_id]['clicks'] += int(row['Clicks'])
                    if 'Impressions' in row:
                        campaign_stats[campaign_id]['impressions'] += int(row['Impressions'])
                except Exception as e:
                    logger.error(f"Error processing campaign stats row: {e}")
                    continue
            
            # Формируем результат и сортируем по расходам
            for campaign_id, stats in campaign_stats.items():
                campaign_data = campaign_dict.get(campaign_id)
                if not campaign_data:
                    continue
                
                # Вычисляем CTR
                ctr = 0.0
                if stats['impressions'] > 0 and stats['clicks'] > 0:
                    ctr = (stats['clicks'] / stats['impressions']) * 100
                
                # Формируем запись
                campaign_info = {
                    'id': campaign_id,
                    'name': campaign_data.get('Name', f'Кампания {campaign_id}'),
                    'state': campaign_data.get('State', 'UNKNOWN'),
                    'cost': stats['cost'],
                    'clicks': stats['clicks'],
                    'impressions': stats['impressions'],
                    'ctr': ctr
                }
                
                result.append(campaign_info)
            
            # Сортируем по расходам и ограничиваем количество
            result.sort(key=lambda x: x['cost'], reverse=True)
            return result[:limit]
                
        except Exception as e:
            logger.exception(f"Error processing campaign stats: {e}")
            # В случае ошибки возвращаем список кампаний без статистики
            result = []
            for i, campaign in enumerate(all_campaigns):
                if i >= limit:
                    break
                result.append({
                    'id': campaign.get('Id', '0'),
                    'name': campaign.get('Name', 'Неизвестная кампания'),
                    'state': campaign.get('State', 'UNKNOWN'),
                    'cost': 0.0,
                    'clicks': 0,
                    'impressions': 0,
                    'ctr': 0.0
                })
            return result
    
    def _init_api_client(self):
        """Инициализация API клиента tapi_yandex_direct"""
        if not self.token:
            return False
            
        # Если токен истек, пытаемся обновить его
        if self.token.is_expired():
            if not self.ensure_fresh_token():
                return False
        
        # Создаем API клиент с доступом к нужным сервисам
        try:
            self.api_client = YandexDirect(
                access_token=self.token.access_token,
                login=self.token.client_login,
                is_sandbox=False,
                # Использовать язык по умолчанию
                language='ru'
            )
            return True
        except Exception as e:
            logger.exception(f"Error initializing YandexDirect API client: {e}")
            return False
    
    def get_auth_url(self):
        """Generate URL for user authorization"""
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'force_confirm': 'yes',
            'scope': 'direct'
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"
    
    def get_token(self, code):
        """
        Exchange authorization code for access token
        
        Args:
            code: The authorization code from the callback
            
        Returns:
            dict: Token response with access_token, refresh_token, expires_in, etc.
        """
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': self.redirect_uri
        }
        
        response = requests.post(self.TOKEN_URL, data=data)
        
        if response.status_code != 200:
            logger.error(f"Error getting token: {response.text}")
            return None
        
        return response.json()
    
    def refresh_token(self, refresh_token):
        """
        Refresh an expired access token
        
        Args:
            refresh_token: The refresh token to use
            
        Returns:
            dict: New token response
        """
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        response = requests.post(self.TOKEN_URL, data=data)
        
        if response.status_code != 200:
            logger.error(f"Error refreshing token: {response.text}")
            return None
        
        return response.json()
    
    def ensure_fresh_token(self):
        """
        Check if token is expired and refresh if needed
        
        Returns:
            bool: True if token is valid, False otherwise
        """
        if not self.token:
            logger.error("No token available")
            return False
        
        # Check if token is expired
        if self.token.is_expired():
            logger.info(f"Token for {self.token.client_login} is expired, refreshing...")
            
            # Refresh the token
            token_data = self.refresh_token(self.token.refresh_token)
            if not token_data:
                return False
            
            # Update token in database
            self.token.access_token = token_data['access_token']
            self.token.refresh_token = token_data.get('refresh_token', self.token.refresh_token)
            self.token.expires_at = datetime.utcnow() + timedelta(seconds=token_data['expires_in'])
            self.token.updated_at = datetime.utcnow()
            
            db.session.commit()
            logger.info(f"Token refreshed successfully for {self.token.client_login}")
        
        return True
    
    def get_campaigns(self, include_archived=False):
        """
        Get the list of campaigns for the user
        
        Args:
            include_archived: Whether to include archived campaigns
            
        Returns:
            dict: API response with campaigns data
        """
        if not self._init_api_client():
            return None
            
        try:
            # Подготовка фильтра для кампаний
            selection_criteria = {}
            if not include_archived:
                selection_criteria = {
                    'States': ['ON', 'OFF', 'SUSPENDED', 'ENDED']  # Исключаем ARCHIVED
                }
            
            # Указываем поля, которые нужно получить
            field_names = [
                'Id', 'Name', 'Status', 'State', 'Type', 
                'DailyBudget', 'Statistics'
            ]
            
            # Используем прямой HTTP запрос вместо библиотеки tapi_yandex_direct
            import requests
            import json
            
            # Подготавливаем заголовки запроса
            headers = {
                "Authorization": f"Bearer {self.token.access_token}",
                "Accept-Language": "ru",
                "Content-Type": "application/json; charset=utf-8"
            }
            
            # Добавляем client_login если доступен
            if hasattr(self.token, 'client_login') and self.token.client_login:
                headers["Client-Login"] = self.token.client_login
                
            # Формируем данные запроса
            data = {
                "method": "get",
                "params": {
                    "SelectionCriteria": {} if include_archived else {"States": ["ON", "OFF", "SUSPENDED"]},
                    "FieldNames": ["Id", "Name", "Status", "State", "Type", "DailyBudget", "Statistics"]
                }
            }
            
            # URL API
            url = "https://api.direct.yandex.com/json/v5/campaigns"
            
            # Выполняем запрос
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'Campaigns': result.get('result', {}).get('Campaigns', [])
                }
            else:
                logger.error(f"API error: {response.status_code} - {response.text}")
                return {'Campaigns': []}
            
            
        except YandexDirectApiError as e:
            logger.error(f"Yandex Direct API error: {e}")
            return None
        except Exception as e:
            logger.exception(f"Error getting campaigns: {e}")
            return None
        
    def get_campaign_details(self, campaign_ids=None):
        """
        Get detailed information about specific campaigns including statistics
        
        Args:
            campaign_ids: List of campaign IDs (optional, if None gets all campaigns)
            
        Returns:
            list: List of campaign details with statistics
        """
        # Get campaigns first
        campaigns_response = self.get_campaigns(include_archived=True)
        if not campaigns_response:
            return []
            
        campaigns = campaigns_response.get('Campaigns', [])
        
        # Filter by IDs if specified
        if campaign_ids:
            campaigns = [c for c in campaigns if str(c.get('Id')) in [str(cid) for cid in campaign_ids]]
            
        # Get statistics for today if available
        today = datetime.now().strftime('%Y-%m-%d')
        stats_df = self._get_stats_report(
            report_type='CAMPAIGN_PERFORMANCE_REPORT',
            date_range_type='TODAY',
            campaign_ids=[c.get('Id') for c in campaigns] if campaigns else None
        )
        
        # Create detailed campaign objects
        result = []
        for campaign in campaigns:
            campaign_id = str(campaign.get('Id'))
            
            # Находим статистику по кампании за сегодня
            campaign_stats = {}
            if not stats_df.empty and 'CampaignId' in stats_df.columns:
                campaign_row = stats_df[stats_df['CampaignId'] == campaign_id]
                if not campaign_row.empty:
                    for col in stats_df.columns:
                        campaign_stats[col] = campaign_row.iloc[0][col]
            
            # Формируем детальный объект кампании
            campaign_detail = {
                'Id': campaign_id,
                'Name': campaign.get('Name', ''),
                'Status': campaign.get('Status', {}).get('value', '') if isinstance(campaign.get('Status'), dict) else campaign.get('Status', ''),
                'State': campaign.get('State', {}).get('value', '') if isinstance(campaign.get('State'), dict) else campaign.get('State', ''),
                'Type': campaign.get('Type', {}).get('value', '') if isinstance(campaign.get('Type'), dict) else campaign.get('Type', ''),
                'DailyBudget': campaign.get('DailyBudget', {}).get('Amount', 0) if campaign.get('DailyBudget') else 0,
                'Impressions': campaign_stats.get('Impressions', 0),
                'Clicks': campaign_stats.get('Clicks', 0),
                'Cost': campaign_stats.get('Cost', 0),
                'LastUpdated': datetime.now().isoformat()
            }
            
            result.append(campaign_detail)
            
        return result
    
    def _get_stats_report(self, report_type, date_range_type='LAST_7_DAYS', date_from=None, date_to=None, campaign_ids=None, field_names=None):
        """
        Получает отчет по статистике через tapi_yandex_direct
        
        Args:
            report_type: Тип отчета (CAMPAIGN_PERFORMANCE_REPORT и т.д.)
            date_range_type: Тип диапазона дат (TODAY, YESTERDAY, LAST_7_DAYS и т.д.)
            date_from: Дата начала в формате YYYY-MM-DD (если указан CUSTOM_DATE)
            date_to: Дата окончания в формате YYYY-MM-DD (если указан CUSTOM_DATE)
            campaign_ids: Список ID кампаний для фильтрации
            field_names: Список полей для отчета
            
        Returns:
            pandas.DataFrame: DataFrame с данными отчета
        """
        if not self._init_api_client():
            return pd.DataFrame()
        
        if not field_names:
            field_names = [
                'CampaignId', 'CampaignName', 'Impressions', 'Clicks', 'Ctr', 
                'Cost', 'AvgCpc', 'Conversions', 'ConversionRate', 'CostPerConversion'
            ]
            
        # Подготовка параметров для запроса отчета
        body = {
            'SelectionCriteria': {},
            'FieldNames': field_names,
            'ReportName': f'{report_type} {date_range_type} {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            'ReportType': report_type,
            'DateRangeType': date_range_type,
            'Format': 'TSV',
            'IncludeVAT': 'YES',
            'IncludeDiscount': 'YES'
        }
        
        # Если указан CUSTOM_DATE, добавляем даты
        if date_range_type == 'CUSTOM_DATE':
            if date_from and date_to:
                body['SelectionCriteria']['DateFrom'] = date_from
                body['SelectionCriteria']['DateTo'] = date_to
            else:
                logger.error("For CUSTOM_DATE range both date_from and date_to must be specified")
                return pd.DataFrame()
                
        # Добавляем фильтр по кампаниям, если указан
        if campaign_ids:
            body['SelectionCriteria']['CampaignIds'] = campaign_ids
        
        try:
            # Получаем отчет через tapi_yandex_direct
            # Преобразуем body в JSON строку, как ожидает API
            body_json = json.dumps(body)
            report_result = self.api_client.reports().get(body_json)
            
            # Проверяем результат
            if not report_result or not report_result.get('data'):
                logger.warning("Empty report received from Yandex Direct API")
                return pd.DataFrame()
                
            # Преобразуем результат в DataFrame
            df = pd.DataFrame(report_result.get('data', []))
            
            # Форматируем данные если DataFrame не пустой
            if not df.empty:
                # Преобразуем числовые поля
                for col in ['Impressions', 'Clicks']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # Cost в API Яндекс Директа возвращается в миллионах, делим на 1,000,000
                if 'Cost' in df.columns:
                    df['Cost'] = pd.to_numeric(df['Cost'], errors='coerce') / 1000000
                
                # CTR возвращается как десятичная дробь, умножаем на 100 для процентов
                if 'Ctr' in df.columns:
                    df['Ctr'] = pd.to_numeric(df['Ctr'], errors='coerce') * 100
                    
            return df
            
        except YandexDirectApiError as e:
            logger.error(f"Yandex Direct API error: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.exception(f"Error getting stats report: {e}")
            return pd.DataFrame()
    
    def get_campaign_stats(self, campaign_ids=None, date_from=None, date_to=None):
        """
        Get statistics for campaigns
        
        Args:
            campaign_ids: List of campaign IDs (optional)
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)
            
        Returns:
            dict: Campaign statistics or None on error
        """
        # Если даты указаны, используем CUSTOM_DATE
        if date_from and date_to:
            df = self._get_stats_report(
                report_type='CAMPAIGN_PERFORMANCE_REPORT',
                date_range_type='CUSTOM_DATE',
                date_from=date_from,
                date_to=date_to,
                campaign_ids=campaign_ids
            )
        else:
            # Иначе используем последние 7 дней по умолчанию
            df = self._get_stats_report(
                report_type='CAMPAIGN_PERFORMANCE_REPORT',
                date_range_type='LAST_7_DAYS',
                campaign_ids=campaign_ids
            )
        
        if df.empty:
            return None
            
        # Преобразуем DataFrame в структуру, совместимую с предыдущей версией API
        try:
            rows = []
            for _, row in df.iterrows():
                row_dict = {}
                for col in df.columns:
                    row_dict[col] = row[col]
                rows.append(row_dict)
                
            return {
                'Rows': rows,
                'data': rows  # для совместимости со старым кодом
            }
        except Exception as e:
            logger.exception(f"Error processing campaign stats: {e}")
            return None
    
    def get_campaign_stats_dataframe(self, campaign_ids=None, date_from=None, date_to=None):
        """
        Get campaign statistics as a pandas DataFrame
        
        Returns:
            pandas.DataFrame: Campaign statistics
        """
        # Если даты указаны, используем CUSTOM_DATE
        if date_from and date_to:
            return self._get_stats_report(
                report_type='CAMPAIGN_PERFORMANCE_REPORT',
                date_range_type='CUSTOM_DATE',
                date_from=date_from,
                date_to=date_to,
                campaign_ids=campaign_ids
            )
        else:
            # Иначе используем последние 7 дней по умолчанию
            return self._get_stats_report(
                report_type='CAMPAIGN_PERFORMANCE_REPORT',
                date_range_type='LAST_7_DAYS',
                campaign_ids=campaign_ids
            )


def get_user_client(user_id):
    """
    Get a YandexDirectAPI client for a specific user
    
    Args:
        user_id: User ID
        
    Returns:
        YandexDirectAPI: Configured API client or None
    """
    # Находим либо токен по умолчанию, либо первый активный токен
    token = YandexToken.query.filter_by(user_id=user_id, is_default=True).first()
    if not token:
        token = YandexToken.query.filter_by(user_id=user_id, is_active=True).first()
    
    if not token:
        logger.warning(f"No active Yandex token found for user {user_id}")
        return None
    
    return YandexDirectAPI(token)


def store_token_for_user(user_id, token_data, client_login=None):
    """
    Store or update OAuth token for a user
    
    Args:
        user_id: User ID
        token_data: Token response from the API
        client_login: Optional client login (for manual token entry)
        
    Returns:
        YandexToken: The stored token object
    """
    # Check if user already has a token
    existing_token = YandexToken.query.filter_by(user_id=user_id).first()
    
    expires_at = datetime.utcnow() + timedelta(seconds=token_data['expires_in'])
    
    if existing_token:
        # Update existing token
        existing_token.access_token = token_data['access_token']
        existing_token.refresh_token = token_data.get('refresh_token', existing_token.refresh_token)
        existing_token.expires_at = expires_at
        existing_token.updated_at = datetime.utcnow()
        if client_login:
            existing_token.client_login = client_login
        token = existing_token
    else:
        # Create new token
        token = YandexToken(
            user_id=user_id,
            access_token=token_data['access_token'],
            refresh_token=token_data['refresh_token'],
            expires_at=expires_at,
            token_type=token_data.get('token_type', 'Bearer'),
            client_login=client_login,
            is_active=True,
            is_default=True  # Первый токен пользователя делаем активным по умолчанию
        )
        db.session.add(token)
    
    # Commit the changes
    db.session.commit()
    
    # Если логин клиента не указан, пытаемся получить его через API
    if not client_login:
        try:
            # Создаем API клиент с новым токеном
            client = YandexDirectAPI(token)
            if client._init_api_client():
                # Получаем информацию о клиенте
                clients_info = client.api_client.clients().get(
                    FieldNames=['Login']
                )
                
                if clients_info and 'Clients' in clients_info and clients_info['Clients']:
                    token.client_login = clients_info['Clients'][0]['Login']
                    # Используем имя клиента как название аккаунта, если оно не задано
                    if not token.account_name:
                        token.account_name = token.client_login
                    db.session.commit()
        except Exception as e:
            logger.exception(f"Error getting client info: {e}")
    
    return token
