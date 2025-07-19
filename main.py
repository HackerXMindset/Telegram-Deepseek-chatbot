from telethon import TelegramClient, events
from telethon.sessions import StringSession
import logging
import os
from dotenv import load_dotenv
import asyncio
import sys
import aiohttp
import time
import signal
import re

# Load environment variables
load_dotenv()

# Minimal logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

class SimpleConfig:
    def __init__(self):
        self.api_id = int(os.environ['API_ID'])
        self.api_hash = os.environ['API_HASH']
        self.string_session = os.environ.get('STRING_SESSION', '')
        self.bot_username = os.environ['BOT_USERNAME'].lower().replace('@', '')
        
        # API keys
        api_keys_str = os.environ.get('API_KEYS', os.environ.get('API_KEY', ''))
        self.api_keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]
        
        # Performance settings
        self.timeout = 15
        self.max_tokens = 500  # Short responses

class APIManager:
    def __init__(self, api_keys):
        self.keys = api_keys
        self.current = 0
        self.failures = set()
    
    def get_key(self):
        if len(self.failures) >= len(self.keys):
            self.failures.clear()
        
        for _ in range(len(self.keys)):
            key = self.keys[self.current]
            if key not in self.failures:
                return key
            self.current = (self.current + 1) % len(self.keys)
        
        return self.keys[0]
    
    def mark_failure(self, key):
        self.failures.add(key)
    
    def mark_success(self, key):
        self.failures.discard(key)

class SimpleBot:
    def __init__(self):
        self.config = SimpleConfig()
        self.api_manager = APIManager(self.config.api_keys)
        self.session = None
        self.bot_user_id = None
        self.shutdown_flag = False
        
        # Simple system prompt for truth and brevity
        self.system_prompt = """You are a helpful AI that gives precise, accurate, and truthful answers. 
        
        Rules:
        - Keep answers as SHORT as possible
        - Be ACCURATE and factual only
        - Tell the TRUTH, admit if you don't know something
        - No fluff or unnecessary words
        - Be direct and to the point
        - If uncertain, say so clearly"""
        
        # Stats
        self.stats = {
            'messages_processed': 0,
            'api_calls': 0,
            'start_time': time.time()
        }
        
        # Initialize client
        session = StringSession(self.config.string_session) if self.config.string_session else StringSession()
        self.client = TelegramClient(session, self.config.api_id, self.config.api_hash)
        
        # Bot mention pattern (fixed)
        self.mention_pattern = re.compile(rf'@{re.escape(self.config.bot_username)}', re.IGNORECASE)
    
    async def start(self):
        try:
            # Create HTTP session
            connector = aiohttp.TCPConnector(limit=50, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
            
            # Start Telegram client
            await self.client.start()
            me = await self.client.get_me()
            self.bot_user_id = me.id
            
            print(f"🤖 Simple Truth Bot started as @{me.username}")
            print(f"🎯 Mode: Fast, Accurate, Brief responses")
            
            # Save session if new
            if not self.config.string_session:
                session_string = self.client.session.save()
                with open('.env', 'a') as f:
                    f.write(f"\nSTRING_SESSION={session_string}")
                print("💾 Session saved")
            
            # Message handler
            @self.client.on(events.NewMessage(incoming=True))
            async def handle_message(event):
                await self.process_message(event)
            
            # Shutdown handler
            def shutdown_handler(signum, frame):
                print("\n🛑 Shutting down...")
                self.shutdown_flag = True
            
            signal.signal(signal.SIGINT, shutdown_handler)
            signal.signal(signal.SIGTERM, shutdown_handler)
            
            print("✅ Bot running! Press Ctrl+C to stop")
            
            while not self.shutdown_flag:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Startup error: {e}")
            raise
        finally:
            await self.cleanup()
    
    async def process_message(self, event):
        try:
            # Skip if bot message or empty
            if (self.shutdown_flag or 
                not event.raw_text or 
                event.sender_id == self.bot_user_id):
                return
            
            # Skip bots
            try:
                sender = await event.get_sender()
                if hasattr(sender, 'bot') and sender.bot:
                    return
            except:
                return
            
            text = event.raw_text.strip()
            user_id = event.sender_id
            is_group = event.is_group
            
            self.stats['messages_processed'] += 1
            
            # Handle /stats command (DM only)
            if text.lower() == '/stats' and not is_group:
                await self.send_stats(event)
                return
            
            should_respond = False
            
            if is_group:
                # In groups: only respond to mentions or replies
                is_mentioned = bool(self.mention_pattern.search(text))
                is_reply_to_bot = False
                
                # Check if replying to bot
                try:
                    if event.is_reply:
                        reply_msg = await event.get_reply_message()
                        if reply_msg and reply_msg.sender_id == self.bot_user_id:
                            is_reply_to_bot = True
                except:
                    pass
                
                should_respond = is_mentioned or is_reply_to_bot
                
                # Remove mention from text
                if is_mentioned:
                    text = self.mention_pattern.sub('', text).strip()
            else:
                # In DMs: respond to everything except commands
                should_respond = True
            
            if should_respond and text:
                await self.handle_query(event, text)
                
        except Exception as e:
            logger.error(f"Message processing error: {e}")
    
    async def send_stats(self, event):
        """Send bot statistics (DM only)"""
        uptime = int(time.time() - self.stats['start_time'])
        hours = uptime // 3600
        minutes = (uptime % 3600) // 60
        
        stats_text = f"""📊 **Bot Statistics**

🔢 Messages processed: {self.stats['messages_processed']}
🧠 AI responses: {self.stats['api_calls']}
⏱️ Uptime: {hours}h {minutes}m
🔑 Active API keys: {len(self.config.api_keys) - len(self.api_manager.failures)}/{len(self.config.api_keys)}"""
        
        await event.reply(stats_text)
    
    async def handle_query(self, event, query):
        """Handle user query with AI"""
        try:
            # Show typing
            try:
                async with self.client.action(event.chat_id, 'typing'):
                    response = await self.get_ai_response(query)
                    await event.reply(response)
            except:
                # Fallback without typing
                response = await self.get_ai_response(query)
                await event.reply(response)
                
        except Exception as e:
            logger.error(f"Query handling error: {e}")
            try:
                await event.reply("Error processing request.")
            except:
                pass
    
    async def get_ai_response(self, query):
        """Get AI response - fast and accurate"""
        for attempt in range(2):
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
                    "temperature": 0.1,  # Low temperature for accuracy
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
                            self.stats['api_calls'] += 1
                            return result['choices'][0]['message']['content'].strip()
                    
                    # Handle API errors
                    error_text = await response.text()
                    raise Exception(f"API error {response.status}")
                    
            except Exception as e:
                self.api_manager.mark_failure(api_key)
                if attempt == 1:
                    logger.error(f"AI API failed: {e}")
                    return "Unable to process request at the moment."
                
                await asyncio.sleep(0.5)
        
        return "Service temporarily unavailable."
    
    async def cleanup(self):
        """Cleanup resources"""
        print("🧹 Cleaning up...")
        try:
            if self.session:
                await self.session.close()
            if self.client.is_connected():
                await self.client.disconnect()
            print("✅ Cleanup completed")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

async def main():
    bot = None
    try:
        bot = SimpleBot()
        await bot.start()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    finally:
        if bot:
            await bot.cleanup()
    return 0

if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Failed to start: {e}")
        sys.exit(1)
