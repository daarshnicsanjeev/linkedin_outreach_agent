"""
Backward compatibility shim for ConfigManager.
Re-exports ConfigManager from the refactored location.
"""

from src.linkedin_agent.core.config import ConfigManager

__all__ = ['ConfigManager']
