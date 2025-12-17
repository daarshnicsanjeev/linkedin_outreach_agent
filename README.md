# 🚀 Zero-Trust LinkedIn AI Agent Suite

A privacy-first AI automation suite for LinkedIn networking. Includes two powerful agents:
- **Outreach Agent** - AI-powered messaging for legal professionals with personalized "Zero-Trust" strategy reports
- **Notification Agent** - Automated connection invites to users who engage with your content
- **Invite Withdrawal Agent** - Automated cleanup of old, pending connection invites

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Playwright](https://img.shields.io/badge/Playwright-Automation-green.svg)
![Gemini](https://img.shields.io/badge/Google-Gemini%20AI-orange.svg)
![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)

---

## ✨ Features

### 🎯 LinkedIn Outreach Agent (`linkedin_agent.py`)

| Feature | Description |
|---------|-------------|
| **AI Role Classification** | Uses Gemini AI to classify connections as `PRACTICING` (lawyers), `GENERAL` (legal-adjacent), or `SKIP` |
| **Zero-Trust Analysis** | Generates AI prompts with bracketed placeholders—no PII ever exposed |
| **PDF Reports** | Creates accessible, screen-reader friendly strategy PDFs |
| **Smart Messaging** | Role-based messaging workflow with duplicate prevention |
| **Vision AI Identity Verification** | Uses Gemini Vision to verify chat participant name before sending—prevents wrong-person messages |
| **Robust Chat Retry** | Dynamic retry logic with multiple fallback selectors for reliable chat opening |
| **Self-Optimization** | Learns from run history to automatically adjust 7 different timeout/retry settings |
| **Login Detection** | Audio alerts + toast notifications when login required |

### 🔔 Notification Engagement Agent (`notification_agent.py`)

| Feature | Description |
|---------|-------------|
| **AI Engagement Detection** | Uses Gemini AI to classify notifications—handles all reaction types (like, love, celebrate, insightful, etc.) |
| **Auto Connection Invites** | Sends invites to engaged non-connections (no note) |
| **Rate Limiting** | Configurable limits (default: 50 invites/run, 5s delay) |
| **Duplicate Prevention** | Tracks history to avoid re-inviting |
| **Multi-Profile Support** | Handles notifications with multiple engagers |
| **Fallback Detection** | Keyword-based fallback if AI unavailable |

### 🧹 Invite Withdrawal Agent (`invite_withdrawal_agent.py`)

| Feature | Description |
|---------|-------------|
| **Age-Based Cleanup** | Automatically withdraws invites older than 1 month (configurable) |
| **Smart Filtering** | Skips newer invites to give them time to accept |
| **Dialog Handling** | Automatically handles "Withdraw invite?" confirmation dialogs |
| **Bulk Processing** | Efficiently processes and withdraws multiple pages of sent invites |

---

## 📋 Prerequisites

- **Windows 10/11**
- **Python 3.8+** ([Download](https://www.python.org/downloads/))
- **Google Chrome**
- **Gemini API Key** ([Get one free](https://aistudio.google.com/))

---

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/linkedin-agent.git
cd linkedin-agent
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure API Key
Create a `.env` file:
```env
GEMINI_API_KEY=your_actual_api_key_here
```

---

## 🚀 Usage

### Outreach Agent (Messaging)
```bash
python linkedin_agent.py
```

**What it does:**
1. Scans your LinkedIn connections
2. AI classifies each contact's role
3. For **PRACTICING** lawyers: Sends intro → Generates personalized PDF → Sends follow-up with attachment
4. For **GENERAL** contacts: Sends intro only
5. Logs all activity and cleans up

### Notification Agent (Connection Invites)
```bash
python notification_agent.py
```
Or use the batch file:
```bash
run_notification_agent.bat
```

**What it does:**
1. Opens LinkedIn notifications page
2. Uses **Gemini AI** to classify each notification as engagement or not
3. Handles all reaction types: like, love, celebrate, insightful, curious, etc.
4. Checks connection status for each engager
5. Sends connection invites to non-connections
6. Tracks history to prevent duplicates

### 🧹 Invite Withdrawal Agent (Cleanup)
```bash
python invite_withdrawal_agent.py
```

**What it does:**
1. Navigates to "Sent Invites" page
2. identify invites older than the threshold (default: 1 month)
3. Withdraws them one by one
4. Handles confirmation dialogs automatically

> **First Run**: Chrome will open. Log in to LinkedIn manually. The session persists for future runs.

---

## ⏰ Automated Scheduling

### Outreach Agent (Daily 5PM-11PM, 1 contact/hour)
1. Edit paths in `run_agent_background.bat`
2. Run as Administrator:
```bash
setup_schedule.bat
```

### Manual Browser Launch
If Chrome connection fails, start the debug browser first:
```bash
start_agent_browser.bat
```

---

## 📁 Project Structure

```
linkedin-agent/
├── linkedin_agent.py        # Main outreach agent
├── notification_agent.py    # Notification engagement agent
├── invite_withdrawal_agent.py # Invite withdrawal agent
├── config.json              # Runtime configuration
├── config_manager.py        # Configuration management
├── optimizer.py             # Self-optimization logic
├── requirements.txt         # Python dependencies
├── .env                     # API keys (not committed)
├── .env.example             # API key template
├── .gitignore               # Git ignore rules
│
├── history.json             # Outreach message history (auto-generated)
├── notification_history.json # Notification agent history (auto-generated)
├── agent_history.json       # Run metrics for optimization (auto-generated)
│
├── run_agent_background.bat      # Background execution wrapper
├── run_notification_agent.bat    # Notification agent launcher
├── setup_schedule.bat            # Windows Task Scheduler setup
└── start_agent_browser.bat       # Manual Chrome debug launcher
```

---

## ⚙️ Configuration

### `config.json`

The agent uses a dynamic configuration that the self-optimizer adjusts automatically:

```json
{
  "keywords_practicing": ["partner", "attorney", ...],
  "keywords_general": ["student", "paralegal", ...],
  "timeouts": {
    "page_load": 5000,
    "scroll_wait": 10000,
    "message_send_wait": 2000,
    ...
  },
  "limits": {
    "max_scrolls": 50,
    "max_retries": 5,
    ...
  },
  "outreach_agent": {
    "fast_forward_wait": 1.5,
    "login_wait_timeout_seconds": 300
  },
  "notification_agent": {
    "max_notifications_per_run": 100,
    "max_invites_per_run": 50,
    "delay_between_invites": 5,
    "scroll_attempts": 15
  },
  "invite_withdrawal": {
    "min_age_days": 31,
    "delay_between_withdrawals": 2,
    "max_withdrawals_per_run": 100,
    "dialog_timeout_ms": 3000
  }
}
```

### Self-Optimizer Rules

The `optimizer.py` automatically tunes these values based on run history for **each agent type**:

| Agent | Metric | Action |
|-------|--------|--------|
| **Outreach** | Low scroll success rate | Increases `scroll_wait` |
| **Outreach** | Message verification failures | Increases `message_send_wait`, `ui_response_wait_ms` |
| **Outreach** | Chat open failures | Increases `chat_open_retries`, `chat_open_delay_ms` |
| **Outreach** | Identity verification failures | Increases `identity_poll_retries`, `identity_poll_delay_ms` |
| **Outreach** | File upload failures | Increases `file_upload_wait_ms` |
| **Notification** | Invite errors | Increases `delay_between_invites` |
| **Withdrawal** | Dialog timeouts | Increases `dialog_timeout_ms` |
| **All** | **Stable performance** | **Decreases waits/delays to speed up** |

### Agent Specific Configuration

All agent parameters are now centralzied in `config.json`.

**Notification Agent Settings:**
- `max_notifications_per_run`: Limit processing per session
- `max_invites_per_run`: Limit outgoing invites
- `delay_between_invites`: Base delay (optimized automatically)

**Invite Withdrawal Settings:**
- `min_age_days`: Invites older than this are withdrawn
- `max_withdrawals_per_run`: Safety limit per session
- `dialog_timeout_ms`: Wait time for confirmation dialogs (optimized automatically)

---

## 🔒 Privacy & Security

- **Local Execution** — Runs entirely on your machine
- **No Cloud Storage** — No data sent to external servers
- **Zero-Trust AI** — Generated prompts use `[PLACEHOLDER]` syntax, never real client data
- **Session Isolation** — Chrome profile stored locally at `C:\ChromeAutomationProfile`
- **Auto-Cleanup** — All temporary PDFs and screenshots are deleted immediately after the session ends

---

## 🧪 Testing

```bash
python test_connect.py      # Browser connection test
python test_v2_logic.py     # Business logic tests
python test_optimizer.py    # Optimizer tests
```

---

## 📊 Logs & History

| File | Purpose |
|------|---------|
| `agent_log.txt` | Detailed outreach agent logs |
| `notification_agent_log.txt` | Notification agent logs |
| `history.json` | Message history per contact |
| `notification_history.json` | Invited profiles & run history |
| `agent_history.json` | Run metrics for self-optimization |
| `resume_state.json` | Saves scrolling progress to resume after interruptions |

---

## 🔧 Troubleshooting

### Chrome Connection Failed (`ECONNREFUSED`)
```bash
# Option 1: Start debug browser manually
start_agent_browser.bat

# Option 2: Kill existing Chrome processes
taskkill /F /IM chrome.exe
# Then run agent again
```

### Login Required Alert
- The agent will play an audio alert and show a Windows notification
- Log in to LinkedIn in the opened browser
- Click "Resume Agent" in the notification

### PDF Generation Errors
- Usually caused by Unicode characters in names
- The agent auto-sanitizes text for PDF compatibility

---

## ⚠️ Disclaimer

This tool is for **educational and productivity purposes**. Please:
- Use responsibly
- Adhere to [LinkedIn's User Agreement](https://www.linkedin.com/legal/user-agreement)
- Review AI outputs before sending
- Respect LinkedIn's rate limits

The "Zero-Trust" protocols minimize data exposure, but always exercise judgment.

---

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

**Made with ❤️ for legal professionals embracing AI responsibly**
