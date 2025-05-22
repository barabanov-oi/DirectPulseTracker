import logging
from app import app
from routes import main
from routes import auth
from routes import reports
from routes import admin
from routes import diagnostics

# Register blueprints with app
app.register_blueprint(main.main_bp)
app.register_blueprint(auth.auth_bp)
app.register_blueprint(reports.reports_bp)
app.register_blueprint(admin.admin_bp)
app.register_blueprint(diagnostics.diagnostics_bp)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Note: We don't need to register blueprints here since they're already
# registered at the end of each route file

logger.info("Application initialized and ready")

# Note: Scheduler and Telegram bot are disabled for initial startup
# from scheduler import init_scheduler
# init_scheduler()

if __name__ == "__main__":
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)
