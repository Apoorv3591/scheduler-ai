from flask import Flask, request, jsonify, redirect, session, url_for, g
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials as GoogleCredentials
from googleapiclient.discovery import build
import google.auth.transport.requests
import firebase_admin
from firebase_admin import credentials as fb_credentials, firestore, auth as firebase_auth
import threading
import os
import json

from agent_core import run_agent_for_user, auth_services
from calendar_scheduler import schedule_event
from response_processor import process_replies
from event_parser import parse_event
from firebase_utils import get_firestore
from datetime import datetime
# -------------------- FLASK SETUP --------------------
app = Flask(__name__)
app.secret_key = "your_super_secret_key_here"
CORS(app)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# -------------------- FIREBASE INIT --------------------
firebase_admin.initialize_app(fb_credentials.Certificate("/etc/secrets/firebase_service_key.json"))
db = firestore.client()

# -------------------- CONSTANTS --------------------
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly"
]
CLIENT_SECRET_FILE = "/etc/secrets/credentials.json"
background_agents = {}
agent_flags = {}

# -------------------- HELPERS --------------------

def require_login(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing Authorization Header"}), 401
        token = auth_header.split("Bearer ")[1]
        try:
            decoded = firebase_auth.verify_id_token(token)
            g.firebase_uid = decoded["uid"]
            return f(*args, **kwargs)
        except Exception as e:
            return jsonify({"error": f"Invalid token: {str(e)}"}), 401
    return wrapper

def get_user_services(uid):
    doc_ref = db.collection("users").document(uid)
    doc = doc_ref.get()
    if not doc.exists:
        raise Exception(f"No stored credentials for uid={uid}")
    creds_data = doc.to_dict().get("google_creds")
    if not creds_data:
        raise Exception("Missing google_creds in Firestore")
    creds = GoogleCredentials(
        token=creds_data["token"],
        refresh_token=creds_data["refresh_token"],
        token_uri=creds_data["token_uri"],
        client_id=creds_data["client_id"],
        client_secret=creds_data["client_secret"],
        scopes=creds_data["scopes"]
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
    gmail = build("gmail", "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)
    return gmail, calendar

# -------------------- ROUTES --------------------

@app.route("/")
def home():
    return {"status": "AI Scheduler running"}, 200

# @app.route("/start-oauth")
# def start_oauth():
#     uid = request.args.get("uid")
#     if not uid:
#         return jsonify({"error": "Unauthorized"}), 401
#     flow = Flow.from_client_secrets_file(
#         CLIENT_SECRET_FILE,
#         scopes=SCOPES,
#         redirect_uri=url_for("oauth_callback", _external=True)
#     )
#     auth_url, state = flow.authorization_url(
#         access_type="offline",
#         include_granted_scopes="true",
#         prompt="consent"
#     )
#     session["uid"] = uid
#     session["state"] = state
#     return redirect(auth_url)

# @app.route("/oauth/callback")
# def oauth_callback():
#     if "uid" not in session or "state" not in session:
#         return "Missing session", 400
#     flow = Flow.from_client_secrets_file(
#         CLIENT_SECRET_FILE,
#         scopes=SCOPES,
#         redirect_uri=url_for("oauth_callback", _external=True)
#     )
#     flow.fetch_token(authorization_response=request.url)
#     credentials = flow.credentials
#     token_data = {
#         "token": credentials.token,
#         "refresh_token": credentials.refresh_token,
#         "token_uri": credentials.token_uri,
#         "client_id": credentials.client_id,
#         "client_secret": credentials.client_secret,
#         "scopes": credentials.scopes,
#         "expiry": str(credentials.expiry)
#     }
#     uid = session["uid"]
#     db.collection("users").document(uid).set({"google_creds": token_data}, merge=True)
#     return redirect("http://localhost:3000/dashboard?auth_success=true")

@app.route("/agent-status")
@require_login
def agent_status():
    uid = g.firebase_uid
    doc = db.collection("users").document(uid).get()
    if doc.exists:
        status = doc.to_dict().get("agentEnabled", False)
        return jsonify({"running": status}), 200
    return jsonify({"running": False}), 200

@app.route("/toggle-agent", methods=["POST"])
@require_login
def toggle_agent():
    data = request.get_json()
    enable = data.get("enable", False)
    uid = g.firebase_uid
    doc_ref = db.collection("users").document(uid)
    doc_ref.set({"agentEnabled": enable}, merge=True)

    if enable:
        if uid not in background_agents:
            stop_event = threading.Event()
            thread = threading.Thread(target=run_agent_for_user, args=(uid, stop_event), daemon=True)
            background_agents[uid] = thread
            agent_flags[uid] = stop_event
            thread.start()
            print(f"✅ Started agent for UID: {uid}")
    else:
        if uid in agent_flags:
            agent_flags[uid].set()
            background_agents.pop(uid, None)
            agent_flags.pop(uid, None)
            print(f"🛑 Stopped agent for UID: {uid}")

    return jsonify({"uid": uid, "running": enable}), 200

@app.route("/schedule", methods=["POST"])
@require_login
def schedule():
    data = request.get_json()
    email_text = data.get("email_text")
    sender_email = data.get("sender_email")
    if not email_text or not sender_email:
        return jsonify({"error": "Missing email_text or sender_email"}), 400

    uid = g.firebase_uid
    try:
        gmail, calendar = get_user_services(uid)
        parsed = parse_event(email_text)
        event_dict = json.loads(parsed)
        if all(k in event_dict for k in ("title", "date", "start", "end")):
            link = schedule_event(calendar, event_dict, sender_email, gmail)
            return jsonify({"status": "success", "link": link}), 200
        else:
            return jsonify({"error": "Missing fields in event"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/check-replies", methods=["POST"])
@require_login
def check_replies():
    uid = g.firebase_uid
    try:
        gmail, calendar = get_user_services(uid)
        process_replies(gmail, calendar , uid)
        return jsonify({"status": "Checked replies"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/user-status")
def user_status():
    uid = request.args.get("uid")
    if not uid:
        return jsonify({"connected": False, "reason": "Missing UID"}), 400
    doc = db.collection("users").document(uid).get()
    if doc.exists and doc.to_dict().get("google_creds"):
        return jsonify({"connected": True}), 200
    return jsonify({"connected": False}), 200

@app.route('/api/activity-stats/<uid>', methods=['GET'])
def activity_stats(uid):
    try:
        db = get_firestore()
        logs = db.collection("users").document(uid).collection("activity_log").stream()

        from collections import Counter
        from datetime import datetime

        activity_counter = Counter()
        for log in logs:
            data = log.to_dict()
            ts = datetime.fromisoformat(data["timestamp"])
            key = ts.strftime("%Y-%m-%d")
            activity_counter[key] += 1

        return jsonify(activity_counter)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/upcoming-events/<uid>', methods=['GET'])
def upcoming_events(uid):
    try:
        _, service = get_user_services(uid)  # Fixed line
        now = datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=5, singleEvents=True,
            orderBy='startTime').execute()
        events = events_result.get('items', [])
        return jsonify(events)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/store-creds', methods=['POST'])
def store_creds():
    data = request.json
    uid = data.get('uid')
    token = data.get('access_token')
    if not uid or not token:
        return jsonify({"error": "Missing uid or token"}), 400

    db = get_firestore()
    db.collection("users").document(uid).set(
        {"google_creds": {"access_token": token}},
        merge=True
    )
    return jsonify({"message": "Stored successfully"}), 200

# -------------------- MAIN --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
