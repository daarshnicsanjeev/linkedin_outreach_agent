# Agent Documentation

Detailed documentation for each LinkedIn automation agent.

---

## Outreach Agent

**Purpose:** Scans LinkedIn connections, identifies legal professionals using AI, and sends personalized messages with PDF strategy reports.

**Entry Points:**
```bash
python -m src.linkedin_agent.cli outreach
python linkedin_agent.py  # Legacy
```

### Workflow

1. **Navigate** to Connections page
2. **Scan** visible connection cards
3. **Classify** each connection with Gemini AI:
   - `PRACTICING` - Active lawyers/attorneys
   - `GENERAL` - Legal-adjacent (paralegals, students)
   - `SKIP` - Not relevant
4. **Generate** PDF strategy report for relevant connections
5. **Open chat** and verify recipient identity with Gemini Vision
6. **Send** personalized message with PDF attachment

### Configuration

```json
{
  "outreach_agent": {
    "fast_forward_wait": 1.5,
    "login_wait_timeout_seconds": 300
  },
  "limits": {
    "max_scrolls": 50,
    "max_retries": 5
  }
}
```

### Data Files

| File | Purpose |
|------|---------|
| `data/history.json` | Processed connections |
| `data/resume_state.json` | Scroll position for resume |
| `logs/outreachagent.log` | Agent logs |

---

## Comment Agent

**Purpose:** Scans LinkedIn feed for posts by legal professionals and generates AI-powered professional comments.

**Entry Points:**
```bash
python -m src.linkedin_agent.cli comment
python comment_agent.py  # Legacy
```

### Workflow

1. **Navigate** to LinkedIn feed
2. **Identify** current user (for self-exclusion)
3. **Scroll** and collect posts from legal professionals
4. **Generate** professional comments using Gemini AI
5. **Display** review UI with approve/regenerate options
6. **Post** approved comments with verification

### Review UI Features

- Edit generated comments inline
- Regenerate individual comments
- Approve/skip per post
- View original post link
- Real-time posting status

### Configuration

```json
{
  "comment_agent": {
    "max_posts_per_run": 10,
    "review_server_port": 8080
  }
}
```

### Data Files

| File | Purpose |
|------|---------|
| `data/comment_history.json` | Posted URLs to avoid duplicates |

---

## Engagement Agent

**Purpose:** Monitors LinkedIn notifications for mentions and replies, likes the content, and generates a review report.

**Entry Points:**
```bash
python -m src.linkedin_agent.cli engagement
python engagement_agent.py  # Legacy
```

### Workflow

1. **Navigate** to LinkedIn feed to identify current user
2. **Navigate** to Notifications page
3. **Filter** for:
   - "mentioned you" notifications
   - "replied to your" notifications
   - "commented on your" notifications
4. **Like** each relevant item
5. **Verify** like success with Gemini AI
6. **Generate** accessible HTML review report
7. **Wait** for user to click "Done & Cleanup"

### Features

- **Self-exclusion:** Won't like your own content
- **Gemini verification:** Confirms like was successful
- **Status badges:** Shows success/failed/already-liked

### Configuration

```json
{
  "engagement_agent": {
    "max_scroll_attempts": 10,
    "max_notifications_per_run": 50,
    "review_server_port": 8000
  }
}
```

### Data Files

| File | Purpose |
|------|---------|
| `data/processed_notifications.json` | Processed notification IDs |
| `data/notification_state.json` | Last processed position |

---

## Notification Agent

**Purpose:** Scans notifications for engagement (likes, comments, reactions) and sends connection invites to engaged non-connections.

**Entry Points:**
```bash
python -m src.linkedin_agent.cli notification
python notification_agent.py  # Legacy
```

### Workflow

1. **Navigate** to Notifications page
2. **Scroll** to load notifications
3. **Extract** engagement notifications:
   - Liked your post/comment
   - Reacted to your content
   - Commented on your post
   - Mentioned you
4. **Check** connection status for each engager
5. **Send** connection invite (without note)
6. **Track** history to avoid re-inviting

### Rate Limiting

- Configurable daily invite limit
- Human-like delays between actions
- Long pauses every N actions

### Configuration

```json
{
  "notification_agent": {
    "max_notifications_per_run": 100,
    "max_invites_per_run": 50,
    "delay_between_invites": 5,
    "scroll_attempts": 15
  }
}
```

### Data Files

| File | Purpose |
|------|---------|
| `data/notification_history.json` | Invited profiles, daily counts |

---

## Search Agent

**Purpose:** Searches LinkedIn Jobs and Posts using Boolean queries to find legal automation opportunities.

**Entry Points:**
```bash
python -m src.linkedin_agent.cli search
python search_agent.py  # Legacy (if exists)
```

### Workflow

1. **Generate** Boolean search queries for:
   - Legal AI jobs
   - Legal automation posts
2. **Search** LinkedIn Jobs with each query
3. **Search** LinkedIn Posts with each query
4. **Filter** results for relevance using Gemini
5. **Deduplicate** across all searches
6. **Display** review UI
7. **Export** interested results to CSV

### Example Queries

```
"legal AI" AND (freelance OR contract OR consultant)
"AI automation" AND legal AND (hiring OR seeking)
"generative AI" AND legal AND (freelance OR contract)
```

### Data Files

| File | Purpose |
|------|---------|
| `data/search_history.json` | Seen URLs |
| `data/search_results.json` | Full results archive |

---

## Invite Withdrawal Agent

**Purpose:** Cleans up old pending connection invites (older than 30 days).

**Entry Points:**
```bash
python -m src.linkedin_agent.cli withdraw
python invite_withdrawal_agent.py  # Legacy
```

### Workflow

1. **Navigate** to Sent Invitations page
2. **Scroll** to load pending invites
3. **Filter** invites older than configured age
4. **Withdraw** each old invite
5. **Handle** confirmation dialogs

### Configuration

```json
{
  "invite_withdrawal": {
    "min_age_days": 31,
    "delay_between_withdrawals": 2,
    "max_withdrawals_per_run": 100,
    "dialog_timeout_ms": 3000
  }
}
```

---

## Creating a Custom Agent

### Template

```python
"""
My Custom Agent
===============
Description of what this agent does.
"""

import asyncio
from ..agents.base_agent import BaseAgent
from ..utils.anti_detection import human_delay, human_scroll

class MyCustomAgent(BaseAgent):
    """Custom agent for [purpose]."""
    
    def get_agent_name(self) -> str:
        return "MyCustomAgent"
    
    def __init__(self, config_path: str = "config.json"):
        super().__init__(config_path)
        
        # Add custom metrics
        self.run_metrics.update({
            "custom_metric": 0,
            "agent_type": "my_custom_agent"
        })
    
    async def run(self):
        """Main agent logic."""
        try:
            # Navigate
            await self.navigate("https://www.linkedin.com/")
            
            # Load history
            history = self.load_history("my_history.json")
            
            # Do work...
            self.log("Processing...")
            
            # Use Gemini
            response = self.gemini.generate("Prompt here")
            
            # Save history
            self.save_history("my_history.json", history)
            
            # Alert user
            self.play_ready_sound()
            
        except Exception as e:
            self.log(f"Error: {e}")
            self.record_error(str(e))


# Entry point
async def main():
    agent = MyCustomAgent()
    await agent.execute()

if __name__ == "__main__":
    asyncio.run(main())
```

### Register in CLI

1. Add to `src/linkedin_agent/agents/__init__.py`:
   ```python
   from .my_custom_agent import MyCustomAgent
   ```

2. Add command to `src/linkedin_agent/cli.py`:
   ```python
   elif args.command == "mycustom":
       from .agents.my_custom_agent import MyCustomAgent
       agent = MyCustomAgent(config_path=args.config)
   ```
