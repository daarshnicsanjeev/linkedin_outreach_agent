# 🚀 Zero-Trust LinkedIn AI Agent

A privacy-first AI agent that automates LinkedIn networking for legal professionals. Uses **AI-powered role classification** to intelligently identify target profiles, generates personalized "Zero-Trust" AI strategy reports using Google Gemini, and sends customized messages—all while keeping sensitive client data safe.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Playwright](https://img.shields.io/badge/Playwright-Automation-green.svg)
![Gemini](https://img.shields.io/badge/Google-Gemini%20AI-orange.svg)
![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)

## ✨ Features

### Core Capabilities
- **🔍 AI-Powered Role Classification**: Uses Gemini AI to intelligently classify connections as:
  - `PRACTICING` - Active legal professionals (Partners, Attorneys, Counsel)
  - `GENERAL` - Legal-adjacent professionals (Legal Tech, Consultants)
  - `SKIP` - Non-relevant profiles
  
- **📊 Zero-Trust Analysis**: Generates practice-specific AI prompts that require *no* PII (Personally Identifiable Information) to run

- **📄 Accessible PDF Generation**: Creates professional, screen-reader friendly PDF reports ("Zero-Trust AI Strategy")

- **💬 Smart Messaging**: Role-based messaging with:
  - Full workflow for PRACTICING lawyers (intro + personalized report)
  - Intro-only for GENERAL contacts
  - Auto-skip for non-relevant profiles

### Technical Features
- **⚡ Dynamic Waiting**: Smart page load detection instead of fixed delays
- **🎯 Identity Verification**: Multi-selector chat verification with fuzzy name matching
- **🧹 Auto Cleanup**: Closes all tabs and deletes PDFs on session end
- **📈 Self-Optimization**: Learns from run history to adjust timeouts and settings
- **🔄 Duplicate Prevention**: Tracks message history to avoid re-messaging

## 📋 Prerequisites

- Windows OS (10/11)
- [Python 3.8+](https://www.python.org/downloads/)
- Google Chrome installed
- [Google Gemini API Key](https://aistudio.google.com/)

## 🛠️ Installation

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/linkedin-agent.git
cd linkedin-agent
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure API Key
Create a `.env` file in the project root:
```env
GEMINI_API_KEY=your_actual_api_key_here
```

## 🚀 Usage

### Quick Start
```bash
python linkedin_agent.py
```

> **Note**: On first run, Chrome will open. Log in to LinkedIn manually. The session persists for future runs.

### What Happens
1. Agent scans your LinkedIn connections
2. AI classifies each connection's role
3. For PRACTICING lawyers:
   - Sends intro message
   - Extracts their website/firm info
   - Generates personalized AI strategy PDF
   - Sends follow-up with PDF attached
4. For GENERAL contacts: Sends intro only
5. Logs all activity and cleans up

### Automated Scheduling
To run daily (5 PM - 11 PM, 1 contact/hour):

1. Edit paths in `run_agent_background.bat`
2. Run as Administrator:
```bash
setup_schedule.bat
```

## 📁 Project Structure

```
linkedin-agent/
├── linkedin_agent.py     # Main agent (browser control, AI, messaging)
├── config.json           # Runtime configuration
├── config_manager.py     # Configuration management
├── optimizer.py          # Self-optimization logic
├── requirements.txt      # Python dependencies
├── .env                  # API keys (not committed)
├── .gitignore           # Git ignore rules
├── history.json         # Message history (auto-generated)
├── agent_history.json   # Run metrics (auto-generated)
├── run_agent_background.bat   # Background execution wrapper
└── setup_schedule.bat   # Windows Task Scheduler setup
```

## ⚙️ Configuration

Edit `config.json` to customize behavior:

```json
{
  "timing": {
    "page_load_wait": 5000,
    "scroll_wait": 10000,
    "message_send_wait": 3000
  },
  "limits": {
    "max_scrolls": 50,
    "candidates_per_run": 1
  }
}
```

## 🔒 Privacy & Security

- **Local Execution**: Runs entirely on your machine
- **No Data Storage**: No connection data sent to external servers
- **Zero-Trust AI**: Generated prompts use bracketed placeholders, never real client data
- **Session Isolation**: Chrome profile stored locally (`C:\ChromeAutomationProfile`)

## 📊 How AI Classification Works

The agent uses Gemini AI to analyze:
1. **Headline**: Job title and company
2. **About Section**: Profile description (when available)

Classification logic:
- `PRACTICING`: Contains legal job titles (Partner, Attorney, Counsel, etc.)
- `GENERAL`: Legal-adjacent but not practicing (Legal Tech, Consultant)
- `SKIP`: Non-legal or insufficient information

## 🧪 Testing

Run tests to verify components:
```bash
python test_connect.py      # Browser connection test
python test_v2_logic.py     # Logic tests
python test_optimizer.py    # Optimizer tests
```

## 📝 Logs & History

- `agent_log.txt` - Detailed run logs
- `history.json` - Message history per contact
- `agent_history.json` - Run metrics for optimization

## ⚠️ Disclaimer

This tool is for **educational and productivity purposes**. Please:
- Use responsibly
- Adhere to [LinkedIn's User Agreement](https://www.linkedin.com/legal/user-agreement)
- Review AI outputs before sending
- Respect LinkedIn's rate limits

The "Zero-Trust" protocols minimize data exposure, but always exercise judgment.

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

**Made with ❤️ for legal professionals embracing AI responsibly**
