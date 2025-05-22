import logging
import json
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app import app
from models import Schedule, Condition, User, Report
from yandex_direct import get_user_client
from report_generator import generate_report, evaluate_condition
from telegram_bot import send_report_notification, start_bot

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None

def init_scheduler():
    """Initialize the scheduler and register all jobs"""
    global scheduler
    
    # Start the Telegram bot
    start_bot()
    
    # Create a scheduler
    scheduler = BackgroundScheduler(timezone=pytz.UTC)
    
    # Add jobs
    with app.app_context():
        # Schedule timed reports
        schedules = Schedule.query.filter_by(is_active=True).all()
        for schedule in schedules:
            add_scheduled_report(schedule)
        
        # Schedule condition checks
        conditions = Condition.query.filter_by(is_active=True).all()
        for condition in conditions:
            add_condition_check(condition)
    
    # Add a job to refresh all schedules every hour
    scheduler.add_job(
        refresh_schedules,
        'interval',
        hours=1,
        id='refresh_schedules'
    )
    
    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started with all jobs")

def refresh_schedules():
    """Refresh all schedule and condition jobs"""
    logger.info("Refreshing all scheduled jobs")
    global scheduler
    
    with app.app_context():
        # Clear existing jobs
        for job in scheduler.get_jobs():
            if job.id != 'refresh_schedules':
                scheduler.remove_job(job.id)
        
        # Re-add schedule jobs
        schedules = Schedule.query.filter_by(is_active=True).all()
        for schedule in schedules:
            add_scheduled_report(schedule)
        
        # Re-add condition jobs
        conditions = Condition.query.filter_by(is_active=True).all()
        for condition in conditions:
            add_condition_check(condition)
    
    logger.info(f"Scheduler refreshed: {len(scheduler.get_jobs())} jobs active")

def add_scheduled_report(schedule):
    """
    Add a scheduled report job
    
    Args:
        schedule: Schedule model instance
    """
    job_id = f"schedule_{schedule.id}"
    
    try:
        # Parse the cron expression
        cron_parts = schedule.cron_expression.split()
        
        if len(cron_parts) != 5:
            logger.error(f"Invalid cron expression for schedule {schedule.id}: {schedule.cron_expression}")
            return
        
        # Get user's timezone
        timezone = pytz.timezone(schedule.user.timezone) if schedule.user.timezone else pytz.UTC
        
        # Create a cron trigger
        trigger = CronTrigger(
            minute=cron_parts[0],
            hour=cron_parts[1],
            day=cron_parts[2],
            month=cron_parts[3],
            day_of_week=cron_parts[4],
            timezone=timezone
        )
        
        # Add the job
        scheduler.add_job(
            run_scheduled_report,
            trigger,
            args=[schedule.id],
            id=job_id,
            replace_existing=True
        )
        
        logger.info(f"Added scheduled report job {job_id} with cron: {schedule.cron_expression}")
    except Exception as e:
        logger.exception(f"Error adding scheduled report {schedule.id}: {e}")

def add_condition_check(condition):
    """
    Add a condition check job
    
    Args:
        condition: Condition model instance
    """
    job_id = f"condition_{condition.id}"
    
    try:
        # Create interval trigger
        trigger = IntervalTrigger(
            seconds=condition.check_interval,
            timezone=pytz.UTC
        )
        
        # Add the job
        scheduler.add_job(
            check_condition,
            trigger,
            args=[condition.id],
            id=job_id,
            replace_existing=True
        )
        
        logger.info(f"Added condition check job {job_id} with interval: {condition.check_interval}s")
    except Exception as e:
        logger.exception(f"Error adding condition check {condition.id}: {e}")

def run_scheduled_report(schedule_id):
    """
    Run a scheduled report
    
    Args:
        schedule_id: Schedule ID
    """
    logger.info(f"Running scheduled report {schedule_id}")
    
    with app.app_context():
        try:
            # Get the schedule
            schedule = Schedule.query.get(schedule_id)
            
            if not schedule or not schedule.is_active:
                logger.warning(f"Schedule {schedule_id} not found or inactive")
                return
            
            # Get the user's Yandex Direct client
            client = get_user_client(schedule.user_id)
            
            if not client:
                logger.error(f"No Yandex Direct client available for user {schedule.user_id}")
                return
            
            # Generate the report
            report_data, summary = generate_report(client, schedule.template)
            
            if not report_data:
                logger.error(f"Failed to generate report for schedule {schedule_id}")
                return
            
            # Create a report record
            report = Report(
                user_id=schedule.user_id,
                template_id=schedule.template_id,
                schedule_id=schedule.id,
                title=f"{schedule.name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                summary=summary,
                data_json=json.dumps(report_data),
                date_from=report_data.get('date_from'),
                date_to=report_data.get('date_to')
            )
            
            from app import db
            db.session.add(report)
            db.session.commit()
            
            # Send Telegram notification
            send_report_notification(schedule.user_id, report.id, summary)
            
            logger.info(f"Scheduled report {schedule_id} completed successfully")
        except Exception as e:
            logger.exception(f"Error running scheduled report {schedule_id}: {e}")

def check_condition(condition_id):
    """
    Check a condition and run report if triggered
    
    Args:
        condition_id: Condition ID
    """
    logger.info(f"Checking condition {condition_id}")
    
    with app.app_context():
        try:
            # Get the condition
            condition = Condition.query.get(condition_id)
            
            if not condition or not condition.is_active:
                logger.warning(f"Condition {condition_id} not found or inactive")
                return
            
            # Get the user's Yandex Direct client
            client = get_user_client(condition.user_id)
            
            if not client:
                logger.error(f"No Yandex Direct client available for user {condition.user_id}")
                return
            
            # Parse the condition
            condition_data = json.loads(condition.condition_json)
            
            # Evaluate condition
            triggered, report_data, summary = evaluate_condition(client, condition.template, condition_data)
            
            if not triggered:
                logger.debug(f"Condition {condition_id} not triggered")
                return
            
            # Create a report record
            report = Report(
                user_id=condition.user_id,
                template_id=condition.template_id,
                condition_id=condition.id,
                title=f"{condition.name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                summary=summary,
                data_json=json.dumps(report_data),
                date_from=report_data.get('date_from'),
                date_to=report_data.get('date_to')
            )
            
            from app import db
            db.session.add(report)
            db.session.commit()
            
            # Send Telegram notification
            send_report_notification(condition.user_id, report.id, summary)
            
            logger.info(f"Condition {condition_id} triggered, report generated")
        except Exception as e:
            logger.exception(f"Error checking condition {condition_id}: {e}")
