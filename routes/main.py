import logging
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app import app
from models import ReportTemplate, Schedule, Condition, Report
from yandex_direct import get_user_client

# Set up logging
logger = logging.getLogger(__name__)

# Create Blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Homepage route"""
    # If user is logged in, redirect to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    return render_template('login.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """User dashboard showing statistics and recent reports"""
    # Get user's Yandex Direct token and client
    yandex_client = get_user_client(current_user.id)
    
    # Check if the user has connected Yandex Direct
    has_yandex_token = yandex_client is not None
    
    # Get user's recent reports
    recent_reports = Report.query.filter_by(user_id=current_user.id)\
        .order_by(Report.created_at.desc())\
        .limit(5)\
        .all()
    
    # Get user's templates
    templates = ReportTemplate.query.filter_by(user_id=current_user.id)\
        .order_by(ReportTemplate.name)\
        .all()
    
    # Get user's schedules
    schedules = Schedule.query.filter_by(user_id=current_user.id)\
        .order_by(Schedule.name)\
        .all()
    
    # Get user's conditions
    conditions = Condition.query.filter_by(user_id=current_user.id)\
        .order_by(Condition.name)\
        .all()
    
    return render_template(
        'dashboard.html',
        has_yandex_token=has_yandex_token,
        recent_reports=recent_reports,
        templates=templates,
        schedules=schedules,
        conditions=conditions
    )

# Register Blueprint with app
app.register_blueprint(main_bp)
