from telethon import TelegramClient, events
from telethon.sessions import StringSession
import logging
import os
from dotenv import load_dotenv
import asyncio
import sys
from collections import defaultdict, deque
import aiohttp
import time
import re
from datetime import datetime, timedelta

# Load environment variables from .env file
load_dotenv()

# Set up logging to both file and console for better debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Get configuration from environment variables
API_ID = os.environ.get('API_ID')
API_HASH = os.environ.get('API_HASH')
STRING_SESSION = os.environ.get('STRING_SESSION', '')
BOT_USERNAME = os.environ.get('BOT_USERNAME')

# Get all API keys from environment variables
API_KEYS = [os.environ.get(f'API_KEY{i}') for i in range(1, 11) if os.environ.get(f'API_KEY{i}')]
if os.environ.get('API_KEY'):
    API_KEYS.insert(0, os.environ.get('API_KEY'))
API_KEYS = list(dict.fromkeys(API_KEYS))  # Remove duplicates

# API key management
api_key_errors = {}  # {api_key: error_timestamp}
current_api_key_index = 0
API_KEY_ERROR_TIMEOUT = 24 * 60 * 60  # 24 hours in seconds

# Global uptime monitoring
uptime_url = None
uptime_task = None
PING_INTERVAL = 180  # 3 minutes in seconds

# System prompts (cleaned - no crypto)
NORMAL_SYSTEM_PROMPT = """You are CleanAI, a helpful AI assistant. Keep responses short and accurate. Be friendly and slightly witty but helpful. Don't be overly polite - be direct and to the point. If someone asks something obvious, gently point it out but stay helpful."""

HELPFUL_SYSTEM_PROMPT = """You are CleanAI, a very helpful AI assistant. Keep responses short and accurate. Be as helpful as possible while staying concise. Be supportive and informative. Provide direct, useful answers with a warm tone."""

logger.info("Starting CleanAI bot initialization...")
logger.info(f"API_ID: {'✓' if API_ID else '✗'}")
logger.info(f"API_HASH: {'✓' if API_HASH else '✗'}")
logger.info(f"STRING_SESSION: {'✓' if STRING_SESSION else '✗'}")
logger.info(f"API_KEYS found: {len(API_KEYS)}")
logger.info(f"BOT_USERNAME: {BOT_USERNAME if BOT_USERNAME else '✗'}")

# Validate required configuration
if not all([API_ID, API_HASH, BOT_USERNAME]) or not API_KEYS:
    logger.error("Missing required configuration in .env file")
    logger.error("Please ensure .env file contains API_ID, API_HASH, BOT_USERNAME, and at least one API_KEY")
    sys.exit(1)

# Normalize bot username (remove @ and convert to lowercase for comparison)
BOT_USERNAME_NORMALIZED = BOT_USERNAME.lower().replace('@', '')
logger.info(f"Bot will respond to mentions of: {BOT_USERNAME} (case-insensitive)")

# Initialize session with StringSession
if STRING_SESSION:
    session = StringSession(STRING_SESSION)
    logger.info("Using existing session string")
else:
    session = StringSession()
    logger.info("Creating new session")

# Initialize the Telethon client
try:
    client = TelegramClient(session, int(API_ID), API_HASH)
    logger.info("Telethon client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Telethon client: {e}")
    sys.exit(1)

# Store user message history (user_id -> deque of last 5 messages)
user_message_history = defaultdict(lambda: deque(maxlen=5))

# Track active requests
active_requests = set()

def get_next_api_key():
    """Get the next available API key, skipping errored ones"""
    global current_api_key_index
    
    current_time = time.time()
    attempts = 0
    
    while attempts < len(API_KEYS):
        api_key = API_KEYS[current_api_key_index]
        
        if api_key in api_key_errors:
            error_time = api_key_errors[api_key]
            if current_time - error_time < API_KEY_ERROR_TIMEOUT:
                logger.info(f"Skipping API key {current_api_key_index + 1} (errored {(current_time - error_time)/3600:.1f}h ago)")
                current_api_key_index = (current_api_key_index + 1) % len(API_KEYS)
                attempts += 1
                continue
            else:
                del api_key_errors[api_key]
                logger.info(f"API key {current_api_key_index + 1} error timeout expired, back in rotation")
        
        logger.info(f"Using API key {current_api_key_index + 1}/{len(API_KEYS)}")
        return api_key
    
    logger.warning("All API keys have errors, using the one with oldest error")
    oldest_key = min(api_key_errors.keys(), key=lambda k: api_key_errors[k])
    current_api_key_index = API_KEYS.index(oldest_key)
    return oldest_key

def mark_api_key_error(api_key):
    """Mark an API key as having an error"""
    api_key_errors[api_key] = time.time()
    logger.warning(f"Marked API key {API_KEYS.index(api_key) + 1} as errored for 24 hours")
    global current_api_key_index
    current_api_key_index = (current_api_key_index + 1) % len(API_KEYS)

def get_user_context(user_id, be_helpful=False):
    """Get the last 5 (helpful) or 3 (normal) messages from a user as context"""
    messages = list(user_message_history[user_id])
    if not messages:
        return ""
    
    if be_helpful:
        context = "Previous 5 messages from this user:\n"
        for i, msg in enumerate(messages, 1):
            context += f"{i}. {msg}\n"
    else:
        context = "Previous 3 messages from this user:\n"
        for i, msg in enumerate(messages[-3:], 1):
            context += f"{i}. {msg}\n"
    return context

def add_user_message(user_id, message):
    """Add a message to user's history (keeps only last 5)"""
    user_message_history[user_id].append(message)
    logger.info(f"Added message to history for user {user_id}. History size: {len(user_message_history[user_id])}")

async def ping_url(url):
    """Ping a URL and return status"""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url) as response:
                logger.info(f"Pinged {url} - Status: {response.status}")
                return response.status
    except Exception as e:
        logger.error(f"Failed to ping {url}: {e}")
        return None

async def uptime_monitor():
    """Background task to ping the uptime URL every 3 minutes"""
    global uptime_url
    
    while uptime_url:
        try:
            await ping_url(uptime_url)
            await asyncio.sleep(PING_INTERVAL)
        except asyncio.CancelledError:
            logger.info("Uptime monitor task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in uptime monitor: {e}")
            await asyncio.sleep(PING_INTERVAL)

async def set_uptime_url(url):
    """Set or update the global uptime URL"""
    global uptime_url, uptime_task
    
    # Cancel existing task if any
    if uptime_task and not uptime_task.done():
        uptime_task.cancel()
        try:
            await uptime_task
        except asyncio.CancelledError:
            pass
    
    # Validate URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    uptime_url = url
    logger.info(f"Set uptime URL to: {uptime_url}")
    
    # Start new monitoring task
    uptime_task = asyncio.create_task(uptime_monitor())
    
    # Do initial ping
    status = await ping_url(uptime_url)
    return status

async def ask_api_with_fallback(query, user_context="", user_id=None, be_helpful=False):
    """Async API call with automatic fallback to next API key on error"""
    request_id = f"{user_id}_{int(time.time())}" if user_id else f"unknown_{int(time.time())}"
    logger.info(f"[{request_id}] Starting API request (helpful: {be_helpful}): {query[:50]}...")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    system_prompt = HELPFUL_SYSTEM_PROMPT if be_helpful else NORMAL_SYSTEM_PROMPT
    
    messages = [{"role": "system", "content": system_prompt}]
    if user_context:
        messages.append({"role": "system", "content": f"Context: {user_context}"})
    messages.append({"role": "user", "content": query})
    
    data = {
        "model": "deepseek/deepseek-r1-0528:free",
        "messages": messages
    }
    
    for attempt in range(len(API_KEYS)):
        api_key = get_next_api_key()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "CleanAI-Bot"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        result = await response.json()
                        if 'choices' in result and result['choices']:
                            api_response = result['choices'][0]['message']['content']
                            logger.info(f"[{request_id}] API response received successfully with key {current_api_key_index + 1}")
                            return api_response
                        else:
                            logger.error(f"[{request_id}] Invalid API response structure with key {current_api_key_index + 1}")
                            mark_api_key_error(api_key)
                            continue
                    else:
                        logger.error(f"[{request_id}] API request failed with status {response.status} using key {current_api_key_index + 1}")
                        mark_api_key_error(api_key)
                        continue
        except asyncio.TimeoutError:
            logger.error(f"[{request_id}] API request timed out with key {current_api_key_index + 1}")
            mark_api_key_error(api_key)
            continue
        except Exception as e:
            logger.error(f"[{request_id}] Unexpected error with key {current_api_key_index + 1}: {e}")
            mark_api_key_error(api_key)
            continue
    
    logger.error(f"[{request_id}] All API keys failed")
    return "Error: All API keys are currently unavailable. Please try again later."

def is_bot_mentioned(text):
    """Check if bot is mentioned in the text (case-insensitive)"""
    text_lower = text.lower()
    return BOT_USERNAME_NORMALIZED in text_lower

async def process_user_query(event, user_id, query, user_context, sender_info, replied_message=None):
    """Process a single user query asynchronously"""
    request_key = f"{user_id}_{event.id}"
    
    try:
        active_requests.add(request_key)
        logger.info(f"[User {user_id}] Processing query concurrently. Active requests: {len(active_requests)}")
        
        typing_task = asyncio.create_task(client.action(event.chat_id, 'typing').__aenter__())
        be_helpful = query.strip().endswith('...')
        
        # Handle summarization requests
        if replied_message:
            if 'summarize' in query.lower() or 'summarise' in query.lower():
                query = f"Summarize this message concisely: {replied_message.raw_text}"
                logger.info(f"[User {user_id}] Summarization request detected")
        
        response = await ask_api_with_fallback(query, user_context, user_id, be_helpful)
        
        try:
            typing_action = await typing_task
            await typing_action.__aexit__(None, None, None)
        except:
            pass
        
        await event.reply(response, parse_mode='markdown')
        logger.info(f"[User {user_id}] Response sent successfully")
        
    except Exception as e:
        logger.error(f"[User {user_id}] Error processing query: {e}")
        try:
            await event.reply("Sorry, I encountered an error processing your request.")
        except:
            pass
    finally:
        active_requests.discard(request_key)
        logger.info(f"[User {user_id}] Query processing completed. Active requests: {len(active_requests)}")

@client.on(events.NewMessage(pattern=r'^/up(?:\s+(.+))?$'))
async def handle_uptime_command(event):
    """Handle /up command to set uptime monitoring URL"""
    try:
        match = event.pattern_match
        url_arg = match.group(1) if match.group(1) else None
        
        if not url_arg:
            current_status = f"Currently monitoring: {uptime_url}" if uptime_url else "No URL being monitored"
            await event.reply(f"🔄 **Uptime Monitor**\n\n{current_status}\n\nUsage: `/up <url>` to set/change URL")
            return
        
        url = url_arg.strip()
        logger.info(f"Setting uptime URL to: {url}")
        
        # Set the uptime URL and get initial ping status
        status = await set_uptime_url(url)
        
        if status:
            await event.reply(f"🟢 **Uptime Monitor Started**\n\nURL: `{uptime_url}`\nStatus: {status}\nPinging every 3 minutes")
        else:
            await event.reply(f"🟡 **Uptime Monitor Started**\n\nURL: `{uptime_url}`\nInitial ping failed, but monitoring continues\nPinging every 3 minutes")
        
        logger.info(f"Uptime monitoring started for: {uptime_url}")
        
    except Exception as e:
        logger.error(f"Error handling uptime command: {e}")
        await event.reply("❌ Error setting up uptime monitoring. Please check the URL and try again.")

@client.on(events.NewMessage(incoming=True))
async def handler(event):
    try:
        # Skip if it's a command (already handled by command handlers)
        if event.raw_text.startswith('/'):
            return
            
        sender = await event.get_sender()
        if sender and sender.bot:
            return
        
        me = await client.get_me()
        if event.sender_id == me.id:
            return
        
        user_id = event.sender_id
        message_text = event.raw_text
        add_user_message(user_id, message_text)
        
        is_private = event.is_private
        is_group = event.is_group
        is_mention = is_bot_mentioned(event.raw_text) if is_group else False
        is_reply_to_bot = event.is_reply and (await event.get_reply_message()).sender_id == me.id if is_group else False
        
        if is_private or (is_group and (is_mention or is_reply_to_bot)):
            logger.info(f"[User {user_id}] Message received in {'private' if is_private else 'group'} chat")
            
            replied_message = None
            if event.is_reply:
                try:
                    replied_message = await event.get_reply_message()
                    logger.info(f"[User {user_id}] Replied message detected: {replied_message.raw_text[:100]}...")
                except Exception as e:
                    logger.error(f"[User {user_id}] Error getting replied message: {e}")
            
            if is_private:
                query = event.raw_text
            else:  # group message
                if is_mention:
                    pattern = re.compile(re.escape(BOT_USERNAME), re.IGNORECASE)
                    query = pattern.sub('', event.raw_text).strip()
                elif is_reply_to_bot:
                    query = event.raw_text
            
            if not query:
                logger.info(f"[User {user_id}] Empty query received, ignoring")
                return
            
            logger.info(f"[User {user_id}] Processing query: {query}")
            be_helpful = query.strip().endswith('...')
            user_context = get_user_context(user_id, be_helpful)
            logger.info(f"[User {user_id}] User context: {user_context[:100]}..." if user_context else f"[User {user_id}] No previous context")
            
            sender_info = f"@{sender.username}" if sender.username else f"User {user_id}"
            asyncio.create_task(process_user_query(event, user_id, query, user_context, sender_info, replied_message))
            logger.info(f"[User {user_id}] Query processing started asynchronously")
                
    except Exception as e:
        logger.error(f"Error in message handler: {e}")

async def main():
    try:
        logger.info("Starting Telegram client...")
        await client.start()
        
        me = await client.get_me()
        logger.info(f"CleanAI bot connected successfully as: {me.first_name} (@{me.username})")
        
        if not STRING_SESSION:
            session_string = client.session.save()
            try:
                with open('.env', 'a') as f:
                    f.write(f"\nSTRING_SESSION={session_string}")
                logger.info("New session string saved to .env")
            except Exception as e:
                logger.error(f"Failed to save session string: {e}")
        
        logger.info("🤖 CleanAI Bot is running and listening for messages...")
        logger.info(f"📱 Responds to mentions of: {BOT_USERNAME} (case-insensitive) in groups and all private messages")
        logger.info("🔄 Use /up <url> to start uptime monitoring")
        logger.info("⏹️  Press Ctrl+C to stop the bot")
        await client.run_until_disconnected()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise
    finally:
        # Clean up uptime task
        global uptime_task
        if uptime_task and not uptime_task.done():
            uptime_task.cancel()
            try:
                await uptime_task
            except asyncio.CancelledError:
                pass
        logger.info("CleanAI Bot shutting down...")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("CleanAI Bot stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
