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
import signal
from typing import Dict, Optional, List
import re

# Load environment variables
load_dotenv()

# Minimal logging setup
logging.basicConfig(
    level=logging.WARNING,  # Only warnings and errors
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_errors.log')
    ]
)
logger = logging.getLogger(__name__)

class FastConfig:
    """Lightweight configuration manager"""
    def __init__(self):
        self.api_id = int(os.environ['API_ID'])
        self.api_hash = os.environ['API_HASH']
        self.string_session = os.environ.get('STRING_SESSION', '')
        self.bot_username = os.environ['BOT_USERNAME'].lower().replace('@', '')
        
        # Multiple API keys support
        api_keys_str = os.environ.get('API_KEYS', os.environ.get('API_KEY', ''))
        self.api_keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]
        
        # Performance settings
        self.context_size = 3  # Reduced from 10 to 3 for speed
        self.rate_limit = 2    # Reduced from 3 to 2 seconds
        self.timeout = 30      # Reduced from 60 to 30 seconds
        self.max_tokens = 1024 # Reduced from 2048 for faster responses

class FastAPIManager:
    """Lightweight API key manager with minimal overhead"""
    def __init__(self, api_keys: List[str]):
        self.keys = api_keys
        self.current = 0
        self.failures = set()
    
    def get_key(self) -> str:
        if len(self.failures) >= len(self.keys):
            self.failures.clear()  # Reset if all failed
        
        for _ in range(len(self.keys)):
            key = self.keys[self.current]
            if key not in self.failures:
                return key
            self.current = (self.current + 1) % len(self.keys)
        
        return self.keys[0]  # Fallback
    
    def mark_failure(self, key: str):
        self.failures.add(key)
        self.current = (self.current + 1) % len(self.keys)
    
    def mark_success(self, key: str):
        self.failures.discard(key)

class FastContext:
    """Ultra-lightweight context manager"""
    def __init__(self, max_size: int = 3):
        self.user_history = defaultdict(lambda: deque(maxlen=max_size))
        self.group_history = defaultdict(lambda: deque(maxlen=max_size))
    
    def add_message(self, user_id: int, chat_id: int, text: str, username: str = None):
        # Only store essential info
        msg = f"{username or 'User'}: {text[:100]}"  # Truncate long messages
        self.user_history[user_id].append(msg)
        if chat_id != user_id:  # Group chat
            self.group_history[chat_id].append(msg)
    
    def get_context(self, user_id: int, chat_id: int) -> str:
        context = []
        
        # Group context first (more relevant for current conversation)
        if chat_id != user_id and self.group_history[chat_id]:
            context.extend(list(self.group_history[chat_id])[-2:])  # Last 2 group messages
        
        # User context
        if self.user_history[user_id]:
            context.extend(list(self.user_history[user_id])[-1:])   # Last 1 user message
        
        return " | ".join(context[-3:]) if context else ""  # Max 3 messages total

class FastRateLimit:
    """Minimal rate limiting with O(1) operations"""
    def __init__(self, limit_seconds: int = 2):
        self.limit = limit_seconds
        self.last_request = {}
    
    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        if user_id in self.last_request:
            if now - self.last_request[user_id] < self.limit:
                return False
        self.last_request[user_id] = now
        return True

class UltraFastBot:
    """Ultra-fast Telegram bot with minimal overhead"""
    
    def __init__(self):
        self.config = FastConfig()
        self.api_manager = FastAPIManager(self.config.api_keys)
        self.context = FastContext(self.config.context_size)
        self.rate_limit = FastRateLimit(self.config.rate_limit)
        
        # Pre-compile regex for performance
        self.bot_mention_pattern = re.compile(
            rf'\b{re.escape(self.config.bot_username)}\b', 
            re.IGNORECASE
        )
        
        # Create persistent HTTP session for connection pooling
        self.session = None
        
        # Initialize Telethon client
        session = StringSession(self.config.string_session) if self.config.string_session else StringSession()
        self.client = TelegramClient(session, self.config.api_id, self.config.api_hash)
        
        # Minimal system prompt for faster API calls
        self.system_prompt = "You are MrxSeek, a helpful AI assistant. Be concise and direct."
        
        self.bot_user_id = None
        self.shutdown_flag = False
    
    async def start(self):
        """Start the bot with optimal performance settings"""
        try:
            # Create persistent HTTP session with optimized settings
            connector = aiohttp.TCPConnector(
                limit=100,           # Connection pool size
                ttl_dns_cache=300,   # DNS cache TTL
                use_dns_cache=True,  # Enable DNS caching
                keepalive_timeout=30, # Keep connections alive
                enable_cleanup_closed=True
            )
            
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    'User-Agent': 'TelegramBot/1.0',
                    'Connection': 'keep-alive'
                }
            )
            
            # Start Telegram client
            await self.client.start()
            me = await self.client.get_me()
            self.bot_user_id = me.id
            
            print(f"🚀 Fast bot started as @{me.username}")
            print(f"⚡ Response time optimized for maximum speed")
            print(f"🔑 {len(self.config.api_keys)} API keys loaded")
            
            # Save session if new
            if not self.config.string_session:
                session_string = self.client.session.save()
                with open('.env', 'a') as f:
                    f.write(f"\nSTRING_SESSION={session_string}")
                print("💾 Session saved")
            
            # Register optimized event handler
            @self.client.on(events.NewMessage(incoming=True))
            async def handle_message(event):
                await self.process_message(event)
            
            # Setup shutdown handler
            def shutdown_handler(signum, frame):
                print("\n🛑 Shutting down...")
                self.shutdown_flag = True
            
            signal.signal(signal.SIGINT, shutdown_handler)
            signal.signal(signal.SIGTERM, shutdown_handler)
            
            print("✅ Bot is running! Press Ctrl+C to stop")
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Startup error: {e}")
            raise
        finally:
            await self.cleanup()
    
    async def process_message(self, event):
        """Ultra-fast message processing with minimal checks"""
        try:
            # Fast exit conditions
            if (self.shutdown_flag or 
                not event.is_group or 
                not event.raw_text or 
                event.sender_id == self.bot_user_id):
                return
            
            sender = await event.get_sender()
            if not sender or sender.bot:
                return
            
            text = event.raw_text
            user_id = event.sender_id
            chat_id = event.chat_id
            username = sender.username
            
            # Always update context (minimal overhead)
            self.context.add_message(user_id, chat_id, text, username)
            
            # Fast mention/reply detection
            is_mention = bool(self.bot_mention_pattern.search(text))
            is_reply = (event.is_reply and 
                       (await event.get_reply_message()).sender_id == self.bot_user_id)
            
            if not (is_mention or is_reply):
                return
            
            # Fast rate limiting
            if not self.rate_limit.is_allowed(user_id):
                return  # Silent rate limiting for speed
            
            # Process query asynchronously without blocking
            asyncio.create_task(self.handle_query(event, user_id, chat_id, text, username))
            
        except Exception as e:
            logger.error(f"Message processing error: {e}")
    
    async def handle_query(self, event, user_id: int, chat_id: int, text: str, username: str):
        """Handle user query with maximum speed optimization"""
        try:
            # Fast query extraction
            query = self.bot_mention_pattern.sub('', text).strip()
            if not query:
                return
            
            # Get minimal context
            context = self.context.get_context(user_id, chat_id)
            
            # Show typing with minimal delay
            async with self.client.action(event.chat_id, 'typing'):
                # Get AI response
                response = await self.get_ai_response(query, context)
                
                # Send response immediately
                await event.reply(response)
                
        except Exception as e:
            logger.error(f"Query handling error: {e}")
            try:
                await event.reply("❌ Error occurred. Try again.")
            except:
                pass
    
    async def get_ai_response(self, query: str, context: str) -> str:
        """Optimized AI API call with minimal overhead"""
        for attempt in range(2):  # Max 2 attempts for speed
            try:
                api_key = self.api_manager.get_key()
                
                # Minimal message structure
                messages = [{"role": "system", "content": self.system_prompt}]
                
                if context:
                    messages.append({"role": "assistant", "content": f"Context: {context}"})
                
                messages.append({"role": "user", "content": query})
                
                # Optimized API request
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": "deepseek/deepseek-r1-0528:free",
                    "messages": messages,
                    "max_tokens": self.config.max_tokens,
                    "temperature": 0.7,
                    "stream": False  # Disable streaming for faster simple responses
                }
                
                # Use persistent session for connection reuse
                async with self.session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=data
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        if result.get('choices'):
                            self.api_manager.mark_success(api_key)
                            return result['choices'][0]['message']['content'].strip()
                    
                    # Handle API errors
                    error_text = await response.text()
                    raise Exception(f"API error {response.status}: {error_text[:100]}")
                    
            except Exception as e:
                self.api_manager.mark_failure(self.api_manager.get_key())
                if attempt == 1:  # Last attempt
                    logger.error(f"AI API failed: {e}")
                    return "⚡ Service temporarily unavailable. Please try again."
                
                await asyncio.sleep(0.5)  # Brief pause before retry
        
        return "❌ Unable to process request."
    
    async def cleanup(self):
        """Fast cleanup"""
        if self.session:
            await self.session.close()
        if self.client.is_connected():
            await self.client.disconnect()
        print("🧹 Cleanup completed")

# Ultra-fast main function
async def main():
    bot = None
    try:
        bot = UltraFastBot()
        await bot.start()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    finally:
        if bot:
            await bot.cleanup()
    return 0

if __name__ == '__main__':
    # Run with optimized event loop policy
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Failed to start: {e}")
        sys.exit(1)
