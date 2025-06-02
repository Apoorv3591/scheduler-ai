import os
import json
import time
import re
from google.oauth2.credentials import Credentials as GoogleCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email_reader import extract_body
from event_parser import parse_event
from calendar_scheduler import schedule_event
from response_processor import process_replies
import firebase_admin
from firebase_admin import credentials, firestore
from activity_logger import log_user_activity

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]


def get_firestore():
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("/etc/secrets/firebase_service_key.json"))
    return firestore.client()


# def auth_services(uid=None):
#     creds = None
#     creds_path = '/etc/secrets/credentials.json'

#     if uid:
#         token_path = f'tokens/{uid}.json'
#         if os.path.exists(token_path):
#             creds = Credentials.from_authorized_user_file(token_path, SCOPES)
#         else:
#             os.makedirs('tokens', exist_ok=True)
#             flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
#             creds = flow.run_local_server(port=0)
#             with open(token_path, 'w') as token:
#                 token.write(creds.to_json())
#     else:
#         # Admin credentials
#         creds = Credentials.from_authorized_user_file('token.json', SCOPES)

#     gmail_service = build('gmail', 'v1', credentials=creds)
#     calendar_service = build('calendar', 'v3', credentials=creds)
#     return gmail_service, calendar_service

def auth_services(uid):
    db = get_firestore()
    doc_ref = db.collection("users").document(uid)
    doc = doc_ref.get()
    if not doc.exists:
        raise Exception(f"No stored credentials for uid={uid}")

    creds_data = doc.to_dict().get("google_creds", {})
    
    # ✅ Support both new (access_token) and legacy (token) field
    token = creds_data.get("access_token") or creds_data.get("token")
    if not token:
        raise Exception(f"Missing access token for uid={uid}")

    refresh_token = creds_data.get("refresh_token")
    client_id = creds_data.get("client_id") or os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = creds_data.get("client_secret") or os.environ.get("GOOGLE_CLIENT_SECRET")
    token_uri = creds_data.get("token_uri", "https://oauth2.googleapis.com/token")
    scopes = creds_data.get("scopes") or [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly"
    ]

    creds = GoogleCredentials(
        token=token,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes
    )

    

    gmail = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)
    return gmail, calendar

def extract_sender_email(headers):
    sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), None)
    if sender:
        match = re.search(r'<(.+?)>', sender)
        return match.group(1) if match else sender
    return None

def load_seen_ids(uid):
    """
    Load the seen message IDs for a specific user from Firestore.
    """
    db = get_firestore()
    try:
        doc = db.collection("users").document(uid).get()
        if doc.exists:
            seen_ids = doc.to_dict().get("google_creds", {}).get("seen_ids", [])
            return set(seen_ids)
    except Exception as e:
        print(f"⚠️ Failed to load seen_ids for UID {uid}: {e}")
    return set()

def save_seen_ids(uid, seen_ids_set):
    """
    Save updated seen message IDs for the user back to Firestore without overwriting other google_creds fields.
    """
    db = get_firestore()
    try:
        doc_ref = db.collection("users").document(uid)
        doc_ref.update({
            "google_creds.seen_ids": list(seen_ids_set)
        })
    except Exception as e:
        print(f"⚠️ Failed to save seen_ids for UID {uid}: {e}")

def user_agent_loop(uid, gmail, calendar):
    seen_ids = load_seen_ids(uid)
    print(f"🤖 Agent started for user: {uid}")

    stop_event = agent_flags.get(uid)
    if stop_event is None:
        stop_event = threading.Event()
        agent_flags[uid] = stop_event

    while not stop_event.is_set():
        try:
            results = gmail.users().messages().list(
                userId='me', labelIds=['INBOX'], q="is:unread", maxResults=5
            ).execute()
            messages = results.get('messages', [])

            if not messages:
                print("📭 No unread messages.")
            else:
                for msg in messages:
                    msg_id = msg['id']
                    if msg_id in seen_ids:
                        continue

                    seen_ids.add(msg_id)
                    full_msg = gmail.users().messages().get(
                        userId='me', id=msg_id, format='full'
                    ).execute()
                    payload = full_msg.get("payload", {})
                    email_text = extract_body(payload)
                    sender_email = extract_sender_email(payload.get("headers", []))

                    print(f"\n📧 From: {sender_email}\n📨 Email: {email_text[:200]}...")
                    log_user_activity(uid, "EmailProcessed", f"Parsed subject from {sender_email}")
                    parsed = parse_event(email_text)
                    print("🤖 GPT:", parsed)

                    try:
                        event_dict = json.loads(parsed)
                        if all(k in event_dict for k in ("title", "date", "start", "end")):
                            link = schedule_event(calendar, event_dict, sender_email, gmail)
                            print("✅ Event scheduled:", link)
                        else:
                            print("⚠️ Missing required fields.")
                    except json.JSONDecodeError:
                        print("⚠️ GPT output is not valid JSON.")
                    except Exception as e:
                        print("❌ Scheduling error:", e)

            # Trim seen_ids to last 500
            if len(seen_ids) > 500:
                seen_ids = set(list(seen_ids)[-500:])
            save_seen_ids(uid, seen_ids)

            process_replies(gmail, calendar,uid)

        except Exception as e:
            print("❌ Agent loop error:", e)

        time.sleep(60)

    print(f"👋 Agent thread stopped for user {uid}")

def run_agent_for_user(uid, stop_event):
    print(f"🚀 run_agent_for_user() called for UID: {uid}")
    try:
        gmail, calendar = auth_services(uid)
        seen_ids = load_seen_ids(uid)
        print(f"🤖 Background agent thread started for {uid}")
    except Exception as e:
        print(f"❌ Agent failed to start for {uid}: {e}")
        return  # Exit the thread

    while not stop_event.is_set():
        try:
            results = gmail.users().messages().list(
                userId='me', labelIds=['INBOX'], q="is:unread", maxResults=5
            ).execute()
            messages = results.get('messages', [])

            for msg in messages:
                msg_id = msg['id']
                if msg_id in seen_ids:
                    continue

                seen_ids.add(msg_id)
                full_msg = gmail.users().messages().get(
                    userId='me', id=msg_id, format='full'
                ).execute()
                payload = full_msg.get("payload", {})
                email_text = extract_body(payload)
                sender_email = extract_sender_email(payload.get("headers", []))

                print(f"\n📧 From: {sender_email}\n📨 Email: {email_text[:200]}...")
                log_user_activity(uid, "EmailProcessed", f"Parsed subject from {sender_email}")
                parsed = parse_event(email_text)
                print("🤖 GPT:", parsed)

                try:
                    event_dict = json.loads(parsed)
                    if all(k in event_dict for k in ("title", "date", "start", "end")):
                        link = schedule_event(calendar, event_dict, sender_email, gmail)
                        print("✅ Event scheduled:", link)
                        log_user_activity(uid, "EventScheduled", f"Scheduled '{event_dict['title']}' on {event_dict['date']} at {event_dict['start']}")
                    else:
                        print("⚠️ Missing required fields.")
                except json.JSONDecodeError:
                    print("⚠️ GPT output is not valid JSON.")
                except Exception as e:
                    print("❌ Scheduling error:", e)

            # Trim seen_ids to last 500
            if len(seen_ids) > 500:
                seen_ids = set(list(seen_ids)[-500:])
            save_seen_ids(uid, seen_ids)

            process_replies(gmail, calendar,uid)

        except Exception as e:
            print("❌ Agent run error:", e)

        time.sleep(60)

    print(f"👋 Agent thread stopped for user {uid}")
