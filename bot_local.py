"""
Same bot as bot.py, with ONE layer swapped: extraction runs on a local model
via Ollama instead of the Gemini API. Nothing else changes — state machine,
Calendar creation, and Telegram handling are identical to bot.py.

Use this when a message might contain something you'd rather not send to a
cloud API. Trade-off: local inference is slower than Gemini and can be less
consistent, since it's a much smaller model running on your own hardware.

Setup:
    pip install ollama
    ollama pull qwen3:8b
"""
import os
import json
import time
import asyncio
import logging
import html
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any

import ollama
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ------------------- Configuration -------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CALENDAR_ID = "primary"
OLLAMA_MODEL = "qwen3:8b"   # swap the tag here to try another local model

# ------------------- Logging -------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Google Calendar authentication
SCOPES = ['https://www.googleapis.com/auth/calendar']
try:
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open('token.json', 'w') as token_file:
            token_file.write(creds.to_json())
except FileNotFoundError:
    logger.error("token.json not found. Run get_token.py first.")
    raise
calendar_service = build('calendar', 'v3', credentials=creds)

# -------------------------------------------------------------------
# DEBUG PRINTING: prints a labeled block to the console after each step
# -------------------------------------------------------------------
def debug_print(label: str, value):
    bar = "=" * 60
    print(f"\n{bar}\n[STEP] {label}\n{bar}\n{value}\n{bar}\n")

# JSON schemas passed to Ollama's `format` param — this constrains the local
# model's output to match this shape at the decoder level, so (unlike the
# Gemini version) there's no regex step needed to pull JSON out of free text.
EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "event_name": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"]},
        "time": {"type": ["string", "null"]},
        "duration_minutes": {"type": "integer"},
        "location": {"type": ["string", "null"]},
        "description": {"type": ["string", "null"]},
        "recurrence": {"type": ["string", "null"]},
        "missing": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["event_name", "date", "time", "duration_minutes",
                 "location", "description", "recurrence", "missing"]
}
DATE_SCHEMA = {"type": "object", "properties": {"date": {"type": ["string", "null"]}}, "required": ["date"]}

# -------------------------------------------------------------------
# Retry wrapper: mirrors bot.py's generate_with_retry, adapted for a local
# service instead of a cloud quota — retries if Ollama isn't reachable yet.
# -------------------------------------------------------------------
def generate_with_retry(prompt: str, schema: dict, max_retries: int = 3) -> str:
    delay = 2
    for attempt in range(max_retries):
        try:
            response = ollama.generate(model=OLLAMA_MODEL, prompt=prompt, format=schema)
            return response['response']
        except Exception as e:
            is_connection_issue = "connect" in str(e).lower() or "refused" in str(e).lower()
            debug_print("Ollama call raised an exception",
                        f"attempt={attempt + 1}/{max_retries}  is_connection_issue={is_connection_issue}\n{e}")
            if is_connection_issue and attempt < max_retries - 1:
                logger.warning(f"Ollama not reachable (attempt {attempt + 1}/{max_retries}), retrying in {delay}s")
                time.sleep(delay)
                delay *= 2
                continue
            raise

# ------------------- State Management -------------------
user_states: Dict[int, Dict[str, Any]] = {}

STATE_IDLE = "IDLE"
STATE_AWAITING_DATE = "AWAITING_DATE"
STATE_CONFIRMATION = "CONFIRMATION"

# -------------------------------------------------------------------
# 1. MAIN EVENT EXTRACTION (first message)
# -------------------------------------------------------------------
def get_extraction_prompt():
    today = date.today().isoformat()
    prompt = """You are a calendar extraction assistant. Today is TODAY_VALUE.
Extract the event details from the user's message.

Return **only** a JSON object with these keys:
- event_name: string
- date: string in YYYY-MM-DD format (e.g., "2026-08-15")
- time: string in HH:MM 24-hour format (e.g., "14:30") or null
- duration_minutes: integer (default 60 if not mentioned)
- location: string or null
- description: string or null
- recurrence: string in RRULE format or null (e.g., "FREQ=WEEKLY;BYDAY=MO")
- missing: array of critical missing fields (always check "date" and "time" unless a recurring rule makes them unnecessary)

Important rules:
- If the message says "tomorrow", use the date after TODAY_VALUE.
- If a date like "15th August" is given without a year, assume it's the next occurrence after TODAY_VALUE (likely 2026-08-15 for 2026).
- If a time is not given, mark "time" as missing.
- If a date is not clear, mark "date" as missing.

Examples:
Message: "Lunch with Sarah tomorrow at 1pm"
Output: {"event_name": "Lunch with Sarah", "date": "2026-08-07", "time": "13:00", "duration_minutes": 60, "location": null, "description": null, "recurrence": null, "missing": []}

Message: "airbus oa will be on 15th august"
Output: {"event_name": "airbus oa", "date": "2026-08-15", "time": null, "duration_minutes": 60, "location": null, "description": null, "recurrence": null, "missing": ["time"]}

Now process this message: "USER_MESSAGE"
"""
    return prompt.replace("TODAY_VALUE", today)

def extract_event_details(text: str) -> Dict[str, Any]:
    prompt = get_extraction_prompt().replace("USER_MESSAGE", text)
    debug_print("Prompt sent to local model (event extraction)", prompt)
    raw = None
    try:
        raw = generate_with_retry(prompt, EVENT_SCHEMA)
        debug_print("Local model raw response (event extraction)", raw)
        logger.info(f"Local model raw extraction output: {raw!r}")
        data = json.loads(raw)  # format=schema guarantees valid JSON, no regex needed
        if 'missing' not in data or not isinstance(data['missing'], list):
            data['missing'] = []
        debug_print("Parsed extraction result", json.dumps(data, indent=2))
        return data
    except Exception as e:
        debug_print("Extraction FAILED", f"{e}\n\nRaw response was: {raw!r}")
        logger.error(f"Extraction failed: {e}. Raw response was: {raw!r}")
        return {
            "event_name": None, "date": None, "time": None, "duration_minutes": 60,
            "location": None, "description": None, "recurrence": None,
            "missing": ["date", "time"]
        }

# -------------------------------------------------------------------
# 2. DATE EXTRACTION (when bot asks "What date?")
# -------------------------------------------------------------------
def get_date_extraction_prompt():
    today = date.today().isoformat()
    prompt = """Today is TODAY_VALUE. Extract a date from the user's reply.
Return a JSON object like {"date": "YYYY-MM-DD"}, or {"date": null} if unclear.
Examples:
User: "15th august" -> {"date": "2026-08-15"}
User: "tomorrow" -> date after TODAY_VALUE
User: "next Monday" -> compute the correct date
Now: "USER_MESSAGE" """
    return prompt.replace("TODAY_VALUE", today)

async def extract_date_from_reply(text: str) -> Optional[str]:
    prompt = get_date_extraction_prompt().replace("USER_MESSAGE", text)
    debug_print("Prompt sent to local model (date extraction)", prompt)
    try:
        raw = await asyncio.to_thread(generate_with_retry, prompt, DATE_SCHEMA)
        debug_print("Local model raw response (date extraction)", raw)
        data = json.loads(raw)
        result = data.get('date')
        if not result:
            debug_print("Parsed date", "None")
            return None
        datetime.strptime(result, '%Y-%m-%d')
        debug_print("Parsed date", result)
        return result
    except Exception as e:
        debug_print("Date extraction FAILED", str(e))
        return None

# -------------------------------------------------------------------
# Helper: fill in safe defaults
# -------------------------------------------------------------------
def finalize_extracted(extracted: Dict[str, Any]) -> Dict[str, Any]:
    if not extracted.get('event_name'):
        extracted['event_name'] = 'Event'
    if not extracted.get('duration_minutes'):
        extracted['duration_minutes'] = 60
    if not extracted.get('time'):
        extracted['all_day'] = True
    debug_print("Finalized event data (defaults applied)", json.dumps(extracted, indent=2))
    return extracted

# -------------------------------------------------------------------
# Helper: Format confirmation message
# -------------------------------------------------------------------
async def ask_confirmation(update: Update, extracted: Dict):
    name = html.escape(str(extracted.get('event_name', 'Event')))
    lines = [f"📌 <b>{name}</b>"]
    if extracted.get('all_day'):
        lines.append(f"📅 {html.escape(str(extracted['date']))} (all day)")
    else:
        lines.append(f"📅 {html.escape(str(extracted['date']))} at {html.escape(str(extracted['time']))}")
    dur = extracted.get('duration_minutes') or 60
    lines.append(f"⏳ Duration: {dur} min")
    if extracted.get('location'):
        lines.append(f"📍 {html.escape(str(extracted['location']))}")
    if extracted.get('description'):
        lines.append(f"📝 {html.escape(str(extracted['description']))}")
    if extracted.get('recurrence'):
        lines.append(f"🔁 Repeats: {html.escape(str(extracted['recurrence']))}")
    msg = "\n".join(lines) + "\n\nCreate this event? (yes/no)"
    debug_print("Confirmation message being sent to Telegram", msg)
    await update.message.reply_text(msg, parse_mode='HTML')

# -------------------------------------------------------------------
# Create Google Calendar Event (supports all-day)
# -------------------------------------------------------------------
def create_calendar_event(summary: str, start_date: str, start_time: Optional[str] = None,
                          duration_minutes: int = 60, location: Optional[str] = None,
                          description: Optional[str] = None, recurrence: Optional[str] = None,
                          all_day: bool = False):
    if all_day:
        event_body = {
            'summary': summary, 'location': location, 'description': description,
            'start': {'date': start_date, 'timeZone': 'Asia/Kolkata'},
            'end': {
                'date': (datetime.fromisoformat(start_date) + timedelta(days=1)).strftime('%Y-%m-%d'),
                'timeZone': 'Asia/Kolkata',
            },
        }
    else:
        start_dt = datetime.fromisoformat(f"{start_date}T{start_time}:00")
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        event_body = {
            'summary': summary, 'location': location, 'description': description,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Kolkata'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Kolkata'},
        }
    if recurrence:
        event_body['recurrence'] = [f"RRULE:{recurrence}"]

    debug_print("Event body being sent to Google Calendar API", json.dumps(event_body, indent=2, default=str))
    created_event = calendar_service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
    debug_print("Google Calendar API response", json.dumps(created_event, indent=2, default=str))
    return created_event

# -------------------------------------------------------------------
# Main Telegram message handler
# -------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    text = update.message.text.strip()
    state = user_states.get(user_id, {}).get('state', STATE_IDLE)
    debug_print("Incoming Telegram message", f"user_id={user_id}\ncurrent_state={state}\ntext={text!r}")

    if state == STATE_IDLE:
        extracted = await asyncio.to_thread(extract_event_details, text)
        missing = extracted.get('missing', [])

        if 'date' in missing or not extracted.get('date'):
            debug_print("Decision", f"Date missing (missing={missing}) -> asking user for date")
            user_states[user_id] = {'state': STATE_AWAITING_DATE, 'extracted': extracted}
            await update.message.reply_text("📅 What date? (e.g., 2026-08-15, tomorrow, next Monday)")
            return

        finalize_extracted(extracted)
        user_states[user_id] = {'state': STATE_CONFIRMATION, 'extracted': extracted}
        await ask_confirmation(update, extracted)

    elif state == STATE_AWAITING_DATE:
        date_str = await extract_date_from_reply(text)
        if not date_str:
            await update.message.reply_text("I didn't understand that date. Please try again (e.g., 2026-08-15, tomorrow).")
            return
        user_data = user_states[user_id]
        user_data['extracted']['date'] = date_str
        finalize_extracted(user_data['extracted'])
        user_data['state'] = STATE_CONFIRMATION
        await ask_confirmation(update, user_data['extracted'])

    elif state == STATE_CONFIRMATION:
        user_data = user_states.get(user_id)
        if not user_data:
            await update.message.reply_text("Something went wrong. Please start again.")
            user_states.pop(user_id, None)
            return

        if text.lower() in ['yes', 'y', 'confirm', 'ok']:
            extracted = user_data['extracted']
            try:
                event = await asyncio.to_thread(
                    create_calendar_event,
                    summary=extracted['event_name'], start_date=extracted['date'],
                    start_time=extracted.get('time'), duration_minutes=extracted.get('duration_minutes', 60),
                    location=extracted.get('location'), description=extracted.get('description'),
                    recurrence=extracted.get('recurrence'), all_day=extracted.get('all_day', False)
                )
                if extracted.get('all_day'):
                    await update.message.reply_text(
                        f"✅ All-day event created!\n📌 {event.get('summary')}\n"
                        f"📅 {event['start'].get('date')}\n🔗 {event.get('htmlLink')}"
                    )
                else:
                    await update.message.reply_text(
                        f"✅ Event created!\n📌 {event.get('summary')}\n"
                        f"📅 {event['start'].get('dateTime', event['start'].get('date'))}\n🔗 {event.get('htmlLink')}"
                    )
            except Exception as e:
                debug_print("Calendar creation FAILED", str(e))
                logger.error(f"Calendar API error: {e}")
                await update.message.reply_text("❌ Failed to create event. Please try again.")
            finally:
                user_states.pop(user_id, None)
        elif text.lower() in ['no', 'n', 'cancel']:
            await update.message.reply_text("Cancelled. Send a new message to create an event.")
            user_states.pop(user_id, None)
        else:
            await update.message.reply_text("Please reply with Yes or No to confirm.")

# -------------------------------------------------------------------
def main():
    if not TELEGRAM_TOKEN:
        logger.error("Please set the TELEGRAM_TOKEN environment variable.")
        return
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot started (local model). Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
