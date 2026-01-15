"""
Browser Management Utilities
=============================
Shared browser launch, connection, and cleanup functionality.
Extracted from individual agent implementations for reuse.
"""

import asyncio
import os
import subprocess
import socket
from datetime import datetime
from playwright.async_api import async_playwright

from .anti_detection import human_delay, human_mouse_move


class BrowserManager:
    """
    Manages Chrome browser instances with remote debugging.
    
    Handles:
    - Launching Chrome with debug port
    - Connecting to existing browser instances
    - Chrome PID detection and cleanup
    - Chat popup management
    """
    
    def __init__(self, debug_port=9222, user_data_dir=None, headless=False):
        self.debug_port = debug_port
        self.user_data_dir = user_data_dir or os.path.join(os.getcwd(), "user_data")
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.chrome_pid = None
        self.chrome_launched_by_us = False
    
    def is_port_in_use(self) -> bool:
        """Check if the debug port is already in use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', self.debug_port)) == 0
    
    def get_chrome_path(self) -> str:
        """Get the Chrome executable path for the current OS."""
        # Windows paths
        chrome_paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
        
        for path in chrome_paths:
            if os.path.exists(path):
                return path
        
        raise FileNotFoundError("Chrome executable not found")
    
    async def launch_chrome(self, log_func=None) -> bool:
        """
        Launch Chrome with remote debugging enabled.
        
        Returns True if Chrome was launched, False if already running.
        """
        if self.is_port_in_use():
            if log_func:
                log_func(f"Chrome already running on port {self.debug_port}")
            return False
        
        chrome_path = self.get_chrome_path()
        
        # Ensure user data directory exists
        os.makedirs(self.user_data_dir, exist_ok=True)
        
        cmd = [
            chrome_path,
            f"--remote-debugging-port={self.debug_port}",
            f"--user-data-dir={self.user_data_dir}",
            "--disable-features=TranslateUI",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        
        if self.headless:
            cmd.append("--headless=new")
        
        if log_func:
            log_func(f"Launching Chrome with debugging on port {self.debug_port}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        self.chrome_pid = process.pid
        self.chrome_launched_by_us = True
        
        # Wait for Chrome to start
        for _ in range(30):
            await asyncio.sleep(0.5)
            if self.is_port_in_use():
                if log_func:
                    log_func("Chrome started successfully")
                return True
        
        raise TimeoutError("Chrome failed to start within 15 seconds")
    
    async def connect(self, log_func=None) -> None:
        """Connect to Chrome via CDP."""
        if not self.is_port_in_use():
            await self.launch_chrome(log_func)
        
        self.playwright = await async_playwright().start()
        
        if log_func:
            log_func(f"Connecting to Chrome on port {self.debug_port}")
        
        self.browser = await self.playwright.chromium.connect_over_cdp(
            f"http://localhost:{self.debug_port}"
        )
        
        # Get or create context
        contexts = self.browser.contexts
        if contexts:
            self.context = contexts[0]
            if log_func:
                log_func(f"Reusing existing context with {len(self.context.pages)} pages")
        else:
            self.context = await self.browser.new_context()
            if log_func:
                log_func("Created new browser context")
        
        # Get or create page
        pages = self.context.pages
        if pages:
            self.page = pages[0]
            if log_func:
                log_func("Reusing existing page")
        else:
            self.page = await self.context.new_page()
            if log_func:
                log_func("Created new page")
    
    async def navigate(self, url: str, timeout: int = 30000, log_func=None) -> None:
        """Navigate to a URL with human-like behavior."""
        await human_delay(0.5, 1.5)
        
        if log_func:
            log_func(f"Navigating to {url}")
        
        await self.page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        await human_delay(2.0, 4.0)
        await human_mouse_move(self.page)
    
    async def close_chat_popups(self, log_func=None) -> int:
        """
        Close any open chat/messaging popups.
        
        Returns the number of popups closed.
        """
        closed_count = 0
        
        # Selectors for close buttons
        close_selectors = [
            'button[data-control-name="overlay.close_conversation_window"]',
            'button.msg-overlay-bubble-header__control--close',
            'button[aria-label="Close your conversation"]',
            'button[aria-label="Minimize your chat with"]',
            'button.msg-overlay-list-bubble__control--close',
        ]
        
        for selector in close_selectors:
            try:
                buttons = await self.page.query_selector_all(selector)
                for button in buttons:
                    if await button.is_visible():
                        await button.click()
                        closed_count += 1
                        await asyncio.sleep(0.3)
            except Exception:
                pass
        
        if closed_count > 0 and log_func:
            log_func(f"Closed {closed_count} chat popup(s)")
        
        return closed_count
    
    def identify_chrome_pid(self) -> int:
        """Find PID of process listening on the debug port."""
        try:
            import psutil
            for conn in psutil.net_connections(kind='inet'):
                if conn.laddr.port == self.debug_port and conn.status == 'LISTEN':
                    return conn.pid
        except ImportError:
            pass
        except Exception:
            pass
        return None
    
    async def cleanup(self, log_func=None) -> None:
        """Clean up browser resources."""
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            
            if log_func:
                log_func("Browser resources cleaned up")
        except Exception as e:
            if log_func:
                log_func(f"Cleanup error: {e}")
    
    async def terminate_chrome(self, log_func=None) -> None:
        """Terminate Chrome if we launched it."""
        if not self.chrome_launched_by_us:
            return
        
        try:
            import psutil
            pid = self.chrome_pid or self.identify_chrome_pid()
            if pid:
                parent = psutil.Process(pid)
                for child in parent.children(recursive=True):
                    child.terminate()
                parent.terminate()
                
                if log_func:
                    log_func(f"Terminated Chrome (PID: {pid})")
        except Exception as e:
            if log_func:
                log_func(f"Error terminating Chrome: {e}")


# Convenience function for simple usage
async def get_browser(user_data_dir=None, log_func=None) -> BrowserManager:
    """Get a connected BrowserManager instance."""
    manager = BrowserManager(user_data_dir=user_data_dir)
    await manager.connect(log_func)
    return manager
