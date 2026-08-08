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
3. If the date is unclear, it asks. Otherwise it shows you a summary and asks **yes/no**.
4. On confirmation, the event lands on your Google Calendar — all-day if no time was mentioned, timed otherwise.

State is tracked per Telegram chat, so it handles multiple back-and-forth messages (e.g., "what date?" → your reply → confirmation) without losing context.

## Two backends, same bot

This repo ships two versions of the extraction layer — same state machine, same Calendar logic, same Telegram handling. Only the model call differs.

|             | `bot.py`               | `bot_local.py`                               |
|---------|----------------------------|----------------------------------------------|
| Model   | Gemini API (cloud)         | Local model via [Ollama](https://ollama.com) |
| Speed   | Fast                       | Slower (runs on your own hardware)           |
| Data    | Message text sent to Google| Never leaves your machine                    |
| Setup   | Just an API key            | Ollama installed + model pulled              |

Default day-to-day use is `bot.py` — it's fast and the accuracy is noticeably better. `bot_local.py` exists for the cases where a message might contain something you'd rather not send to a third-party API, and speed isn't the priority for that particular message.

## Setup

**1. Clone and install dependencies**
```bash
git clone <your-repo-url>
cd Calander_bot
pip install -r requirements.txt
```

**2. Create a Telegram bot**
Message [@BotFather](https://t.me/BotFather) on Telegram, run `/newbot`, and save the token it gives you.

**3. Set up Google Calendar access**
- In [Google Cloud Console](https://console.cloud.google.com/), create a project, enable the **Google Calendar API**, and create an OAuth 2.0 Client ID (Desktop app type). Download it as `credentials.json` into this folder.
- Run `python get_token.py` — it opens a browser for you to sign in and grants calendar access, then saves `token.json`.

**4. Set environment variables**
```bash
export TELEGRAM_TOKEN="your-telegram-bot-token"
export GEMINI_API_KEY="your-gemini-api-key"     # only needed for bot.py
```

**5. Run it**
```bash
python bot.py            # cloud (Gemini)
# or
python bot_local.py      # local (Ollama) — requires: ollama pull qwen3:8b
```

`credentials.json` and `token.json` contain real credentials and are excluded via `.gitignore` — never commit them.

## Tech stack

Python · python-telegram-bot · Google Calendar API (OAuth2) · Gemini API · Ollama (local LLM) · structured JSON extraction with schema validation

## Known limitations

- State is in-memory — restarting the bot mid-conversation loses that chat's progress.
- Extraction quality depends on the model backend — the local model is noticeably less consistent than Gemini on ambiguous phrasing.
- Single calendar (`primary`) — no support for choosing which calendar to write to, yet.
- Location/description extraction is best-effort and can occasionally misfire on unusual phrasing.

## Disclaimer

Personal project, not affiliated with Google, Telegram, or Ollama.
