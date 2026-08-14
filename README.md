# calander_bot

Turn a casual Telegram message into a Google Calendar event — no typing dates, no opening Calendar, no missed placement deadlines.

## Why

Placement season updates don't arrive as neat, structured emails. They show up mid-conversation, in whatever phrasing whoever's typing happens to use:

> "Airbus OA will be on 25th August (tentatively)"
> "TCS interview next Monday 10am"
> "shortlist result for Infosys tomorrow"

Manually converting every one of these into a calendar entry is exactly the kind of small, repetitive task that gets skipped when ten of them show up in one evening — and the one you skip is always the one that mattered. This bot reads the message, figures out what you meant, and asks you to confirm before it touches your calendar.

## How it works

1. Message the bot naturally — no command syntax, no fixed format.
2. It extracts the event name, date, time (if given), duration, location, description, and recurrence.
3. If the date is unclear, it asks. Otherwise it shows you a summary and asks yes/no.
4. On confirmation, the event lands on your Google Calendar — all-day if no time was mentioned, timed otherwise.

State is tracked per Telegram chat, so it handles multiple back-and-forth messages (e.g., "what date?" → your reply → confirmation) without losing context.

## Two backends, same bot

This repo ships two versions of the extraction layer — same state machine, same Calendar logic, same Telegram handling. Only the model call differs.

|             | `bot.py`            | `bot_local.py`                  |
|-------------|----------------------|----------------------------------|
| **Model**   | Gemini API (cloud)  | Local model via Ollama          |
| **Speed**   | Fast                 | Slower (runs on your own hardware) |
| **Data**    | Message text sent to Google | Never leaves your machine |
| **Setup**   | Just an API key     | Ollama installed + model pulled |

Default day-to-day use is `bot.py` — it's fast and the accuracy is noticeably better. `bot_local.py` exists for the cases where a message might contain something you'd rather not send to a third-party API, and speed isn't the priority for that particular message.

---

## Setup

CalPal is a Telegram bot that turns casual messages into Google Calendar events using Google's Gemini AI.

### 📋 What You'll Need

- A Windows / macOS / Linux computer
- A Google account (for Calendar & Gemini)
- A Telegram account (for the bot)
- About 15 minutes of your time

### 🧰 Step 1 — Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download the latest Python 3.11 or 3.12 installer.
3. Run the installer.
   - ✅ Check the box **"Add Python to PATH"**
   - ✅ Make sure **"pip"** is selected
4. Finish the installation.

To verify, open a terminal (Command Prompt or PowerShell) and type:

```bash
python --version
```

You should see something like `Python 3.12.x`.

### 📥 Step 2 — Clone the Repo

```bash
git clone <your-repo-url>
cd calander_bot
```

Or, without git: go to the [GitHub repo](https://github.com/omg-o/calander_bot), click the green **"Code"** button → **Download ZIP**, and extract it.

### 🖥️ Step 3 — Open the Project in VS Code (Recommended)

1. If you don't have VS Code, download it from [code.visualstudio.com](https://code.visualstudio.com/).
2. Open VS Code.
3. Click **File → Open Folder…** → select the `calander_bot` folder.
4. Inside VS Code, open a new terminal: **Terminal → New Terminal** (or press `` Ctrl + ` ``).

### 🐍 Step 4 — Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it:

**Windows (PowerShell / CMD):**
```bash
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
source .venv/bin/activate
```

Your terminal prompt should now start with `(.venv)`.

### 📦 Step 5 — Install Dependencies

Make sure you're in the `calander_bot` folder (the one with `requirements.txt`), then run:

```bash
pip install -r requirements.txt
```

Wait for everything to install — you'll see a **"Successfully installed …"** message.

### 🔑 Step 6 — Get Your Telegram Bot Token

1. Open Telegram and search for **[BotFather](https://t.me/BotFather)**.
2. Send the command `/newbot` and follow the instructions:
   - Give your bot a name (e.g., "My CalPal")
   - Give it a username (must end with `bot`, e.g., `mycalpal_bot`)
3. BotFather will reply with a token that looks like:
   ```
   1236789:AxampleTokoesHere000000000
   ```
4. **Copy this token!** You'll need it soon.

### 🧠 Step 7 — Get a Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Sign in with your Google account.
3. Click **"Create API key"**.
4. Choose **"Create API key in new project"** (or select an existing project).
5. Copy the key — it looks like `AIza...`.

> ⚠️ **Important:** You must also enable the API service:
> 1. Visit the [Google Cloud Console](https://console.cloud.google.com/).
> 2. Make sure the same project is selected.
> 3. Go to **APIs & Services → Library**.
> 4. Search for **"Generative Language API"** and click **Enable**.

### 📅 Step 8 — Enable Google Calendar API & Get OAuth Credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Select your project (the one from the previous step).
3. Navigate to **APIs & Services → Library**.
4. Search for **"Google Calendar API"** → click **Enable**.
5. Now go to **APIs & Services → Credentials**.
6. Click **Create Credentials → OAuth client ID**.
7. Set Application type to **"Desktop app"**, give it a name (e.g., "CalPal Bot").
8. Click **Create**. A dialog with client ID and secret appears — click **Download JSON**.
9. Rename the downloaded file to `credentials.json`.
10. Move this `credentials.json` file into your `calander_bot` folder (next to `bot.py`).

### ⚙️ Step 9 — Configure Environment Variables

In the `calander_bot` folder, create a new file named `.env` (exactly this, no extension).

Open it and paste:

```env
TELEGRAM_TOKEN=your_telegram_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
```

Replace the token and key with the ones you copied earlier.
No quotes, no spaces around `=`.

Save the file.

> 🔒 **Security tip:** Add `.env`, `credentials.json`, and `token.json` to your `.gitignore` so you never accidentally commit your secrets to GitHub.

### 🔐 Step 10 — Authenticate Your Google Account

In the VS Code terminal (with the virtual environment active), run:

```bash
python get_token.py
```

1. A browser window will open asking you to log in to your Google account.
2. Grant calendar access.
3. After you accept, the terminal will say **"token.json saved"**.

A file `token.json` will appear in your project folder — this is your permanent calendar access.

### 🚀 Step 11 — Run the Bot!

In the same terminal, run:

```bash
python bot.py
```

You should see:

```
2026-08-12 ... - Bot started. Press Ctrl+C to stop.
```

Now go to Telegram, find your bot (by its username), and start a chat.

### 📱 Step 12 — Test It

Send the bot a message like:

- `Interview on 15th August at 2pm`
- `Doctor appointment tomorrow morning`
- `Team standup every weekday at 9am`

The bot will:

1. Extract the details using Gemini
2. Ask you to confirm
3. Create the event in your Google Calendar 🎉

---

## Tech stack

Python · python-telegram-bot · Google Calendar API (OAuth2) · Gemini API · Ollama (local LLM) · structured JSON extraction with schema validation

## Known limitations

- State is in-memory — restarting the bot mid-conversation loses that chat's progress.
- Extraction quality depends on the model backend — the local model is noticeably less consistent than Gemini on ambiguous phrasing.
- Single calendar (primary) — no support for choosing which calendar to write to, yet.
- Location/description extraction is best-effort and can occasionally misfire on unusual phrasing.

## Disclaimer

Personal project, not affiliated with Google, Telegram, or Ollama.
