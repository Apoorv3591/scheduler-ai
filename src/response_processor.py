import re
import json
from confirmation_tracker import (
    get_pending_confirmation,
    remove_pending_confirmation
)
from calendar_scheduler import schedule_event
from email_reader import extract_body
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def parse_confirmation_reply(reply_text, options):
    # Ask GPT to convert natural language into a selected option
    prompt = f"""
You are an assistant that interprets user replies to meeting suggestions.

The original options were:
{json.dumps(options, indent=2)}

The user's reply is:
\"\"\"
{reply_text}
\"\"\"

Respond with only the selected option as JSON. Use exact values from the original list.
If no option matches, return: null
"""

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )

    content = response.choices[0].message.content.strip()
    try:
        return json.loads(content)
    except:
        return None

def process_replies(gmail_service, calendar_service):
    print("📥 Checking replies to suggested meeting options...")
    results = gmail_service.users().messages().list(userId='me', labelIds=['INBOX'], q="is:unread", maxResults=5).execute()
    messages = results.get('messages', [])

    for msg in messages:
        full_msg = gmail_service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
        headers = full_msg.get("payload", {}).get("headers", [])
        payload = full_msg.get("payload", {})
        sender_email = next((h['value'] for h in headers if h['name'].lower() == 'from'), None)

        if sender_email:
            match = re.search(r'<(.+?)>', sender_email)
            if match:
                sender_email = match.group(1)

            pending = get_pending_confirmation(sender_email)
            if pending:
                reply_text = extract_body(payload)
                print(f"📨 Reply from {sender_email}:\n{reply_text[:300]}...\n")

                selected = parse_confirmation_reply(reply_text, pending['options'])

                if selected:
                    event_info = {
                        "title": "Confirmed Meeting",
                        "date": selected['date'],
                        "start": selected['start'],
                        "end": selected['end']
                    }

                    schedule_event(calendar_service, event_info, sender_email=sender_email, gmail_service=gmail_service)
                    remove_pending_confirmation(sender_email)
                    print(f"✅ Scheduled confirmed slot for {sender_email}.")
                else:
                    print("⚠️ Could not match a valid option from reply.")

        # Mark the email as read after processing
        gmail_service.users().messages().modify(userId='me', id=msg['id'], body={'removeLabelIds': ['UNREAD']}).execute()
