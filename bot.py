import os
import json
import re
import html
import time
import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any

import google.generativeai as genai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ------------------- Configuration -------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CALENDAR_ID = "primary"

# ------------------- Logging -------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.6-flash')   # gemini-2.0-flash shut down, gemini-2.5-flash blocked for new-user projects — this is Google's current GA default with a free tier

# Google Calendar authentication
SCOPES = ['https://www.googleapis.com/auth/calendar']
try:
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # BUGFIX: persist the refreshed token so a restart doesn't rely on the stale file
        with open('token.json', 'w') as token_file:
            token_file.write(creds.to_json())
except FileNotFoundError:
    logger.error("token.json not found. Run the OAuth setup flow to generate it first.")
    raise
calendar_service = build('calendar', 'v3', credentials=creds)

# -------------------------------------------------------------------
# DEBUG PRINTING: prints a labeled block to the console after each step
# so you can see exactly what's happening at every stage
# -------------------------------------------------------------------
def debug_print(label: str, value):
    bar = "=" * 60
    print(f"\n{bar}\n[STEP] {label}\n{bar}\n{value}\n{bar}\n")

# -------------------------------------------------------------------
# Retry wrapper: free-tier quota will occasionally 429 even when working —
# retry a couple of times with backoff instead of treating it as a hard failure
# -------------------------------------------------------------------
def generate_with_retry(prompt: str, max_retries: int = 3):
    delay = 2
    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt)
        except Exception as e:
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            debug_print("Gemini call raised an exception", f"attempt={attempt + 1}/{max_retries}  is_rate_limit={is_rate_limit}\n{e}")
            if is_rate_limit and attempt < max_retries - 1:
                logger.warning(f"Gemini rate-limited (attempt {attempt + 1}/{max_retries}), retrying in {delay}s")
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
    debug_print("Prompt sent to Gemini (event extraction)", prompt)
    raw = None
    try:
        response = generate_with_retry(prompt)
        raw = response.text.strip()
        debug_print("Gemini raw response (event extraction)", raw)
        logger.info(f"Gemini raw extraction output: {raw!r}")
        # Find the first JSON object
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            json_str = match.group(0)
        else:
            json_str = raw
        data = json.loads(json_str)
        if 'missing' not in data or not isinstance(data['missing'], list):
            data['missing'] = []
        debug_print("Parsed extraction result", json.dumps(data, indent=2))
        return data
    except Exception as e:
        # BUGFIX: log the raw text that failed to parse — without this you
        # can't tell whether the API call itself failed or the JSON was malformed
        debug_print("Extraction FAILED", f"{e}\n\nRaw response was: {raw!r}")
        logger.error(f"Extraction failed: {e}. Raw response was: {raw!r}")
        return {
            "event_name": None,
            "date": None,
            "time": None,
            "duration_minutes": 60,
            "location": None,
            "description": None,
            "recurrence": None,
            "missing": ["date", "time"]
        }

# -------------------------------------------------------------------
# 2. DATE EXTRACTION (when bot asks "What date?")
# -------------------------------------------------------------------
def get_date_extraction_prompt():
    today = date.today().isoformat()
    prompt = """Today is TODAY_VALUE. Extract a date from the user's reply.
Return ONLY the date in YYYY-MM-DD format, or "null" if unclear.
Examples:
User: "15th august" → "2026-08-15"
User: "tomorrow" → date after TODAY_VALUE
User: "next Monday" → compute the correct date
Now: "USER_MESSAGE" → """
    return prompt.replace("TODAY_VALUE", today)

async def extract_date_from_reply(text: str) -> Optional[str]:
    prompt = get_date_extraction_prompt().replace("USER_MESSAGE", text)
    debug_print("Prompt sent to Gemini (date extraction)", prompt)
    try:
        # BUGFIX: run the blocking SDK call in a worker thread so it doesn't
        # freeze the bot's event loop for other users while waiting on Gemini
        response = await asyncio.to_thread(generate_with_retry, prompt)
        result = response.text.strip()
        debug_print("Gemini raw response (date extraction)", result)
        if result.lower() == 'null':
            debug_print("Parsed date", "None (Gemini returned 'null')")
            return None
        # Validate format
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
    """
    Guarantee sane values before we show a confirmation / create an event.
    BUGFIX: the LLM's "missing" list can't be fully trusted on its own — it
    may leave a field explicitly null without flagging it as missing — so we
    also double-check the actual field values here instead of only trusting
    "missing".
    """
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
    # BUGFIX: use HTML parse mode + escaping instead of "**bold**" with
    # parse_mode='Markdown' (legacy Markdown doesn't support "**", and
    # unescaped LLM-extracted text can contain characters that break parsing)
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
# Create Google Calendar Event (supports all‑day)
# -------------------------------------------------------------------
def create_calendar_event(summary: str, start_date: str,
                          start_time: Optional[str] = None,
                          duration_minutes: int = 60,
                          location: Optional[str] = None,
                          description: Optional[str] = None,
                          recurrence: Optional[str] = None,
                          all_day: bool = False):
    if all_day:
        # All-day events use 'date' fields, no time
        event_body = {
            'summary': summary,
            'location': location,
            'description': description,
            'start': {
                'date': start_date,
                'timeZone': 'Asia/Kolkata',
            },
            'end': {
                'date': (datetime.fromisoformat(start_date) + timedelta(days=1)).strftime('%Y-%m-%d'),
                'timeZone': 'Asia/Kolkata',
            },
        }
    else:
        # Timed event
        start_dt_str = f"{start_date}T{start_time}:00"
        start_dt = datetime.fromisoformat(start_dt_str)
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        event_body = {
            'summary': summary,
            'location': location,
            'description': description,
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'Asia/Kolkata',
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'Asia/Kolkata',
            },
        }
    if recurrence:
        event_body['recurrence'] = [f"RRULE:{recurrence}"]

    debug_print("Event body being sent to Google Calendar API", json.dumps(event_body, indent=2, default=str))

    created_event = calendar_service.events().insert(
        calendarId=CALENDAR_ID,
        body=event_body
    ).execute()

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
        # BUGFIX: offload the blocking Gemini call to a thread
        extracted = await asyncio.to_thread(extract_event_details, text)
        missing = extracted.get('missing', [])

        # If date missing (or the LLM left it empty without flagging it) → ask for date
        if 'date' in missing or not extracted.get('date'):
            debug_print("Decision", f"Date missing (missing={missing}) -> asking user for date, moving to STATE_AWAITING_DATE")
            user_states[user_id] = {
                'state': STATE_AWAITING_DATE,
                'extracted': extracted,
            }
            await update.message.reply_text("📅 What date? (e.g., 2026-08-15, tomorrow, next Monday)")
            return

        # Date is present — fill in safe defaults (event name / duration / all-day) and confirm
        finalize_extracted(extracted)
        debug_print("Decision", "Date present -> moving to STATE_CONFIRMATION")
        user_states[user_id] = {
            'state': STATE_CONFIRMATION,
            'extracted': extracted,
        }
        await ask_confirmation(update, extracted)

    elif state == STATE_AWAITING_DATE:
        date_str = await extract_date_from_reply(text)
        if not date_str:
            debug_print("Decision", "Could not parse a date from the reply -> asking again")
            await update.message.reply_text("I didn't understand that date. Please try again (e.g., 2026-08-15, tomorrow).")
            return

        user_data = user_states[user_id]
        user_data['extracted']['date'] = date_str

        finalize_extracted(user_data['extracted'])
        debug_print("Decision", f"Date set to {date_str} -> moving to STATE_CONFIRMATION")
        user_data['state'] = STATE_CONFIRMATION
        await ask_confirmation(update, user_data['extracted'])

    elif state == STATE_CONFIRMATION:
        user_data = user_states.get(user_id)
        if not user_data:
            debug_print("Decision", "No stored state found for this user -> resetting")
            await update.message.reply_text("Something went wrong. Please start again.")
            user_states.pop(user_id, None)
            return

        if text.lower() in ['yes', 'y', 'confirm', 'ok']:
            debug_print("Decision", "User confirmed -> creating calendar event")
            extracted = user_data['extracted']
            try:
                # BUGFIX: offload the blocking Calendar API call to a thread
                event = await asyncio.to_thread(
                    create_calendar_event,
                    summary=extracted['event_name'],
                    start_date=extracted['date'],
                    start_time=extracted.get('time'),
                    duration_minutes=extracted.get('duration_minutes', 60),
                    location=extracted.get('location'),
                    description=extracted.get('description'),
                    recurrence=extracted.get('recurrence'),
                    all_day=extracted.get('all_day', False)
                )
                if extracted.get('all_day'):
                    await update.message.reply_text(
                        f"✅ All‑day event created!\n"
                        f"📌 {event.get('summary')}\n"
                        f"📅 {event['start'].get('date')}\n"
                        f"🔗 {event.get('htmlLink')}"
                    )
                else:
                    await update.message.reply_text(
                        f"✅ Event created!\n"
                        f"📌 {event.get('summary')}\n"
                        f"📅 {event['start'].get('dateTime', event['start'].get('date'))}\n"
                        f"🔗 {event.get('htmlLink')}"
                    )
            except Exception as e:
                debug_print("Calendar creation FAILED", str(e))
                logger.error(f"Calendar API error: {e}")
                await update.message.reply_text("❌ Failed to create event. Please try again.")
            finally:
                user_states.pop(user_id, None)
        elif text.lower() in ['no', 'n', 'cancel']:
            debug_print("Decision", "User cancelled")
            await update.message.reply_text("Cancelled. Send a new message to create an event.")
            user_states.pop(user_id, None)
        else:
            debug_print("Decision", f"Unrecognized confirmation reply: {text!r} -> re-prompting")
            await update.message.reply_text("Please reply with Yes or No to confirm.")

# -------------------------------------------------------------------
# Main function
# -------------------------------------------------------------------
def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        logger.error("Please set TELEGRAM_TOKEN and GEMINI_API_KEY environment variables.")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()