# DirectPulse - Yandex Direct Reports Application

## Overview
DirectPulse is a Flask-based web application designed to automate and streamline the reporting process for Yandex Direct advertising campaigns. The system allows users to connect their Yandex Direct accounts, generate customizable reports, schedule recurring reports, and set up conditional alerts that can be delivered via Telegram.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture
The application follows a typical Model-View-Controller (MVC) architecture using Flask as the web framework:

1. **Backend**: Python 3.11 with Flask for handling HTTP requests, routing, and business logic
2. **Database**: SQLAlchemy ORM with PostgreSQL for data persistence
3. **Frontend**: HTML templates with Bootstrap 5 for responsive UI, and JavaScript for dynamic interactions
4. **Authentication**: Flask-Login for user session management and Yandex OAuth for API integration
5. **Scheduling**: APScheduler for managing recurring reports and condition checks
6. **Notifications**: Telegram Bot API for delivering reports and alerts to users

The application is designed to run as a web service that can be accessed by multiple users, each with their own Yandex Direct accounts, report templates, schedules, and conditions.

## Key Components

### User Management
- User registration, login, and profile management
- Role-based access control (regular users vs. admin users)
- Personal timezone settings for reports

### Yandex Direct Integration
- OAuth2 authentication flow with Yandex Direct API
- Token storage and automatic refresh mechanisms
- Campaign statistics retrieval and processing

### Report Generation
- Customizable templates with selectable metrics and date ranges
- On-demand and scheduled report generation
- Data visualization with charts and tables
- Export capabilities (CSV, PDF)

### Automation
- Scheduled reports using cron expressions
- Conditional alerts based on custom thresholds
- Background job processing for non-blocking operations

### Notifications
- Telegram bot integration for report delivery
- Chat binding for users to receive their reports

### Admin Portal
- User management for administrators
- System-wide statistics and monitoring
- Token and report management capabilities

## Data Flow

1. **Authentication Flow**:
   - User registers/logs in with email and password
   - User connects their Yandex Direct account via OAuth
   - OAuth tokens are securely stored in the database

2. **Report Generation Flow**:
   - User creates a report template specifying metrics and date range
   - System fetches data from Yandex Direct API
   - Data is processed and formatted according to the template
   - Report is stored in the database and presented to the user

3. **Scheduling Flow**:
   - User creates a schedule with a cron expression and template
   - Scheduler creates a job to run at the specified times
   - When triggered, the job generates a report
   - Generated report is stored and notification is sent via Telegram

4. **Conditional Alerts Flow**:
   - User creates a condition with metrics, thresholds, and check interval
   - Scheduler periodically checks if the condition is met
   - When condition is met, a report is generated
   - Alert is sent to the user via Telegram

## External Dependencies

### Required APIs
- **Yandex Direct API**: For accessing advertising campaign data
- **Telegram Bot API**: For sending notifications and reports to users

### Python Packages
- **Flask**: Web framework
- **Flask-SQLAlchemy**: ORM for database operations
- **Flask-Login**: User authentication
- **Gunicorn**: WSGI HTTP server
- **APScheduler**: Background task scheduling
- **Pandas**: Data manipulation and analysis
- **Requests**: HTTP client for API calls
- **Telegram Python Bot**: Bot implementation

### Frontend Libraries
- **Bootstrap 5**: CSS framework for responsive design
- **DataTables**: For interactive table displays
- **Chart.js**: For data visualization
- **FontAwesome**: For icons

## Deployment Strategy

The application is configured to deploy on Replit with the following settings:

1. **Runtime Environment**:
   - Python 3.11
   - Packages managed via the `pyproject.toml`

2. **Database**:
   - PostgreSQL (specified in the Nix configuration)
   - Database URL provided via environment variables

3. **Web Server**:
   - Gunicorn as the WSGI server
   - Binding to 0.0.0.0:5000

4. **Environment Variables Required**:
   - `DATABASE_URL`: PostgreSQL connection string
   - `SESSION_SECRET`: Secret key for session management
   - `YANDEX_CLIENT_ID`: Yandex Direct OAuth application ID
   - `YANDEX_CLIENT_SECRET`: Yandex Direct OAuth secret
   - `YANDEX_REDIRECT_URI`: OAuth callback URL
   - `TELEGRAM_BOT_TOKEN`: Telegram Bot API token
   - `FLASK_ENV`: Environment (development/production)

5. **Deployment Configuration**:
   - Autoscaling enabled
   - Run command: `gunicorn --bind 0.0.0.0:5000 main:app`

### Project Initialization
- Database tables are automatically created at startup
- Admin user should be created manually or through a setup script

## Development Guidelines

1. **Database Models**:
   - All models are defined in `models.py`
   - Use SQLAlchemy relationships for associations

2. **Routes Organization**:
   - Routes are organized in blueprints by feature area
   - Main areas: main, auth, reports, admin

3. **Template Structure**:
   - Base template with common elements
   - Feature-specific template folders
   - Component reuse through inclusion

4. **JavaScript**:
   - Functionality is organized by feature in separate JS files
   - Charts and data visualization with Chart.js
   - Form handling and validation

5. **API Integration**:
   - Yandex Direct API wrapper in `yandex_direct.py`
   - Token refresh and error handling

6. **Security Considerations**:
   - OAuth tokens stored securely
   - User data isolation
   - Role-based access control for admin features