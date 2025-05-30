from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def parse_event(email_text):
    prompt = f"""You are a meeting assistant that extracts calendar events from email messages.

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
{email_text}
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
