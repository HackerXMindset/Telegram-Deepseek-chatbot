from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Channel, User, Chat
import logging
import os
from dotenv import load_dotenv
import asyncio
import sys
import aiohttp
import time
import signal
from typing import Dict, Optional, List, Union
import re
import json
from datetime import datetime

# Load environment variables
load_dotenv()

# Minimal logging setup - only errors
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('bot_errors.log')]
)
logger = logging.getLogger(__name__)

class Config:
    """Lightweight configuration"""
    def __init__(self):
        self.api_id = int(os.environ['API_ID'])
        self.api_hash = os.environ['API_HASH']
        self.string_session = os.environ.get('STRING_SESSION', '')
        self.bot_username = os.environ['BOT_USERNAME'].lower().replace('@', '')
        
        # API keys support
        api_keys_str = os.environ.get('API_KEYS', os.environ.get('API_KEY', ''))
        self.api_keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]
        
        # Credit-saving settings
        self.max_tokens = 150  # Very short responses only
        self.timeout = 10      # Quick timeout to save time
        self.temperature = 0.1 # Minimal creativity for factual responses

class APIManager:
    """Simple API key rotation"""
    def __init__(self, api_keys: List[str]):
        self.keys = api_keys
        self.current = 0
        self.failures = set()
    
    def get_key(self) -> str:
        # Reset failures if all keys failed
        if len(self.failures) >= len(self.keys):
            self.failures.clear()
        
        # Find working key
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

class StatsTracker:
    """Simple statistics tracking"""
    def __init__(self):
        self.queries_answered = 0
        self.api_calls_made = 0
        self.failed_responses = 0
        self.start_time = datetime.now()
        self.total_tokens_used = 0  # Estimated
    
    def increment_query(self):
        self.queries_answered += 1
    
    def increment_api_call(self, estimated_tokens: int = 0):
        self.api_calls_made += 1
        self.total_tokens_used += estimated_tokens
    
    def increment_failure(self):
        self.failed_responses += 1
    
    def get_stats_message(self) -> str:
        uptime = datetime.now() - self.start_time
        uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds//60)%60}m"
        
        return f"""📊 **Bot Statistics**

🔢 **Queries Answered:** {self.queries_answered}
🤖 **API Calls Made:** {self.api_calls_made}
❌ **Failed Responses:** {self.failed_responses}
🧮 **Est. Tokens Used:** {self.total_tokens_used:,}
⏱️ **Uptime:** {uptime_str}"""

class TruthFocusedBot:
    """Credit-efficient, truth-focused Telegram bot"""
    
    def __init__(self):
        self.config = Config()
        self.api_manager = APIManager(self.config.api_keys)
        self.stats = StatsTracker()
        
        # Bot mention pattern - exact match only
        self.bot_mention_pattern = re.compile(
            rf'@{re.escape(self.config.bot_username)}\b', 
            re.IGNORECASE
        )
        
        # HTTP session for API calls
        self.session = None
        
        # Telethon client
        session = StringSession(self.config.string_session) if self.config.string_session else StringSession()
        self.client = TelegramClient(session, self.config.api_id, self.config.api_hash)
        
        # Ultra-focused system prompt for truth and brevity
        self.system_prompt = """You are a factual assistant that gives extremely short, truthful answers.

RULES:
- Answer in 1-2 sentences maximum
- Only state facts you're certain about
- If uncertain, say "I can't answer that truthfully"
- No speculation, guessing, or creative responses
- Be direct and concise
- No pleasantries or filler words"""
        
        self.bot_user_id = None
        self.shutdown_flag = False
        
        print(f"🤖 Truth Bot initialized with {len(self.config.api_keys)} API keys")
    
    async def start(self):
        """Start the bot"""
        try:
            # Create HTTP session
            connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
            
            # Start Telegram client
            await self.client.start()
            me = await self.client.get_me()
            self.bot_user_id = me.id
            
            print(f"✅ Bot started as @{me.username}")
            print(f"🎯 Mode: Truth-focused, credit-efficient")
            print(f"🔧 Triggers: @mentions, replies to bot, /stats in DM")
            
            # Save session if new
            if not self.config.string_session:
                session_string = self.client.session.save()
                with open('.env', 'a') as f:
                    f.write(f"\nSTRING_SESSION={session_string}")
                print("💾 Session saved")
            
            # Register event handler
            @self.client.on(events.NewMessage(incoming=True))
            async def handle_message(event):
                if not self.shutdown_flag:
                    await self.process_message(event)
            
            # Setup shutdown handler
            def shutdown_handler(signum, frame):
                print("\n🛑 Shutting down...")
                self.shutdown_flag = True
                asyncio.create_task(self.shutdown())
            
            signal.signal(signal.SIGINT, shutdown_handler)
            signal.signal(signal.SIGTERM, shutdown_handler)
            
            print("🚀 Bot running! Only responds when explicitly triggered.")
            
            # Keep running
            while not self.shutdown_flag:
                await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Startup error: {e}")
            raise
        finally:
            await self.cleanup()
    
    async def process_message(self, event):
        """Process messages - only trigger when explicitly needed"""
        try:
            # Fast exit conditions - save processing
            if (self.shutdown_flag or 
                not event.raw_text or 
                event.sender_id == self.bot_user_id):
                return
            
            # Get basic info
            text = event.raw_text.strip()
            user_id = event.sender_id
            chat_id = event.chat_id
            is_group = event.is_group
            is_channel = event.is_channel
            
            # Skip channels entirely
            if is_channel:
                return
            
            # Skip bot messages
            try:
                sender = await event.get_sender()
                if hasattr(sender, 'bot') and sender.bot:
                    return
            except:
                return
            
            # TRIGGER DETECTION - This is where we save credits!
            should_respond = False
            trigger_type = None
            
            if not is_group:
                # DM: Only respond to /stats command
                if text.lower().startswith('/stats'):
                    should_respond = True
                    trigger_type = "stats_command"
            else:
                # GROUP: Only respond to mentions or replies to bot
                
                # Check for bot mention
                if self.bot_mention_pattern.search(text):
                    should_respond = True
                    trigger_type = "mention"
                
                # Check if it's a reply to bot message
                elif event.is_reply:
                    try:
                        reply_msg = await event.get_reply_message()
                        if reply_msg and reply_msg.sender_id == self.bot_user_id:
                            should_respond = True
                            trigger_type = "reply_to_bot"
                    except:
                        pass  # Ignore reply check errors
            
            # EXIT EARLY IF NOT TRIGGERED - Save credits!
            if not should_respond:
                return
            
            print(f"🎯 Triggered: {trigger_type} from user {user_id}")
            
            # Handle the triggered response
            await self.handle_triggered_message(event, text, trigger_type, is_group)
            
        except Exception as e:
            logger.error(f"Message processing error: {e}")
    
    async def handle_triggered_message(self, event, text: str, trigger_type: str, is_group: bool):
        """Handle messages that passed trigger detection"""
        try:
            # Handle /stats command (DM only)
            if trigger_type == "stats_command":
                await event.reply(self.stats.get_stats_message())
                return
            
            # Clean the query for AI processing
            if is_group and trigger_type == "mention":
                # Remove bot mention from query
                query = self.bot_mention_pattern.sub('', text).strip()
            else:
                query = text.strip()
            
            # Empty query check
            if not query:
                await event.reply("I can't answer that truthfully.")
                self.stats.increment_failure()
                return
            
            # Get AI response - this is our only API call
            response = await self.get_truthful_response(query)
            
            # Send response
            await event.reply(response)
            self.stats.increment_query()
            
        except Exception as e:
            logger.error(f"Triggered message handling error: {e}")
            try:
                await event.reply("I can't answer that truthfully.")
                self.stats.increment_failure()
            except:
                pass
    
    async def get_truthful_response(self, query: str) -> str:
        """Get truthful, concise AI response"""
        for attempt in range(2):  # Max 2 attempts
            try:
                api_key = self.api_manager.get_key()
                
                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": query}
                ]
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": "deepseek/deepseek-r1-0528:free",
                    "messages": messages,
                    "max_tokens": self.config.max_tokens,
                    "temperature": self.config.temperature,
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
                            
                            ai_response = result['choices'][0]['message']['content'].strip()
                            
                            # Estimate tokens used (rough calculation)
                            estimated_tokens = len(query.split()) + len(ai_response.split()) + 50
                            self.stats.increment_api_call(estimated_tokens)
                            
                            # Ensure response is concise
                            if len(ai_response) > 300:  # Truncate if too long
                                ai_response = ai_response[:297] + "..."
                            
                            return ai_response
                    
                    # API error
                    self.api_manager.mark_failure(api_key)
                    await asyncio.sleep(0.1)  # Brief delay before retry
                    
            except Exception as e:
                self.api_manager.mark_failure(self.api_manager.get_key())
                if attempt == 1:  # Last attempt
                    logger.error(f"AI API failed: {e}")
                    self.stats.increment_failure()
                    return "I can't answer that truthfully."
                
                await asyncio.sleep(0.1)
        
        return "I can't answer that truthfully."
    
    async def shutdown(self):
        """Graceful shutdown"""
        print("🔄 Shutting down...")
        print(f"📊 Final stats: {self.stats.queries_answered} queries, {self.stats.api_calls_made} API calls")
        self.shutdown_flag = True
    
    async def cleanup(self):
        """Cleanup resources"""
        try:
            if self.session:
                await self.session.close()
            if self.client.is_connected():
                await self.client.disconnect()
            print("✅ Cleanup completed")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

async def main():
    """Main function"""
    bot = None
    try:
        bot = TruthFocusedBot()
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
    # Optimize for Windows if needed
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Failed to start: {e}")
        sys.exit(1)
