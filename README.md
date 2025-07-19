A Telegram bot that uses OpenRouter's DeepSeek AI to respond intelligently in DMs and groups. Designed for speed, scalability, and simplicity.

---

## 🚀 Features

- 🧠 AI-powered replies (via DeepSeek API)
- ⚡ Ultra-low-latency message handling
- 🔁 Context-aware responses (up to 3 past messages)
- 🔐 Multi-key support with automatic failover
- 👥 Works in both DMs and group chats
- ⛔ Built-in rate limiting to prevent spam
- 🧹 Graceful shutdown and cleanup handling
- 📚 Context memory for smarter answers

---

## 🛠️ Setup Instructions

### 1. Clone the Repo

```bash
git clone https://github.com/HackerXMindset/Telegram-Deepseek-chatbot.git
cd Telegram-Deepseek-chatbot.git
````

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Create `.env` File

Create a `.env` file in the root directory with the following content:

```dotenv
API_ID=your_telegram_api_id
API_HASH=your_telegram_api_hash
BOT_USERNAME=@your_bot_username
STRING_SESSION=   # Leave empty for first run
API_KEYS=your_openrouter_api_key_1,your_api_key_2 (comma-separated)
```

> 📌 Get your `API_ID` and `API_HASH` from [https://my.telegram.org](https://my.telegram.org)

> 🔑 Get your OpenRouter API key(s) from [https://openrouter.ai](https://openrouter.ai/deepseek/deepseek-r1:free)

### 4. Run the Bot

```bash
python main.py
```

> 💾 On first run, it will generate a session string and auto-save it to your `.env`.

---

## 🤖 Bot Behavior

* **DMs**: Replies to all messages
* **Groups**: Replies only if:

  * The bot is mentioned (e.g., `@YourBotName`)
  * A user replies to the bot’s message

---

## 📄 File Overview

| File               | Description                              |
| ------------------ | ---------------------------------------- |
| `main.py`          | Main bot engine (Telethon + DeepSeek AI) |
| `.env`             | Stores credentials and API keys          |
| `requirements.txt` | Python packages needed for the bot       |

---

## 🧼 Graceful Exit

Use `Ctrl+C` to exit. The bot will:

* Stop cleanly
* Save the session if newly generated
* Close all HTTP and Telegram connections

---

## 🧪 Troubleshooting

* ❌ **Bot not responding in groups**: Make sure it’s mentioned (`@BotUsername`) or replied to directly.
* ❌ **API failures**: Add multiple API keys in `.env` like: `API_KEYS=key1,key2,key3`
* ❌ **Session issues**: Delete the existing `STRING_SESSION` in `.env` and restart the bot.

---

## 📜 License

MIT License — free to use, modify, and deploy.

---

