"""
Backward compatibility shim for AgentOptimizer.
Re-exports AgentOptimizer from the refactored location.
"""

from src.linkedin_agent.core.optimizer import AgentOptimizer

__all__ = ['AgentOptimizer']
