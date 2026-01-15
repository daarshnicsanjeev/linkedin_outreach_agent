"""
Backward compatibility shim for anti_detection utilities.
Re-exports from the refactored location.
"""

from src.linkedin_agent.utils.anti_detection import (
    human_delay, 
    human_scroll, 
    human_mouse_move, 
    human_like_navigate,
    human_like_click,
    human_like_type,
    get_random_viewport_size,
    RateLimiter
)

__all__ = [
    'human_delay', 
    'human_scroll', 
    'human_mouse_move', 
    'human_like_navigate',
    'human_like_click',
    'human_like_type',
    'get_random_viewport_size',
    'RateLimiter'
]
