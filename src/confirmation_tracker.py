import json
import os

PENDING_FILE = "pending_confirmations.json"

def load_pending_confirmations():
    if not os.path.exists(PENDING_FILE):
        return {}
    with open(PENDING_FILE, "r") as f:
        return json.load(f)

def save_pending_confirmations(data):
    with open(PENDING_FILE, "w") as f:
        json.dump(data, f, indent=2)

def add_pending_confirmation(sender_email, options, message_id=None):
    data = load_pending_confirmations()
    data[sender_email] = {
        "options": options,
        "message_id": message_id
    }
    save_pending_confirmations(data)

def remove_pending_confirmation(sender_email):
    data = load_pending_confirmations()
    if sender_email in data:
        del data[sender_email]
        save_pending_confirmations(data)

def get_pending_confirmation(sender_email):
    data = load_pending_confirmations()
    return data.get(sender_email)