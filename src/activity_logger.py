from datetime import datetime
from firebase_utils import get_firestore

def log_user_activity(uid, event_type, details):
    """
    Logs a user activity with a timestamp into Firestore.
    """
    db = get_firestore()
    try:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "details": details
        }
        db.collection("users").document(uid).collection("activity_log").add(log_entry)
    except Exception as e:
        print(f"⚠️ Failed to log activity for {uid}: {e}")
