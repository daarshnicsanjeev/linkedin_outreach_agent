# Contributing to Zero-Trust LinkedIn Agent

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/yourusername/linkedin-agent.git
   cd linkedin-agent
   ```
3. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. Copy `.env.example` to `.env` and add your API key:
   ```bash
   cp .env.example .env
   ```

3. Test the CLI works:
   ```bash
   python -m src.linkedin_agent.cli --help
   ```

---

## Project Architecture

### Package Structure

```
src/linkedin_agent/
├── agents/           # Agent implementations (inherit from BaseAgent)
├── core/             # ConfigManager, AgentOptimizer, constants
├── utils/            # BrowserManager, AudioManager, GeminiClient
├── templates/        # HTML templates for review pages
└── cli.py            # Unified CLI entry point
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `BaseAgent` | `agents/base_agent.py` | Abstract base class with shared functionality |
| `BrowserManager` | `utils/browser.py` | Chrome automation with debugging |
| `GeminiClient` | `utils/gemini.py` | Gemini AI integration |
| `AudioManager` | `utils/audio.py` | Sound alerts and notifications |
| `ConfigManager` | `core/config.py` | Configuration loading |
| `AgentOptimizer` | `core/optimizer.py` | Self-tuning based on run history |

---

## Creating a New Agent

All agents must inherit from `BaseAgent`:

```python
from ..agents.base_agent import BaseAgent

class MyNewAgent(BaseAgent):
    def get_agent_name(self) -> str:
        return "MyNewAgent"
    
    async def run(self):
        """Your agent logic here."""
        # Use inherited methods:
        await self.navigate("https://www.linkedin.com/")
        history = self.load_history("my_history.json")
        response = self.gemini.generate("prompt...")
        self.log("Processing...")
        self.play_ready_sound()
```

### Adding to CLI

1. Create your agent in `src/linkedin_agent/agents/`
2. Add to `src/linkedin_agent/agents/__init__.py`
3. Add case to `src/linkedin_agent/cli.py`

---

## Code Guidelines

### Style
- Follow PEP 8 for Python code
- Use type hints where possible
- Add docstrings to all public methods
- Keep functions focused and small

### Agents
- Always inherit from `BaseAgent`
- Use `self.log()` instead of `print()`
- Use `self.gemini` instead of creating new clients
- Use `self.play_ready_sound()` for alerts

### Commits
- Write clear, concise commit messages
- Use present tense ("Add feature" not "Added feature")
- Reference issues when applicable

---

## Testing

```bash
# Test imports work
python -c "from src.linkedin_agent.agents import *; print('OK')"

# Run a specific agent
python -m src.linkedin_agent.cli engagement

# Test with legacy entry point
python engagement_agent.py
```

**Testing Guidelines:**
- Test with a real LinkedIn account (be mindful of rate limits)
- If changes affect `BaseAgent`, test ALL agents
- Add debug screenshots when troubleshooting

---

## Pull Request Process

1. **Update documentation** if you change functionality
2. **Verify imports** work for all agents
3. **Test thoroughly** before submitting
4. **Describe your changes** clearly in the PR description

---

## Reporting Issues

When reporting bugs, please include:
- Python version
- Operating system
- Steps to reproduce
- Relevant log output (sanitize personal data)
- Debug screenshots if applicable

---

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

---

Thank you for contributing! 🎉
