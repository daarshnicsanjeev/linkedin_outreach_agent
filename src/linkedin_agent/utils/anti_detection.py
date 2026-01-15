"""
Anti-Detection Utilities for LinkedIn Agents
=============================================
Shared utilities to make browser automation look more human-like
and avoid LinkedIn's automation detection.

Usage:
    from anti_detection import human_delay, human_scroll, human_mouse_move, human_like_navigate

Created: 2026-01-06
"""

import asyncio
import random


async def human_delay(min_seconds=1.5, max_seconds=4.0):
    """
    Add a random human-like delay to avoid detection.
    
    Args:
        min_seconds: Minimum delay in seconds
        max_seconds: Maximum delay in seconds
    """
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)


async def human_scroll(page, scroll_amount=None):
    """
    Scroll in a human-like manner using mouse wheel events.
    Uses actual wheel events that trigger LinkedIn's infinite scroll detection.
    
    Args:
        page: Playwright page object
        scroll_amount: Total scroll distance (randomized if None)
    """
    if scroll_amount is None:
        scroll_amount = random.randint(200, 500)
    
    # Scroll in smaller increments with pauses (like a human using scroll wheel)
    # Each wheel "tick" is typically 100-120px
    tick_size = random.randint(80, 140)
    num_ticks = max(1, scroll_amount // tick_size)
    
    # Move mouse to center of page first (like a real user)
    viewport = page.viewport_size
    if viewport:
        center_x = viewport['width'] // 2 + random.randint(-100, 100)
        center_y = viewport['height'] // 2 + random.randint(-50, 50)
        await page.mouse.move(center_x, center_y)
        await asyncio.sleep(random.uniform(0.1, 0.3))
    
    for i in range(num_ticks):
        # Variable tick size to simulate natural scrolling
        jitter = random.randint(-20, 30)
        delta = tick_size + jitter
        
        # Use mouse.wheel which fires actual wheel events
        await page.mouse.wheel(0, delta)
        
        # Small pause between wheel ticks (like natural scrolling)
        if i < num_ticks - 1:
            await asyncio.sleep(random.uniform(0.05, 0.2))


async def human_mouse_move(page, target_element=None):
    """
    Simulate random mouse movements to look more natural.
    
    Args:
        page: Playwright page object
        target_element: Optional element to move towards
    """
    try:
        if target_element:
            # Move towards the element
            box = await target_element.bounding_box()
            if box:
                x = box['x'] + random.randint(5, int(box['width']) - 5)
                y = box['y'] + random.randint(5, int(box['height']) - 5)
                await page.mouse.move(x, y, steps=random.randint(5, 15))
                await asyncio.sleep(random.uniform(0.1, 0.3))
        else:
            # Random movement within viewport
            viewport = page.viewport_size
            if viewport:
                x = random.randint(100, viewport['width'] - 100)
                y = random.randint(100, viewport['height'] - 100)
                await page.mouse.move(x, y, steps=random.randint(3, 10))
                await asyncio.sleep(random.uniform(0.1, 0.3))
    except:
        pass


async def human_like_navigate(page, url, timeout=45000):
    """
    Navigate to a URL with human-like pre and post delays.
    
    Args:
        page: Playwright page object
        url: URL to navigate to
        timeout: Navigation timeout in ms
    """
    # Small delay before navigation (human thinking time)
    await human_delay(0.5, 1.5)
    
    # Navigate
    await page.goto(url, timeout=timeout)
    
    # Wait for page to settle + human reading time
    await human_delay(2.0, 4.0)
    
    # Random mouse movement to look natural
    await human_mouse_move(page)


async def human_like_click(page, element, pre_delay=True, post_delay=True):
    """
    Click an element with human-like behavior.
    
    Args:
        page: Playwright page object
        element: Element to click
        pre_delay: Add delay before clicking
        post_delay: Add delay after clicking
    """
    try:
        if pre_delay:
            await human_delay(0.3, 1.0)
        
        # Move mouse to element first
        await human_mouse_move(page, element)
        
        # Small pause before click (like human aiming)
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        # Click
        await element.click()
        
        if post_delay:
            await human_delay(0.5, 1.5)
    except Exception as e:
        # Fallback to direct click
        await element.click()


async def human_like_type(page, element, text, clear_first=True):
    """
    Type text with human-like speed variations.
    
    Args:
        page: Playwright page object
        element: Input element to type into
        text: Text to type
        clear_first: Clear the field first
    """
    try:
        if clear_first:
            await element.fill("")
            await asyncio.sleep(random.uniform(0.2, 0.5))
        
        # Type character by character with variable speed
        for char in text:
            await element.type(char, delay=random.randint(50, 150))
            
            # Occasional longer pause (like thinking)
            if random.random() < 0.05:  # 5% chance
                await asyncio.sleep(random.uniform(0.3, 0.8))
        
        await human_delay(0.3, 0.8)
    except:
        # Fallback to direct fill
        await element.fill(text)


def get_random_viewport_size():
    """Get a random but realistic viewport size."""
    viewports = [
        {"width": 1920, "height": 1080},
        {"width": 1536, "height": 864},
        {"width": 1440, "height": 900},
        {"width": 1366, "height": 768},
        {"width": 1280, "height": 720},
    ]
    return random.choice(viewports)


# Rate limiting helpers
class RateLimiter:
    """Helper to ensure we don't make too many requests too fast."""
    
    def __init__(self, min_delay=5, max_delay=15, long_pause_every=3, long_pause_duration=(20, 40)):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.long_pause_every = long_pause_every
        self.long_pause_min = long_pause_duration[0]
        self.long_pause_max = long_pause_duration[1]
        self.request_count = 0
    
    async def wait(self, log_func=None):
        """Wait before the next action."""
        self.request_count += 1
        
        # Regular delay
        delay = random.uniform(self.min_delay, self.max_delay)
        if log_func:
            log_func(f"  [Pause {delay:.1f}s...]")
        await asyncio.sleep(delay)
        
        # Extra long pause periodically
        if self.request_count % self.long_pause_every == 0:
            extra_pause = random.uniform(self.long_pause_min, self.long_pause_max)
            if log_func:
                log_func(f"  [Extended break {extra_pause:.0f}s...]")
            await asyncio.sleep(extra_pause)
    
    def reset(self):
        """Reset the counter."""
        self.request_count = 0
