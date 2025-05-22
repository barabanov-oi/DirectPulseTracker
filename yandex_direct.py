import os
import json
import logging
import requests
from datetime import datetime, timedelta
from urllib.parse import urlencode
import pandas as pd
from models import YandexToken, User
from app import db

logger = logging.getLogger(__name__)

class YandexDirectAPI:
    """Class to interact with Yandex Direct API"""
    
    # API endpoints
    AUTH_URL = 'https://oauth.yandex.ru/authorize'
    TOKEN_URL = 'https://oauth.yandex.ru/token'
    API_URL = 'https://api.direct.yandex.com/json/v5/'
    
    def __init__(self, token=None):
        """
        Initialize with a token object or client credentials
        
        Args:
            token: YandexToken model instance (optional)
        """
        self.token = token
        self.client_id = os.environ.get('YANDEX_CLIENT_ID')
        self.client_secret = os.environ.get('YANDEX_CLIENT_SECRET')
        self.redirect_uri = os.environ.get('YANDEX_REDIRECT_URI', 'http://localhost:5000/auth/yandex/callback')
    
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
    
    def make_api_request(self, service, method, params=None):
        """
        Make a request to the Yandex Direct API
        
        Args:
            service: API service name (campaigns, keywords, etc.)
            method: API method name (get, add, update, etc.)
            params: Request parameters
            
        Returns:
            dict: API response
        """
        if not self.ensure_fresh_token():
            logger.error("Cannot make API request - invalid token")
            return None
        
        # Prepare the API request
        url = f"{self.API_URL}{service}"
        headers = {
            'Authorization': f"Bearer {self.token.access_token}",
            'Accept-Language': 'en',
            'Content-Type': 'application/json; charset=utf-8',
        }
        
        # Add client login header if available
        if self.token.client_login:
            headers['Client-Login'] = self.token.client_login
        
        # Prepare request data
        data = {
            'method': method,
            'params': params or {}
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 200:
                return response.json().get('result', {})
            else:
                error_data = response.json().get('error', {})
                logger.error(f"API error: {error_data}")
                return None
        except Exception as e:
            logger.exception(f"Error making API request: {e}")
            return None
    
    def get_campaigns(self):
        """Get the list of campaigns for the user"""
        params = {
            'SelectionCriteria': {},
            'FieldNames': ['Id', 'Name', 'Status', 'State', 'Statistics']
        }
        
        return self.make_api_request('campaigns', 'get', params)
    
    def get_campaign_stats(self, campaign_ids=None, date_from=None, date_to=None):
        """
        Get statistics for campaigns
        
        Args:
            campaign_ids: List of campaign IDs (optional)
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)
            
        Returns:
            dict: Campaign statistics
        """
        if not date_from:
            date_from = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        if not date_to:
            date_to = datetime.utcnow().strftime('%Y-%m-%d')
        
        # Prepare selection criteria
        selection_criteria = {}
        if campaign_ids:
            selection_criteria['CampaignIds'] = campaign_ids
        
        params = {
            'SelectionCriteria': selection_criteria,
            'FieldNames': [
                'CampaignId', 'CampaignName', 'Impressions', 'Clicks', 'Ctr', 
                'Cost', 'AvgCpc', 'Conversions', 'ConversionRate', 'CostPerConversion'
            ],
            'ReportType': 'CAMPAIGN_PERFORMANCE_REPORT',
            'DateRangeType': 'CUSTOM_DATE',
            'DateFrom': date_from,
            'DateTo': date_to
        }
        
        response = self.make_api_request('reports', 'get', params)
        return response
    
    def get_campaign_stats_dataframe(self, campaign_ids=None, date_from=None, date_to=None):
        """
        Get campaign statistics as a pandas DataFrame
        
        Returns:
            pandas.DataFrame: Campaign statistics
        """
        stats = self.get_campaign_stats(campaign_ids, date_from, date_to)
        
        if not stats:
            return pd.DataFrame()
        
        # Convert the stats to a DataFrame
        try:
            df = pd.DataFrame(stats['data'])
            
            # Process and format the data
            if not df.empty:
                # Convert cost from microseconds to actual currency
                if 'Cost' in df.columns:
                    df['Cost'] = df['Cost'] / 1000000
                
                # Convert CTR to percentage
                if 'Ctr' in df.columns:
                    df['Ctr'] = df['Ctr'] * 100
                
                # Format column names
                df.columns = [col.replace('Campaign', '') for col in df.columns]
            
            return df
        except Exception as e:
            logger.exception(f"Error processing campaign stats: {e}")
            return pd.DataFrame()


def get_user_client(user_id):
    """
    Get a YandexDirectAPI client for a specific user
    
    Args:
        user_id: User ID
        
    Returns:
        YandexDirectAPI: Configured API client or None
    """
    token = YandexToken.query.filter_by(user_id=user_id).first()
    
    if not token:
        logger.warning(f"No Yandex token found for user {user_id}")
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
            client_login=client_login
        )
        db.session.add(token)
    
    # Commit the changes
    db.session.commit()
    
    # Get client login if available
    client = YandexDirectAPI(token)
    user_info = client.make_api_request('clients', 'get', {
        'FieldNames': ['Login']
    })
    
    if user_info and 'Clients' in user_info and user_info['Clients']:
        token.client_login = user_info['Clients'][0]['Login']
        db.session.commit()
    
    return token
