import json
import logging
import pandas as pd
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, Response
from flask_login import login_required, current_user
from datetime import datetime

from app import app, db
from models import ReportTemplate, Schedule, Condition, Report
from yandex_direct import get_user_client
from report_generator import generate_report, get_date_range

# Set up logging
logger = logging.getLogger(__name__)

# Create Blueprint
reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

@reports_bp.route('/')
@login_required
def reports_list():
    """List all reports for the current user"""
    # Get all reports for the current user
    reports = Report.query.filter_by(user_id=current_user.id)\
        .order_by(Report.created_at.desc())\
        .all()
    
    return render_template('reports/list.html', reports=reports)

@reports_bp.route('/view/<int:report_id>')
@login_required
def view_report(report_id):
    """View a specific report"""
    # Get the report
    report = Report.query.get_or_404(report_id)
    
    # Check if the report belongs to the current user
    if report.user_id != current_user.id and not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('reports.reports_list'))
    
    # Parse the report data
    report_data = json.loads(report.data_json)
    
    return render_template('report.html', report=report, report_data=report_data)

@reports_bp.route('/templates', methods=['GET'])
@login_required
def templates_list():
    """List all report templates for the current user"""
    # Get all templates for the current user
    templates = ReportTemplate.query.filter_by(user_id=current_user.id)\
        .order_by(ReportTemplate.name)\
        .all()
    
    return render_template('reports/templates.html', templates=templates)

@reports_bp.route('/templates/new', methods=['GET', 'POST'])
@login_required
def create_template():
    """Create a new report template"""
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        description = request.form.get('description', '')
        date_range = request.form.get('date_range', 'LAST_7_DAYS')
        
        # Get selected metrics
        metrics = []
        for metric in ['Impressions', 'Clicks', 'Cost', 'Ctr', 'Conversions', 'ConversionRate', 'CostPerConversion']:
            if metric in request.form:
                metrics.append(metric)
        
        if not name or not metrics:
            flash('Name and at least one metric are required', 'danger')
            return redirect(url_for('reports.create_template'))
        
        # Create new template
        template = ReportTemplate(
            user_id=current_user.id,
            name=name,
            description=description,
            metrics=json.dumps(metrics),
            date_range=date_range
        )
        
        db.session.add(template)
        db.session.commit()
        
        flash('Report template created successfully', 'success')
        return redirect(url_for('reports.templates_list'))
    
    return render_template('reports/template_form.html')

@reports_bp.route('/templates/edit/<int:template_id>', methods=['GET', 'POST'])
@login_required
def edit_template(template_id):
    """Edit an existing report template"""
    # Get the template
    template = ReportTemplate.query.get_or_404(template_id)
    
    # Check if the template belongs to the current user
    if template.user_id != current_user.id and not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('reports.templates_list'))
    
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        description = request.form.get('description', '')
        date_range = request.form.get('date_range', 'LAST_7_DAYS')
        
        # Get selected metrics
        metrics = []
        for metric in ['Impressions', 'Clicks', 'Cost', 'Ctr', 'Conversions', 'ConversionRate', 'CostPerConversion']:
            if metric in request.form:
                metrics.append(metric)
        
        if not name or not metrics:
            flash('Name and at least one metric are required', 'danger')
            return redirect(url_for('reports.edit_template', template_id=template_id))
        
        # Update template
        template.name = name
        template.description = description
        template.metrics = json.dumps(metrics)
        template.date_range = date_range
        
        db.session.commit()
        
        flash('Report template updated successfully', 'success')
        return redirect(url_for('reports.templates_list'))
    
    # Parse template metrics for form
    template_metrics = json.loads(template.metrics)
    
    return render_template('reports/template_form.html', template=template, template_metrics=template_metrics)

@reports_bp.route('/templates/delete/<int:template_id>', methods=['POST'])
@login_required
def delete_template(template_id):
    """Delete a report template"""
    # Get the template
    template = ReportTemplate.query.get_or_404(template_id)
    
    # Check if the template belongs to the current user
    if template.user_id != current_user.id and not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('reports.templates_list'))
    
    # Delete the template
    db.session.delete(template)
    db.session.commit()
    
    flash('Report template deleted successfully', 'success')
    return redirect(url_for('reports.templates_list'))

@reports_bp.route('/generate', methods=['GET', 'POST'])
@login_required
def generate_report_view():
    """Generate a report on demand"""
    # Get user's templates
    templates = ReportTemplate.query.filter_by(user_id=current_user.id)\
        .order_by(ReportTemplate.name)\
        .all()
    
    if not templates:
        flash('Create a report template first', 'warning')
        return redirect(url_for('reports.create_template'))
    
    if request.method == 'POST':
        # Get form data
        template_id = request.form.get('template_id')
        
        if not template_id:
            flash('Template selection is required', 'danger')
            return redirect(url_for('reports.generate_report_view'))
        
        # Get the template
        template = ReportTemplate.query.get_or_404(template_id)
        
        # Check if the template belongs to the current user
        if template.user_id != current_user.id and not current_user.is_admin:
            flash('Access denied', 'danger')
            return redirect(url_for('reports.generate_report_view'))
        
        # Get user's Yandex Direct client
        yandex_client = get_user_client(current_user.id)
        
        if not yandex_client:
            flash('Connect your Yandex Direct account first', 'warning')
            return redirect(url_for('auth.yandex_authorize'))
        
        # Generate the report
        report_data, summary = generate_report(yandex_client, template)
        
        if not report_data:
            flash('Failed to generate report', 'danger')
            return redirect(url_for('reports.generate_report_view'))
        
        # Create report record
        date_from = datetime.strptime(report_data['date_from'], '%Y-%m-%d').date()
        date_to = datetime.strptime(report_data['date_to'], '%Y-%m-%d').date()
        
        report = Report(
            user_id=current_user.id,
            template_id=template.id,
            title=f"{template.name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            summary=summary,
            data_json=json.dumps(report_data),
            date_from=date_from,
            date_to=date_to
        )
        
        db.session.add(report)
        db.session.commit()
        
        flash('Report generated successfully', 'success')
        return redirect(url_for('reports.view_report', report_id=report.id))
    
    return render_template('reports/generate.html', templates=templates)

@reports_bp.route('/schedules', methods=['GET'])
@login_required
def schedules_list():
    """List all report schedules for the current user"""
    # Get all schedules for the current user
    schedules = Schedule.query.filter_by(user_id=current_user.id)\
        .order_by(Schedule.name)\
        .all()
    
    return render_template('reports/schedules.html', schedules=schedules)

@reports_bp.route('/schedules/new', methods=['GET', 'POST'])
@login_required
def create_schedule():
    """Create a new report schedule"""
    # Get user's templates
    templates = ReportTemplate.query.filter_by(user_id=current_user.id)\
        .order_by(ReportTemplate.name)\
        .all()
    
    if not templates:
        flash('Create a report template first', 'warning')
        return redirect(url_for('reports.create_template'))
    
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        template_id = request.form.get('template_id')
        cron_expression = request.form.get('cron_expression')
        is_active = 'is_active' in request.form
        
        if not name or not template_id or not cron_expression:
            flash('All fields are required', 'danger')
            return redirect(url_for('reports.create_schedule'))
        
        # Create new schedule
        schedule = Schedule(
            user_id=current_user.id,
            template_id=template_id,
            name=name,
            cron_expression=cron_expression,
            is_active=is_active
        )
        
        db.session.add(schedule)
        db.session.commit()
        
        # Restart the scheduler to pick up the new schedule
        from scheduler import refresh_schedules
        refresh_schedules()
        
        flash('Report schedule created successfully', 'success')
        return redirect(url_for('reports.schedules_list'))
    
    return render_template('reports/schedule_form.html', templates=templates)

@reports_bp.route('/schedules/edit/<int:schedule_id>', methods=['GET', 'POST'])
@login_required
def edit_schedule(schedule_id):
    """Edit an existing report schedule"""
    # Get the schedule
    schedule = Schedule.query.get_or_404(schedule_id)
    
    # Check if the schedule belongs to the current user
    if schedule.user_id != current_user.id and not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('reports.schedules_list'))
    
    # Get user's templates
    templates = ReportTemplate.query.filter_by(user_id=current_user.id)\
        .order_by(ReportTemplate.name)\
        .all()
    
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        template_id = request.form.get('template_id')
        cron_expression = request.form.get('cron_expression')
        is_active = 'is_active' in request.form
        
        if not name or not template_id or not cron_expression:
            flash('All fields are required', 'danger')
            return redirect(url_for('reports.edit_schedule', schedule_id=schedule_id))
        
        # Update schedule
        schedule.name = name
        schedule.template_id = template_id
        schedule.cron_expression = cron_expression
        schedule.is_active = is_active
        
        db.session.commit()
        
        # Restart the scheduler to pick up the updated schedule
        from scheduler import refresh_schedules
        refresh_schedules()
        
        flash('Report schedule updated successfully', 'success')
        return redirect(url_for('reports.schedules_list'))
    
    return render_template('reports/schedule_form.html', schedule=schedule, templates=templates)

@reports_bp.route('/schedules/delete/<int:schedule_id>', methods=['POST'])
@login_required
def delete_schedule(schedule_id):
    """Delete a report schedule"""
    # Get the schedule
    schedule = Schedule.query.get_or_404(schedule_id)
    
    # Check if the schedule belongs to the current user
    if schedule.user_id != current_user.id and not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('reports.schedules_list'))
    
    # Delete the schedule
    db.session.delete(schedule)
    db.session.commit()
    
    # Restart the scheduler to remove the deleted schedule
    from scheduler import refresh_schedules
    refresh_schedules()
    
    flash('Report schedule deleted successfully', 'success')
    return redirect(url_for('reports.schedules_list'))

@reports_bp.route('/conditions', methods=['GET'])
@login_required
def conditions_list():
    """List all report conditions for the current user"""
    # Get all conditions for the current user
    conditions = Condition.query.filter_by(user_id=current_user.id)\
        .order_by(Condition.name)\
        .all()
    
    return render_template('reports/conditions.html', conditions=conditions)

@reports_bp.route('/conditions/new', methods=['GET', 'POST'])
@login_required
def create_condition():
    """Create a new report condition"""
    # Get user's templates
    templates = ReportTemplate.query.filter_by(user_id=current_user.id)\
        .order_by(ReportTemplate.name)\
        .all()
    
    if not templates:
        flash('Create a report template first', 'warning')
        return redirect(url_for('reports.create_template'))
    
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        template_id = request.form.get('template_id')
        condition_json = request.form.get('condition_json')
        check_interval = request.form.get('check_interval', 3600)
        is_active = 'is_active' in request.form
        
        if not name or not template_id or not condition_json:
            flash('All fields are required', 'danger')
            return redirect(url_for('reports.create_condition'))
        
        try:
            # Validate JSON
            json.loads(condition_json)
        except json.JSONDecodeError:
            flash('Invalid condition JSON', 'danger')
            return redirect(url_for('reports.create_condition'))
        
        # Create new condition
        condition = Condition(
            user_id=current_user.id,
            template_id=template_id,
            name=name,
            condition_json=condition_json,
            check_interval=int(check_interval),
            is_active=is_active
        )
        
        db.session.add(condition)
        db.session.commit()
        
        # Restart the scheduler to pick up the new condition
        from scheduler import refresh_schedules
        refresh_schedules()
        
        flash('Report condition created successfully', 'success')
        return redirect(url_for('reports.conditions_list'))
    
    return render_template('reports/condition_form.html', templates=templates)

@reports_bp.route('/conditions/edit/<int:condition_id>', methods=['GET', 'POST'])
@login_required
def edit_condition(condition_id):
    """Edit an existing report condition"""
    # Get the condition
    condition = Condition.query.get_or_404(condition_id)
    
    # Check if the condition belongs to the current user
    if condition.user_id != current_user.id and not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('reports.conditions_list'))
    
    # Get user's templates
    templates = ReportTemplate.query.filter_by(user_id=current_user.id)\
        .order_by(ReportTemplate.name)\
        .all()
    
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        template_id = request.form.get('template_id')
        condition_json = request.form.get('condition_json')
        check_interval = request.form.get('check_interval', 3600)
        is_active = 'is_active' in request.form
        
        if not name or not template_id or not condition_json:
            flash('All fields are required', 'danger')
            return redirect(url_for('reports.edit_condition', condition_id=condition_id))
        
        try:
            # Validate JSON
            json.loads(condition_json)
        except json.JSONDecodeError:
            flash('Invalid condition JSON', 'danger')
            return redirect(url_for('reports.edit_condition', condition_id=condition_id))
        
        # Update condition
        condition.name = name
        condition.template_id = template_id
        condition.condition_json = condition_json
        condition.check_interval = int(check_interval)
        condition.is_active = is_active
        
        db.session.commit()
        
        # Restart the scheduler to pick up the updated condition
        from scheduler import refresh_schedules
        refresh_schedules()
        
        flash('Report condition updated successfully', 'success')
        return redirect(url_for('reports.conditions_list'))
    
    return render_template('reports/condition_form.html', condition=condition, templates=templates)

@reports_bp.route('/conditions/delete/<int:condition_id>', methods=['POST'])
@login_required
def delete_condition(condition_id):
    """Delete a report condition"""
    # Get the condition
    condition = Condition.query.get_or_404(condition_id)
    
    # Check if the condition belongs to the current user
    if condition.user_id != current_user.id and not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('reports.conditions_list'))
    
    # Delete the condition
    db.session.delete(condition)
    db.session.commit()
    
    # Restart the scheduler to remove the deleted condition
    from scheduler import refresh_schedules
    refresh_schedules()
    
    flash('Report condition deleted successfully', 'success')
    return redirect(url_for('reports.conditions_list'))

@reports_bp.route('/export/<int:report_id>')
@login_required
def export_report(report_id):
    """Export a report as CSV"""
    # Get the report
    report = Report.query.get_or_404(report_id)
    
    # Check if the report belongs to the current user
    if report.user_id != current_user.id and not current_user.is_admin:
        flash('Access denied', 'danger')
        return redirect(url_for('reports.reports_list'))
    
    # Parse the report data
    report_data = json.loads(report.data_json)
    
    # Create DataFrame from campaigns data
    df = pd.DataFrame(report_data.get('campaigns', []))
    
    if df.empty:
        flash('No data to export', 'warning')
        return redirect(url_for('reports.view_report', report_id=report_id))
    
    # Generate CSV
    csv_data = df.to_csv(index=False)
    
    # Create response
    response = Response(
        csv_data,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={report.title.replace(" ", "_")}.csv',
            'Content-Type': 'text/csv'
        }
    )
    
    return response

# Register Blueprint with app
app.register_blueprint(reports_bp)
