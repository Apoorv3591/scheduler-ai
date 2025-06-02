import firebase_admin
from firebase_admin import credentials, firestore

def get_firestore():
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate("/etc/secrets/firebase_service_key.json"))
    return firestore.client()
