import logging
import sys
from pathlib import Path

# Добавляем текущую директорию в путь для импортов
sys.path.insert(0, str(Path(__file__).parent))

from app import app
# Импортируем из переименованной папки app_routes
from app_routes import main, auth, reports, admin, diagnostics, account_manager, optimization

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Регистрируем blueprints здесь
app.register_blueprint(main.main_bp)
app.register_blueprint(auth.auth_bp)
app.register_blueprint(reports.reports_bp)
app.register_blueprint(admin.admin_bp)
app.register_blueprint(diagnostics.diagnostics_bp, url_prefix='/diagnostics')
app.register_blueprint(account_manager.account_manager)
app.register_blueprint(optimization.optimization_bp)

logger.info("Application initialized and ready")

# Note: Scheduler and Telegram bot are disabled for initial startup
# from scheduler import init_scheduler
# init_scheduler()

if __name__ == "__main__":
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)
