# CleanAI Bot - Complete Koyeb Repository

## 📁 Repository Structure

```
cleanai-bot/
├── cleanai_bot.py          # Your main bot script (rename from Bot (93).py)
├── requirements.txt        # Python dependencies
├── Procfile               # Koyeb process definition
├── runtime.txt            # Python version specification
├── .env.example           # Environment variables template
├── .gitignore             # Git ignore file
├── README.md              # Project documentation
├── Dockerfile             # Optional Docker configuration
└── koyeb.toml             # Optional Koyeb configuration
```

---

## 📄 **requirements.txt**

```txt
telethon==1.36.0
python-dotenv==1.0.0
aiohttp==3.9.1
requests==2.31.0
asyncio-mqtt==0.16.1
```

---

## 🚀 **Procfile**

```
web: python cleanai_bot.py
```

---

## 🐍 **runtime.txt**

```
python-3.11.7
```

---

## 🔒 **.env.example**

```env
# Telegram Bot Configuration
API_ID=your_telegram_api_id_here
API_HASH=your_telegram_api_hash_here
BOT_USERNAME=@YourBotUsername
STRING_SESSION=your_session_string_here

# OpenRouter API Keys (at least one required)
API_KEY=your_primary_openrouter_api_key
API_KEY1=your_backup_api_key_1
API_KEY2=your_backup_api_key_2
API_KEY3=your_backup_api_key_3
API_KEY4=your_backup_api_key_4
API_KEY5=your_backup_api_key_5
API_KEY6=your_backup_api_key_6
API_KEY7=your_backup_api_key_7
API_KEY8=your_backup_api_key_8
API_KEY9=your_backup_api_key_9
API_KEY10=your_backup_api_key_10

# Optional: Logging Level (INFO, DEBUG, WARNING, ERROR)
LOG_LEVEL=INFO
```

---

## 🚫 **.gitignore**

```gitignore
# Environment variables
.env
.env.local
.env.production

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
pip-wheel-metadata/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Virtual Environment
venv/
env/
ENV/
env.bak/
venv.bak/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Logs
*.log
logs/
bot.log

# OS
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db

# Session files
*.session
*.session-journal

# Temporary files
*.tmp
*.temp
```

---

## 📖 **README.md**

```markdown
# 🤖 CleanAI Bot

A lightweight AI-powered Telegram bot with uptime monitoring capabilities, designed for seamless deployment on Koyeb.

## ✨ Features

- 🧠 **AI Assistant**: Responds in private chats and when mentioned in groups
- 📝 **Message Summarization**: Reply to any message and ask for a summary
- 🔄 **Uptime Monitoring**: Keep any URL alive with `/up <url>` command
- 🔑 **API Key Rotation**: Automatic fallback between multiple OpenRouter keys
- ⚡ **Async Processing**: Handle multiple requests concurrently
- 📚 **Context Awareness**: Remembers recent conversation history

## 🚀 Quick Deploy to Koyeb

### 1. Prerequisites
- Koyeb account
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- OpenRouter API key(s) from [OpenRouter](https://openrouter.ai/)

### 2. Get Telegram Credentials
1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Get your `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org)
3. Run the bot locally once to generate `STRING_SESSION`

### 3. Deploy on Koyeb
1. Fork this repository
2. Connect your GitHub to Koyeb
3. Create a new Koyeb app from this repository
4. Set environment variables in Koyeb dashboard:
   ```
   API_ID=your_api_id
   API_HASH=your_api_hash
   BOT_USERNAME=@yourbotusername
   STRING_SESSION=your_session_string
   API_KEY=your_openrouter_key
   ```
5. Deploy!

## 🎮 Usage

### Basic Chat
- **Private Message**: Just send any message to the bot
- **Group Chat**: Mention the bot `@yourbotname` or reply to its messages
- **Helpful Mode**: End your message with `...` for more detailed responses

### Commands
- `/up <url>` - Start monitoring a URL (pings every 3 minutes)
- `/up` - Check current monitoring status

### Special Features
- **Summarization**: Reply to any message and include "summarize" in your text
- **Context Memory**: Bot remembers your last 3-5 messages for better conversations

## 🔧 Configuration

### Environment Variables
| Variable | Required | Description |
|----------|----------|-------------|
| `API_ID` | ✅ | Telegram API ID from my.telegram.org |
| `API_HASH` | ✅ | Telegram API Hash from my.telegram.org |
| `BOT_USERNAME` | ✅ | Your bot's username (with @) |
| `STRING_SESSION` | ✅ | Generated session string |
| `API_KEY` | ✅ | Primary OpenRouter API key |
| `API_KEY1-10` | ❌ | Backup OpenRouter API keys |

### Local Development
1. Clone the repository
2. Copy `.env.example` to `.env`
3. Fill in your credentials
4. Install dependencies: `pip install -r requirements.txt`
5. Run: `python cleanai_bot.py`

## 📊 Monitoring

The bot includes comprehensive logging:
- Request tracking with unique IDs
- API key rotation status
- Uptime monitoring status
- Error handling and recovery

Check Koyeb logs for real-time monitoring.

## 🛠️ Customization

### System Prompts
Edit the prompts in `cleanai_bot.py`:
- `NORMAL_SYSTEM_PROMPT`: Default personality
- `HELPFUL_SYSTEM_PROMPT`: Activated with `...` suffix

### Ping Interval
Change `PING_INTERVAL` in the script (default: 180 seconds = 3 minutes)

## 🆘 Troubleshooting

### Common Issues
1. **Bot not responding**: Check `STRING_SESSION` and bot permissions
2. **API errors**: Verify OpenRouter API keys are valid
3. **Deployment fails**: Ensure all required environment variables are set
4. **Uptime monitoring not working**: Check URL format (must include protocol)

### Getting Help
- Check Koyeb application logs
- Verify environment variables in Koyeb dashboard
- Test locally first with `.env` file

## 📄 License

MIT License - feel free to modify and distribute!

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

**Made with ❤️ for the Koyeb community**
```

---

## 🐳 **Dockerfile** (Optional)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Expose port (Koyeb requirement)
EXPOSE 8000

# Run the bot
CMD ["python", "cleanai_bot.py"]
```

---

## ⚙️ **koyeb.toml** (Optional Koyeb Config)

```toml
[app]
name = "cleanai-bot"

[services.bot]
type = "web"
name = "cleanai-bot-service"

[services.bot.build]
type = "buildpack"
build_command = "pip install -r requirements.txt"

[services.bot.deploy]
command = "python cleanai_bot.py"

[services.bot.instance]
type = "nano"

[services.bot.ports]
port = 8000
protocol = "http"

[services.bot.env]
# Environment variables will be set in Koyeb dashboard
```

---

## 🚀 **Deployment Instructions**

### Method 1: GitHub Integration (Recommended)
1. Create a new repository on GitHub
2. Push all these files to your repository
3. Connect GitHub to Koyeb
4. Create new app from your repository
5. Set environment variables in Koyeb dashboard
6. Deploy!

### Method 2: Koyeb CLI
```bash
# Install Koyeb CLI
curl -fsSL https://cli.koyeb.com/install.sh | bash

# Login
koyeb auth login

# Deploy
koyeb app init cleanai-bot
koyeb service create cleanai-bot \
  --app cleanai-bot \
  --git github.com/yourusername/cleanai-bot \
  --git-branch main \
  --instance-type nano \
  --env API_ID=your_api_id \
  --env API_HASH=your_api_hash \
  --env BOT_USERNAME=@yourbotname \
  --env STRING_SESSION=your_session \
  --env API_KEY=your_openrouter_key
```

### Method 3: Docker Deploy
```bash
# Build and push to a registry, then deploy on Koyeb
docker build -t your-registry/cleanai-bot .
docker push your-registry/cleanai-bot

# Deploy via Koyeb dashboard using Docker image
```

---

## 🔧 **Environment Setup Guide**

### Getting STRING_SESSION:
1. Run the bot locally first with `API_ID`, `API_HASH`, and `BOT_USERNAME`
2. It will generate a session file and append `STRING_SESSION` to your `.env`
3. Copy this value to your Koyeb environment variables

### Multiple API Keys:
Add as many backup keys as you want:
```
API_KEY=primary_key
API_KEY1=backup_1
API_KEY2=backup_2
# ... up to API_KEY10
```

---

## 📈 **Monitoring & Scaling**

- **Logs**: Check Koyeb app logs for real-time monitoring
- **Health**: Bot automatically handles API key rotation
- **Scaling**: Koyeb nano instance is sufficient for most use cases
- **Uptime**: The `/up` command keeps other services alive, but Koyeb keeps your bot alive!

---

**That's your complete repository! Just add your main script as `cleanai_bot.py` and you're ready to deploy! 🚀**
