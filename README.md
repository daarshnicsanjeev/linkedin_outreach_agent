# 🚀 Zero-Trust LinkedIn AI Agent Suite

A privacy-first AI automation suite for LinkedIn networking with modular, maintainable architecture.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Playwright](https://img.shields.io/badge/Playwright-Automation-green.svg)
![Gemini](https://img.shields.io/badge/Google-Gemini%20AI-orange.svg)
![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)

---

## ✨ Agent Suite

| Agent | Purpose | Entry Point |
|-------|---------|-------------|
| **Outreach Agent** | AI-powered messaging to legal professionals with PDF reports | `outreach` |
| **Comment Agent** | Automated commenting on posts by legal professionals | `comment` |
| **Engagement Agent** | Likes mentions and replies to your content | `engagement` |
| **Notification Agent** | Sends connection invites to users who engage | `notification` |
| **Search Agent** | Boolean search for legal automation opportunities | `search` |
| **Invite Withdrawal Agent** | Cleanup old pending connection invites | `withdraw` |

---

## 🛠️ Installation

### 1. Clone & Install
```bash
git clone https://github.com/yourusername/linkedin-agent.git
cd linkedin-agent
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure API Key
Create a `.env` file:
```env
GEMINI_API_KEY=your_actual_api_key_here
```

---

## 🚀 Usage

### Using the CLI (Recommended)

```bash
# Run any agent using the unified CLI
python -m src.linkedin_agent.cli <agent>

# Examples:
python -m src.linkedin_agent.cli outreach
python -m src.linkedin_agent.cli comment
python -m src.linkedin_agent.cli engagement
python -m src.linkedin_agent.cli notification
python -m src.linkedin_agent.cli search
```

### CLI Options
```bash
python -m src.linkedin_agent.cli <agent> [options]

Options:
  --config, -c    Path to config file (default: config.json)
  --headless      Run browser in headless mode
  --debug         Enable debug mode with extra logging
```

### Legacy Entry Points (Still Supported)
```bash
# Original scripts in project root still work
python linkedin_agent.py       # Outreach
python comment_agent.py        # Comment
python engagement_agent.py     # Engagement
python notification_agent.py   # Notification
```

> **First Run**: Chrome will open. Log in to LinkedIn manually. The session persists for future runs.

---

## 📁 Project Structure

```
linkedin-agent/
├── src/linkedin_agent/          # Main package
│   ├── agents/                  # Agent implementations
│   │   ├── base_agent.py        # Shared agent functionality (~300 lines)
│   │   ├── outreach_agent.py    # Connection messaging
│   │   ├── comment_agent.py     # Auto-commenting
│   │   ├── engagement_agent.py  # Mentions & replies
│   │   ├── notification_agent.py # Connection invites
│   │   └── search_agent.py      # Prospect search
│   │
│   ├── core/                    # Core infrastructure
│   │   ├── config.py            # ConfigManager
│   │   ├── optimizer.py         # Self-optimization
│   │   └── constants.py         # Shared constants
│   │
│   ├── utils/                   # Shared utilities
│   │   ├── browser.py           # BrowserManager
│   │   ├── audio.py             # AudioManager
│   │   ├── gemini.py            # GeminiClient
│   │   └── anti_detection.py    # Human-like behavior
│   │
│   ├── templates/               # HTML templates
│   │   └── review_base.html     # Review page styling
│   │
│   └── cli.py                   # Command-line interface
│
├── data/                        # Persistent data (gitignored)
├── logs/                        # Log files (gitignored)
├── debug/                       # Debug artifacts (gitignored)
├── user_data/                   # Chrome profile (gitignored)
│
├── linkedin_agent.py            # Legacy entry point
├── comment_agent.py             # Legacy entry point
├── engagement_agent.py          # Legacy entry point
├── notification_agent.py        # Legacy entry point
│
├── config.json                  # Runtime configuration
├── pyproject.toml               # Python packaging
├── requirements.txt             # Dependencies
└── .env                         # API keys (not committed)
```

---

## 🏗️ Architecture

### BaseAgent Design

All agents inherit from `BaseAgent`, which provides:

```python
class BaseAgent(ABC):
    # Browser Management
    async def start_browser()      # Connect to Chrome with debugging
    async def navigate(url)        # Human-like navigation
    async def close_chat_popups()  # Handle LinkedIn chat modals
    async def stop_browser()       # Clean disconnect
    
    # Logging & Config
    def log(msg)                   # Console + file logging
    def get_config(key, default)   # Dot-notation config access
    
    # AI Integration  
    @property gemini               # Lazy-loaded GeminiClient
    
    # Audio Alerts
    def play_ready_sound()         # Multi-tone attention alert
    def play_complete_sound()      # Victory fanfare
    def show_notification(...)     # Windows toast notification
    
    # History Management
    def load_history(filename)     # Load JSON from data/
    def save_history(filename)     # Atomic save to data/
    
    # Debug Utilities
    async def capture_debug_screenshot()
    async def capture_debug_html()
    
    # Lifecycle
    async def execute()            # Main entry point (start → run → stop)
```

### Creating a New Agent

```python
from ..agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    def get_agent_name(self) -> str:
        return "MyAgent"
    
    async def run(self):
        """Your agent logic here."""
        await self.navigate("https://www.linkedin.com/")
        # ... do work ...
        self.play_complete_sound()
```

---

## ⚙️ Configuration

### `config.json`

```json
{
  "keywords_practicing": ["partner", "attorney", ...],
  "keywords_general": ["student", "paralegal", ...],
  "timeouts": {
    "page_load": 5000,
    "scroll_wait": 10000,
    "message_send_wait": 2000
  },
  "limits": {
    "max_scrolls": 50,
    "max_retries": 5
  },
  "notification_agent": {
    "max_notifications_per_run": 100,
    "max_invites_per_run": 50,
    "delay_between_invites": 5
  },
  "engagement_agent": {
    "max_scroll_attempts": 10,
    "max_notifications_per_run": 50,
    "review_server_port": 8000
  }
}
```

### Self-Optimizer

The `AgentOptimizer` automatically tunes values based on run history:

| Metric | Action |
|--------|--------|
| Low scroll success rate | Increases `scroll_wait` |
| Message verification failures | Increases `message_send_wait` |
| Chat open failures | Increases `chat_open_retries` |
| Stable performance | Decreases waits to speed up |

---

## 📊 Data Files

| File | Location | Purpose |
|------|----------|---------|
| `history.json` | `data/` | Outreach message history |
| `comment_history.json` | `data/` | Posted comments tracking |
| `notification_history.json` | `data/` | Invited profiles |
| `*.log` | `logs/` | Agent-specific logs |
| `debug_*.png` | `debug/screenshots/` | Debug screenshots |

---

## 🔒 Privacy & Security

- **Local Execution** — Runs entirely on your machine
- **No Cloud Storage** — No data sent to external servers
- **Zero-Trust AI** — Generated prompts use `[PLACEHOLDER]` syntax
- **Session Isolation** — Chrome profile stored locally
- **Auto-Cleanup** — Temporary files deleted after sessions

---

## 🔧 Troubleshooting

### Chrome Connection Failed
```bash
# Kill existing Chrome and try again
taskkill /F /IM chrome.exe
python -m src.linkedin_agent.cli engagement
```

### Login Required
- Agent plays audio alert and shows Windows notification
- Log in to LinkedIn in the opened browser
- Agent continues automatically

### Import Errors
```bash
# Make sure you're in the project root
cd linkedin_outreach_agent

# Run with explicit path
python -m src.linkedin_agent.cli engagement
```

---

## ⚠️ Disclaimer

This tool is for **educational and productivity purposes**. Please:
- Use responsibly
- Adhere to [LinkedIn's User Agreement](https://www.linkedin.com/legal/user-agreement)
- Review AI outputs before sending
- Respect LinkedIn's rate limits

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

**Made with ❤️ for legal professionals embracing AI responsibly**
