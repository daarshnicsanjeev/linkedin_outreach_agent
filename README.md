# Zero-Trust LinkedIn Agent

A privacy-first AI agent that automates LinkedIn networking for legal professionals. It scans connections, identifies target profiles (e.g., Partners, Founders), generates "Zero-Trust" AI strategy reports using Google Gemini, and sends personalized messages—all while keeping sensitive client data safe.

## Features

- **Automated Scanning**: Browses LinkedIn connections to find relevant legal professionals.
- **Zero-Trust Analysis**: Uses Google Gemini to generate practice-specific AI prompts that require *no* PII (Personally Identifiable Information) to run.
- **PDF Generation**: Creates a professional, accessible PDF report ("Zero-Trust AI Strategy") for each contact.
- **Smart Messaging**: Sends a connection message and a follow-up message with the report attached.
- **Privacy First**: Runs locally on your machine. Login sessions are stored locally. No data is sent to third-party servers other than the Gemini API for prompt generation (which itself follows Zero-Trust protocols).
- **Schedule Ready**: Includes scripts to run automatically in the background (e.g., daily 5 PM - 11 PM).

## Prerequisites

- Windows OS
- [Python 3.8+](https://www.python.org/downloads/)
- Google Chrome installed
- A [Google Gemini API Key](https://aistudio.google.com/)

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/linkedin-agent.git
    cd linkedin-agent
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure API Key**:
    - Rename `.env.example` to `.env` (or create a new `.env` file).
    - Add your Gemini API Key:
      ```
      GEMINI_API_KEY=your_actual_api_key_here
      ```

## Usage

### Manual Run

To run the agent once:

```bash
python linkedin_agent.py
```

*Note: The first time you run it, a Chrome window will open. You must log in to LinkedIn manually. The session will be saved for future runs.*

### Automated Schedule

To set up the agent to run automatically (Daily, 5 PM - 11 PM, 1 contact/hour):

1.  Edit `run_agent_background.bat` to ensure the paths match your installation.
2.  Run `setup_schedule.bat` (Run as Administrator).

## Project Structure

- `linkedin_agent.py`: Main agent logic (browser control, AI generation, messaging).
- `requirements.txt`: Python dependencies.
- `run_agent_background.bat`: Wrapper script for background execution.
- `setup_schedule.bat`: Script to register the Windows Task.
- `user_data/`: Stores Chrome user profile (cookies/login). **Do not commit this.**

## Disclaimer

This tool is for educational and productivity purposes. Please use responsibly and adhere to LinkedIn's User Agreement and Professional Community Policies. The "Zero-Trust" protocols are designed to minimize data exposure but always review AI outputs before use.
