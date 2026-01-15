"""
Base Agent Class
================
Shared functionality for all LinkedIn agents.
Eliminates code duplication across agent implementations.
"""

import asyncio
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any, Callable

from ..utils.browser import BrowserManager
from ..utils.audio import AudioManager, play_ready_sound, play_complete_sound
from ..utils.gemini import GeminiClient, get_gemini_client
from ..core.config import ConfigManager
from ..core.optimizer import AgentOptimizer
from ..core.constants import (
    DATA_DIR, LOGS_DIR, DEBUG_DIR, USER_DATA_DIR,
    CHROME_DEBUG_PORT, DEFAULT_PAGE_LOAD_TIMEOUT
)


class BaseAgent(ABC):
    """
    Abstract base class for LinkedIn automation agents.
    
    Provides common functionality:
    - Browser management (launch, connect, cleanup)
    - Logging infrastructure
    - History file management
    - Configuration access
    - Audio alerts
    - Gemini AI integration
    
    Subclasses must implement:
    - run(): Main agent logic
    - get_agent_name(): Returns agent identifier
    """
    
    def __init__(self, config_path: str = "config.json"):
        """
        Initialize the base agent.
        
        Args:
            config_path: Path to configuration file
        """
        # Core components
        self.config_manager = ConfigManager(config_path)
        self.optimizer = AgentOptimizer(config_manager=self.config_manager)
        self.browser_manager: Optional[BrowserManager] = None
        self.audio_manager = AudioManager(app_id=f"LinkedIn {self.get_agent_name()}")
        self._gemini_client: Optional[GeminiClient] = None
        
        # Browser references (shortcuts)
        self.browser = None
        self.context = None
        self.page = None
        
        # State tracking
        self.start_time: Optional[datetime] = None
        self.actions_taken = 0
        self.errors_encountered = 0
        
        # Metrics for optimization (agents can add custom metrics)
        self.run_metrics = {
            "agent_type": self.get_agent_name().lower()
        }
        
        # Ensure directories exist
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(LOGS_DIR, exist_ok=True)
        os.makedirs(DEBUG_DIR, exist_ok=True)
    
    @abstractmethod
    def get_agent_name(self) -> str:
        """Return the agent's identifier (e.g., 'CommentAgent')."""
        pass
    
    @abstractmethod
    async def run(self) -> None:
        """Main agent execution logic. Must be implemented by subclasses."""
        pass
    
    # ==================== Logging ====================
    
    def log(self, msg: str) -> None:
        """Log a message with timestamp to console and file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{self.get_agent_name()}] {msg}"
        print(log_line, flush=True)
        
        # Append to agent-specific log file
        log_file = os.path.join(LOGS_DIR, f"{self.get_agent_name().lower()}.log")
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
        except Exception:
            pass
    
    # ==================== Browser Management ====================
    
    async def start_browser(self) -> None:
        """Initialize browser connection."""
        self.browser_manager = BrowserManager(
            debug_port=CHROME_DEBUG_PORT,
            user_data_dir=USER_DATA_DIR
        )
        
        await self.browser_manager.connect(log_func=self.log)
        
        # Set shortcuts
        self.browser = self.browser_manager.browser
        self.context = self.browser_manager.context
        self.page = self.browser_manager.page
        
        self.log("Browser connected successfully")
    
    async def navigate(self, url: str, timeout: int = None) -> None:
        """Navigate to a URL with proper waiting."""
        if not self.browser_manager:
            raise RuntimeError("Browser not initialized. Call start_browser() first.")
        
        timeout = timeout or self.get_config("timeouts.page_load", DEFAULT_PAGE_LOAD_TIMEOUT)
        await self.browser_manager.navigate(url, timeout=timeout, log_func=self.log)
    
    async def close_chat_popups(self) -> int:
        """Close any open chat popups."""
        if not self.browser_manager:
            return 0
        return await self.browser_manager.close_chat_popups(log_func=self.log)
    
    async def stop_browser(self, terminate: bool = False) -> None:
        """Clean up browser resources."""
        if self.browser_manager:
            await self.browser_manager.cleanup(log_func=self.log)
            
            if terminate:
                await self.browser_manager.terminate_chrome(log_func=self.log)
            
            self.browser_manager = None
            self.browser = None
            self.context = None
            self.page = None
    
    # ==================== Configuration ====================
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value with dot notation support."""
        return self.config_manager.get(key, default)
    
    def set_config(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        self.config_manager.set(key, value)
    
    # ==================== Gemini AI ====================
    
    @property
    def gemini(self) -> GeminiClient:
        """Lazy-load Gemini client."""
        if self._gemini_client is None:
            self._gemini_client = get_gemini_client()
        return self._gemini_client
    
    async def classify_with_ai(self, text: str, categories: list) -> Dict[str, Any]:
        """Classify text into categories using Gemini."""
        return await self.gemini.classify_text(text, categories)
    
    async def is_legal_professional(self, headline: str) -> bool:
        """Check if headline indicates a legal professional."""
        return await self.gemini.is_legal_professional(headline)
    
    # ==================== Audio Notifications ====================
    
    def play_ready_sound(self) -> None:
        """Play sound alert when ready for user review."""
        self.audio_manager.play_ready_sound()
    
    def play_complete_sound(self) -> None:
        """Play sound alert when task completes."""
        self.audio_manager.play_complete_sound()
    
    def show_notification(self, title: str, message: str) -> None:
        """Show a Windows toast notification."""
        self.audio_manager.show_toast_notification(title, message)
    
    # ==================== History/State Management ====================
    
    def get_history_path(self, filename: str) -> str:
        """Get path to a history file in the data directory."""
        return os.path.join(DATA_DIR, filename)
    
    def load_history(self, filename: str) -> Dict[str, Any]:
        """Load history from a JSON file."""
        path = self.get_history_path(filename)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            self.log(f"Error loading history from {filename}: {e}")
        return {}
    
    def save_history(self, filename: str, data: Dict[str, Any]) -> None:
        """Save history to a JSON file atomically."""
        path = self.get_history_path(filename)
        temp_path = path + ".tmp"
        
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            
            # Atomic rename
            if os.path.exists(path):
                os.remove(path)
            os.rename(temp_path, path)
            
        except Exception as e:
            self.log(f"Error saving history to {filename}: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    # ==================== Debug Utilities ====================
    
    async def capture_debug_screenshot(self, context_name: str) -> str:
        """Capture a debug screenshot."""
        if not self.page:
            return None
        
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"debug_{context_name}_{timestamp}.png"
        path = os.path.join(DEBUG_DIR, "screenshots", filename)
        
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            await self.page.screenshot(path=path)
            self.log(f"Debug screenshot saved: {filename}")
            return path
        except Exception as e:
            self.log(f"Screenshot error: {e}")
            return None
    
    async def capture_debug_html(self, context_name: str) -> str:
        """Capture debug DOM snapshot."""
        if not self.page:
            return None
        
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"debug_{context_name}_{timestamp}.html"
        path = os.path.join(DEBUG_DIR, "dom", filename)
        
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            html = await self.page.content()
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            self.log(f"Debug HTML saved: {filename}")
            return path
        except Exception as e:
            self.log(f"HTML capture error: {e}")
            return None
    
    # ==================== Metrics & Optimization ====================
    
    def record_action(self) -> None:
        """Record that an action was taken (for rate limiting/metrics)."""
        self.actions_taken += 1
    
    def record_error(self, error_msg: str = None) -> None:
        """Record that an error occurred."""
        self.errors_encountered += 1
        if error_msg:
            if "errors" not in self.run_metrics:
                self.run_metrics["errors"] = []
            self.run_metrics["errors"].append(error_msg)
    
    def get_run_metrics(self) -> Dict[str, Any]:
        """Get metrics for the current run."""
        duration = None
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "agent": self.get_agent_name(),
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": duration,
            "actions_taken": self.actions_taken,
            "errors": self.errors_encountered,
        }
    
    def save_run_metrics(self) -> None:
        """Save run metrics for optimization."""
        metrics = self.get_run_metrics()
        self.optimizer.log_run(metrics)
    
    # ==================== Lifecycle Hooks ====================
    
    async def on_start(self) -> None:
        """Called when agent starts. Override for custom behavior."""
        self.start_time = datetime.now()
        self.log(f"=== {self.get_agent_name()} Starting ===")
    
    async def on_complete(self) -> None:
        """Called when agent completes. Override for custom behavior."""
        self.save_run_metrics()
        self.log(f"=== {self.get_agent_name()} Complete ===")
        self.log(f"Actions: {self.actions_taken}, Errors: {self.errors_encountered}")
    
    async def on_error(self, error: Exception) -> None:
        """Called when an unhandled error occurs. Override for custom behavior."""
        self.record_error()
        self.log(f"ERROR: {error}")
        await self.capture_debug_screenshot("error")
    
    # ==================== Main Entry Point ====================
    
    async def execute(self) -> None:
        """
        Execute the agent with proper lifecycle management.
        
        This is the recommended way to run an agent:
        ```
        agent = MyAgent()
        await agent.execute()
        ```
        """
        try:
            await self.on_start()
            await self.start_browser()
            await self.run()
            await self.on_complete()
            
        except Exception as e:
            await self.on_error(e)
            raise
            
        finally:
            await self.stop_browser()
