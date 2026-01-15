"""
LinkedIn Engagement Agent (Mentions & Replies)
==============================================
Monitors notifications specifically for mentions and replies.
Likes the content and generates an accessible review report.

Features:
- Filters for "mentioned you" or "replied to your comment"
- Likes the post/comment
- Generates accessible HTML report
- Launches local server for review
- One-click cleanup via UI

Author: AI Agent
Created: 2024-12-18
"""

import asyncio
import os
import time
import json
import threading
import webbrowser
import signal
import subprocess
import socket
import re
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from google import genai
from config_manager import ConfigManager
from optimizer import AgentOptimizer

# Anti-detection utilities
from anti_detection import (
    human_delay, human_scroll, human_mouse_move, 
    human_like_navigate, human_like_click
)

# Load environment variables
load_dotenv()

# Configuration
NOTIFICATIONS_URL = "https://www.linkedin.com/notifications/"
REVIEW_HTML_FILE = "engagement_review.html"
CHROME_PID = None
SHUTDOWN_EVENT = threading.Event()

class ReviewHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for the review server."""
    
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            if os.path.exists(REVIEW_HTML_FILE):
                with open(REVIEW_HTML_FILE, "r", encoding="utf-8") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            else:
                self.wfile.write(b"<h1>Error: Report file not found.</h1>")
        else:
            self.send_error(404)

    def do_POST(self):
        global CHROME_PID
        if self.path == "/shutdown":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Shutting down...")
            print("\n[Server] Shutdown signal received. Cleaning up...")
            
            # Delete the report file
            if os.path.exists(REVIEW_HTML_FILE):
                try:
                    os.remove(REVIEW_HTML_FILE)
                    print(f"[Cleanup] Deleted {REVIEW_HTML_FILE}")
                except Exception as e:
                    print(f"[Cleanup] Error deleting file: {e}")
            
            # Kill Chrome Process if known
            if CHROME_PID:
                print(f"[Cleanup] Killing Chrome process {CHROME_PID}...")
                try:
                    subprocess.run(['taskkill', '/F', '/PID', str(CHROME_PID)], capture_output=True)
                except Exception as e:
                    print(f"[Cleanup] Error killing Chrome: {e}")

            # Signal main loop to exit
            SHUTDOWN_EVENT.set()

class EngagementAgent:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.config_manager = ConfigManager()
        self.optimizer = AgentOptimizer(config_manager=self.config_manager)
        
        self.processed_links = []
        self.chrome_pid = None
        self.user_name = None
        
        # Metrics
        self.run_metrics = {
            "mentions_found": 0,
            "replies_found": 0,
            "third_party_mentions_found": 0,
            "comments_on_post_found": 0,
            "actions_taken": 0,
            "errors": 0,
            "agent_type": "engagement_agent"
        }
        
        self.history_file = "processed_notifications.json"
        self.history = self.load_history()
        self.state_file = "notification_state.json"
        self.last_processed_id = self.load_last_state()
        
        # Gemini AI client for verification
        self.genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_name = "gemini-2.0-flash"

    def load_last_state(self):
        """Load the ID of the last processed notification."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    return data.get("last_processed_id")
            except Exception as e:
                self.log(f"Error loading state: {e}")
        return None

    def save_last_state(self, notification_id):
        """Save the ID of the newest processed notification."""
        try:
            with open(self.state_file, "w") as f:
                json.dump({"last_processed_id": notification_id, "timestamp": str(datetime.now())}, f)
        except Exception as e:
            self.log(f"Error saving state: {e}")

    async def capture_debug_data(self, page, context_name):
        """Capture screenshot and DOM for debugging."""
        try:
            timestamp = datetime.now().strftime("%H%M%S")
            filename_base = f"debug_{context_name}_{timestamp}"
            
            # Screenshot
            png_path = f"{filename_base}.png"
            await page.screenshot(path=png_path)
            self.log(f"  [DEBUG] Saved screenshot: {png_path}")
            
            # DOM
            html_path = f"{filename_base}.html"
            content = await page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.log(f"  [DEBUG] Saved DOM: {html_path}")
            
        except Exception as e:
            self.log(f"  [DEBUG] Failed to capture debug data: {e}")

    def load_history(self):
        """Load processed notification IDs."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    return set(json.load(f))
            except Exception as e:
                self.log(f"Error loading history: {e}")
                return set()
        return set()

    def save_history(self):
        """Save processed notification IDs."""
        try:
            with open(self.history_file, "w") as f:
                json.dump(list(self.history), f)
        except Exception as e:
            self.log(f"Error saving history: {e}")

    def log(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    async def launch_browser(self):
        global CHROME_PID
        """Launch Chrome with remote debugging enabled."""
        self.log("Checking for existing Chrome processes on port 9222...")
        try:
            result = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True,
                text=True,
                timeout=10
            )
            for line in result.stdout.split('\n'):
                if ':9222' in line and 'LISTENING' in line:
                    parts = line.split()
                    if parts:
                        old_pid = parts[-1]
                        self.log(f"Found existing process on port 9222 (PID: {old_pid}). Terminating...")
                        subprocess.run(['taskkill', '/F', '/PID', old_pid], capture_output=True)
                        await asyncio.sleep(2)
        except Exception as e:
            self.log(f"Warning: Could not check for existing processes: {e}")
        
        # Find Chrome path
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            "chrome.exe"
        ]
        
        chrome_path = None
        for path in chrome_paths:
            if os.path.exists(path) or path == "chrome.exe":
                chrome_path = path
                break
        
        if not chrome_path:
            self.log("Chrome executable not found.")
            return False
        
        user_data_dir = r"C:\ChromeAutomationProfile"
        cmd = [
            chrome_path,
            "--remote-debugging-port=9222",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-client-side-phishing-detection",
            "--disable-hang-monitor"
        ]
        
        self.log(f"Launching Chrome: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.chrome_pid = process.pid
        CHROME_PID = process.pid
        self.log(f"Chrome launched with PID: {self.chrome_pid}")
        
        # Wait for Chrome to start
        for i in range(15):
            await asyncio.sleep(1)
            if process.poll() is not None:
                self.log(f"ERROR: Chrome process exited prematurely")
                return False
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', 9222))
                sock.close()
                if result == 0:
                    self.log(f"Chrome debug port ready (after {i+1}s)")
                    await asyncio.sleep(2)
                    return True
            except:
                pass
        
        self.log("WARNING: Chrome launched but port 9222 not detected after 15s")
        return False

    def identify_existing_chrome_pid(self):
        """Find PID of process listening on 9222."""
        global CHROME_PID
        try:
            result = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in result.stdout.split('\n'):
                if ':9222' in line and 'LISTENING' in line:
                    parts = line.split()
                    if parts:
                        pid = parts[-1]
                        self.chrome_pid = pid
                        CHROME_PID = pid
                        self.log(f"Identified existing Chrome PID: {pid}")
                        return
            self.log("Could not identify existing Chrome PID from netstat.")
        except Exception as e:
            self.log(f"Error identifying Chrome PID: {e}")

    async def start(self):
        """Initialize browser connection."""
        self.log("Starting Engagement Agent...")
        playwright = await async_playwright().start()
        
        try:
            self.log("Attempting to connect to existing Chrome on port 9222...")
            self.browser = await playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            self.context = self.browser.contexts[0]
            self.page = await self.context.new_page()
            self.log("Connected to existing Chrome.")
            self.identify_existing_chrome_pid()
        except Exception as e:
            self.log(f"Failed to connect to existing Chrome: {e}")
            self.log("Attempting to launch Chrome...")
            
            if not await self.launch_browser():
                raise Exception("Could not launch Chrome")
            
            # Retry connection
            for attempt in range(5):
                await asyncio.sleep(3)
                try:
                    self.log(f"Connection attempt {attempt + 1}/5...")
                    self.browser = await playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
                    self.context = self.browser.contexts[0]
                    self.page = await self.context.new_page()
                    self.log("Connected to launched Chrome.")
                    break
                except Exception as e2:
                    self.log(f"Attempt {attempt + 1} failed: {e2}")
                    if attempt == 4:
                        raise e2

        print("DEBUG: Going to feed", flush=True)
        await self.page.goto("https://www.linkedin.com/feed/")
        print("DEBUG: Waiting for feed load", flush=True)
        await asyncio.sleep(5)  # Wait for load
        
        # Ensure view is clear of chat popups
        await self.close_chat_popups()
        
        # Scrape User Name for self-exclusion
        try:
            # Try sidebar first
            name_el = await self.page.query_selector(".feed-identity-module__actor-link")
            if name_el:
                full_text = await name_el.inner_text()
                # Text usually has name + headline. But query_selector might just be the link context.
                # Let's try image alt in nav, it's cleaner: "Photo of [Name]"
                pass
            
            # reliable: nav me image
            me_img = await self.page.query_selector("button.global-nav__primary-link-me-menu-trigger img")
            if me_img:
                alt = await me_img.get_attribute("alt")
                # Format: "Photo of [Name]" or just "[Name]" depending on context
                if alt and "Photo of " in alt:
                    self.user_name = alt.replace("Photo of ", "").strip()
                elif alt:
                    self.user_name = alt.strip()
            
            if self.user_name:
                self.log(f"Identified current user as: '{self.user_name}'")
            else:
                self.log("WARNING: Could not identify current user name. Self-liking prevention may be limited.")
                
        except Exception as e:
            self.log(f"Error getting user name: {e}")

        print("DEBUG: start() finished", flush=True)

    async def close_chat_popups(self):
        """Close any open chat/messaging popups."""
        try:
            # multiple selectors for the close button on chat windows
            selectors = [
                 "button[data-control-name='overlay.close_conversation_window']",
                 "button[aria-label^='Close conversation']",
                 "button[aria-label^='Close message']",
                 "aside.msg-overlay-conversation-bubble button[type='button'] svg[data-supported-dps-icon-name='compact-close-small']", # Icon approach
                 "aside.msg-overlay-conversation-bubble header button" # Header close button
            ]
            
            # Try finding any open chat windows first
            open_chats = await self.page.query_selector_all("aside.msg-overlay-conversation-bubble")
            if open_chats:
                self.log(f"Found {len(open_chats)} open chat popups. Closing...")
                for chat in open_chats:
                    # Try to find the close button within THIS specific chat window
                    close_btn = await chat.query_selector("button[aria-label^='Close'], button.msg-overlay-bubble-header__control--close-btn")
                    
                    if not close_btn:
                         # Try finding button by looking for the SVG icon inside it
                         close_btn = await chat.query_selector("button:has(svg[data-supported-dps-icon-name='compact-close-small'])")

                    if close_btn and await close_btn.is_visible():
                        await close_btn.click()
                        await asyncio.sleep(0.5)
            
            # Fallback: check global selectors
            for sel in selectors:
                btns = await self.page.query_selector_all(sel)
                for btn in btns:
                    if await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.5)
        except Exception as e:
            self.log(f"Warning: Error closing chat popups: {e}")

    async def verify_like_posted(self, page, author_name, notification_type):
        """Use Gemini to verify if the like was successfully applied."""
        try:
            # Wait for UI to stabilize
            await asyncio.sleep(3)
            
            # First, try direct DOM check for aria-pressed="true"
            like_btns = await page.query_selector_all("button[aria-label*='Like'], button[aria-label*='React']")
            for btn in like_btns:
                label = await btn.get_attribute("aria-label") or ""
                pressed = await btn.get_attribute("aria-pressed")
                
                # Skip self-like buttons
                if "your comment" in label.lower() or "your reply" in label.lower():
                    continue
                if self.user_name and self.user_name.lower() in label.lower():
                    continue
                    
                # Check if any relevant like button is pressed
                if pressed == "true" and ("like" in label.lower() or "react" in label.lower()):
                    self.log(f"  Verification: Found pressed like button: '{label}'")
                    return "success"
            
            # Fallback: Use Gemini to analyze the page
            all_text = await page.evaluate("document.body.innerText")
            context = all_text[-10000:]  # Last portion of page text
            
            prompt = f"""Analyze this LinkedIn page content and determine if a Like action was successfully performed.

CONTEXT:
- Notification type: {notification_type}
- Target author: {author_name}

PAGE CONTENT (partial):
{context}

Look for indicators that a like was successfully applied:
1. A "Liked" or reaction indicator visible
2. "You and X others" type text near reactions
3. Any filled/solid reaction icon indication
4. Text like "You reacted" or similar confirmation

Respond with ONLY "YES" if you see clear evidence the like was applied.
Respond with "NO" if there's no evidence or the like button appears unpressed.
Respond with "ALREADY" if the content was already liked before."""

            response = self.genai_client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            result = response.text.strip().upper()
            
            self.log(f"  Gemini verification response: {result}")
            
            if "YES" in result:
                return "success"
            elif "ALREADY" in result:
                return "already_liked"
            else:
                return "failed"
                
        except Exception as e:
            self.log(f"  Warning: Verification error: {e}")
            return "unknown"

    async def process_notifications(self):
        self.log("Checking notifications...")
        # ANTI-DETECTION: Human-like navigation
        await human_like_navigate(self.page, NOTIFICATIONS_URL)

        # Get notification cards
        self.log(f"DEBUG: Starting notification scan...")
        
        # --- Scrolling Phase ---
        # Scroll until we find the last processed ID or hit limit
        cards = []
        found_last_processed = False
        scroll_attempts = 0
        max_scroll_attempts = self.config_manager.get("engagement_agent.max_scroll_attempts", 10)
        
        while not found_last_processed and scroll_attempts < max_scroll_attempts:
            cards = await self.page.query_selector_all("article.nt-card")
            self.log(f"DEBUG: Found {len(cards)} cards (Scroll {scroll_attempts}).")
            
            # Check if last processed ID is in current view
            if self.last_processed_id:
                for card in cards:
                    link = await card.query_selector("a.nt-card__headline")
                    if link:
                        url = await link.get_attribute("href")
                        if url:
                            if url.startswith("/"): url = "https://www.linkedin.com" + url
                            
                            # ID extraction logic (shared)
                            notif_id = url
                            if "activity:" in url:
                                match = re.search(r"activity:(\d+)", url)
                                if match: notif_id = f"activity:{match.group(1)}"
                            
                            if notif_id == self.last_processed_id:
                                self.log(f"Found last processed notification: {notif_id}. Stopping scroll.")
                                found_last_processed = True
                                break
            
            if not found_last_processed:
                self.log("Last processed notification not found yet. Scrolling...")
                # ANTI-DETECTION: Human-like scrolling
                await human_scroll(self.page, random.randint(600, 900))
                await human_delay(2.0, 4.0)
                scroll_attempts += 1
        
        # --- Processing Phase ---
        max_processing = self.config_manager.get("engagement_agent.max_notifications_per_run", 50)
        newest_notification_id = None
        
        for i, card in enumerate(cards[:max_processing]):
            try:
                # Use full card text to be more robust
                raw_text = await card.inner_text()
                text = raw_text.lower()
                text_lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
                
                if i < 3: self.log(f"DEBUG: Card {i} text: {text[:50]}...")

                is_mention = "mentioned you" in text
                is_reply = "replied to your" in text
                # NEW: Detect third-party mention reactions
                # Pattern: "X reacted to Y's comment that mentioned you"
                is_third_party_mention = "comment that mentioned you" in text
                # NEW: Detect comments on your posts
                # Pattern: "X commented on your post"
                is_comment_on_post = "commented on your" in text
                
                if is_mention or is_reply or is_third_party_mention or is_comment_on_post:
                    self.log(f"Found relevant notification: {text[:50]}...")
                    
                    # Click to view (opens in current tab usually, but good to handle new tab)
                    # We will command-click or just click and wait
                    link = await card.query_selector("a.nt-card__headline")
                    if not link:
                        continue
                        
                    url = await link.get_attribute("href")
                    if url and url.startswith("/"):
                        url = "https://www.linkedin.com" + url
                    
                    # Extract unique ID for history (using URN from URL if possible)
                    # URL format: .../urn:li:activity:7407...?...
                    # We'll use the full URL as ID for simplicity, or extract the activity URN
                    notification_id = url
                    if "activity:" in url:
                        try:
                            # Extract activity URN part for robust ID
                            match = re.search(r"activity:(\d+)", url)
                            if match:
                                notification_id = f"activity:{match.group(1)}"
                        except: pass
                    
                    # Stop condition check
                    if self.last_processed_id and notification_id == self.last_processed_id:
                        self.log(f"Reached last processed notification ({notification_id}). Stopping run.")
                        break

                    # Capture newest ID (the first valid one we see)
                    if newest_notification_id is None:
                        newest_notification_id = notification_id

                    if notification_id in self.history:
                        self.log(f"Skipping already processed notification: {notification_id}")
                        continue
                        
                    # Extract author and specific context for accessibility
                    author = "Unknown"
                    notification_type = "Notification"
                    
                    # Granular classification
                    if "comment that mentioned you" in text:
                        # Third-party reaction: "[Person A] reacted to [Person B]'s comment that mentioned you"
                        # We want to like Person B's comment (the one that mentioned us), not Person A
                        notification_type = "Reaction to Third-Party Mention"
                        
                        # Clean text first - remove status prefixes
                        text_clean = text
                        for prefix in ["status is online", "status is reachable", "status is away", "status is busy", "unread notification."]:
                            text_clean = text_clean.replace(prefix, "").strip()
                        
                        # Extract Person B (the one who mentioned you) - pattern: "to [Person B]'s comment"
                        # Example: "avi sommer liked sophie baidoshvili's comment that mentioned you"
                        mention_match = re.search(r"(?:to\s+)?(.+?)(?:'s|æs|'s)\s+comment\s+that\s+mentioned\s+you", text_clean, re.IGNORECASE)
                        if mention_match:
                            author = mention_match.group(1).strip()
                            # Sometimes there's extra text before the name, try to clean it
                            # Pattern: "liked sophie" -> just "sophie"
                            parts = author.split()
                            if len(parts) >= 2 and parts[0] in ['liked', 'loved', 'reacted', 'celebrated', 'found']:
                                author = ' '.join(parts[1:])
                        else:
                            author = "Unknown"
                    elif "mentioned you" in text:
                        if "comment" in text:
                            notification_type = "Mention in Comment"
                        else:
                            notification_type = "Mention in Post"
                        author = text.split("mentioned you")[0].strip()
                    elif "replied to your" in text:
                        notification_type = "Reply to Comment"
                        author = text.split("replied to your")[0].strip()
                    elif "commented on your" in text:
                        notification_type = "Comment on Post"
                        author = text.split("commented on your")[0].strip()
                    elif "reacted to your" in text:
                        if "comment" in text:
                            notification_type = "Reaction to Comment"
                        else:
                            notification_type = "Reaction to Post"
                        author = text.split("reacted to your")[0].strip()
                            
                    # Store for report - will update like_status after action
                    notification_entry = {
                        "type": notification_type,
                        "text": text, # Keep for legacy/debug
                        "text_lines": text_lines,
                        "url": url,
                        "time": datetime.now().strftime("%H:%M"),
                        "author": author,
                        "like_status": "pending"  # Will be updated after action
                    }
                    self.processed_links.append(notification_entry)
                    entry_index = len(self.processed_links) - 1  # Track index for updating
                    
                    self.log(f"Acting on: {url}")
                    
                    # Add to history immediately (will save after loop or on specific success)
                    self.history.add(notification_id)
                    self.save_history()
                    
                    # Use a fresh page to visit the link and Like
                    action_page = await self.context.new_page()
                    try:
                        # Use longer timeout (60s) and domcontentloaded instead of networkidle
                        # networkidle waits for ALL network activity to stop, which takes forever on LinkedIn
                        try:
                            await action_page.goto(url, timeout=60000, wait_until="domcontentloaded")
                        except Exception as nav_error:
                            self.log(f"First navigation attempt failed: {nav_error}")
                            self.log("Retrying with longer timeout...")
                            await action_page.goto(url, timeout=90000, wait_until="commit")

                        # Give dynamic content time to render (increased from 2s)
                        await asyncio.sleep(4)
                        
                        # Target specific comment if urn present
                        target_container = action_page # Default to page
                        comment_id = None
                        specific_found = False
                        
                        if "commentUrn" in url or "replyUrn" in url:
                            try:
                                # Prioritize replyUrn (the specific reply) over commentUrn (the parent thread)
                                target_urn_key = "replyUrn" if "replyUrn" in url else "commentUrn"
                                
                                # Regex to extract ID
                                pattern = f"{target_urn_key}=urn%3Ali%3Acomment%3A%28.+?%2C(\\d+)%29"
                                match = re.search(pattern, url)
                                if match:
                                    comment_id = match.group(1)
                                    self.log(f"Targeting specific ID: {comment_id}")
                                    
                                    # Try robust set of selectors for the specific comment container
                                    # LinkedIn uses data-urn="urn:li:comment:(...)" or data-id
                                    selectors = [
                                        f"article[data-urn*='{comment_id}']",
                                        f"div[data-urn*='{comment_id}']",
                                        f"div[data-id*='{comment_id}']",
                                        f"li[data-urn*='{comment_id}']" 
                                    ]
                                    
                                    for sel in selectors:
                                        try:
                                            # Wait briefly for it to appear
                                            el = await action_page.wait_for_selector(sel, state="attached", timeout=2000)
                                            if el:
                                                target_container = el
                                                specific_found = True
                                                self.log(f"Found specific container with selector: {sel}")
                                                
                                                # CRITICAL: Scroll into view to ensure buttons are loaded/interactable
                                                await el.scroll_into_view_if_needed()
                                                await asyncio.sleep(2)  # Increased wait for buttons to render
                                                break
                                        except:
                                            continue
                                            
                                    if not specific_found:
                                        self.log("Specific container not found by ID. Searching for 'highlighted' comment...")
                                        # Fallback: Look for the 'highlighted' comment class linkedin sometimes uses
                                        try:
                                            highlighted = await action_page.query_selector(".highlighted-comment")
                                            if highlighted:
                                                target_container = highlighted
                                                await highlighted.scroll_into_view_if_needed()
                                                specific_found = True
                                                self.log("Found .highlighted-comment container.")
                                        except: pass

                            except Exception as e:
                                self.log(f"Error targeting comment: {e}")

                        # Find Like button within target container
                        self.log(f"DEBUG: capturing state before searching for buttons...")
                        
                        # Wait for Like buttons to render before searching
                        try:
                            await action_page.wait_for_selector(
                                "button[aria-label*='Like'], button[aria-label*='React']",
                                state="attached",
                                timeout=10000  # 10 second timeout
                            )
                            self.log("Like/React buttons detected in DOM")
                        except:
                            self.log("Warning: Like buttons not found after 10s wait")
                        
                        await self.capture_debug_data(action_page, f"before_find_buttons_{entry_index}")

                        # Retry button search up to 3 times with increasing waits
                        like_btns = []
                        for attempt in range(3):
                            like_btns = await target_container.query_selector_all("button[aria-label*='Like'], button[aria-label*='React'], button[aria-label*='reaction']")
                            if like_btns:
                                break
                            self.log(f"No buttons found on attempt {attempt + 1}, waiting 2s...")
                            await asyncio.sleep(2)
                        
                        # If we targeted a specific container but found no buttons, 
                        # it might be because the buttons are in a child 'actions' div
                        if specific_found and not like_btns:
                             self.log("No buttons in top container, checking children...")
                             like_btns = await target_container.query_selector_all("button")
                        
                        if not like_btns:
                            self.log("DEBUG: No buttons found at all! Capturing state...")
                            await self.capture_debug_data(action_page, f"no_buttons_found_{entry_index}")

                        self.log(f"Found {len(like_btns)} potential action buttons.")
                        
                        clicked = False
                        target_btn = None
                        
                        # Clean author name for matching (remove status prefixes, lowercase)
                        author_clean = author.lower().strip()
                        # Remove common prefixes like "status is online/reachable"
                        for prefix in ["status is online", "status is reachable", "status is away", "status is busy"]:
                            author_clean = author_clean.replace(prefix, "").strip()
                        # Also strip newlines and extra whitespace
                        author_clean = ' '.join(author_clean.split())
                        
                        self.log(f"Looking for Like button belonging to: '{author_clean}'")
                        
                        # PASS 1: Find the button that matches the author
                        for btn in like_btns:
                            label = await btn.get_attribute("aria-label") or ""
                            label_lower = label.lower()
                            pressed = await btn.get_attribute("aria-pressed")
                            
                            # Filter for actual Like/React buttons
                            if not ("like" in label_lower or "react" in label_lower):
                                continue
                                
                            self.log(f"Checking button: '{label}', Pressed: {pressed}")
                            
                            # --- SELF-LIKING PREVENTION ---
                            # 1. Check for "Like your comment" (LinkedIn standard text)
                            if "your comment" in label_lower or "your reply" in label_lower:
                                self.log(f"Skipping self-like (Label says 'your'): '{label}'")
                                continue
                                
                            # 2. Check against User Name
                            if self.user_name and self.user_name.lower() in label_lower:
                                self.log(f"Skipping self-like (Name match '{self.user_name}'): '{label}'")
                                continue
                            
                            # --- AUTHOR MATCHING ---
                            # Check if this button belongs to the notification author
                            if author_clean and author_clean != "unknown" and author_clean in label_lower:
                                self.log(f"MATCH: Button matches author '{author_clean}'")
                                target_btn = btn
                                break
                        
                        # PASS 2: If no author-specific match, prefer buttons for specific comments
                        # (buttons with "'s comment" or "'s reply" in the label)
                        if not target_btn and like_btns:
                            self.log(f"WARNING: No button matched author '{author_clean}'. Looking for comment-specific buttons...")
                            
                            # First, try to find buttons that are for a specific person's comment (not generic)
                            for btn in like_btns:
                                label = await btn.get_attribute("aria-label") or ""
                                label_lower = label.lower()
                                pressed = await btn.get_attribute("aria-pressed")
                                
                                if not ("like" in label_lower or "react" in label_lower):
                                    continue
                                if "your comment" in label_lower or "your reply" in label_lower:
                                    continue
                                if self.user_name and self.user_name.lower() in label_lower:
                                    continue
                                
                                # PREFER buttons that are for a specific person's comment
                                # These will have patterns like "'s comment", "'s reply", or unicode variants
                                # LinkedIn uses different apostrophe characters (', ', Æ, etc.)
                                is_comment_specific = False
                                if " comment" in label_lower or " reply" in label_lower:
                                    # Check if it's for a person (not generic "React Like")
                                    # Pattern: "React Like to [Name]'s comment" or similar
                                    if "to " in label_lower and " comment" in label_lower:
                                        is_comment_specific = True
                                    elif "to " in label_lower and " reply" in label_lower:
                                        is_comment_specific = True
                                
                                if is_comment_specific and pressed != "true":
                                    self.log(f"Found comment-specific button: '{label}'")
                                    target_btn = btn
                                    break
                            
                            # If still no match, log all available buttons for debugging
                            if not target_btn:
                                self.log("No comment-specific buttons found. Available buttons:")
                                for btn in like_btns:
                                    label = await btn.get_attribute("aria-label") or ""
                                    pressed = await btn.get_attribute("aria-pressed")
                                    self.log(f"  - '{label}' (pressed={pressed})")
                                
                                # Last resort: use first available (but this is not ideal)
                                for btn in like_btns:
                                    label = await btn.get_attribute("aria-label") or ""
                                    label_lower = label.lower()
                                    pressed = await btn.get_attribute("aria-pressed")
                                    
                                    if not ("like" in label_lower or "react" in label_lower):
                                        continue
                                    if "your comment" in label_lower or "your reply" in label_lower:
                                        continue
                                    if self.user_name and self.user_name.lower() in label_lower:
                                        continue
                                        
                                    if pressed != "true":
                                        self.log(f"FALLBACK: Using generic button: '{label}'")
                                        target_btn = btn
                                        break
                        
                        # Click the target button
                        if target_btn:
                            pressed = await target_btn.get_attribute("aria-pressed")
                            label = await target_btn.get_attribute("aria-label") or ""
                            
                            if pressed != "true":
                                try:
                                    # Try regular click first
                                    await target_btn.click(timeout=5000)
                                    self.log(f"Clicked '{label}'")
                                    self.run_metrics["actions_taken"] += 1
                                    clicked = True
                                    await asyncio.sleep(2)  # Wait for like to register
                                except Exception as click_err:
                                    self.log(f"Regular click failed: {click_err}, trying force click...")
                                    try:
                                        # Fallback: force click
                                        await target_btn.click(force=True, timeout=5000)
                                        self.log(f"Force-clicked '{label}'")
                                        self.run_metrics["actions_taken"] += 1
                                        clicked = True
                                        await asyncio.sleep(2)
                                    except Exception as force_err:
                                        self.log(f"Force click also failed: {force_err}")
                            else:
                                self.log(f"Button '{label}' already pressed.")
                                clicked = True
                                self.processed_links[entry_index]["like_status"] = "already_liked"
                        
                        # Verify the like was applied
                        if clicked and self.processed_links[entry_index]["like_status"] != "already_liked":
                            self.log("  Verifying like with Gemini...")
                            like_status = await self.verify_like_posted(action_page, author, notification_type)
                            self.processed_links[entry_index]["like_status"] = like_status
                            self.log(f"  Like verification result: {like_status}")
                        elif not clicked:
                            self.log("Could not find a suitable unpressed Like button.")
                            self.processed_links[entry_index]["like_status"] = "failed"
                            await self.capture_debug_data(action_page, f"like_failed_{entry_index}")
                            
                    except Exception as e:
                        self.log(f"Error acting on notification: {e}")
                        self.run_metrics["errors"] += 1
                        self.processed_links[entry_index]["like_status"] = "error"
                    finally:
                        await action_page.close()
                        
                    if is_third_party_mention: self.run_metrics["third_party_mentions_found"] += 1
                    if is_comment_on_post: self.run_metrics["comments_on_post_found"] += 1
                    if is_mention: self.run_metrics["mentions_found"] += 1
                    if is_reply: self.run_metrics["replies_found"] += 1
                    
            except Exception as e:
                self.log(f"Error processing card {i}: {e}")

        # Save the newest notification ID as state for next run
        if newest_notification_id:
            self.log(f"Saving newest notification ID as state: {newest_notification_id}")
            self.save_last_state(newest_notification_id)
        elif self.last_processed_id:
            # If no new notifications found but we have a last state, keep it? 
            # Or maybe we just processed nothing. 
            pass

    def generate_report(self):
        """Generate accessible HTML report."""
        rows = ""
        for item in self.processed_links:
            # Create descriptive label for screen readers
            action_label = f"View {item['type']} by {item.get('author', 'someone')} on LinkedIn"
            
            # Format text parts from lines
            lines = item.get('text_lines', [item['text']])
            formatted_text = ""
            
            if lines:
                # Header (Who did what)
                formatted_text += f"<div class='notif-header'><strong>{lines[0]}</strong></div>"
                
                # Content (What they said - usually 2nd line)
                if len(lines) > 1:
                    formatted_text += f"<div class='notif-content'>&ldquo;{lines[1]}&rdquo;</div>"
                
                # Context (Original post/comment - usually rest)
                if len(lines) > 2:
                    context_text = " ".join(lines[2:])
                    formatted_text += f"<div class='notif-context'>On: {context_text}</div>"
            else:
                formatted_text = item['text']

            # Generate status badge based on like_status
            like_status = item.get('like_status', 'unknown')
            if like_status == 'success':
                status_badge = '<span class="status-badge status-success">✓ Liked</span>'
            elif like_status == 'already_liked':
                status_badge = '<span class="status-badge status-already">Already Liked</span>'
            elif like_status == 'failed':
                status_badge = '<span class="status-badge status-failed">✗ Failed</span>'
            elif like_status == 'error':
                status_badge = '<span class="status-badge status-error">⚠ Error</span>'
            else:
                status_badge = '<span class="status-badge status-unknown">? Unknown</span>'

            rows += f"""
            <tr>
                <th scope="row">{item['type']}</th>
                <td>{formatted_text}</td>
                <td>
                    <a href="{item['url']}" target="_blank" aria-label="{action_label}">
                        View on LinkedIn
                        <span class="sr-only">({item['type']} by {item.get('author', 'someone')})</span>
                    </a>
                </td>
                <td>{status_badge}</td>
                <td>{item['time']}</td>
            </tr>
            """
            
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Engagement Review</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; line-height: 1.6; color: #333; }}
                h1 {{ color: #0a66c2; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; vertical-align: top; }}
                th {{ background-color: #f4f4f4; color: #333; min-width: 120px; }}
                
                /* Notification Text Structure */
                .notif-header {{ margin-bottom: 8px; color: #191919; }}
                .notif-content {{ background: #f9f9f9; padding: 8px; border-left: 3px solid #0a66c2; margin-bottom: 8px; font-style: italic; }}
                .notif-context {{ font-size: 0.9em; color: #666; }}
                
                /* Status badges */
                .status-badge {{ padding: 4px 10px; border-radius: 12px; font-size: 0.85em; font-weight: 600; display: inline-block; }}
                .status-success {{ background-color: #d4edda; color: #155724; }}
                .status-already {{ background-color: #e2e3e5; color: #383d41; }}
                .status-failed {{ background-color: #f8d7da; color: #721c24; }}
                .status-error {{ background-color: #fff3cd; color: #856404; }}
                .status-unknown {{ background-color: #d6d8db; color: #1b1e21; }}
                
                .sr-only {{ position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }}
                .btn-container {{ margin-top: 30px; text-align: center; }}
                .close-btn {{
                    background-color: #d11124;
                    color: white;
                    border: none;
                    padding: 15px 30px;
                    font-size: 18px;
                    cursor: pointer;
                    border-radius: 5px;
                }}
                .close-btn:hover {{ background-color: #a00c1b; }}
                
                /* Modal Styles */
                .modal-backdrop {{
                    position: fixed;
                    top: 0; left: 0; width: 100%; height: 100%;
                    background: rgba(0,0,0,0.6);
                    display: flex; justify-content: center; align-items: center;
                    z-index: 1000;
                }}
                .modal-backdrop[hidden] {{ display: none; }}
                .modal {{
                    background: white; padding: 30px; border-radius: 8px;
                    max-width: 400px; width: 90%;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.3);
                    text-align: center;
                }}
                .modal-actions {{ margin-top: 20px; display: flex; justify-content: space-around; }}
            </style>
        </head>
        <body>
            <main>
                <h1>Engagement Session Review</h1>
                <p>The following interactions were processed:</p>
                
                <table aria-label="Processed Notifications">
                    <thead>
                        <tr>
                            <th>Type</th>
                            <th>Notification Text</th>
                            <th>Link</th>
                            <th>Like Status</th>
                            <th>Time Processed</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
                
                <div class="btn-container">
                    <button id="shutdownBtn" class="close-btn" aria-haspopup="dialog" aria-controls="confirmModal">Done & Cleanup</button>
                    <p id="statusMsg" style="margin-top:10px; font-weight:bold;"></p>
                </div>
                
                <!-- Accessible Modal Structure -->
                <div id="confirmModal" role="dialog" aria-modal="true" aria-labelledby="modalTitle" aria-describedby="modalDesc" class="modal-backdrop" hidden>
                    <div class="modal" tabindex="-1">
                        <h2 id="modalTitle">Confirm Cleanup</h2>
                        <p id="modalDesc">Are you sure? This will close the agent/browser and delete this report.</p>
                        <div class="modal-actions">
                            <button id="confirmYes" class="close-btn" style="background-color: #d11124;">Yes, Shutdown</button>
                            <button id="confirmNo" class="close-btn" style="background-color: #666;">Cancel</button>
                        </div>
                    </div>
                </div>

            </main>
            
            <script>
                document.addEventListener('DOMContentLoaded', function() {{
                    var btn = document.getElementById('shutdownBtn');
                    var modal = document.getElementById('confirmModal');
                    var yesBtn = document.getElementById('confirmYes');
                    var noBtn = document.getElementById('confirmNo');
                    var status = document.getElementById('statusMsg');
                    var lastFocusedElement;

                    if(btn && modal && yesBtn && noBtn) {{
                        // Open Modal
                        btn.addEventListener('click', function() {{
                            lastFocusedElement = document.activeElement;
                            modal.hidden = false;
                            // Trap focus in modal
                            yesBtn.focus();
                        }});

                        // Cancel Action
                        noBtn.addEventListener('click', function() {{
                            modal.hidden = true;
                            if(lastFocusedElement) lastFocusedElement.focus();
                        }});
                        
                        // Close on Escape
                        modal.addEventListener('keydown', function(e) {{
                            if (e.key === 'Escape') {{
                                modal.hidden = true;
                                if(lastFocusedElement) lastFocusedElement.focus();
                            }}
                        }});

                        // Confirm Action
                        yesBtn.addEventListener('click', function() {{
                            modal.hidden = true;
                            status.innerText = "Shutting down...";
                            btn.disabled = true;
                            
                            fetch('/shutdown', {{ method: 'POST' }})
                            .then(function() {{
                                window.close();
                            }})
                            .catch(function(e) {{
                                console.log("Fetch error (expected):", e);
                                window.close();
                            }});
                        }});
                    }} else {{
                        alert("Error: Accessible components missing.");
                    }}
                }});
            </script>
        </body>
        </html>
        """
        
        with open(REVIEW_HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html_content)
        self.log(f"Report generated: {REVIEW_HTML_FILE}")

    async def run(self):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.log(f"Starting run (Attempt {attempt+1}/{max_retries})...")
                await self.start()
                await self.process_notifications()
                
                self.generate_report()
                
                # Open report in the existing browser context
                port = self.config_manager.get("engagement_agent.review_server_port", 8000)

                # Start Server
                server_address = ('127.0.0.1', port)
                # Ensure port is free or handle error
                try:
                    server = HTTPServer(server_address, ReviewHandler)
                except OSError:
                    self.log(f"Port {port} in use. Trying {port+1}...")
                    port += 1
                    server_address = ('127.0.0.1', port)
                    server = HTTPServer(server_address, ReviewHandler)

                url = f"http://127.0.0.1:{port}"
                print(f"Review Server started at {url}", flush=True)
                
                # Run server in a separate thread
                server_thread = threading.Thread(target=server.serve_forever)
                server_thread.daemon = True
                server_thread.start()
                
                try:
                    report_page = await self.context.new_page()
                    await report_page.goto(url)
                    
                    # Close all other tabs
                    for page in self.context.pages:
                        if page != report_page:
                            await page.close()
                except Exception as e:
                    self.log(f"Warning: Could not open report: {e}")

                print("Server running. waiting for cleanup signal...", flush=True)
                
                # Wait for shutdown signal
                while not SHUTDOWN_EVENT.is_set():
                    await asyncio.sleep(1)
                
                break # Success

            except Exception as e:
                is_target_closed = "Target page, context or browser has been closed" in str(e)
                if is_target_closed and attempt < max_retries - 1:
                    self.log(f"Browser closed unexpectedly (Attempt {attempt+1}). Retrying...")
                    # Cleanup before retry
                    self.log("[Cleanup] Cleaning up before retry...")
                    if self.context: 
                        try:
                            await self.context.close()
                        except: pass
                    pid_to_kill = self.chrome_pid or CHROME_PID
                    if pid_to_kill:
                        try:
                            subprocess.run(['taskkill', '/F', '/PID', str(pid_to_kill)], capture_output=True)
                        except: pass
                    
                    await asyncio.sleep(5)
                else:
                    self.log(f"CRITICAL ERROR: {e}")
                    import traceback
                    traceback.print_exc()
                    break
            finally:
                self.log("[Cleanup] logic triggered.")
                if self.context: 
                    try:
                        await self.context.close()
                        self.log("[Cleanup] Browser context closed.")
                    except: pass
                
                # Kill Chrome Process if known and event was set (user requested)
                # We check chrome_pid (instance var) or global CHROME_PID
                pid_to_kill = self.chrome_pid or CHROME_PID
                if pid_to_kill and SHUTDOWN_EVENT.is_set():
                    print(f"[Cleanup] Terminating specific Chrome process {pid_to_kill}...", flush=True)
                    try:
                        subprocess.run(['taskkill', '/F', '/PID', str(pid_to_kill)], capture_output=True)
                    except Exception as e:
                        print(f"[Cleanup] Error terminating Chrome: {e}")
            


if __name__ == "__main__":
    print("DEBUG: Script started", flush=True)
    try:
        agent = EngagementAgent()
        asyncio.run(agent.run())
    except Exception as e:
        print(f"DEBUG: Critical error in main: {e}", flush=True)
        import traceback
        traceback.print_exc()
