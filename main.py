#!/usr/bin/env python3
"""
Enhanced Telegram Bot with improved features:
- Multiple API key support with automatic failover
- Increased context window (last 10 messages per user)
- Group conversation context tracking
- Robust error handling and recovery
- Advanced rate limiting
- Better logging and monitoring
- Configuration validation
- Graceful shutdown handling
"""

from telethon import TelegramClient, events
from telethon.sessions import StringSession
import requests
import logging
import os
from dotenv import load_dotenv
import json
import asyncio
import sys
from collections import defaultdict, deque
import aiohttp
import time
import random
import signal
from typing import List, Dict, Optional, Tuple
import re
from datetime import datetime, timedelta
import traceback

# Load environment variables from .env file
load_dotenv()

# Enhanced logging configuration
def setup_logging():
    """Setup comprehensive logging with rotation"""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # File handler for detailed logs
    file_handler = logging.FileHandler('bot_detailed.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    
    # Console handler for important messages
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    
    # Error file handler
    error_handler = logging.FileHandler('bot_errors.log', encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.addHandler(error_handler)
    
    return logger

logger = setup_logging()

class ConfigManager:
    """Manages configuration and validation"""
    
    def __init__(self):
        self.api_id = os.environ.get('API_ID')
        self.api_hash = os.environ.get('API_HASH')
        self.string_session = os.environ.get('STRING_SESSION', '')
        self.bot_username = os.environ.get('BOT_USERNAME')
        
        # Support multiple API keys (comma-separated)
        api_keys_str = os.environ.get('API_KEYS', os.environ.get('API_KEY', ''))
        self.api_keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]
        
        # Advanced configuration
        self.max_context_messages = int(os.environ.get('MAX_CONTEXT_MESSAGES', '10'))
        self.group_context_messages = int(os.environ.get('GROUP_CONTEXT_MESSAGES', '5'))
        self.rate_limit_seconds = int(os.environ.get('RATE_LIMIT_SECONDS', '3'))
        self.max_concurrent_requests = int(os.environ.get('MAX_CONCURRENT_REQUESTS', '10'))
        self.api_timeout = int(os.environ.get('API_TIMEOUT', '60'))
        self.retry_attempts = int(os.environ.get('RETRY_ATTEMPTS', '3'))
        
        self.validate()
    
    def validate(self):
        """Validate all required configuration"""
        missing_config = []
        
        if not self.api_id:
            missing_config.append('API_ID')
        if not self.api_hash:
            missing_config.append('API_HASH')
        if not self.api_keys:
            missing_config.append('API_KEYS or API_KEY')
        if not self.bot_username:
            missing_config.append('BOT_USERNAME')
        
        if missing_config:
            logger.error(f"Missing required configuration: {', '.join(missing_config)}")
            logger.error("Please ensure .env file contains all required variables")
            sys.exit(1)
        
        # Normalize bot username
        self.bot_username_normalized = self.bot_username.lower().replace('@', '')
        
        logger.info("Configuration validated successfully")
        logger.info(f"API Keys available: {len(self.api_keys)}")
        logger.info(f"Max context messages: {self.max_context_messages}")
        logger.info(f"Group context messages: {self.group_context_messages}")

class APIKeyManager:
    """Manages multiple API keys with automatic failover"""
    
    def __init__(self, api_keys: List[str]):
        self.api_keys = api_keys
        self.current_key_index = 0
        self.failed_keys = set()
        self.key_usage_count = defaultdict(int)
        self.key_last_used = defaultdict(float)
        self.key_error_count = defaultdict(int)
        logger.info(f"Initialized API key manager with {len(api_keys)} keys")
    
    def get_current_key(self) -> str:
        """Get the current active API key"""
        if len(self.failed_keys) >= len(self.api_keys):
            # All keys failed, reset failed keys (maybe they're working again)
            logger.warning("All API keys failed, resetting failure status")
            self.failed_keys.clear()
            self.key_error_count.clear()
        
        # Find next working key
        attempts = 0
        while attempts < len(self.api_keys):
            key = self.api_keys[self.current_key_index]
            if key not in self.failed_keys:
                return key
            
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            attempts += 1
        
        # Fallback to first key if all seem failed
        return self.api_keys[0]
    
    def mark_key_success(self, key: str):
        """Mark API key as successful"""
        if key in self.failed_keys:
            self.failed_keys.discard(key)
            logger.info(f"API key {key[:8]}... recovered from failure")
        
        self.key_usage_count[key] += 1
        self.key_last_used[key] = time.time()
        self.key_error_count[key] = max(0, self.key_error_count[key] - 1)
    
    def mark_key_failure(self, key: str, error: str):
        """Mark API key as failed"""
        self.key_error_count[key] += 1
        
        # Mark as failed if too many consecutive errors
        if self.key_error_count[key] >= 3:
            self.failed_keys.add(key)
            logger.error(f"API key {key[:8]}... marked as failed after {self.key_error_count[key]} errors")
        
        # Switch to next key
        self.switch_key()
        logger.warning(f"Switched to next API key due to error: {error}")
    
    def switch_key(self):
        """Switch to next available API key"""
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
    
    def get_key_stats(self) -> Dict:
        """Get usage statistics for all keys"""
        return {
            'total_keys': len(self.api_keys),
            'active_keys': len(self.api_keys) - len(self.failed_keys),
            'failed_keys': len(self.failed_keys),
            'usage_count': dict(self.key_usage_count),
            'error_count': dict(self.key_error_count)
        }

class ContextManager:
    """Enhanced context management for users and groups"""
    
    def __init__(self, max_user_messages: int, max_group_messages: int):
        self.max_user_messages = max_user_messages
        self.max_group_messages = max_group_messages
        
        # User-specific message history
        self.user_message_history = defaultdict(lambda: deque(maxlen=max_user_messages))
        
        # Group conversation context (last N messages from any user in the group)
        self.group_context = defaultdict(lambda: deque(maxlen=max_group_messages))
        
        # Track user activity
        self.user_last_activity = defaultdict(float)
        
        logger.info(f"Context manager initialized: {max_user_messages} user messages, {max_group_messages} group messages")
    
    def add_user_message(self, user_id: int, message: str, username: str = None):
        """Add message to user's personal history"""
        timestamp = datetime.now().strftime("%H:%M")
        formatted_message = f"[{timestamp}] {message}"
        
        self.user_message_history[user_id].append(formatted_message)
        self.user_last_activity[user_id] = time.time()
        
        logger.debug(f"Added message to user {user_id} history. Total: {len(self.user_message_history[user_id])}")
    
    def add_group_message(self, chat_id: int, user_id: int, message: str, username: str = None):
        """Add message to group conversation context"""
        timestamp = datetime.now().strftime("%H:%M")
        user_display = f"@{username}" if username else f"User_{user_id}"
        formatted_message = f"[{timestamp}] {user_display}: {message}"
        
        self.group_context[chat_id].append(formatted_message)
        
        logger.debug(f"Added message to group {chat_id} context. Total: {len(self.group_context[chat_id])}")
    
    def get_user_context(self, user_id: int) -> str:
        """Get user's personal message history"""
        messages = list(self.user_message_history[user_id])
        if not messages:
            return ""
        
        context = "User's recent messages:\n"
        for msg in messages:
            context += f"• {msg}\n"
        
        return context
    
    def get_group_context(self, chat_id: int) -> str:
        """Get recent group conversation context"""
        messages = list(self.group_context[chat_id])
        if not messages:
            return ""
        
        context = "Recent group conversation:\n"
        for msg in messages:
            context += f"• {msg}\n"
        
        return context
    
    def get_combined_context(self, user_id: int, chat_id: int) -> str:
        """Get combined user and group context"""
        user_ctx = self.get_user_context(user_id)
        group_ctx = self.get_group_context(chat_id)
        
        combined = ""
        if group_ctx:
            combined += group_ctx + "\n"
        if user_ctx:
            combined += user_ctx
        
        return combined.strip()

class RateLimiter:
    """Advanced rate limiting with different limits for different actions"""
    
    def __init__(self, default_limit: int = 3):
        self.default_limit = default_limit
        self.user_timestamps = defaultdict(list)
        self.user_request_count = defaultdict(int)
        self.global_concurrent = 0
        self.max_global_concurrent = 20
        
    def is_rate_limited(self, user_id: int, limit_seconds: int = None) -> Tuple[bool, float]:
        """Check if user is rate limited, return (is_limited, remaining_time)"""
        if limit_seconds is None:
            limit_seconds = self.default_limit
            
        current_time = time.time()
        user_requests = self.user_timestamps[user_id]
        
        # Remove old requests (older than limit_seconds)
        while user_requests and current_time - user_requests[0] > limit_seconds:
            user_requests.pop(0)
        
        if user_requests:
            remaining_time = limit_seconds - (current_time - user_requests[-1])
            if remaining_time > 0:
                return True, remaining_time
        
        return False, 0.0
    
    def add_request(self, user_id: int):
        """Record a new request for the user"""
        current_time = time.time()
        self.user_timestamps[user_id].append(current_time)
        self.user_request_count[user_id] += 1
    
    def can_process_globally(self) -> bool:
        """Check if we can process more requests globally"""
        return self.global_concurrent < self.max_global_concurrent
    
    def increment_global(self):
        """Increment global concurrent counter"""
        self.global_concurrent += 1
    
    def decrement_global(self):
        """Decrement global concurrent counter"""
        self.global_concurrent = max(0, self.global_concurrent - 1)

class TelegramBot:
    """Enhanced Telegram bot with robust error handling"""
    
    def __init__(self):
        self.config = ConfigManager()
        self.api_manager = APIKeyManager(self.config.api_keys)
        self.context_manager = ContextManager(
            self.config.max_context_messages, 
            self.config.group_context_messages
        )
        self.rate_limiter = RateLimiter(self.config.rate_limit_seconds)
        
        # Initialize Telethon client
        self.session = StringSession(self.config.string_session) if self.config.string_session else StringSession()
        self.client = TelegramClient(self.session, int(self.config.api_id), self.config.api_hash)
        
        # Bot state
        self.active_requests = set()
        self.bot_user_id = None
        self.shutdown_requested = False
        
        # System prompt
        self.system_prompt = """You are MrxSeek, an intelligent and helpful AI assistant. You provide accurate, concise, and contextually relevant responses. You can help with programming, general knowledge, problem-solving, and creative tasks. Use the provided conversation context to give more personalized and relevant responses. Keep responses conversational and engaging while being informative."""
        
        logger.info("TelegramBot initialized successfully")
    
    async def start(self):
        """Start the bot with proper initialization"""
        try:
            logger.info("Starting Telegram client...")
            await self.client.start()
            
            # Get bot info
            me = await self.client.get_me()
            self.bot_user_id = me.id
            logger.info(f"Bot connected successfully as: {me.first_name} (@{me.username})")
            
            # Save new session if needed
            if not self.config.string_session:
                session_string = self.client.session.save()
                try:
                    with open('.env', 'a') as f:
                        f.write(f"\nSTRING_SESSION={session_string}")
                    logger.info("New session string saved to .env")
                except Exception as e:
                    logger.error(f"Failed to save session string: {e}")
            
            # Register event handlers
            self.client.add_event_handler(self.handle_message, events.NewMessage(incoming=True))
            
            # Setup graceful shutdown
            self.setup_signal_handlers()
            
            logger.info("Bot is running and listening for messages...")
            logger.info(f"Bot will respond to mentions of: {self.config.bot_username}")
            logger.info(f"Context tracking: {self.config.max_context_messages} user messages, {self.config.group_context_messages} group messages")
            logger.info(f"Rate limiting: 1 request per user per {self.config.rate_limit_seconds} seconds")
            logger.info("Press Ctrl+C to stop the bot")
            
            # Keep the bot running
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            logger.error(traceback.format_exc())
            raise
    
    def setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.shutdown_requested = True
            
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def handle_message(self, event):
        """Enhanced message handler with robust error handling"""
        try:
            # Skip if shutdown requested
            if self.shutdown_requested:
                return
            
            # Only respond in group chats
            if not event.is_group:
                return
            
            # Get sender information
            sender = await event.get_sender()
            if not sender or sender.bot or event.sender_id == self.bot_user_id:
                return
            
            user_id = event.sender_id
            message_text = event.raw_text or ""
            username = sender.username
            chat_id = event.chat_id
            
            # Add message to context (always track, even if not responding)
            self.context_manager.add_user_message(user_id, message_text, username)
            self.context_manager.add_group_message(chat_id, user_id, message_text, username)
            
            # Check if bot should respond
            is_mention = self.is_bot_mentioned(message_text)
            is_reply_to_bot = event.is_reply and (await event.get_reply_message()).sender_id == self.bot_user_id
            
            if not (is_mention or is_reply_to_bot):
                return
            
            # Check global rate limiting
            if not self.rate_limiter.can_process_globally():
                await event.reply("🔄 System is busy, please try again in a moment.")
                return
            
            # Check user rate limiting
            is_limited, remaining_time = self.rate_limiter.is_rate_limited(user_id)
            if is_limited:
                await event.reply(f"⏳ Please wait {remaining_time:.1f} seconds before your next request.")
                return
            
            # Process the query
            await self.process_query(event, user_id, chat_id, message_text, username)
            
        except Exception as e:
            logger.error(f"Error in message handler: {e}")
            logger.error(traceback.format_exc())
            try:
                await event.reply("❌ An error occurred processing your message.")
            except:
                pass
    
    async def process_query(self, event, user_id: int, chat_id: int, message_text: str, username: str):
        """Process user query with enhanced context and error handling"""
        request_key = f"{user_id}_{event.id}"
        
        try:
            # Add to active requests and rate limiter
            self.active_requests.add(request_key)
            self.rate_limiter.add_request(user_id)
            self.rate_limiter.increment_global()
            
            logger.info(f"[User {user_id}] Processing query in chat {chat_id}")
            
            # Extract query
            query = self.extract_query(message_text)
            if not query.strip():
                return
            
            # Get enhanced context
            context = self.context_manager.get_combined_context(user_id, chat_id)
            
            # Send typing indicator
            async with self.client.action(event.chat_id, 'typing'):
                # Get AI response with retries
                response = await self.get_ai_response_with_retry(query, context, user_id)
                
                # Send response
                await event.reply(response, parse_mode='markdown')
                
            logger.info(f"[User {user_id}] Response sent successfully")
            
        except Exception as e:
            logger.error(f"[User {user_id}] Error processing query: {e}")
            logger.error(traceback.format_exc())
            try:
                await event.reply("❌ Sorry, I encountered an error processing your request. Please try again.")
            except:
                pass
        finally:
            # Cleanup
            self.active_requests.discard(request_key)
            self.rate_limiter.decrement_global()
    
    async def get_ai_response_with_retry(self, query: str, context: str, user_id: int) -> str:
        """Get AI response with retry logic and API key failover"""
        last_error = None
        
        for attempt in range(self.config.retry_attempts):
            try:
                api_key = self.api_manager.get_current_key()
                response = await self.call_ai_api(query, context, user_id, api_key)
                
                # Mark success and return
                self.api_manager.mark_key_success(api_key)
                return response
                
            except Exception as e:
                last_error = e
                logger.warning(f"[User {user_id}] Attempt {attempt + 1} failed: {e}")
                
                # Mark API key failure
                current_key = self.api_manager.get_current_key()
                self.api_manager.mark_key_failure(current_key, str(e))
                
                if attempt < self.config.retry_attempts - 1:
                    await asyncio.sleep(1)  # Brief delay before retry
        
        # All attempts failed
        logger.error(f"[User {user_id}] All retry attempts failed. Last error: {last_error}")
        return "❌ I'm having trouble connecting to my AI service right now. Please try again in a moment."
    
    async def call_ai_api(self, query: str, context: str, user_id: int, api_key: str) -> str:
        """Make API call to AI service"""
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "TelegramBot"
        }
        
        # Build messages
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        if context:
            messages.append({"role": "system", "content": f"Conversation Context:\n{context}"})
        
        messages.append({"role": "user", "content": query})
        
        data = {
            "model": "deepseek/deepseek-r1-0528:free",
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.7
        }
        
        timeout = aiohttp.ClientTimeout(total=self.config.api_timeout)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    if 'choices' in result and result['choices']:
                        return result['choices'][0]['message']['content']
                    else:
                        raise Exception("Invalid API response structure")
                else:
                    error_text = await response.text()
                    raise Exception(f"API request failed with status {response.status}: {error_text}")
    
    def is_bot_mentioned(self, text: str) -> bool:
        """Check if bot is mentioned (case-insensitive)"""
        text_lower = text.lower()
        return self.config.bot_username_normalized in text_lower
    
    def extract_query(self, message_text: str) -> str:
        """Extract query from message text"""
        # Remove bot username mentions (case-insensitive)
        pattern = re.compile(re.escape(self.config.bot_username), re.IGNORECASE)
        query = pattern.sub('', message_text).strip()
        
        # Remove extra whitespace
        query = ' '.join(query.split())
        
        return query
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Initiating graceful shutdown...")
        
        # Wait for active requests to complete (with timeout)
        timeout = 30  # 30 seconds timeout
        start_time = time.time()
        
        while self.active_requests and (time.time() - start_time) < timeout:
            logger.info(f"Waiting for {len(self.active_requests)} active requests to complete...")
            await asyncio.sleep(1)
        
        if self.active_requests:
            logger.warning(f"Timeout reached, {len(self.active_requests)} requests still active")
        
        # Disconnect client
        if self.client.is_connected():
            await self.client.disconnect()
        
        # Log final statistics
        stats = self.api_manager.get_key_stats()
        logger.info(f"Final API key statistics: {stats}")
        logger.info("Bot shutdown completed")

# Main execution
async def main():
    """Main function to run the bot"""
    bot = None
    try:
        bot = TelegramBot()
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        return 1
    finally:
        if bot:
            await bot.shutdown()
    
    return 0

if __name__ == '__main__':
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Failed to run bot: {e}")
        sys.exit(1)
