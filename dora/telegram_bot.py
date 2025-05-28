"""Telegram bot for Dora the Explora."""

import asyncio
import logging
import json
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from dora.models.config import DoraConfig
from dora.http_client import DoraHTTPClient

# Set up logging
logger = logging.getLogger(__name__)

# Authorized user
AUTHORIZED_USER = "jewpacabra"

# Global state to track if bot is processing
class BotState:
    def __init__(self):
        self.is_processing = False
        self.processing_user = None
        self.processing_city = None
        self.processing_start_time = None
        self.lock = asyncio.Lock()
        self.timeout_seconds = 300  # 5 minutes timeout
        
    async def start_processing(self, user: str, city: str) -> bool:
        """Try to start processing. Returns True if successful, False if busy."""
        async with self.lock:
            # Check if current processing has timed out
            if self.is_processing and self.processing_start_time:
                elapsed = (datetime.now() - self.processing_start_time).seconds
                if elapsed > self.timeout_seconds:
                    logger.warning(f"Previous processing timed out after {elapsed}s")
                    self.is_processing = False
                    
            if self.is_processing:
                return False
            self.is_processing = True
            self.processing_user = user
            self.processing_city = city
            self.processing_start_time = datetime.now()
            return True
            
    async def stop_processing(self):
        """Mark processing as complete."""
        async with self.lock:
            self.is_processing = False
            self.processing_user = None
            self.processing_city = None
            self.processing_start_time = None
            
    def get_status(self) -> str:
        """Get current processing status."""
        if not self.is_processing:
            return "idle"
        elapsed = (datetime.now() - self.processing_start_time).seconds
        return f"Processing request for {self.processing_city} by @{self.processing_user} ({elapsed}s ago)"

# Global bot state instance
bot_state = BotState()


async def check_user(update: Update) -> bool:
    """Check if the user is authorized."""
    # Allow all users in groups (when bot is mentioned)
    if update.effective_chat.type in ['group', 'supergroup']:
        return True
    
    # For private chats, check if user is authorized
    username = update.effective_user.username
    if username != AUTHORIZED_USER:
        await update.message.reply_text(
            "Sorry, this bot is currently private. Access restricted to authorized users only."
        )
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    # In groups, everyone can use the bot
    if update.effective_chat.type in ['group', 'supergroup']:
        bot_username = context.bot.username
        await update.message.reply_text(
            "🎭 Welcome to Dora the Explora!\n\n"
            "I can help you discover exciting events in any city.\n"
            "To use me in a group, mention me with a city name:\n\n"
            f"Example: @{bot_username} London\n"
            f"Example: @{bot_username} Tokyo\n"
            f"Example: @{bot_username} New York\n\n"
            "Type /help for detailed instructions and available commands."
        )
    else:
        # In private chats, check authorization
        if not await check_user(update):
            return
            
        await update.message.reply_text(
            "🎭 Welcome to Dora the Explora!\n\n"
            "I can help you discover exciting events in any city.\n"
            "Just send me a city name and I'll find the top events for you!\n\n"
            "Example: San Francisco\n"
            "Example: London\n"
            "Example: Tokyo\n\n"
            "Type /help for detailed instructions and available commands."
        )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /status command."""
    status = bot_state.get_status()
    if status == "idle":
        await update.message.reply_text(
            "✅ I'm ready to process your request!\n\n"
            "Send me a city name to discover events."
        )
    else:
        # Calculate remaining time estimate (rough)
        if bot_state.processing_start_time:
            elapsed = (datetime.now() - bot_state.processing_start_time).seconds
            if elapsed < 30:
                estimate = "~1-2 minutes remaining"
            elif elapsed < 60:
                estimate = "~1 minute remaining"
            else:
                estimate = "processing (may take a few more minutes)"
        else:
            estimate = "processing"
            
        await update.message.reply_text(
            f"⏳ Currently busy\n\n"
            f"Status: {status}\n"
            f"Estimate: {estimate}\n\n"
            "New requests will be dropped until this completes."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command - show bot usage and commands."""
    chat_type = update.effective_chat.type
    bot_username = context.bot.username
    
    if chat_type in ['group', 'supergroup']:
        help_text = f"""🎭 **Dora the Explora - Event Discovery Bot**

**How to use in groups:**
Mention me with a city name to discover events:
`@{bot_username} London`
`@{bot_username} New York`
`@{bot_username} Tokyo`

**Available commands:**
• `/help` - Show this help message
• `/start` - Welcome message and quick start
• `/status` - Check if I'm busy or ready
• `/debug` - Show technical information

**How it works:**
1. Mention me with a city name
2. I'll search for upcoming events (concerts, sports, festivals, etc.)
3. You'll get a list of events with details and recommendations
4. Only one request is processed at a time - others are dropped

**Notes:**
• I process requests one at a time
• If I'm busy, your request will be dropped (not queued)
• Processing typically takes 1-2 minutes
• I show 3 events in groups (to avoid spam)
"""
    else:
        help_text = f"""🎭 **Dora the Explora - Event Discovery Bot**

**How to use in private chat:**
Simply send me a city name:
`London`
`New York`
`Tokyo`

**Available commands:**
• `/help` - Show this help message
• `/start` - Welcome message and quick start
• `/status` - Check if I'm busy or ready
• `/debug` - Show technical information

**How it works:**
1. Send me any city name
2. I'll search for upcoming events (concerts, sports, festivals, etc.)
3. You'll get a detailed list with:
   - Event descriptions
   - Dates and locations
   - Target audiences
   - Personalized notifications
4. Only one request is processed at a time

**Notes:**
• Private chat access is restricted
• I show 10 events in private chats
• Each request takes 1-2 minutes to process
• New requests are dropped if I'm busy
"""
    
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /test command - test bot functionality."""
    await update.message.reply_text("Test message 1: Direct reply")
    
    # Try to send a message to the group
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Test message 2: Using send_message"
        )
    except Exception as e:
        await update.message.reply_text(f"Error sending message: {e}")


async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /debug command - show debug info."""
    bot = await context.bot.get_me()
    chat = update.effective_chat
    user = update.effective_user
    
    # Get bot's member status in the group
    member_status = "Unknown"
    if chat.type in ['group', 'supergroup']:
        try:
            bot_member = await context.bot.get_chat_member(chat.id, bot.id)
            member_status = bot_member.status
        except Exception as e:
            member_status = f"Error: {e}"
    
    debug_info = f"""Debug Information:
Bot username: @{bot.username}
Bot ID: {bot.id}
Chat type: {chat.type}
Chat ID: {chat.id}
Chat title: {chat.title if chat.title else 'N/A'}
Bot status in chat: {member_status}
User: @{user.username} ({user.id})
Message: {update.message.text if update.message else 'No message'}
Update type: {update.update_id}
Can bot see messages: {bot.can_read_all_group_messages if hasattr(bot, 'can_read_all_group_messages') else 'Unknown'}
    """
    
    await update.message.reply_text(debug_info)


async def handle_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle city input from the user."""
    if not update.message or not update.message.text:
        return
        
    # Skip command messages as they're handled separately
    if update.message.text.startswith('/'):
        return
        
    # Log the message for debugging
    logger.info(f"Received message: {update.message.text} in chat type: {update.effective_chat.type}")
    
    message_text = update.message.text.strip()
    
    # In groups, bot needs to be mentioned
    if update.effective_chat.type in ['group', 'supergroup']:
        bot_username = context.bot.username
        
        # Check if bot is mentioned
        if f'@{bot_username}' not in message_text:
            return
            
        # Extract city from mention - remove the bot mention
        city = message_text.replace(f'@{bot_username}', '').strip()
        
        if not city:
            await update.message.reply_text("Please provide a city name after mentioning me.")
            return
            
        logger.info(f"Processing city '{city}' from group mention")
    else:
        # In private chat, the whole message is the city
        city = message_text
        
        # Check authorization for private chats
        if not await check_user(update):
            return
    
    if not city:
        await update.message.reply_text("Please provide a city name.")
        return
    
    # Check if bot is already processing a request
    username = update.effective_user.username or update.effective_user.first_name
    can_process = await bot_state.start_processing(username, city)
    
    if not can_process:
        status = bot_state.get_status()
        await update.message.reply_text(
            f"❌ I'm currently busy processing another request.\n\n"
            f"Status: {status}\n\n"
            "Your request has been dropped. Please wait for the current request to complete and try again."
        )
        logger.info(f"Dropped request from {username} for {city} - bot is busy")
        return
    
    # Send "typing" status
    await update.message.chat.send_action("typing")
    
    # Send initial message
    processing_msg = await update.message.reply_text(
        f"🔍 Initializing search for events in {city}...\n"
        "This may take 1-2 minutes."
    )
    
    # Progress tracking
    progress_steps = {
        "INITIALIZING": "🔧 Setting up search system...",
        "CREATING_AGENTS": "🤖 Preparing AI agents...",
        "BUILDING_TOOLS": "⚙️ Building processing tools...",
        "STARTING_SEARCH": "🔍 Starting event discovery...",
        "RUNNING_ORCHESTRATOR": "🎭 Finding and analyzing events...",
        "PROCESSING_RESULTS": "📊 Processing and formatting results...",
        "COMPLETED": "✅ Search completed!"
    }
    
    async def progress_callback(step: str, details: str):
        """Update the user with progress information."""
        try:
            if step in progress_steps:
                progress_text = progress_steps[step]
                if details:
                    progress_text += f"\n{details}"
                
                await processing_msg.edit_text(
                    f"🔍 **Searching for events in {city}**\n\n"
                    f"{progress_text}",
                    parse_mode="Markdown"
                )
        except Exception as e:
            # If message editing fails, don't crash - just log it
            logger.debug(f"Failed to update progress message: {e}")
    
    try:
        # Get the config
        config = DoraConfig()
        
        # In groups, show fewer events to avoid spam
        if update.effective_chat.type in ['group', 'supergroup']:
            events_count = 3
        else:
            events_count = 10
        
        # Create HTTP client
        http_url = f"http://{config.http_host}:{config.http_port}"
        api_key = config.http_api_keys[0] if config.http_api_keys else None
        client = DoraHTTPClient(http_url, api_key)
        
        # Build the message for the HTTP API
        message = f"{city} (events_count={events_count}, days_ahead=14)"
        
        # Process the city via HTTP API
        logger.info(f"Processing city via HTTP: {city} for user: {update.effective_user.username}")
        
        # Update progress to show we're processing
        await progress_callback("RUNNING_ORCHESTRATOR", "Processing through HTTP interface...")
        
        # Create a proper chat completion request with JSON response format
        response = await client.chat_completion_with_json(
            message=message,
            temperature=0.0,
            model="dora-events-v1"
        )
        
        # Extract the results from the response
        if not response or 'choices' not in response or not response['choices']:
            results = None
        else:
            content = response['choices'][0]['message']['content']
            try:
                # Parse the JSON response
                data = json.loads(content)
                results = data.get('notifications', [])
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON response from HTTP server")
                results = None
        
        # Delete the processing message
        try:
            await processing_msg.delete()
        except Exception:
            pass  # Message might already be deleted
        
        if not results:
            await update.message.reply_text(f"No events found in {city}. Try another city!")
            await bot_state.stop_processing()
            return
        
        # Format and send results
        await send_results(update, city, results)
        
    except Exception as e:
        logger.error(f"Error processing city {city}: {e}")
        await processing_msg.delete()
        await update.message.reply_text(
            f"❌ Sorry, I encountered an error while searching for events in {city}.\n"
            "Please try again later or try a different city."
        )
    finally:
        # Always stop processing when done
        await bot_state.stop_processing()


async def send_results(update: Update, city: str, results: list) -> None:
    """Send formatted results to the user."""
    # In groups, mention the user who requested
    mention = ""
    if update.effective_chat.type in ['group', 'supergroup']:
        user = update.effective_user
        mention = f"@{user.username}, " if user.username else ""
    
    # Results from HTTP API are already properly formatted
    # Just filter out any that might be None
    valid_events = [event for event in results if event is not None]
    
    if not valid_events:
        await update.message.reply_text(
            f"{mention}❌ No upcoming events found in {city}. All events found were in the past.",
            parse_mode="Markdown"
        )
        return
    
    # Send header
    await update.message.reply_text(
        f"{mention}🎉 **Events in {city}**\n\n"
        f"Found {len(valid_events)} exciting events!",
        parse_mode="Markdown"
    )
    
    # Send each event as a separate message
    for event_count, result in enumerate(valid_events, 1):
        event = result["event"]
        classification = result["classification"]
        notifications = result["notifications"]
        
        # Format the message
        message = f"**{event_count}. {event['name']}**\n"
        message += f"📅 {event['start_date']}\n"
        if event['end_date']:
            message += f"📅 End: {event['end_date']}\n"
            
        # Split location into venue and address
        location_parts = event['location'].split(',', 1)
        if len(location_parts) > 1:
            venue = location_parts[0].strip()
            address = location_parts[1].strip()
            message += f"📍 Venue: {venue}\n"
            message += f"🏢 Address: {address}\n"
        else:
            message += f"📍 {event['location']}\n"
        
        if event['url']:
            message += f"🔗 [More info]({event['url']})\n"
        
        message += f"\n**Classification:**\n"
        message += f"🏷️ Size: {classification['size']} | Importance: {classification['importance']}\n"
        message += f"👥 Audience: {', '.join(classification['target_audiences'])}\n"
        
        if notifications:
            message += f"\n**Notifications:**\n"
            # Show all notifications with language and group
            for notification in notifications:
                language = notification.get('language', 'en')
                group = notification.get('context', {}).get('group_id', 'default')
                message += f"💬 [{language}/{group}] _{notification['text']}_\n"
        
        # Send the event message
        try:
            await update.message.reply_text(message, parse_mode="Markdown")
        except Exception as e:
            # Fallback without markdown if there's an issue
            logger.warning(f"Failed to send with markdown: {e}")
            await update.message.reply_text(message.replace('*', '').replace('_', ''))
        
        # Add a small delay between messages to avoid rate limiting
        await asyncio.sleep(0.5)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors."""
    logger.error(f"Update {update} caused error {context.error}")
    logger.exception("Exception in error handler:", exc_info=context.error)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Sorry, an error occurred while processing your request. Please try again."
            )
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")


def main() -> None:
    """Start the bot."""
    # Get the token from config
    config = DoraConfig()
    telegram_token = config.telegram_api_key
    
    if not telegram_token:
        logger.error("TELEGRAM_API_KEY not found in configuration")
        return
    
    # Create the Application
    application = Application.builder().token(telegram_token).build()
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("debug", debug))
    application.add_handler(CommandHandler("test", test))
    # Handle non-command text messages
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_city
    ))
    
    # Run the bot
    logger.info("Starting Telegram bot...")
    logger.info(f"Bot token configured: {'Yes' if telegram_token else 'No'}")
    
    # Start polling with all update types
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Reduce verbosity for third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # Run the bot
    main()