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
import random

# Load environment variables
load_dotenv()

# Minimal logging setup
logging.basicConfig(
    level=logging.WARNING,
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
        self.context_size = 5  # Increased for more human-like responses
        self.rate_limit = 1    # Faster response time
        self.timeout = 30
        self.max_tokens = 1500 # Increased for more natural responses
        
        # More lenient settings for human-like behavior
        self.min_query_length = 1  # Respond to single characters too
        self.ignored_patterns = [
            # Much more lenient - only ignore obvious spam
            r'^[.]{3,}$',  # Only dots
            r'^[!]{3,}$',  # Only exclamations
        ]

class FastAPIManager:
    """Lightweight API key manager with minimal overhead"""
    def __init__(self, api_keys: List[str]):
        self.keys = api_keys
        self.current = 0
        self.failures = set()
        self.request_count = 0
    
    def get_key(self) -> str:
        if len(self.failures) >= len(self.keys):
            self.failures.clear()
        
        for _ in range(len(self.keys)):
            key = self.keys[self.current]
            if key not in self.failures:
                return key
            self.current = (self.current + 1) % len(self.keys)
        
        return self.keys[0]
    
    def mark_failure(self, key: str):
        self.failures.add(key)
        self.current = (self.current + 1) % len(self.keys)
    
    def mark_success(self, key: str):
        self.failures.discard(key)
        self.request_count += 1
    
    def get_usage_stats(self) -> str:
        return f"API calls made: {self.request_count}, Active keys: {len(self.keys) - len(self.failures)}/{len(self.keys)}"

class HumanContext:
    """Human-like context manager with personality"""
    def __init__(self, max_size: int = 5):
        self.user_history = defaultdict(lambda: deque(maxlen=max_size))
        self.group_history = defaultdict(lambda: deque(maxlen=max_size))
        self.user_preferences = defaultdict(dict)  # Remember user preferences
        self.conversation_moods = defaultdict(str)  # Track conversation mood
    
    def add_message(self, user_id: int, chat_id: int, text: str, username: str = None):
        # Store full context for more human-like responses
        timestamp = time.strftime("%H:%M")
        msg = {
            'user': username or 'User',
            'text': text,
            'time': timestamp,
            'length': len(text),
            'has_questions': '?' in text,
            'mood': self.detect_mood(text)
        }
        
        self.user_history[user_id].append(msg)
        if chat_id != user_id:
            self.group_history[chat_id].append(msg)
        
        # Update conversation mood
        if msg['mood']:
            self.conversation_moods[user_id] = msg['mood']
    
    def detect_mood(self, text: str) -> str:
        """Detect the mood/tone of the message"""
        text_lower = text.lower()
        
        # Positive indicators
        positive_words = ['happy', 'great', 'awesome', 'good', 'nice', 'love', 'thanks', 'lol', 'haha', '😊', '😄', '👍']
        if any(word in text_lower for word in positive_words):
            return 'positive'
        
        # Negative indicators  
        negative_words = ['sad', 'bad', 'terrible', 'hate', 'angry', 'stupid', 'wtf', 'damn', '😢', '😠', '👎']
        if any(word in text_lower for word in negative_words):
            return 'negative'
        
        # Excited indicators
        if '!' in text or text.isupper() or any(word in text_lower for word in ['wow', 'omg', 'amazing']):
            return 'excited'
        
        # Question indicators
        if '?' in text:
            return 'curious'
            
        return 'neutral'
    
    def get_context(self, user_id: int, chat_id: int) -> str:
        """Get human-like context"""
        context_parts = []
        
        # Get recent conversation flow
        if chat_id != user_id and self.group_history[chat_id]:
            recent_group = list(self.group_history[chat_id])[-3:]
            for msg in recent_group:
                context_parts.append(f"{msg['user']}: {msg['text']}")
        
        if self.user_history[user_id]:
            recent_user = list(self.user_history[user_id])[-2:]
            for msg in recent_user:
                context_parts.append(f"{msg['user']}: {msg['text']}")
        
        # Add mood context
        mood = self.conversation_moods.get(user_id, 'neutral')
        if mood != 'neutral':
            context_parts.append(f"[Conversation mood: {mood}]")
        
        return " | ".join(context_parts[-4:]) if context_parts else ""

class HumanRateLimit:
    """Human-like rate limiting - more natural timing"""
    def __init__(self, limit_seconds: int = 1):
        self.limit = limit_seconds
        self.last_request = {}
        self.conversation_state = defaultdict(dict)  # Track ongoing conversations
    
    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        
        # More lenient for active conversations
        if user_id in self.last_request:
            time_diff = now - self.last_request[user_id]
            
            # Allow faster responses in active conversations (under 30 seconds)
            if time_diff < 30:
                min_wait = 0.5  # Very quick responses like humans
            else:
                min_wait = self.limit
                
            if time_diff < min_wait:
                return False
        
        self.last_request[user_id] = now
        return True

class HumanTriggerSystem:
    """More human-like trigger system - respond to almost everything naturally"""
    def __init__(self, config: FastConfig):
        self.config = config
        self.ignored_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in config.ignored_patterns]
        self.last_responses = defaultdict(lambda: deque(maxlen=3))
        
        # Human-like response patterns
        self.greeting_responses = [
            "Hey there! 👋", "Hello! How's it going?", "Hi! What's up?", 
            "Hey! 😊", "Hello there!", "Hi! Good to see you!",
            "Hey! How are you doing?", "Hi! What's happening?", "Hello! 😊"
        ]
        
        self.acknowledgments = [
            "Got it!", "I see", "Ah, okay", "Right", "Makes sense",
            "Gotcha", "I understand", "Yep", "Alright", "Fair enough"
        ]
        
        self.thinking_responses = [
            "Hmm, let me think...", "That's interesting...", "Good question...",
            "Let me see...", "Interesting point...", "That makes me wonder..."
        ]
    
    def should_trigger_ai(self, query: str, user_id: int, is_group: bool) -> tuple[bool, str]:
        """Much more permissive - respond like a human would"""
        query = query.strip()
        
        # Only ignore very obvious spam
        for pattern in self.ignored_patterns:
            if pattern.match(query):
                return False, "Obvious spam"
        
        # Respond to almost everything, even single letters or simple words
        if len(query) >= 1:
            return True, "Valid human interaction"
        
        return False, "Empty message"
    
    def get_quick_human_response(self, query: str, user_id: int) -> Optional[str]:
        """Generate human-like quick responses"""
        query_lower = query.lower().strip()
        
        # Greetings - but make them feel natural and varied
        greetings = ['hi', 'hello', 'hey', 'sup', 'yo', 'hii', 'helloo', 'heyy']
        if query_lower in greetings:
            response = random.choice(self.greeting_responses)
            # Add some personality variations
            if random.random() < 0.3:
                response += " How can I help you today?"
            return response
        
        # Single letters or short responses
        if len(query) <= 2:
            responses = [
                "?", "What's that about?", "Hmm?", "Go on...", 
                "I'm listening 😊", "Tell me more", "Yeah?"
            ]
            return random.choice(responses)
        
        # Common short phrases
        short_phrases = {
            'ok': random.choice(["Cool!", "Alright!", "Got it!", "👍"]),
            'okay': random.choice(["Sure thing!", "Alright then!", "Sounds good!"]),
            'thanks': random.choice(["You're welcome! 😊", "No problem!", "Anytime!", "Happy to help!"]),
            'lol': random.choice(["😄", "Haha right?", "😂", "I know right!"]),
            'wtf': random.choice(["I know right?", "That's crazy!", "Seriously?!"]),
            'wow': random.choice(["I know right!", "Pretty amazing!", "Right?!", "Incredible!"]),
        }
        
        if query_lower in short_phrases:
            return short_phrases[query_lower]
        
        return None

class UltraHumanBot:
    """Ultra-human-like Telegram bot"""
    
    def __init__(self):
        self.config = FastConfig()
        self.api_manager = FastAPIManager(self.config.api_keys)
        self.context = HumanContext(self.config.context_size)
        self.rate_limit = HumanRateLimit(self.config.rate_limit)
        self.trigger_system = HumanTriggerSystem(self.config)
        
        # More flexible bot mention pattern
        self.bot_mention_pattern = re.compile(
            rf'\b{re.escape(self.config.bot_username)}\b', 
            re.IGNORECASE
        )
        
        # Create persistent HTTP session
        self.session = None
        
        # Initialize Telethon client
        session = StringSession(self.config.string_session) if self.config.string_session else StringSession()
        self.client = TelegramClient(session, self.config.api_id, self.config.api_hash)
        
        # More human-like system prompt
        self.system_prompt = """You are a friendly, helpful human having a natural conversation. 
        
        IMPORTANT: Reply exactly like a real human would - casual, natural, with personality. Use:
        - Natural speech patterns and contractions (I'm, you're, can't, etc.)
        - Casual language and slang when appropriate  
        - Emojis occasionally but don't overdo it
        - Show curiosity, ask follow-up questions
        - Be conversational, not robotic or formal
        - Match the energy and tone of the person you're talking to
        - Use "I" statements and personal touches
        - Keep responses concise but engaging
        
        You're not an AI assistant - you're just a helpful person in a chat. Be genuine, relatable, and human."""
        
        self.bot_user_id = None
        self.shutdown_flag = False
        self.loop = None
        
        # Statistics tracking
        self.stats = {
            'messages_processed': 0,
            'human_responses': 0,
            'api_calls_made': 0,
            'errors_handled': 0
        }
    
    async def start(self):
        """Start the bot with optimal performance settings"""
        try:
            self.loop = asyncio.get_running_loop()
            
            # Create persistent HTTP session
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
            
            print(f"🤖 Ultra-Human Bot started as @{me.username}")
            print(f"💬 Now responding like a real human!")
            print(f"🔧 Reply detection fixed and enhanced")
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
                      f"{self.stats['api_calls_made']} AI responses, "
                      f"{self.stats['human_responses']} quick human responses!")
    
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
                return True, None
            
            if hasattr(sender, 'bot'):
                return sender.bot, getattr(sender, 'username', None)
            elif isinstance(sender, (Channel, Chat)):
                return False, getattr(sender, 'username', None)
            else:
                return False, None
        except Exception as e:
            logger.warning(f"Error getting sender info: {e}")
            return False, None
    
    async def process_message(self, event):
        """Process messages with enhanced reply detection"""
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
                
                if is_bot:
                    return
                    
            except Exception as e:
                logger.warning(f"Could not get sender info: {e}")
                return
            
            text = event.raw_text
            user_id = event.sender_id
            chat_id = event.chat_id
            is_group = event.is_group
            is_channel = event.is_channel
            
            self.stats['messages_processed'] += 1
            
            # Skip channels
            if is_channel:
                return
            
            # Always update context
            self.context.add_message(user_id, chat_id, text, username)
            
            # Enhanced reply detection and response logic
            should_respond = False
            is_mention = False
            is_reply_to_bot = False
            
            if is_group:
                # Check for mentions
                is_mention = bool(self.bot_mention_pattern.search(text))
                
                # Enhanced reply detection
                try:
                    if event.is_reply:
                        reply_msg = await event.get_reply_message()
                        if reply_msg and reply_msg.sender_id == self.bot_user_id:
                            is_reply_to_bot = True
                            print(f"🔄 Detected reply to bot from {username} in group")
                except Exception as e:
                    print(f"⚠️ Reply check error: {e}")
                    # Don't fail completely, just log the error
                
                should_respond = is_mention or is_reply_to_bot
                
                if should_respond:
                    print(f"📨 Group response triggered: mention={is_mention}, reply={is_reply_to_bot}")
            else:
                # In DMs: respond to everything
                should_respond = True
                print(f"💬 DM from {username}")
            
            if not should_respond:
                return
            
            # Rate limiting with human-like timing
            if not self.rate_limit.is_allowed(user_id):
                return
            
            # Process query asynchronously
            asyncio.create_task(self.handle_query(event, user_id, chat_id, text, username, is_group))
            
        except Exception as e:
            self.stats['errors_handled'] += 1
            logger.error(f"Message processing error: {e}")
    
    async def handle_query(self, event, user_id: int, chat_id: int, text: str, username: str, is_group: bool):
        """Handle user query with human-like responses"""
        try:
            # Clean query
            if is_group:
                query = self.bot_mention_pattern.sub('', text).strip()
            else:
                query = text.strip()
                
            if not query:
                # Even empty queries get a human response
                responses = ["Yeah?", "What's up?", "I'm here 😊", "?"]
                await event.reply(random.choice(responses))
                return
            
            # Check if we should use a quick human response
            quick_response = self.trigger_system.get_quick_human_response(query, user_id)
            
            if quick_response and random.random() < 0.7:  # 70% chance to use quick response for simple things
                self.stats['human_responses'] += 1
                # Add natural delay like humans
                await asyncio.sleep(random.uniform(0.5, 2.0))
                await event.reply(quick_response)
                return
            
            # For more complex queries, use AI with human-like context
            context = self.context.get_context(user_id, chat_id)
            
            # Show typing with natural variation
            typing_delay = random.uniform(1.0, 3.0)  # Vary typing time like humans
            
            try:
                async with self.client.action(event.chat_id, 'typing'):
                    await asyncio.sleep(typing_delay)
                    response = await self.get_ai_response(query, context, username)
                    await event.reply(response)
            except:
                # Fallback without typing indicator
                await asyncio.sleep(typing_delay)
                response = await self.get_ai_response(query, context, username)
                await event.reply(response)
                
        except Exception as e:
            self.stats['errors_handled'] += 1
            logger.error(f"Query handling error: {e}")
            try:
                # Even errors get human-like responses
                error_responses = [
                    "Oops, something went wrong 😅", 
                    "Sorry, had a brain freeze there",
                    "My bad, can you try that again?",
                    "Hmm, something's not working right"
                ]
                await event.reply(random.choice(error_responses))
            except:
                pass
    
    async def get_ai_response(self, query: str, context: str, username: str = None) -> str:
        """Get AI response with human personality"""
        for attempt in range(2):
            try:
                api_key = self.api_manager.get_key()
                
                # Enhanced message structure for more human responses
                messages = [{"role": "system", "content": self.system_prompt}]
                
                if context:
                    messages.append({
                        "role": "system", 
                        "content": f"Recent conversation context: {context}"
                    })
                
                if username:
                    messages.append({
                        "role": "system",
                        "content": f"You're chatting with {username}. Be natural and friendly."
                    })
                
                messages.append({"role": "user", "content": query})
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "model": "deepseek/deepseek-r1-0528:free",
                    "messages": messages,
                    "max_tokens": self.config.max_tokens,
                    "temperature": 0.8,  # Higher temperature for more human-like variety
                    "stream": False,
                    "presence_penalty": 0.6,  # Encourage more varied responses
                    "frequency_penalty": 0.3   # Reduce repetition
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
                            ai_response = result['choices'][0]['message']['content'].strip()
                            
                            # Post-process to make it even more human
                            return self.humanize_response(ai_response)
                    
                    error_text = await response.text()
                    raise Exception(f"API error {response.status}: {error_text[:100]}")
                    
            except Exception as e:
                current_key = self.api_manager.get_key()
                self.api_manager.mark_failure(current_key)
                if attempt == 1:
                    self.stats['errors_handled'] += 1
                    logger.error(f"AI API failed: {e}")
                    return random.choice([
                        "Sorry, I'm having trouble thinking right now 😅",
                        "My brain's a bit slow today, can you try again?",
                        "Hmm, something's not clicking for me right now"
                    ])
                
                await asyncio.sleep(0.5)
        
        return "Sorry, I'm having some technical difficulties 😅"
    
    def humanize_response(self, response: str) -> str:
        """Make AI responses even more human-like"""
        # Remove overly formal language
        response = response.replace("I'd be happy to help", "I can help with that")
        response = response.replace("I understand that", "I get that")
        response = response.replace("However,", "But")
        response = response.replace("Additionally,", "Also,")
        response = response.replace("Furthermore,", "And")
        
        # Add more casual touches occasionally
        if random.random() < 0.2:  # 20% chance
            casual_starters = ["Honestly,", "To be honest,", "I mean,", "Well,", "You know,"]
            if not any(response.lower().startswith(starter.lower()) for starter in casual_starters):
                response = f"{random.choice(casual_starters)} {response.lower()}"
        
        # Ensure first letter is capitalized
        if response:
            response = response[0].upper() + response[1:]
        
        return response
    
    async def cleanup(self):
        """Cleanup with stats"""
        print("🧹 Starting cleanup...")
        try:
            print(f"📊 Final Statistics:")
            print(f"   Messages processed: {self.stats['messages_processed']}")
            print(f"   AI responses: {self.stats['api_calls_made']}")
            print(f"   Human-like quick responses: {self.stats['human_responses']}")
            print(f"   Errors handled: {self.stats['errors_handled']}")
            
            if self.session:
                await self.session.close()
            if self.client.is_connected():
                await self.client.disconnect()
            print("✅ Cleanup completed")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

# Main function
async def main():
    bot = None
    try:
        bot = UltraHumanBot()
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
