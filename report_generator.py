import json
import logging
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)

def generate_report(yandex_client, template):
    """
    Generate a report based on a template
    
    Args:
        yandex_client: YandexDirectAPI instance
        template: ReportTemplate model instance
        
    Returns:
        tuple: (report_data_dict, summary_text)
    """
    try:
        # Parse template metrics
        metrics = json.loads(template.metrics)
        
        # Determine date range
        date_from, date_to = get_date_range(template.date_range)
        
        # Get the campaign statistics
        logger.info(f"Requesting data from {date_from} to {date_to}")
        try:
            df = yandex_client.get_campaign_stats_dataframe(
                date_from=date_from.strftime('%Y-%m-%d'),
                date_to=date_to.strftime('%Y-%m-%d')
            )
            logger.info(f"Received dataframe with shape: {df.shape}")
            
            if df.empty:
                logger.warning("Received empty dataframe from Yandex Direct API")
                return None, "Нет данных за выбранный период. Проверьте что: \n1. В аккаунте есть активные кампании\n2. Был выбран корректный период\n3. Токен доступа активен"
            
            # Process and aggregate data
            report_data = process_report_data(df, metrics)
        except Exception as e:
            logger.error(f"Error getting campaign stats: {e}")
            return None, f"Ошибка при получении данных: {str(e)}"
        
        # Generate summary text
        summary = generate_summary(df)
        
        # Add date range to report data
        report_data['date_from'] = date_from.strftime('%Y-%m-%d')
        report_data['date_to'] = date_to.strftime('%Y-%m-%d')
        
        return report_data, summary
    except Exception as e:
        logger.exception(f"Error generating report: {e}")
        return None, f"Error generating report: {str(e)}"

def get_date_range(date_range_str):
    """
    Convert date range string to actual dates
    
    Args:
        date_range_str: String like 'TODAY', 'YESTERDAY', 'LAST_7_DAYS', etc.
        
    Returns:
        tuple: (date_from, date_to) as datetime objects
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    if date_range_str == 'TODAY':
        return today, today
    elif date_range_str == 'YESTERDAY':
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    elif date_range_str == 'LAST_7_DAYS':
        return today - timedelta(days=7), today - timedelta(days=1)
    elif date_range_str == 'LAST_30_DAYS':
        return today - timedelta(days=30), today - timedelta(days=1)
    elif date_range_str == 'THIS_WEEK_MON_TODAY':
        days_since_monday = today.weekday()
        return today - timedelta(days=days_since_monday), today
    elif date_range_str == 'THIS_MONTH':
        return today.replace(day=1), today
    elif date_range_str == 'CUSTOM_DATE':
        # For custom dates, we use default last 7 days
        return today - timedelta(days=7), today - timedelta(days=1)
    else:
        # Default to last 7 days
        return today - timedelta(days=7), today - timedelta(days=1)

def process_report_data(df, metrics):
    """
    Process the DataFrame to create the report data
    
    Args:
        df: pandas.DataFrame with campaign data
        metrics: List of metrics to include
        
    Returns:
        dict: Processed report data with aggregations and campaign details
    """
    # Make a copy of the DataFrame to avoid modifying the original
    df_copy = df.copy()
    
    # Replace NaN values with 0
    df_copy.fillna(0, inplace=True)
    
    # Ensure all required columns exist
    required_columns = ['Id', 'Name', 'Impressions', 'Clicks', 'Cost']
    for col in required_columns:
        if col not in df_copy.columns:
            df_copy[col] = 0
    
    # Calculate additional metrics if not present
    if 'Ctr' not in df_copy.columns and 'Clicks' in df_copy.columns and 'Impressions' in df_copy.columns:
        df_copy['Ctr'] = (df_copy['Clicks'] / df_copy['Impressions'] * 100).fillna(0)
    
    if 'ConversionRate' not in df_copy.columns and 'Conversions' in df_copy.columns and 'Clicks' in df_copy.columns:
        df_copy['ConversionRate'] = (df_copy['Conversions'] / df_copy['Clicks'] * 100).fillna(0)
    
    if 'CostPerConversion' not in df_copy.columns and 'Cost' in df_copy.columns and 'Conversions' in df_copy.columns:
        df_copy['CostPerConversion'] = (df_copy['Cost'] / df_copy['Conversions']).fillna(0)
    
    # Calculate totals
    totals = {
        'Id': 'Total',
        'Name': 'All Campaigns',
        'Impressions': df_copy['Impressions'].sum(),
        'Clicks': df_copy['Clicks'].sum(),
        'Cost': df_copy['Cost'].sum(),
    }
    
    # Calculate averages for rate metrics
    if 'Ctr' in df_copy.columns:
        totals['Ctr'] = (totals['Clicks'] / totals['Impressions'] * 100) if totals['Impressions'] > 0 else 0
    
    if 'Conversions' in df_copy.columns:
        totals['Conversions'] = df_copy['Conversions'].sum()
        
        if 'ConversionRate' in df_copy.columns:
            totals['ConversionRate'] = (totals['Conversions'] / totals['Clicks'] * 100) if totals['Clicks'] > 0 else 0
        
        if 'CostPerConversion' in df_copy.columns:
            totals['CostPerConversion'] = (totals['Cost'] / totals['Conversions']) if totals['Conversions'] > 0 else 0
    
    # Find top campaigns by different metrics
    top_by_cost = df_copy.sort_values('Cost', ascending=False).head(5)
    top_by_clicks = df_copy.sort_values('Clicks', ascending=False).head(5)
    top_by_conversions = df_copy.sort_values('Conversions', ascending=False).head(5) if 'Conversions' in df_copy.columns else pd.DataFrame()
    
    # Create the report data structure
    report_data = {
        'campaigns': df_copy.to_dict('records'),
        'totals': totals,
        'top_campaigns': {
            'by_cost': top_by_cost.to_dict('records'),
            'by_clicks': top_by_clicks.to_dict('records'),
            'by_conversions': top_by_conversions.to_dict('records') if not top_by_conversions.empty else []
        }
    }
    
    return report_data

def generate_summary(df):
    """
    Generate a summary text for the report
    
    Args:
        df: pandas.DataFrame with campaign data
        
    Returns:
        str: Summary text
    """
    # Make sure the DataFrame has the necessary columns
    required_columns = ['Impressions', 'Clicks', 'Cost']
    for col in required_columns:
        if col not in df.columns:
            df[col] = 0
    
    # Calculate totals
    total_impressions = df['Impressions'].sum()
    total_clicks = df['Clicks'].sum()
    total_cost = df['Cost'].sum()
    
    # Calculate CTR
    ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
    
    # Calculate conversions and conversion metrics if available
    has_conversions = 'Conversions' in df.columns
    
    if has_conversions:
        total_conversions = df['Conversions'].sum()
        conversion_rate = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
        cost_per_conversion = (total_cost / total_conversions) if total_conversions > 0 else 0
    
    # Build the summary text
    summary = [
        f"📊 *Report Summary*",
        f"",
        f"💰 *Cost*: {total_cost:,.2f} ₽",
        f"👁️ *Impressions*: {total_impressions:,}",
        f"🖱️ *Clicks*: {total_clicks:,}",
        f"📈 *CTR*: {ctr:.2f}%"
    ]
    
    if has_conversions:
        summary.extend([
            f"🎯 *Conversions*: {total_conversions:,}",
            f"💹 *Conversion Rate*: {conversion_rate:.2f}%",
            f"💲 *Cost per Conversion*: {cost_per_conversion:,.2f} ₽"
        ])
    
    # Add top campaigns by cost if available
    if len(df) > 0:
        top_campaign = df.sort_values('Cost', ascending=False).iloc[0]
        summary.extend([
            f"",
            f"🔝 *Top Campaign by Cost*:",
            f"   {top_campaign.get('Name', 'Unknown')}: {top_campaign.get('Cost', 0):,.2f} ₽"
        ])
    
    return "\n".join(summary)

def evaluate_condition(yandex_client, template, condition_data):
    """
    Evaluate a condition to determine if a report should be triggered
    
    Args:
        yandex_client: YandexDirectAPI instance
        template: ReportTemplate model instance
        condition_data: Dictionary containing condition rules
        
    Returns:
        tuple: (triggered, report_data_dict, summary_text)
    """
    try:
        # Generate the report data
        report_data, summary = generate_report(yandex_client, template)
        
        if not report_data:
            return False, None, None
        
        # Check if conditions are met
        triggered = check_condition_rules(report_data, condition_data)
        
        if triggered:
            # Enhance the summary with the triggered condition
            enhanced_summary = summary + "\n\n" + "⚠️ *Alert Triggered*: " + format_condition_message(condition_data)
            return True, report_data, enhanced_summary
        
        return False, None, None
    except Exception as e:
        logger.exception(f"Error evaluating condition: {e}")
        return False, None, None

def check_condition_rules(report_data, condition_data):
    """
    Check if the report data meets the condition rules
    
    Args:
        report_data: Dictionary containing report data
        condition_data: Dictionary containing condition rules
        
    Returns:
        bool: True if conditions are met, False otherwise
    """
    # Get the totals from the report data
    totals = report_data.get('totals', {})
    
    # Check each rule in the condition
    rules = condition_data.get('rules', [])
    rule_results = []
    
    for rule in rules:
        metric = rule.get('metric')
        operator = rule.get('operator')
        value = rule.get('value', 0)
        
        # Skip if metric not found
        if metric not in totals:
            rule_results.append(False)
            continue
        
        metric_value = totals[metric]
        
        # Evaluate the rule based on the operator
        if operator == '>' and metric_value > value:
            rule_results.append(True)
        elif operator == '>=' and metric_value >= value:
            rule_results.append(True)
        elif operator == '<' and metric_value < value:
            rule_results.append(True)
        elif operator == '<=' and metric_value <= value:
            rule_results.append(True)
        elif operator == '==' and metric_value == value:
            rule_results.append(True)
        else:
            rule_results.append(False)
    
    # Combine the rule results based on the logic (AND/OR)
    logic = condition_data.get('logic', 'AND')
    
    if logic == 'AND':
        return all(rule_results)
    else:  # OR
        return any(rule_results)

def format_condition_message(condition_data):
    """
    Format a human-readable message for the triggered condition
    
    Args:
        condition_data: Dictionary containing condition rules
        
    Returns:
        str: Formatted condition message
    """
    rules = condition_data.get('rules', [])
    logic = condition_data.get('logic', 'AND')
    
    rule_messages = []
    
    for rule in rules:
        metric = rule.get('metric', '')
        operator = rule.get('operator', '')
        value = rule.get('value', 0)
        
        # Format the operator for display
        op_display = {
            '>': 'greater than',
            '>=': 'greater than or equal to',
            '<': 'less than',
            '<=': 'less than or equal to',
            '==': 'equal to'
        }.get(operator, operator)
        
        # Format the metric for display
        metric_display = {
            'Cost': 'Cost',
            'Clicks': 'Clicks',
            'Impressions': 'Impressions',
            'Ctr': 'CTR',
            'Conversions': 'Conversions',
            'ConversionRate': 'Conversion Rate',
            'CostPerConversion': 'Cost per Conversion'
        }.get(metric, metric)
        
        # Format the value based on metric type
        if metric in ['Ctr', 'ConversionRate']:
            formatted_value = f"{value}%"
        elif metric in ['Cost', 'CostPerConversion']:
            formatted_value = f"{value} ₽"
        else:
            formatted_value = str(value)
        
        rule_messages.append(f"{metric_display} is {op_display} {formatted_value}")
    
    # Join the rules with AND/OR
    return " " + logic + " ".join(rule_messages)
