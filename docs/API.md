# API Documentation

Developer reference for the LinkedIn Agent utility modules and classes.

---

## BaseAgent

**Location:** `src/linkedin_agent/agents/base_agent.py`

Abstract base class that all agents inherit from. Provides shared browser management, logging, configuration, audio, AI, and history functionality.

### Constructor

```python
BaseAgent(config_path: str = "config.json")
```

### Abstract Methods (must implement)

```python
def get_agent_name(self) -> str:
    """Return agent identifier (e.g., 'CommentAgent')."""

async def run(self) -> None:
    """Main agent execution logic."""
```

### Browser Methods

| Method | Description |
|--------|-------------|
| `await start_browser()` | Connect to Chrome with debugging |
| `await navigate(url, timeout=None)` | Human-like navigation |
| `await close_chat_popups()` | Close LinkedIn chat modals |
| `await stop_browser(terminate=False)` | Clean disconnect |

### Logging & Config

| Method | Description |
|--------|-------------|
| `log(msg)` | Log to console + agent-specific file |
| `get_config(key, default=None)` | Dot-notation config access |
| `set_config(key, value)` | Update config value |

### Gemini AI

```python
# Access the shared GeminiClient
response = self.gemini.generate("Your prompt here")
response = self.gemini.generate(prompt, temperature=0.3)
```

### Audio Alerts

| Method | Description |
|--------|-------------|
| `play_ready_sound()` | Multi-tone ascending melody (review ready) |
| `play_complete_sound()` | Victory fanfare (task done) |
| `show_notification(title, message)` | Windows toast notification |

### History Management

```python
# Load from data/ directory
history = self.load_history("filename.json")  # Returns {} if not found

# Atomic save to data/ directory  
self.save_history("filename.json", {"key": "value"})
```

### Debug Utilities

```python
await self.capture_debug_screenshot("context_name")  # Saves to debug/screenshots/
await self.capture_debug_html("context_name")        # Saves to debug/dom/
```

### Metrics

```python
self.record_action()        # Increment actions_taken counter
self.record_error("msg")    # Increment errors + add to run_metrics
self.run_metrics["custom_metric"] = value  # Add custom metrics
```

### Lifecycle

```python
# Main entry point - handles start/stop automatically
await agent.execute()

# Lifecycle hooks (override in subclass)
async def on_start(self): ...    # Called before run()
async def on_complete(self): ... # Called after run()
async def on_error(self, e): ... # Called on exception
```

---

## GeminiClient

**Location:** `src/linkedin_agent/utils/gemini.py`

Wrapper around Google Gemini API for text generation, classification, and vision.

### Constructor

```python
GeminiClient(api_key: str = None, model: str = "gemini-2.0-flash")
# Uses GEMINI_API_KEY from environment if api_key not provided
```

### Text Generation

```python
# Simple generation (synchronous)
response = client.generate("Your prompt")
response = client.generate(prompt, temperature=0.3)

# Async generation
response = await client.generate_text(prompt, system_instruction=None, temperature=0.7)

# Sync with system instruction
response = client.generate_text_sync(prompt, system_instruction="Be concise")
```

### Text Classification

```python
result = await client.classify_text(
    text="LinkedIn headline here",
    categories=["LEGAL", "TECH", "OTHER"],
    context="optional context"
)
# Returns: {"category": "LEGAL", "confidence": 0.95, "reasoning": "..."}
```

### Legal Professional Detection

```python
is_legal = await client.is_legal_professional("Partner at Smith & Associates LLP")
# Returns: True/False

is_legal = client.is_legal_professional_sync(headline)  # Sync version
```

### Vision Analysis

```python
# Analyze screenshot
analysis = await client.analyze_screenshot(screenshot_bytes, "What do you see?")

# Verify UI state
result = await client.verify_action(screenshot_bytes, "Comment was posted successfully")
# Returns: {"verified": True, "confidence": 0.9, "details": "..."}
```

---

## BrowserManager

**Location:** `src/linkedin_agent/utils/browser.py`

Manages Chrome browser instances with remote debugging.

### Constructor

```python
BrowserManager(debug_port=9222, user_data_dir=None, headless=False)
```

### Methods

```python
# Check if Chrome is running
is_running = manager.is_port_in_use()

# Launch Chrome (if not running)
launched = await manager.launch_chrome(log_func=None)

# Connect to Chrome
await manager.connect(log_func=print)

# Navigate with human-like behavior
await manager.navigate(url, timeout=30000, log_func=None)

# Close chat popups
closed_count = await manager.close_chat_popups(log_func=None)

# Cleanup
await manager.cleanup(log_func=None)
await manager.terminate_chrome(log_func=None)  # Kill Chrome if we launched it
```

### Properties After Connect

```python
manager.browser   # Playwright browser instance
manager.context   # Browser context
manager.page      # Active page
```

---

## AudioManager

**Location:** `src/linkedin_agent/utils/audio.py`

Sound alerts and Windows toast notifications.

### Constructor

```python
AudioManager(app_id: str = "LinkedIn Agent")
```

### Sound Methods

```python
# Attention-grabbing ascending melody (C5 → E5 → G5 → C6)
manager.play_ready_sound(use_speaker=True)

# Victory fanfare (G5 → C6 held)
manager.play_complete_sound(use_speaker=True)

# Simple alert tone
manager.play_alert_sound(frequency=880.0, duration=0.5, use_speaker=True)
```

### Toast Notifications

```python
manager.show_toast_notification(
    title="Review Ready",
    message="10 comments ready for approval",
    action_label="Open",           # Optional button
    action_url="http://localhost:8080"  # Optional URL
)
```

---

## Anti-Detection Utilities

**Location:** `src/linkedin_agent/utils/anti_detection.py`

Human-like behavior simulation to avoid LinkedIn detection.

### Delay Functions

```python
await human_delay(2.0, 4.0)  # Random delay between 2-4 seconds
```

### Scrolling

```python
await human_scroll(page, distance=500)  # Smooth scroll with variation
```

### Mouse Movement

```python
await human_mouse_move(page)           # Random movement
await human_mouse_move(page, element)  # Move towards element
```

### Click & Type

```python
await human_like_click(page, element)
await human_like_type(page, element, "text to type")
```

### Navigation

```python
await human_like_navigate(page, url)  # Navigate + delays + mouse movement
```

### Rate Limiter

```python
limiter = RateLimiter(
    min_delay=5,
    max_delay=15,
    long_pause_every=3,        # Every 3 actions
    long_pause_duration=(30, 60)
)

await limiter.wait(log_func=print)
```

---

## ConfigManager

**Location:** `src/linkedin_agent/core/config.py`

Load, save, and access configuration with dot notation.

```python
config = ConfigManager("config.json")

# Get with dot notation
value = config.get("timeouts.page_load", default=5000)
value = config.get("notification_agent.max_invites", 50)

# Set value
config.set("limits.max_scrolls", 100)
```

---

## AgentOptimizer

**Location:** `src/linkedin_agent/core/optimizer.py`

Self-tuning based on run history.

```python
optimizer = AgentOptimizer(config_manager=config)

# Log run metrics
optimizer.log_run({
    "agent_type": "outreach_agent",
    "messages_sent": 5,
    "errors": 1,
    "scroll_success_rate": 0.85
})

# Apply optimizations (called automatically)
optimizer.apply_optimizations("outreach_agent")
```

### Auto-Tuned Parameters

| Agent | Trigger | Parameter Adjusted |
|-------|---------|-------------------|
| All | Low scroll success | `scroll_wait` ↑ |
| Outreach | Message verification fail | `message_send_wait` ↑ |
| Outreach | Chat open fail | `chat_open_retries` ↑ |
| Notification | High errors | `delay_between_invites` ↑ |
| All | Stable performance | Waits ↓ (speedup) |

---

## CLI

**Location:** `src/linkedin_agent/cli.py`

Unified command-line interface.

```bash
python -m src.linkedin_agent.cli <command> [options]

Commands:
  outreach      Run connection messaging agent
  comment       Run auto-comment agent
  engagement    Run mentions/replies agent
  notification  Run connection invite agent
  search        Run prospect search agent
  withdraw      Run invite withdrawal agent

Options:
  --config, -c  Path to config file (default: config.json)
  --headless    Run browser in headless mode
  --debug       Enable debug logging
```
