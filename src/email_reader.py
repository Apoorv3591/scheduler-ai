
from googleapiclient.discovery import build
import base64




def extract_body(payload):
    if 'data' in payload.get('body', {}):
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
    elif 'parts' in payload:
        for part in payload['parts']:
            try:
                return extract_body(part)
            except:
                continue
    return "No message body found"

def get_latest_unread_email(service):
    results = service.users().messages().list(userId='me', labelIds=['INBOX'], q="is:unread", maxResults=1).execute()
    messages = results.get('messages', [])
    if not messages:
        return None

    msg = service.users().messages().get(userId='me', id=messages[0]['id'], format='full').execute()
    return extract_body(msg['payload'])

