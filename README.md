# AI Agent Scheduler

This AI agent reads your Gmail, extracts event details using GPT-4, and schedules them in Google Calendar.

## Setup
1. Add Google OAuth `credentials.json` to `credentials/`
2. Install requirements:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
3. Add your `.env` file with OpenAI API key and timezone.
4. Run with:
```bash
PYTHONPATH=src python3 src/main.py
```

## 📐 2. High-Level Design (HLD)

### System Architecture:

```
+-----------------------+
|   Gmail Inbox         | ← Poll for unread & replies
+-----------------------+
             ↓
+-----------------------+     ↔     +----------------------+
|  Main Agent Loop      | ←→ GPT ←→ |  OpenAI Reasoner     |
|  (main.py)            |           |  (Parse + Suggest)   |
+-----------------------+           +----------------------+
             ↓
+-----------------------+
|  Calendar Scheduler    | → Google Calendar API
+-----------------------+
             ↓
+----------------------------+
|  Pending Confirmations DB |
|  (JSON file on disk)      |
+----------------------------+
```

---

## 🧑‍🔬 3. Low-Level Design (LLD)

### 📁 Folder Structure:

```
ai-agent-scheduler/
├── src/
│   ├── main.py
│   ├── email_reader.py
│   ├── event_parser.py
│   ├── calendar_scheduler.py
│   ├── confirmation_tracker.py
│   └── response_processor.py
├── pending_confirmations.json
├── credentials/credentials.json
├── requirements.txt
└── .env
```

---

### 🔄 Main Workflow (main.py)

- Authenticates Gmail and Calendar APIs
- Scans inbox for new emails
- Uses GPT to extract meeting info
- Checks calendar availability
  - ✅ Schedules event if free
  - ❌ Suggests alternatives if busy
- Stores options in `pending_confirmations.json`
- Scans replies and schedules confirmed events

---

### 🧩 Component Details

#### ✅ email_reader.py
- Extracts plain-text email body
- Handles MIME recursion and decoding

#### ✅ event_parser.py
- GPT prompt for strict JSON output:
  - `"title"`, `"date"`, `"start"`, `"end"`
- Handles casual language: "let’s catch up tomorrow"

#### ✅ calendar_scheduler.py
- Checks free/busy via Google Calendar API
- Schedules confirmed events
- If conflict, asks GPT for alternatives
- Emails suggestions via Gmail API

#### ✅ confirmation_tracker.py
- Writes/reads `pending_confirmations.json`
- Tracks which sender is waiting on a reply

#### ✅ response_processor.py
- Scans new replies
- Matches reply text to stored options using GPT
- Schedules selected time if matched
- Marks conversation as complete

---

### 🔐 .env Configuration

```env
OPENAI_API_KEY=sk-xxxxxxx
TIMEZONE=Asia/Kolkata
```

---

### 🔧 SCOPES

```python
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar"
]
```

---