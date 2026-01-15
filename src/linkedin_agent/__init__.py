"""
LinkedIn Agent - A suite of automation agents for LinkedIn outreach and engagement.

This package provides:
- OutreachAgent: Manages connections and personalized outreach
- CommentAgent: Generates and posts comments on legal professionals' posts
- EngagementAgent: Monitors and responds to mentions and engagement
- NotificationAgent: Processes notifications and sends connection invites
- SearchAgent: Searches for and qualifies potential connections
"""

__version__ = "2.0.0"

from .core.config import ConfigManager
from .core.optimizer import AgentOptimizer
