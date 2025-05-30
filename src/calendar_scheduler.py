from googleapiclient.discovery import build
import os
import json
from datetime import timedelta
from dotenv import load_dotenv
from openai import OpenAI
from confirmation_tracker import add_pending_confirmation

load_dotenv()
TIMEZONE = os.getenv("TIMEZONE")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_timezone_suffix():
    offset = timedelta(hours=5, minutes=30) if TIMEZONE == "Asia/Kolkata" else timedelta(0)
    return f"{offset.total_seconds() // 3600:+03.0f}:{int((offset.total_seconds() % 3600) / 60):02}"

def is_time_slot_free(service, start_time_iso, end_time_iso):
    body = {
        "timeMin": start_time_iso,
        "timeMax": end_time_iso,
        "timeZone": TIMEZONE,
        "items": [{"id": "primary"}]
    }
    events_result = service.freebusy().query(body=body).execute()
    busy_slots = events_result['calendars']['primary']['busy']
    return len(busy_slots) == 0

def generate_alternate_slots(event_info):
    prompt = f"""
Given the following event request:

Title: {event_info['title']}
Preferred Date: {event_info['date']}
Preferred Start Time: {event_info['start']}
Preferred End Time: {event_info['end']}

Suggest two alternate time slots that are on the same day or nearby days, avoiding late evenings or early mornings. Return strict JSON in this format:

{{
  "options": [
    {{
      "date": "2025-05-30",
      "start": "14:00",
      "end": "15:00"
    }},
    {{
      "date": "2025-05-31",
      "start": "11:00",
      "end": "12:00"
    }}
  ]
}}
"""
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    content = response.choices[0].message.content
    try:
        return json.loads(content)["options"]
    except Exception:
        print("⚠️ Could not parse alternate slots from GPT.")
        return []

def schedule_event(service, event_info, sender_email=None, gmail_service=None):
    date = event_info['date']
    start = event_info['start']
    end = event_info['end']

    start_time_iso = f"{date}T{start}:00{get_timezone_suffix()}"
    end_time_iso = f"{date}T{end}:00{get_timezone_suffix()}"

    if not is_time_slot_free(service, start_time_iso, end_time_iso):
        print("⛔ Time slot is busy — suggesting alternatives.")
        if sender_email and gmail_service:
            options = generate_alternate_slots(event_info)
            if options:
                add_pending_confirmation(sender_email, options)

                body = "Hi, I'm unavailable at the requested time. Here are two alternate options:\n\n"
                for idx, opt in enumerate(options, 1):
                    body += f"{idx}. {opt['date']} from {opt['start']} to {opt['end']}\n"
                body += "\nPlease reply with your preferred option."

                send_email_reply(gmail_service, sender_email, "Alternate meeting time suggestions", body)
        return None

    event = {
        'summary': event_info['title'],
        'start': {'dateTime': f"{date}T{start}:00", 'timeZone': TIMEZONE},
        'end': {'dateTime': f"{date}T{end}:00", 'timeZone': TIMEZONE}
    }

    if sender_email:
        event['attendees'] = [{'email': sender_email}]

    created = service.events().insert(
        calendarId='primary',
        body=event,
        sendUpdates="all" if sender_email else "none"
    ).execute()

    return created.get('htmlLink')

def send_email_reply(gmail_service, recipient, subject, message_body):
    from email.mime.text import MIMEText
    import base64

    message = MIMEText(message_body)
    message['to'] = recipient
    message['subject'] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body = {'raw': raw}

    gmail_service.users().messages().send(userId='me', body=body).execute()
    print("📤 Suggested alternate slots sent to sender.")
