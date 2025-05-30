import os
import json
import time
import re
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from email_reader import extract_body
from event_parser import parse_event
from calendar_scheduler import schedule_event

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.send'
]

def auth_services():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file('credentials/credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    from googleapiclient.discovery import build
    gmail_service = build('gmail', 'v1', credentials=creds)
    calendar_service = build('calendar', 'v3', credentials=creds)
    return gmail_service, calendar_service

def extract_sender_email(headers):
    sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), None)
    if sender:
        match = re.search(r'<(.+?)>', sender)
        if match:
            return match.group(1)
        return sender
    return None

def main():
    gmail, calendar = auth_services()
    seen_ids = set()

    while True:
        print("\n🔄 Checking for new unread emails...")
        try:
            results = gmail.users().messages().list(userId='me', labelIds=['INBOX'], q="is:unread", maxResults=5).execute()
            messages = results.get('messages', [])

            if not messages:
                print("📭 No new unread emails.")
            else:
                for msg in messages:
                    msg_id = msg['id']
                    if msg_id in seen_ids:
                        continue
                    seen_ids.add(msg_id)

                    full_msg = gmail.users().messages().get(userId='me', id=msg_id, format='full').execute()
                    payload = full_msg.get("payload", {})
                    email_text = extract_body(payload)
                    sender_email = extract_sender_email(payload.get("headers", []))

                    print("\n📨 Email content:\n", email_text[:300], "...\n")
                    print(f"📧 Sender: {sender_email}")

                    parsed = parse_event(email_text)
                    print("🤖 GPT Response:", parsed)

                    try:
                        event_dict = json.loads(parsed)
                        if event_dict and all(k in event_dict for k in ("title", "date", "start", "end")):
                            link = schedule_event(
                                service=calendar,
                                event_info=event_dict,
                                sender_email=sender_email,
                                gmail_service=gmail
                            )
                            if link:
                                print("✅ Event scheduled:", link)
                        else:
                            print("ℹ️ Event info incomplete or missing, skipping.")
                    except json.JSONDecodeError:
                        print("⚠️ GPT response was not valid JSON.")
                    except Exception as e:
                        print("❌ Error while scheduling event:", e)

        except Exception as e:
            print("❌ Failed to read or process email:", e)

        from response_processor import process_replies
        process_replies(gmail, calendar)
        time.sleep(60)

if __name__ == "__main__":
    main()