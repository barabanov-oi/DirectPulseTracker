import os
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
import asyncio
from threading import Thread
from app import app
from models import User, Report
from flask import url_for

# Set up logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Bot token from environment variable
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# Initialize the bot
bot = Bot(token=TELEGRAM_BOT_TOKEN if TELEGRAM_BOT_TOKEN else "placeholder")

# Global application object
application = None

def start_bot():
    """Start the Telegram bot in a separate thread"""
    global application
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set")
        return
    
    try:
        # Create the Application and add handlers
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Register command handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("bind", bind_command))
        
        # Register callback query handler for button clicks
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Start the Bot in a separate thread
        def run_bot():
            asyncio.run(application.run_polling())
        
        thread = Thread(target=run_bot)
        thread.daemon = True
        thread.start()
        
        logger.info("Telegram bot started successfully")
    except Exception as e:
        logger.exception(f"Failed to start Telegram bot: {e}")

def stop_bot():
    """Stop the Telegram bot"""
    global application
    if application:
        # This is now handled through the asyncio event loop
        logger.info("Telegram bot will be stopped on next application shutdown")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    welcome_text = (
        f"👋 Hello, {user.first_name}!\n\n"
        f"I'm DirectPulse bot, your assistant for Yandex Direct advertising reports.\n\n"
        f"To connect this chat to your DirectPulse account, use the /bind command followed by your email address:\n"
        f"Example: /bind your.email@example.com\n\n"
        f"Type /help to see all available commands."
    )
    
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command"""
    help_text = (
        "📋 *DirectPulse Bot Commands:*\n\n"
        "• /start - Start the bot and show the welcome message\n"
        "• /help - Show this help message\n"
        "• /bind youremail@example.com - Connect this chat to your DirectPulse account\n\n"
        "Once connected, you'll automatically receive Yandex Direct report notifications based on your configured schedules and conditions."
    )
    
    await update.message.reply_text(help_text, parse_mode="MARKDOWN")

async def bind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /bind command to link a Telegram chat to a user account"""
    chat_id = str(update.effective_chat.id)
    
    if not context.args:
        await update.message.reply_text(
            "Please provide your email address to bind this chat to your account.\n"
            "Example: /bind your.email@example.com"
        )
        return
    
    email = context.args[0].lower()
    
    # Find the user with the provided email
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        
        if not user:
            await update.message.reply_text(
                "⚠️ No account found with this email address. Please register at our website first."
            )
            return
        
        # Check if this chat is already bound to another user
        existing_user = User.query.filter_by(telegram_chat_id=chat_id).first()
        if existing_user and existing_user.id != user.id:
            await update.message.reply_text(
                "⚠️ This Telegram chat is already linked to another account. "
                "Please contact support if you need to change this."
            )
            return
        
        # Update the user's telegram_chat_id
        user.telegram_chat_id = chat_id
        from app import db
        db.session.commit()
        
        await update.message.reply_text(
            f"✅ Success! This Telegram chat is now linked to your DirectPulse account ({user.username}).\n"
            f"You will receive report notifications here based on your configured schedules and triggers."
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks in messages"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith('report_'):
        report_id = data.split('_')[1]
        with app.app_context():
            # Get the report
            report = Report.query.get(int(report_id))
            if report:
                # Create a URL to view the report
                report_url = url_for('reports.view_report', report_id=report_id, _external=True)
                await query.edit_message_text(
                    text=f"Opening report: {report.title}...\nClick the link below to view the full report.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("View Full Report", url=report_url)]
                    ])
                )
            else:
                await query.edit_message_text(text="Report not found or expired.")

async def send_report_notification_async(user_id, report_id, summary):
    """
    Async function to send a report notification to a user's Telegram chat
    
    Args:
        user_id: User ID
        report_id: Report ID
        summary: Report summary text
    """
    with app.app_context():
        user = User.query.get(user_id)
        report = Report.query.get(report_id)
        
        if not user or not report:
            logger.error(f"User or report not found: user_id={user_id}, report_id={report_id}")
            return
        
        if not user.telegram_chat_id:
            logger.warning(f"User {user.username} does not have a Telegram chat ID")
            return
        
        try:
            # Create a report URL
            report_url = url_for('reports.view_report', report_id=report_id, _external=True)
            
            # Create the message text
            message = (
                f"📊 *New Report: {report.title}*\n\n"
                f"{summary}\n\n"
                f"Period: {report.date_from} to {report.date_to}"
            )
            
            # Add a button to view the full report
            keyboard = [
                [InlineKeyboardButton("View Full Report", url=report_url)],
                [InlineKeyboardButton("Show Details", callback_data=f"report_{report_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send the message
            await bot.send_message(
                chat_id=user.telegram_chat_id,
                text=message,
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
            # Update the report as sent
            report.sent_to_telegram = True
            from app import db
            db.session.commit()
            
            logger.info(f"Report notification sent to user {user.username}")
        except Exception as e:
            logger.exception(f"Error sending Telegram notification: {e}")

def send_report_notification(user_id, report_id, summary):
    """
    Synchronous wrapper for send_report_notification_async
    
    Args:
        user_id: User ID
        report_id: Report ID
        summary: Report summary text
    """
    # Create a new event loop for the async function
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_report_notification_async(user_id, report_id, summary))
        loop.close()
    except Exception as e:
        logger.exception(f"Error in send_report_notification: {e}")
