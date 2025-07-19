from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Channel, User, Chat
import logging
import os
from dotenv import load_dotenv
import asyncio
import sys
from collections import defaultdict, deque
import aiohttp
import time
import signal
from typing import Dict, Optional, List, Union
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
        
        # Credit saving settings
        self.min_query_length = 2  # Minimum chars to trigger AI
        self.ignored_patterns = [
            r'^[.!@#$%^&*()_+=-]*$',  # Only symbols
            r'^hi+$', r'^hello+$', r'^hey+$',  # Simple greetings
            r'^\d+$',  # Only numbers
            r'^[a-z]{1,2}$',  # Single/double letters
        ]

class FastAPIManager:
    """Lightweight API key manager with minimal overhead"""
    def __init__(self, api_keys: List[str]):
        self.keys = api_keys
        self.current = 0
        self.failures = set()
        self.request_count = 0  # Track API usage
    
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
        self.request_count += 1
    
    def get_usage_stats(self) -> str:
        return f"API calls made: {self.request_count}, Active keys: {len(self.keys) - len(self.failures)}/{len(self.keys)}"

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
    """Enhanced rate limiting with credit-saving features"""
    def __init__(self, limit_seconds: int = 2):
        self.limit = limit_seconds
        self.last_request = {}
        self.spam_detection = defaultdict(list)  # Track user message frequency
    
    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        
        # Clean old spam detection entries
        self.spam_detection[user_id] = [
            t for t in self.spam_detection[user_id] 
            if now - t < 60  # Keep last minute of activity
        ]
        
        # Check for spam (more than 5 messages in 1 minute)
        if len(self.spam_detection[user_id]) >= 5:
            return False
        
        # Regular rate limiting
        if user_id in self.last_request:
            if now - self.last_request[user_id] < self.limit:
                return False
        
        self.last_request[user_id] = now
        self.spam_detection[user_id].append(now)
        return True

class SmartTriggerSystem:
    """Smart system to determine when AI response is actually needed"""
    def __init__(self, config: FastConfig):
        self.config = config
        self.ignored_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in config.ignored_patterns]
        self.last_responses = defaultdict(lambda: deque(maxlen=5))  # Track recent responses to avoid repetition
    
    def should_trigger_ai(self, query: str, user_id: int, is_group: bool) -> tuple[bool, str]:
        """
        Determine if AI should be triggered and return (should_trigger, reason)
        """
        query = query.strip()
        
        # Length check
        if len(query) < self.config.min_query_length:
            return False, "Query too short"
        
        # Pattern checks
        for pattern in self.ignored_patterns:
            if pattern.match(query):
                return False, "Matched ignored pattern"
        
        # Check for repetitive queries
        query_lower = query.lower()
        recent = list(self.last_responses[user_id])
        if recent and query_lower in [r.lower() for r in recent]:
            return False, "Repetitive query"
        
        # Smart content analysis
        if self._is_simple_greeting(query):
            return False, "Simple greeting"
        
        if self._is_spam_like(query):
            return False, "Spam-like content"
        
        # Update history
        self.last_responses[user_id].append(query)
        return True, "Valid query"
    
    def _is_simple_greeting(self, text: str) -> bool:
        """Check if text is a simple greeting that doesn't need AI"""
        greetings = ['hi', 'hello', 'hey', 'sup', 'yo', 'hii', 'helloo']
        return text.lower().strip() in greetings
    
    def _is_spam_like(self, text: str) -> bool:
        """Detect spam-like patterns"""
        # Check for excessive repetition
        if len(set(text.lower().replace(' ', ''))) < len(text) / 3:
            return True
        
        # Check for excessive punctuation
        punct_count = sum(1 for c in text if c in '!@#$%^&*()_+-=[]{}|;:,.<>?')
        if punct_count > len(text) / 2:
            return True
        
        return False

class UltraFastBot:
    """Ultra-fast Telegram bot with credit-saving intelligence"""
    
    def __init__(self):
        self.config = FastConfig()
        self.api_manager = FastAPIManager(self.config.api_keys)
        self.context = FastContext(self.config.context_size)
        self.rate_limit = FastRateLimit(self.config.rate_limit)
        self.trigger_system = SmartTriggerSystem(self.config)
        
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
        self.loop = None
        
        # Statistics tracking
        self.stats = {
            'messages_processed': 0,
            'api_calls_saved': 0,
            'api_calls_made': 0,
            'errors_handled': 0
        }
    
    async def start(self):
        """Start the bot with optimal performance settings"""
        try:
            self.loop = asyncio.get_running_loop()
            
            # Create persistent HTTP session with optimized settings
            connector = aiohttp.TCPConnector(
                limit=100,
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=30,
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
            
            print(f"🚀 Ultra-Fast Credit-Saving Bot started as @{me.username}")
            print(f"⚡ Smart AI triggering enabled - Credits will be saved!")
            print(f"🔑 {len(self.config.api_keys)} API keys loaded")
            print(f"💬 Bot responds to DMs and group mentions intelligently")
            
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
                if self.loop and self.loop.is_running():
                    asyncio.create_task(self.shutdown())
            
            signal.signal(signal.SIGINT, shutdown_handler)
            signal.signal(signal.SIGTERM, shutdown_handler)
            
            # Stats reporting task
            asyncio.create_task(self.periodic_stats())
            
            print("✅ Bot is running! Press Ctrl+C to stop")
            
            # Keep running until shutdown
            while not self.shutdown_flag:
                await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Startup error: {e}")
            raise
        finally:
            await self.cleanup()
    
    async def periodic_stats(self):
        """Report statistics periodically"""
        while not self.shutdown_flag:
            await asyncio.sleep(300)  # Every 5 minutes
            if self.stats['messages_processed'] > 0:
                print(f"📊 Stats: {self.stats['messages_processed']} messages, "
                      f"{self.stats['api_calls_made']} API calls, "
                      f"{self.stats['api_calls_saved']} credits saved!")
    
    async def shutdown(self):
        """Graceful shutdown"""
        print("🔄 Initiating graceful shutdown...")
        print(f"📈 Final Stats: {self.api_manager.get_usage_stats()}")
        self.shutdown_flag = True
        await asyncio.sleep(0.1)
    
    def get_safe_sender_info(self, sender: Union[User, Channel, Chat, None]) -> tuple[bool, str]:
        """Safely extract sender information"""
        try:
            if not sender:
                return True, None  # Skip if no sender
            
            # Handle different sender types safely
            if hasattr(sender, 'bot'):  # User object
                return sender.bot, getattr(sender, 'username', None)
            elif isinstance(sender, (Channel, Chat)):  # Channel or Chat
                return False, getattr(sender, 'username', None)  # Not a bot
            else:
                return False, None  # Default: not a bot, no username
        except Exception as e:
            logger.warning(f"Error getting sender info: {e}")
            return False, None  # Safe default
    
    async def process_message(self, event):
        """Ultra-fast message processing with enhanced error handling"""
        try:
            # Fast exit conditions
            if (self.shutdown_flag or 
                not event.raw_text or 
                event.sender_id == self.bot_user_id):
                return
            
            # Safely get sender information
            try:
                sender = await event.get_sender()
                is_bot, username = self.get_safe_sender_info(sender)
                
                if is_bot:  # Skip if sender is a bot
                    return
                    
            except Exception as e:
                logger.warning(f"Could not get sender info: {e}")
                return  # Skip this message if we can't get sender info safely
            
            text = event.raw_text
            user_id = event.sender_id
            chat_id = event.chat_id
            is_group = event.is_group
            is_channel = event.is_channel
            
            self.stats['messages_processed'] += 1
            
            # Skip channels (we can't respond there anyway)
            if is_channel:
                return
            
            # Always update context (minimal overhead)
            self.context.add_message(user_id, chat_id, text, username)
            
            # Determine if bot should respond
            should_respond = False
            
            if is_group:
                # In groups: respond to mentions or replies only
                is_mention = bool(self.bot_mention_pattern.search(text))
                is_reply = False
                try:
                    if event.is_reply:
                        reply_msg = await event.get_reply_message()
                        if reply_msg and reply_msg.sender_id == self.bot_user_id:
                            is_reply = True
                except:
                    pass  # Ignore reply check errors
                
                should_respond = is_mention or is_reply
            else:
                # In DMs: respond to all messages
                should_respond = True
            
            if not should_respond:
                return
            
            # Fast rate limiting
            if not self.rate_limit.is_allowed(user_id):
                return
            
            # Process query asynchronously
            asyncio.create_task(self.handle_query(event, user_id, chat_id, text, username, is_group))
            
        except Exception as e:
            self.stats['errors_handled'] += 1
            logger.error(f"Message processing error: {e}")
    
    async def handle_query(self, event, user_id: int, chat_id: int, text: str, username: str, is_group: bool):
        """Handle user query with smart AI triggering"""
        try:
            # Fast query extraction
            if is_group:
                query = self.bot_mention_pattern.sub('', text).strip()
            else:
                query = text.strip()
                
            if not query:
                return
            
            # Smart AI triggering - SAVE CREDITS!
            should_trigger, reason = self.trigger_system.should_trigger_ai(query, user_id, is_group)
            
            if not should_trigger:
                self.stats['api_calls_saved'] += 1
                
                # Send appropriate quick response without AI
                quick_response = self.get_quick_response(query, reason)
                if quick_response:
                    await event.reply(quick_response)
                return
            
            # Get minimal context
            context = self.context.get_context(user_id, chat_id)
            
            # Show typing only where we have permission
            typing_context = None
            try:
                # Only show typing in private chats or groups where we're sure we can
                if not is_group or event.is_private:
                    typing_context = self.client.action(event.chat_id, 'typing')
            except:
                pass  # Ignore typing errors
            
            if typing_context:
                async with typing_context:
                    response = await self.get_ai_response(query, context)
                    await event.reply(response)
            else:
                response = await self.get_ai_response(query, context)
                await event.reply(response)
                
        except Exception as e:
            self.stats['errors_handled'] += 1
            logger.error(f"Query handling error: {e}")
            try:
                await event.reply("❌ Error occurred. Try again.")
            except:
                pass
    
    def get_quick_response(self, query: str, reason: str) -> Optional[str]:
        """Generate quick responses without AI for simple queries"""
        query_lower = query.lower().strip()
        
        # Simple greetings
        if reason == "Simple greeting":
            greetings_map = {
                'hi': 'Hello! 👋',
                'hello': 'Hi there! 😊',
                'hey': 'Hey! What\'s up? 👋',
                'sup': 'Not much, you? 😊',
                'yo': 'Hey there! 👋'
            }
            return greetings_map.get(query_lower, 'Hello! 👋')
        
        # Very short queries
        if reason == "Query too short":
            return None  # Don't respond to very short queries
        
        # Repetitive queries
        if reason == "Repetitive query":
            return "🔄 You just asked that! Try something different."
        
        return None  # No quick response available
    
    async def get_ai_response(self, query: str, context: str) -> str:
        """Optimized AI API call with enhanced error handling"""
        for attempt in range(2):
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
                    "stream": False
                }
                
                async with self.session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=data
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        if result.get('choices'):
                            self.api_manager.mark_success(api_key)
                            self.stats['api_calls_made'] += 1
                            return result['choices'][0]['message']['content'].strip()
                    
                    # Handle API errors
                    error_text = await response.text()
                    raise Exception(f"API error {response.status}: {error_text[:100]}")
                    
            except Exception as e:
                current_key = self.api_manager.get_key()
                self.api_manager.mark_failure(current_key)
                if attempt == 1:
                    self.stats['errors_handled'] += 1
                    logger.error(f"AI API failed: {e}")
                    return "⚡ Service temporarily unavailable. Please try again."
                
                await asyncio.sleep(0.5)
        
        return "❌ Unable to process request."
    
    async def cleanup(self):
        """Fast cleanup with stats"""
        print("🧹 Starting cleanup...")
        try:
            print(f"📊 Final Statistics:")
            print(f"   Messages processed: {self.stats['messages_processed']}")
            print(f"   API calls made: {self.stats['api_calls_made']}")
            print(f"   Credits saved: {self.stats['api_calls_saved']}")
            print(f"   Errors handled: {self.stats['errors_handled']}")
            
            if self.session:
                await self.session.close()
            if self.client.is_connected():
                await self.client.disconnect()
            print("✅ Cleanup completed")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

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
