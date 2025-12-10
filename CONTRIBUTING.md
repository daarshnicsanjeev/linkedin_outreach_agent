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

3. Run tests to verify setup:
   ```bash
   python test_connect.py
   ```

## Project Components

| File | Purpose |
|------|---------|
| `linkedin_agent.py` | Main outreach agent (messaging, PDF generation) |
| `notification_agent.py` | Engagement-based connection invites |
| `config_manager.py` | Configuration loading/saving |
| `optimizer.py` | Self-optimization from run history |

## Code Guidelines

### Style
- Follow PEP 8 for Python code
- Use descriptive variable and function names
- Add docstrings to functions and classes
- Keep functions focused and small

### Commits
- Write clear, concise commit messages
- Use present tense ("Add feature" not "Added feature")
- Reference issues when applicable

### Testing
- Add tests for new features
- Ensure existing tests pass before submitting
- Test with a real LinkedIn account (be mindful of rate limits)
- Test both agents if changes affect shared code

## Pull Request Process

1. **Update documentation** if you change functionality
2. **Update the README** if you add new features
3. **Test thoroughly** before submitting
4. **Describe your changes** clearly in the PR description
5. **Link related issues** if applicable

## Reporting Issues

When reporting bugs, please include:
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant log output (sanitize any personal data)

## Feature Requests

We welcome feature suggestions! Please:
- Check existing issues first
- Describe the use case
- Explain why it would be valuable

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

## Questions?

Feel free to open an issue for questions or discussions.

---

Thank you for contributing! 🎉
