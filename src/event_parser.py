from openai import OpenAI
from dotenv import load_dotenv
import os
from datetime import datetime
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MAX_EMAIL_LENGTH = 3000  # You can tune this lower if you still hit limits
today = datetime.utcnow().strftime("%Y-%m-%d")
def parse_event(email_text):
    truncated_email = email_text.strip()[:MAX_EMAIL_LENGTH]
    today = datetime.utcnow().strftime("%Y-%m-%d")
    prompt = f""" Today's date is {today}.
    You are a meeting assistant that extracts calendar events from email messages.
    Ensure that suggested times are in the future only.
Return a strict JSON object using this format:
{{
  "title": "Team Sync",
  "date": "YYYY-MM-DD",
  "start": "HH:MM",
  "end": "HH:MM"
}}

Rules:
- Convert relative dates like "tomorrow", "next Friday", or "day after" into YYYY-MM-DD format using today as {get_today()}.
- Interpret common casual intent phrases like "let’s sync", "catch up", "quick call", "connect", "discussion", etc., and assign them a meaningful title.
- Time must be in 24-hour HH:MM format.
- If no meeting is found, return an empty object: {{}}
- DO NOT include any explanations, only valid JSON.

Email:
\"\"\"
{truncated_email}
\"\"\"
"""

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def get_today():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")
