# MrxSeek - Intelligent Telegram Bot

An advanced Telegram bot powered by DeepSeek AI that provides intelligent responses in group chats. The bot features context awareness, rate limiting, concurrent request processing, and comprehensive logging.

## 🚀 Features

- **AI-Powered Responses**: Uses DeepSeek R1 model via OpenRouter API for intelligent conversations
- **Context Awareness**: Remembers the last 3 messages from each user for better context
- **Group Chat Support**: Responds when mentioned (@botusername) or when replied to
- **Rate Limiting**: Prevents spam with configurable rate limits (default: 1 request per 3 seconds per user)
- **Concurrent Processing**: Handles multiple user queries simultaneously without blocking
- **Comprehensive Logging**: Detailed logging to both file and console for debugging
- **Session Management**: Persistent Telegram sessions with automatic session string generation
- **Error Handling**: Robust error handling with graceful fallbacks

## 📋 Prerequisites

- Python 3.7+
- A Telegram account
- OpenRouter API key (for DeepSeek access)
- Telegram API credentials

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd telegram-bot
   ```

2. **Install required packages**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create requirements.txt** (if not present):
   ```txt
   telethon
   requests
   python-dotenv
   aiohttp
   ```

## ⚙️ Configuration

1. **Get Telegram API credentials**
   - Visit [my.telegram.org](https://my.telegram.org)
   - Log in with your phone number
   - Go to "API Development Tools"
   - Create a new application
   - Note down your `API_ID` and `API_HASH`

2. **Get OpenRouter API key**
   - Visit [OpenRouter](https://openrouter.ai)
   - Sign up and get your API key
   - Ensure you have access to the DeepSeek model

3. **Create a .env file**
   ```env
   API_ID=your_telegram_api_id
   API_HASH=your_telegram_api_hash
   API_KEY=your_openrouter_api_key
   BOT_USERNAME=@YourBotUsername
   STRING_SESSION=
   ```

   **Note**: Leave `STRING_SESSION` empty on first run. The bot will generate and save it automatically.

## 🚀 Usage

1. **Start the bot**
   ```bash
   python New.py
   ```

2. **First Run**
   - The bot will prompt you to enter your phone number
   - Enter the verification code sent to your Telegram
   - The session will be saved automatically for future runs

3. **Using the bot in groups**
   - Add the bot to your Telegram group
   - Mention the bot: `@YourBotUsername Hello, how are you?`
   - Or reply to any of the bot's messages
   - The bot will respond with AI-generated content

## 🎛️ Customization

### System Prompt
Edit the `SYSTEM_PROMPT` variable in the code to customize the bot's personality:

```python
SYSTEM_PROMPT = """You are MrxSeek, a helpful and intelligent AI assistant. 
You are friendly, knowledgeable, and always try to provide accurate and useful information. 
You respond in a conversational tone and can help with various topics including programming, 
general knowledge, problem-solving, and creative tasks. Keep your responses concise but 
informative unless specifically asked for detailed explanations."""
```

### Rate Limiting
Modify the `RATE_LIMIT_SECONDS` variable to change the rate limit:

```python
RATE_LIMIT_SECONDS = 3  # Seconds between requests per user
```

### Context History
Change the message history size by modifying the `maxlen` parameter:

```python
user_message_history = defaultdict(lambda: deque(maxlen=3))  # Keep last 3 messages
```

### AI Model
Switch to a different model by changing the model parameter in the API call:

```python
data = {
    "model": "deepseek/deepseek-r1-0528:free",  # Change this to use a different model
    "messages": messages
}
```

## 📊 Logging

The bot creates detailed logs in:
- **Console output**: Real-time logging for monitoring
- **bot.log file**: Persistent logging for debugging

Log levels include:
- INFO: General bot operations
- ERROR: Errors and exceptions
- Request tracking with unique IDs

## 🔧 Troubleshooting

### Common Issues

1. **"Missing required configuration"**
   - Ensure all required variables are set in `.env` file
   - Check that API_ID is numeric and API_HASH is a string

2. **"API request failed"**
   - Verify your OpenRouter API key is valid
   - Check if you have sufficient credits/quota
   - Ensure the DeepSeek model is available

3. **"Bot not responding in groups"**
   - Make sure the bot username in `.env` matches exactly
   - Check if the bot has permission to read messages in the group
   - Verify the bot is mentioned correctly (@botusername)

4. **Session errors**
   - Delete the `STRING_SESSION` from `.env` to create a new session
   - Ensure you're using the correct phone number

### Debug Mode

For additional debugging, modify the logging level:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    # ... rest of the configuration
)
```

## 🔒 Security Considerations

- Keep your `.env` file secure and never commit it to version control
- Add `.env` to your `.gitignore` file
- Use environment variables in production instead of `.env` files
- Regularly rotate your API keys
- Monitor API usage to detect unusual activity

## 📝 Environment Variables Reference

| Variable | Description | Required | Example |
|----------|-------------|----------|---------|
| `API_ID` | Telegram API ID | Yes | `12345678` |
| `API_HASH` | Telegram API Hash | Yes | `abcdef123456...` |
| `API_KEY` | OpenRouter API Key | Yes | `sk-or-v1-...` |
| `BOT_USERNAME` | Bot username (with or without @) | Yes | `@YourBotName` |
| `STRING_SESSION` | Telegram session string | No* | Auto-generated |

*Required after first run for persistent sessions

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Commit your changes (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature/new-feature`)
5. Create a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- [Telethon](https://github.com/LonamiWebs/Telethon) - Telegram client library
- [OpenRouter](https://openrouter.ai) - AI model access
- [DeepSeek](https://deepseek.com) - AI model provider

## 📞 Support

If you encounter any issues or have questions:

1. Check the troubleshooting section above
2. Review the logs in `bot.log` for error details
3. Create an issue on GitHub with:
   - Description of the problem
   - Relevant log entries (remove sensitive information)
   - Your environment details (Python version, OS, etc.)

---

**Note**: This bot is designed for group chats only. It will not respond to direct messages. Make sure to test in a group environment.
