"""
LinkedIn Notification Engagement Agent
======================================
Monitors LinkedIn notifications for engagement (likes, comments, mentions, etc.)
and sends connection invites to non-connected users who have engaged.

Author: AI Agent
Created: 2024-12-09
"""

import asyncio
import json
import os
import subprocess
import socket
import re
import random
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from config_manager import ConfigManager
from optimizer import AgentOptimizer

# Anti-detection utilities
from anti_detection import (
    human_delay, human_scroll, human_mouse_move, 
    human_like_navigate, human_like_click, RateLimiter
)

# Load environment variables
load_dotenv()


# Configuration
NOTIFICATIONS_URL = "https://www.linkedin.com/notifications/"

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(SCRIPT_DIR, "notification_history.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "notification_agent_log.txt")

# Daily invite limit (to avoid LinkedIn detection)
DAILY_INVITE_LIMIT = 10


class WeeklyLimitReachedError(Exception):
    """Raised when LinkedIn's weekly invitation limit is detected."""
    pass


class NotificationAgent:
    """Agent that monitors LinkedIn notifications and sends connection invites."""
    
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self.playwright = None
        self.chrome_pid = None
        
        # Self-Optimization
        # Loads dynamic config and logs performance for auto-tuning
        self.config_manager = ConfigManager()
        self.agent_optimizer = AgentOptimizer(config_manager=self.config_manager)
        
        # Statistics
        self.notifications_processed = 0
        self.invites_sent = 0
        self.already_connected = 0
        self.already_invited = 0
        self.errors = 0
        
        # Run Metrics for Self-Optimization
        # agent_type="notification_agent" ensures the optimizer applies the correct rules
        self.run_metrics = {
            "notifications_processed": 0,
            "invites_sent": 0,
            "errors": 0,
            "agent_type": "notification_agent"
        }
        
        # User profile URL for identifying user's own comments
        self.user_profile_url = None
        
        # Rate limiter for human-like pacing (waits 5-15s between actions, long pause every 3 invites)
        self.rate_limiter = RateLimiter(
            min_delay=5, 
            max_delay=15, 
            long_pause_every=3,  # Every 3 invites, take a longer break
            long_pause_duration=(30, 60)  # 30-60 second break
        )
        
    def log(self, msg):
        """Log message to console and file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {msg}"
        print(log_line)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    
    async def simulate_human_browsing(self):
        """Simulate random human browsing behavior before taking action.
        
        This makes the bot appear more human by doing random actions like:
        - Scrolling up and down
        - Moving mouse to random elements
        - Hovering over profile sections
        - Taking natural reading pauses
        """
        try:
            self.log("    [Simulating human browsing...]")
            
            # Random chance to do different activities
            action = random.choice(["scroll", "scroll", "hover", "read", "scroll_up"])
            
            if action == "scroll":
                # Scroll down a bit then back up
                await human_scroll(self.page, random.randint(150, 350))
                await human_delay(0.5, 1.5)
                
            elif action == "scroll_up":
                # Sometimes scroll up
                await self.page.evaluate(f"window.scrollBy(0, -{random.randint(50, 150)})")
                await human_delay(0.5, 1.0)
                
            elif action == "hover":
                # Hover over random elements
                elements = await self.page.query_selector_all("button, a, img")
                if elements and len(elements) > 0:
                    random_elem = random.choice(elements[:min(10, len(elements))])
                    await human_mouse_move(self.page, random_elem)
                    await human_delay(0.3, 0.8)
                    
            elif action == "read":
                # Just pause like reading
                await human_delay(1.5, 3.5)
            
            # Random mouse movement
            await human_mouse_move(self.page)
            
        except Exception as e:
            # Don't fail if browsing simulation fails
            pass
    
    def classify_notification_with_gemini(self, notification_text):
        """Use Gemini AI to classify if a notification is an engagement notification.
        
        Returns:
            dict: {"is_engagement": bool, "engagement_type": str} or None on error
        """
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
        if not api_key:
            self.log("WARNING: No GEMINI_API_KEY found. Using fallback keyword detection.")
            return None
        
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            
            prompt = f"""Classify this LinkedIn notification.

Notification Text:
\"\"\"
{notification_text[:500]}
\"\"\"

Is this an ENGAGEMENT notification where someone interacted with my content?

Engagement types include (but are not limited to):
- Liked, loved, celebrated, supported, found insightful, found curious (any reaction)
- Commented on my post/comment
- Mentioned me in a post/comment
- Shared or reposted my content
- Replied to my comment
- Viewed my profile
- REACTED TO someone else's comment that MENTIONED ME (third-party mention reaction)

NOT engagement (should be skipped):
- Job recommendations
- Birthday reminders
- Work anniversaries
- "You appeared in X searches"
- Connection suggestions
- News/trending posts
- LinkedIn feature announcements

Respond with ONLY a JSON object in this exact format:
{{"is_engagement": true/false, "engagement_type": "liked"/"loved"/"commented"/"mentioned"/"shared"/"viewed"/"reacted"/"third_party_mention"/"none"}}

If not engagement, use "none" for type."""

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            result_text = response.text.strip()
            # Extract JSON from response (handle markdown code blocks)
            if "```" in result_text:
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
                result_text = result_text.strip()
            
            result = json.loads(result_text)
            self.log(f"  AI Classification: is_engagement={result.get('is_engagement')}, type={result.get('engagement_type')}")
            return result
            
        except json.JSONDecodeError as e:
            self.log(f"  AI response parse error: {e}. Response was: {result_text[:100]}")
            return None
        except Exception as e:
            self.log(f"  AI classification error: {e}")
            return None
    
    def fallback_keyword_detection(self, text_lower):
        """Fallback keyword-based detection if AI fails."""
        engagement_keywords = [
            "liked your", "loves your", "loved your", "celebrated your",
            "supported your", "found your", "reacted to", "commented on",
            "mentioned you", "shared your", "reposted your", "replied to",
            "viewed your profile", "and others",
            "comment that mentioned you"  # Third-party mention reactions
        ]
        return any(kw in text_lower for kw in engagement_keywords)

    def save_metrics(self):
        """Save run metrics to agent history for optimization."""
        try:
            self.run_metrics["notifications_processed"] = self.notifications_processed
            self.run_metrics["invites_sent"] = self.invites_sent
            self.run_metrics["errors"] = self.errors
            
            self.agent_optimizer.log_run(self.run_metrics)
            self.log(f"Optimization metrics saved: {self.run_metrics}")
        except Exception as e:
            self.log(f"Error saving optimization metrics: {e}")
    
    def load_history(self):
        """Load processing history from JSON file."""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {
            "processed_notifications": [],
            "invited_profiles": {},
            "already_connected": [],
            "skipped_profiles": [],
            "daily_invites": {}  # {"YYYY-MM-DD": count}
        }
    
    def get_todays_invite_count(self, history):
        """Get the number of invites sent today."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Ensure daily_invites exists in history
        if "daily_invites" not in history:
            history["daily_invites"] = {}
        
        return history["daily_invites"].get(today, 0)
    
    def increment_daily_invite_count(self, history):
        """Increment today's invite count in history."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Ensure daily_invites exists in history
        if "daily_invites" not in history:
            history["daily_invites"] = {}
        
        current_count = history["daily_invites"].get(today, 0)
        history["daily_invites"][today] = current_count + 1
        
        return history["daily_invites"][today]
    
    def can_send_more_invites_today(self, history):
        """Check if we can send more invites today (under daily limit)."""
        todays_count = self.get_todays_invite_count(history)
        return todays_count < DAILY_INVITE_LIMIT
    
    def save_history(self, data):
        """Save processing history atomically."""
        temp_file = HISTORY_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, HISTORY_FILE)
        
    async def launch_browser(self):
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
    
    async def start(self):
        """Initialize browser connection."""
        self.log("=" * 60)
        self.log("LinkedIn Notification Engagement Agent Starting")
        self.log("=" * 60)
        
        self.playwright = await async_playwright().start()
        
        try:
            self.log("Attempting to connect to existing Chrome on port 9222...")
            self.browser = await self.playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            self.context = self.browser.contexts[0]
            self.page = await self.context.new_page()
            self.log("Connected to existing Chrome.")
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
                    self.browser = await self.playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
                    self.context = self.browser.contexts[0]
                    self.page = await self.context.new_page()
                    self.log("Connected to launched Chrome.")
                    return
                except Exception as e2:
                    self.log(f"Attempt {attempt + 1} failed: {e2}")
                    if attempt == 4:
                        raise e2
    
    async def check_login_required(self):
        """Check if LinkedIn login is required."""
        await asyncio.sleep(2)
        current_url = self.page.url
        
        if "login" in current_url or "authwall" in current_url:
            self.log("LOGIN REQUIRED - Please log in to LinkedIn in the browser window")
            self.log("Waiting for login...")
            
            # Wait for user to log in (up to 5 minutes)
            for _ in range(60):
                await asyncio.sleep(5)
                current_url = self.page.url
                if "login" not in current_url and "authwall" not in current_url:
                    self.log("Login detected. Continuing...")
                    return True
            
            self.log("ERROR: Login timeout. Please run again after logging in.")
            return False
        
        return True
    
    async def detect_user_profile(self):
        """Detect the logged-in user's LinkedIn profile URL."""
        try:
            # Look for the user's profile link in the global nav
            profile_link = await self.page.query_selector("a[href*='/in/'][data-control-name='identity_profile_photo']")
            if not profile_link:
                profile_link = await self.page.query_selector("img.global-nav__me-photo")
                if profile_link:
                    # Get parent anchor
                    profile_link = await profile_link.evaluate_handle("el => el.closest('a')")
            
            if not profile_link:
                # Try the "Me" dropdown
                profile_link = await self.page.query_selector("a.ember-view.global-nav__secondary-link[href*='/in/']")
            
            if profile_link:
                href = await profile_link.get_attribute("href")
                if href and "/in/" in href:
                    # Clean up the URL
                    if not href.startswith("http"):
                        href = "https://www.linkedin.com" + href
                    href = href.split("?")[0].rstrip("/")
                    self.user_profile_url = href
                    self.log(f"Detected user profile: {self.user_profile_url}")
                    return True
            
            # Fallback: navigate to /in/me and get the redirected URL
            self.log("Trying fallback: navigating to /in/me to detect profile...")
            await self.page.goto("https://www.linkedin.com/in/me/", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            current_url = self.page.url
            if "/in/" in current_url and "/me" not in current_url:
                self.user_profile_url = current_url.split("?")[0].rstrip("/")
                self.log(f"Detected user profile via redirect: {self.user_profile_url}")
                return True
            
            self.log("WARNING: Could not detect user profile URL.")
            return False
            
        except Exception as e:
            self.log(f"Error detecting user profile: {e}")
            return False

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
    
    async def navigate_to_notifications(self):
        """Navigate to LinkedIn notifications page."""
        self.log(f"Navigating to notifications: {NOTIFICATIONS_URL}")
        # ANTI-DETECTION: Human-like navigation
        await human_like_navigate(self.page, NOTIFICATIONS_URL)
        
        if not await self.check_login_required():
            return False
        
        # Ensure view is clear of chat popups
        await self.close_chat_popups()

        # Wait for notifications to load
        try:
            await self.page.wait_for_selector(
                "div.nt-card, section.artdeco-card",
                timeout=10000
            )
            self.log("Notifications page loaded.")
            return True
        except:
            self.log("WARNING: Could not detect notification cards. Page may have different structure.")
            return True
    
    async def extract_notifications(self):
        """Extract engagement notifications from the page."""
        self.log("Extracting notifications...")
        
        # Scroll down multiple times to load more notifications
        self.log("Scrolling to load more notifications (with human-like behavior)...")
        last_height = 0
        scroll_attempts = 0
        max_scroll_attempts = self.config_manager.get("notification_agent.scroll_attempts", 15)
        
        while scroll_attempts < max_scroll_attempts:
            # ANTI-DETECTION: Human-like scrolling
            await human_scroll(self.page, random.randint(700, 1200))
            await human_delay(1.5, 3.0)  # Variable wait for content to load
            
            # Check current scroll height
            current_height = await self.page.evaluate("document.body.scrollHeight")
            
            if current_height == last_height:
                # No new content loaded, stop scrolling
                self.log(f"  Stopped scrolling after {scroll_attempts + 1} attempts (no new content)")
                break
            
            last_height = current_height
            scroll_attempts += 1
            
            if scroll_attempts % 5 == 0:
                self.log(f"  Scrolled {scroll_attempts} times...")
                # ANTI-DETECTION: Extra pause every 5 scrolls
                await human_delay(3.0, 6.0)
        
        # Scroll back to top
        await self.page.evaluate("window.scrollTo(0, 0)")
        await human_delay(1.0, 2.0)
        
        notifications = []
        
        # LinkedIn notification selectors
        notification_selectors = [
            "div.nt-card",
            "article.nt-card",
            "div[data-urn*='notification']",
            "section.artdeco-card div.nt-card__content"
        ]
        
        for selector in notification_selectors:
            try:
                cards = await self.page.query_selector_all(selector)
                if cards:
                    self.log(f"Found {len(cards)} notification cards with selector: {selector}")
                    break
            except:
                continue
        else:
            # Fallback: get all notification-like elements
            cards = await self.page.query_selector_all("div.nt-card, article")
            self.log(f"Fallback: Found {len(cards)} potential notification elements")
        
        max_notifications = self.config_manager.get("notification_agent.max_notifications_per_run", 100)
        for i, card in enumerate(cards[:max_notifications]):
            try:
                # Get notification text
                text = await card.inner_text()
                text_lower = text.lower()
                
                # DEBUG: Log first 10 notification texts to see more
                if i < 10:
                    # Clean up text for logging (remove excessive newlines)
                    clean_text = ' '.join(text.split())[:200]
                    self.log(f"  DEBUG [{i+1}]: {clean_text}")
                
                # Use AI to classify this notification
                ai_result = self.classify_notification_with_gemini(text)
                
                if ai_result:
                    is_engagement = ai_result.get("is_engagement", False)
                else:
                    # Fallback to keyword detection if AI fails
                    is_engagement = self.fallback_keyword_detection(text_lower)
                
                if not is_engagement:
                    continue
                
                self.log(f"  [{i+1}] ENGAGEMENT DETECTED: {text[:60].replace(chr(10), ' ')}...")
                
                # Extract profile links from the notification
                links = await card.query_selector_all("a[href*='/in/']")
                profiles = []
                
                self.log(f"    Found {len(links)} profile links in notification")
                
                for link in links:
                    href = await link.get_attribute("href")
                    name_elem = await link.inner_text()
                    name = name_elem.strip() if name_elem else ""
                    
                    # Clean status indicators from name (LinkedIn accessibility text)
                    status_patterns = [
                        "status is online", "status is reachable", "status is away",
                        "status is busy", "status is offline", "active status"
                    ]
                    name_lower_local = name.lower()
                    for sp in status_patterns:
                        if sp in name_lower_local:
                            name = ""
                            break
                    
                    # Less aggressive noise filtering
                    noise_words = ["see all", "unread", "notification settings"]
                    is_noise = any(nw in name.lower() for nw in noise_words) if name else False
                    
                    # Log each link for debugging
                    if len(links) <= 5:
                        self.log(f"    Link: {name[:30] if name else 'NO NAME'} -> {href[:50] if href else 'NO HREF'}")
                    
                    if href and "/in/" in href:
                        if not href.startswith("http"):
                            href = "https://www.linkedin.com" + href
                        href = href.split("?")[0]
                        
                        if not name or is_noise or len(name) < 2:
                            url_name = href.split("/in/")[-1].split("/")[0]
                            url_name = url_name.replace("%2D", "-").replace("%20", " ")
                            url_name = url_name.replace("-", " ")
                            url_name = re.sub(r'\s+[a-z0-9]{6,}$', '', url_name, flags=re.IGNORECASE)
                            url_name = re.sub(r'\s*\d+$', '', url_name)
                            name = url_name.strip().title()
                        
                        if name and not any(nw in name.lower() for nw in noise_words):
                            profiles.append({
                                "name": name,
                                "profile_url": href
                            })
                
                
                # NEW: Handle third-party mention reactions
                # Pattern: "[Person A] reacted to [Person B]'s comment that mentioned you"
                # We want to extract BOTH Person A (reactor) AND Person B (mentioner)
                if "comment that mentioned you" in text_lower:
                    self.log(f"    Third-party mention detected. Extracting mentioner...")
                    
                    # Extract Person B (the mentioner) from the pattern
                    # Pattern variations:
                    # - "Lewis Matthews reacted to Rory Safir's comment that mentioned you"
                    # - "James Tillman liked Ian Mann's comment that mentioned you"
                    mentioner_match = re.search(
                        r"(?:reacted to|liked|loved|celebrated|found.*in)\s+(.+?)'s\s+comment that mentioned you",
                        text_lower
                    )
                    
                    if mentioner_match:
                        mentioner_name_raw = mentioner_match.group(1).strip()
                        # Capitalize properly
                        mentioner_name = mentioner_name_raw.title()
                        self.log(f"    Identified mentioner: {mentioner_name}")
                        
                        # Try to find mentioner's profile link in the notification
                        mentioner_found = False
                        for link in links:
                            href = await link.get_attribute("href")
                            link_text = await link.inner_text()
                            link_text = link_text.strip() if link_text else ""
                            
                            if link_text and mentioner_name.lower() in link_text.lower() and href and "/in/" in href:
                                if not href.startswith("http"):
                                    href = "https://www.linkedin.com" + href
                                href = href.split("?")[0]
                                
                                # Check if this profile is already in the list
                                already_added = any(p["profile_url"] == href for p in profiles)
                                if not already_added:
                                    profiles.append({
                                        "name": link_text.strip(),
                                        "profile_url": href,
                                        "role": "mentioner"
                                    })
                                    self.log(f"    Added mentioner profile: {link_text.strip()} -> {href}")
                                    mentioner_found = True
                                break
                        
                        if not mentioner_found:
                            self.log(f"    Could not find mentioner's profile link for: {mentioner_name}")
                    else:
                        self.log(f"    Could not parse mentioner name from notification text")
                
                # Check for "and X others" expansion
                # Usually text is like "Person A and 5 others liked..."
                # Check for "and X others" expansion
                # Usually text is like "Person A and 5 others liked..."
                if "and" in text_lower and ("others" in text_lower or "other" in text_lower):
                    # Expand all grouped notifications (comments and non-comments)
                    match = re.search(r'and\s+(\d+)\s+others?', text_lower)
                    if match:
                        count = match.group(1)
                        self.log(f"    Found grouped notification (+{count} others). Expanding...")

                        # Find the link to the post/activity
                        # Strategy: Look for the "others" link first, then fallback to general activity link
                        expansion_url = None

                        # 1. Try to find link with text "others"
                        try:
                            others_link = await card.query_selector("a:has-text('other')")
                            if others_link:
                                expansion_url = await others_link.get_attribute("href")
                        except:
                            pass

                        # 2. If no specific "others" link, try to find the main activity link
                        # (often the timestamp or the headline link)
                        if not expansion_url:
                            try:
                                # Look for links that are NOT profile links
                                all_links = await card.query_selector_all("a")
                                for l in all_links:
                                    h = await l.get_attribute("href")
                                    if h and "/in/" not in h and "linkedin.com/feed/update" in h:
                                        expansion_url = h
                                        break
                            except:
                                pass

                        if expansion_url:
                            if not expansion_url.startswith("http"):
                                expansion_url = "https://www.linkedin.com" + expansion_url

                            # Use comment-specific scraping for comment notifications
                            if "comment" in text_lower or "replied" in text_lower:
                                self.log("    Using comment-specific reactor extraction...")
                                additional_profiles = await self.process_comment_reactions(expansion_url)
                            else:
                                additional_profiles = await self.process_related_content_page(expansion_url)

                            if additional_profiles:
                                self.log(f"    Merging {len(additional_profiles)} additional profiles...")
                                profiles.extend(additional_profiles)
                        else:
                            self.log("    Could not find expansion URL for grouped notification.")

                if profiles:
                    seen_urls = set()
                    unique_profiles = []
                    for p in profiles:
                        if p["profile_url"] not in seen_urls:
                            seen_urls.add(p["profile_url"])
                            unique_profiles.append(p)
                    profiles = unique_profiles
                    
                    # Use AI result for engagement_type, or fallback to keyword detection
                    if ai_result and ai_result.get("engagement_type") and ai_result["engagement_type"] != "none":
                        engagement_type = ai_result["engagement_type"]
                    else:
                        engagement_type = "engaged"
                        # Check for third-party mention first (most specific)
                        if "comment that mentioned you" in text_lower:
                            engagement_type = "third_party_mention"
                        elif "viewed your profile" in text_lower:
                            engagement_type = "viewed"
                        elif "loved" in text_lower:
                            engagement_type = "loved"
                        elif "liked" in text_lower:
                            engagement_type = "liked"
                        elif "commented" in text_lower:
                            engagement_type = "commented"
                        elif "mentioned" in text_lower:
                            engagement_type = "mentioned"
                        elif "reacted" in text_lower:
                            engagement_type = "reacted"
                        elif "shared" in text_lower or "reposted" in text_lower:
                            engagement_type = "shared"
                    
                    notifications.append({
                        "text": text[:100] + "..." if len(text) > 100 else text,
                        "engagement_type": engagement_type,
                        "profiles": profiles
                    })
                    
                    self.log(f"    Added {len(profiles)} profile(s): {', '.join([p['name'] for p in profiles[:3]])}")
                else:
                    self.log(f"    ✗ No valid profiles extracted from this notification")
                    
            except Exception as e:
                self.log(f"  Error extracting notification {i+1}: {e}")
                import traceback
                self.log(f"    {traceback.format_exc()}")
                continue
        
        self.log(f"Extracted {len(notifications)} engagement notifications")
        return notifications

    async def process_related_content_page(self, url):
        """
        Open the content page (post/comment) in a new tab and extract reactors.
        Returns a list of profile dicts.
        """
        self.log(f"    Opening related content in new tab: {url}")
        new_page = None
        profiles = []
        
        try:
            # Open new page in background
            new_page = await self.context.new_page()
            await new_page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            # Check for "Reactions" or "Likes" count to click
            # This is usually a button like "1,234 reactions" or similar
            # that opens the list modal.
            
            reaction_trigger_selectors = [
                "button.social-details-social-counts__count-value",
                "button[aria-label*='reactions']",
                "button:has-text('reactions')",
                "button[aria-label*='likes']",
                "span.social-details-social-counts__reactions-count"
            ]
            
            trigger_btn = None
            for selector in reaction_trigger_selectors:
                try:
                    trigger_btn = await new_page.query_selector(selector)
                    if trigger_btn:
                        self.log(f"    Found reaction list trigger: {selector}")
                        break
                except:
                    continue
            
            if trigger_btn:
                # Click to open modal
                await trigger_btn.click()
                await asyncio.sleep(2)
                
                # Wait for modal
                try:
                    await new_page.wait_for_selector("div.artdeco-modal", timeout=5000)
                    self.log("    Reactions modal opened.")
                    
                    # Scroll the modal to load more (basic scroll)
                    modal_content = await new_page.query_selector("div.artdeco-modal__content")
                    if modal_content:
                        for _ in range(3):
                            await modal_content.evaluate("element => element.scrollTop = element.scrollHeight")
                            await asyncio.sleep(1)
                    
                    # Scrape profiles from modal
                    modal_links = await new_page.query_selector_all("div.artdeco-modal a[href*='/in/']")
                    
                    for link in modal_links:
                        href = await link.get_attribute("href")
                        name_elem = await link.inner_text()
                        name = name_elem.strip() if name_elem else ""
                        
                        if href and "/in/" in href and name and len(name) > 2:
                            if not href.startswith("http"):
                                href = "https://www.linkedin.com" + href
                            href = href.split("?")[0]
                            
                            # Basic cleanup
                            if "View profile" not in name:
                                profiles.append({
                                    "name": name,
                                    "profile_url": href
                                })
                    
                    self.log(f"    Extracted {len(profiles)} profiles from details page.")
                    
                except Exception as e:
                    self.log(f"    Failed to open/scrape reactions modal: {e}")
            else:
                self.log("    No reactions trigger found on details page.")

        except Exception as e:
            self.log(f"    Error processing related content page: {e}")
        
        finally:
            if new_page:
                try:
                    await new_page.close()
                except:
                    pass
        
        return profiles
    
    async def process_comment_reactions(self, url):
        """
        Open the content page, find the user's comment, and extract only its reactors.
        This is used for comment-related notifications to avoid pulling all post reactors.
        Returns a list of profile dicts.
        """
        self.log(f"    Opening comment page to extract comment-specific reactors: {url}")
        new_page = None
        profiles = []
        
        if not self.user_profile_url:
            self.log("    WARNING: User profile URL not detected. Falling back to all reactors.")
            return await self.process_related_content_page(url)
        
        try:
            new_page = await self.context.new_page()
            await new_page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            # Extract the user's profile slug from their URL (e.g., "john-doe-123abc")
            user_slug = self.user_profile_url.split("/in/")[-1].rstrip("/")
            self.log(f"    Looking for user's comment (profile slug: {user_slug})")
            
            # Scroll to load comments
            for _ in range(3):
                await new_page.evaluate("window.scrollBy(0, 500)")
                await asyncio.sleep(1)
            
            # Find the user's comment by looking for their profile link in comment containers
            comment_containers = await new_page.query_selector_all("article.comments-comment-item, div.comments-comment-item, div[data-id]")
            
            user_comment = None
            for container in comment_containers:
                try:
                    # Check if this comment is by the user
                    author_link = await container.query_selector(f"a[href*='/in/{user_slug}']")
                    if author_link:
                        user_comment = container
                        self.log("    Found user's comment!")
                        break
                except:
                    continue
            
            if not user_comment:
                # Try alternative: look for any comment with the user's profile link
                user_comment = await new_page.query_selector(f"article:has(a[href*='/in/{user_slug}']), div.comments-comment-item:has(a[href*='/in/{user_slug}'])")
            
            if user_comment:
                # Find the reactions/likes button on this specific comment
                reaction_btn = await user_comment.query_selector("button[aria-label*='reaction'], button:has-text('like'), span.comments-comment-social-bar__reactions-count")
                
                if not reaction_btn:
                    # Try to find any clickable reaction count
                    reaction_btn = await user_comment.query_selector("button.comments-comment-social-bar__reactions-count, button[aria-label*='likes']")
                
                if reaction_btn:
                    self.log("    Clicking on comment's reaction count...")
                    await reaction_btn.click()
                    await asyncio.sleep(2)
                    
                    # Wait for modal
                    try:
                        await new_page.wait_for_selector("div.artdeco-modal", timeout=5000)
                        self.log("    Comment reactions modal opened.")
                        
                        # Scroll the modal
                        modal_content = await new_page.query_selector("div.artdeco-modal__content")
                        if modal_content:
                            for _ in range(3):
                                await modal_content.evaluate("element => element.scrollTop = element.scrollHeight")
                                await asyncio.sleep(1)
                        
                        # Scrape profiles from modal
                        modal_links = await new_page.query_selector_all("div.artdeco-modal a[href*='/in/']")
                        
                        for link in modal_links:
                            href = await link.get_attribute("href")
                            name_elem = await link.inner_text()
                            name = name_elem.strip() if name_elem else ""
                            
                            if href and "/in/" in href and name and len(name) > 2:
                                if not href.startswith("http"):
                                    href = "https://www.linkedin.com" + href
                                href = href.split("?")[0]
                                
                                # Skip the user's own profile
                                if user_slug not in href:
                                    if "View profile" not in name:
                                        profiles.append({
                                            "name": name,
                                            "profile_url": href
                                        })
                        
                        self.log(f"    Extracted {len(profiles)} profiles from comment reactions.")
                        
                    except Exception as e:
                        self.log(f"    Failed to open comment reactions modal: {e}")
                else:
                    self.log("    No reactions button found on user's comment.")
            else:
                self.log("    Could not find user's comment on the page. Falling back to all reactors.")
                profiles = await self.process_related_content_page(url)
                
        except Exception as e:
            self.log(f"    Error processing comment reactions: {e}")
        
        finally:
            if new_page:
                try:
                    await new_page.close()
                except:
                    pass
        
        return profiles
    
    async def check_connection_status(self, profile_url):
        """
        Check if already connected with a user.
        Returns: 'connected', 'pending', 'not_connected', or 'error'
        """
        try:
            self.log(f"  Checking connection status: {profile_url}")
            await self.page.goto(profile_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # Check for various button states
            
            # Already connected - has Message button prominently
            message_btn = await self.page.query_selector(
                "button.message-anywhere-button, " +
                "button[aria-label*='Message'], " +
                "a[href*='/messaging/']"
            )
            
            # Check for Connect button
            connect_btn = await self.page.query_selector(
                "button:has-text('Connect'), " +
                "button[aria-label*='connect' i], " +
                "div.pvs-profile-actions button:has-text('Connect')"
            )
            
            # Check for Pending
            pending = await self.page.query_selector(
                "button:has-text('Pending'), " +
                "button[aria-label*='Pending']"
            )
            
            # Check for Follow (means not connected but can't connect directly)
            follow_btn = await self.page.query_selector(
                "button:has-text('Follow')"
            )
            
            if pending:
                return "pending"
            
            if message_btn and not connect_btn:
                # Has message button but no connect = already connected
                return "connected"
            
            if connect_btn:
                return "not_connected"
            
            if follow_btn and not connect_btn:
                # Only follow available, no connect option
                return "follow_only"
            
            # Try to find any action buttons to understand state
            actions_text = ""
            try:
                actions = await self.page.query_selector("div.pvs-profile-actions")
                if actions:
                    actions_text = await actions.inner_text()
            except:
                pass
            
            if "message" in actions_text.lower() and "connect" not in actions_text.lower():
                return "connected"
            
            self.log(f"    Could not determine connection status. Actions: {actions_text[:50]}")
            return "unknown"
            
        except Exception as e:
            self.log(f"    Error checking connection status: {e}")
            return "error"
    
    async def send_connection_invite(self, profile_url, name):
        """Send a connection invite (without note)."""
        try:
            self.log(f"  Sending connection invite to: {name}")
            
            # ANTI-DETECTION: Variable delay before starting (more unpredictable)
            await human_delay(random.uniform(2.0, 5.0), random.uniform(5.0, 8.0))
            
            # Make sure we're on the profile page
            if profile_url not in self.page.url:
                # ANTI-DETECTION: Human-like navigation
                await human_like_navigate(self.page, profile_url)
            
            # ANTI-DETECTION: Simulate natural browsing (scroll, hover, read) before taking action
            await self.simulate_human_browsing()
            
            # ANTI-DETECTION: Scroll and move mouse naturally
            await human_scroll(self.page, random.randint(200, 400))
            await human_delay(1.0, 2.5)
            
            # Find and click Connect button
            connect_selectors = [
                "button:has-text('Connect')",
                "button[aria-label*='connect' i]",
                "div.pvs-profile-actions button:has-text('Connect')",
                "section.artdeco-card button:has-text('Connect')"
            ]
            
            connect_btn = None
            for selector in connect_selectors:
                try:
                    connect_btn = await self.page.wait_for_selector(selector, timeout=3000)
                    if connect_btn:
                        break
                except:
                    continue
            
            if not connect_btn:
                self.log("    Connect button not found")
                return False
            
            # ANTI-DETECTION: Human-like click with delay
            await human_like_click(self.page, connect_btn)
            await human_delay(1.5, 3.0)
            
            action_taken = False
            
            # Handle "Add a note?" modal - click "Send without a note"
            try:
                # First check for the standard "Send without a note"
                send_now_btn = await self.page.wait_for_selector(
                    "button:has-text('Send without a note'), " +
                    "button:has-text('Send now'), " +
                    "button[aria-label*='Send now']",
                    timeout=3000
                )
                if send_now_btn:
                    self.log("    Clicking 'Send without a note'...")
                    await human_delay(0.5, 1.5)
                    await human_like_click(self.page, send_now_btn)
                    action_taken = True
                    await human_delay(2.0, 4.0)
            except:
                pass
            
            # If we haven't sent yet, check for a generic "Send" button in a modal
            # (Sometimes "Connect" opens a modal where the button is just "Send")
            if not action_taken:
                try:
                    send_btn = await self.page.query_selector(
                        "div.artdeco-modal button:has-text('Send'):not(:has-text('without'))"
                    )
                    if send_btn:
                        self.log("    Clicking 'Send' in modal...")
                        await human_delay(0.5, 1.0)
                        await human_like_click(self.page, send_btn)
                        action_taken = True
                        await asyncio.sleep(2)
                except:
                    pass

            # Verification: Check if status changed to Pending
            self.log("    Verifying invite status...")
            await asyncio.sleep(2)
            
            is_pending = False
            try:
                # Check for Pending button
                pending_btn = await self.page.query_selector(
                    "button:has-text('Pending'), " +
                    "button[aria-label*='Pending']"
                )
                if pending_btn:
                    is_pending = True
            except:
                pass
            
            if is_pending:
                self.log(f"    ✓ Connection invite confirmed (Status: Pending)")
                return True
            else:
                # If we clicked send but it's not pending, maybe it needs more time?
                # Or maybe it failed silently.
                if action_taken:
                    self.log(f"    ⚠ Invite verify failed: Clicked send but status is not 'Pending'. Assuming success but check manually.")
                    # We'll return True here to be optimistic if we actually clicked a send button,
                    # but typically if it worked it SHOULD be pending. 
                    # Let's return False to force a retry next time if it wasn't actually sent.
                    # But if we return keys, we might loop. 
                    # Let's check for 'Connect' button again. If Connect is still there, it failed.
                    
                    try:
                        connect_again = await self.page.query_selector("button:has-text('Connect')")
                        if connect_again:
                             self.log(f"    ❌ Invite failed: 'Connect' button still present.")
                             return False
                    except:
                        pass
                        
                    return True # Optimistic success if we clicked send and Connect is gone
                else:
                    self.log(f"    ❌ Invite failed: 'Connect' clicked but no 'Send' option found and status not Pending.")
                    return False
            
            # --- Check for Weekly Limit Popup or Toast ---
            # Based on user screenshots:
            # 1. Modal Header: "You've reached the weekly invitation limit"
            # 2. Toast: "Your invitation to X was not sent because you have reached the weekly limit..."
            try:
                # Check for Modal
                limit_header = await self.page.query_selector(
                    "h2:has-text('You\\'ve reached the weekly invitation limit'), " +
                    "h2:has-text('Weekly limit reached')"
                )
                
                # Check for Toast (often appears at bottom left)
                limit_toast = await self.page.query_selector(
                    "div.artdeco-toast-item:has-text('weekly limit'), " +
                    "div[role='alert']:has-text('weekly limit')"
                )

                if (limit_header and await limit_header.is_visible()) or (limit_toast and await limit_toast.is_visible()):
                    self.log("    [!] WEEKLY INVITATION LIMIT DETECTED (Modal or Toast)!")
                    
                    # Try to close the modal nicely if it exists
                    try:
                        got_it_btn = await self.page.query_selector("button:has-text('Got it')")
                        if got_it_btn and await got_it_btn.is_visible():
                            self.log("    Clicking 'Got it' to dismiss modal...")
                            await got_it_btn.click()
                    except:
                        pass
                        
                    raise WeeklyLimitReachedError("Weekly invitation limit reached.")
            except WeeklyLimitReachedError:
                raise # Re-raise to be caught by main loop
            except Exception as e:
                # Ignore other errors during limit check
                pass

        except WeeklyLimitReachedError:
            raise
        except Exception as e:
            self.log(f"    Error sending invite: {e}")
            return False
    
    async def process_notifications(self):
        """Main processing loop for notifications."""
        history = self.load_history()
        
        # Check daily invite limit first
        todays_invites = self.get_todays_invite_count(history)
        remaining_today = DAILY_INVITE_LIMIT - todays_invites
        
        if remaining_today <= 0:
            self.log(f"\n" + "="*60)
            self.log(f"DAILY INVITE LIMIT REACHED ({DAILY_INVITE_LIMIT} invites today)")
            self.log(f"Please wait until tomorrow to send more invites.")
            self.log("="*60 + "\n")
            return
        
        self.log(f"\nDaily invite status: {todays_invites}/{DAILY_INVITE_LIMIT} sent today ({remaining_today} remaining)")
        
        notifications = await self.extract_notifications()
        
        if not notifications:
            self.log("No engagement notifications found.")
            return
        
        self.log(f"\nProcessing {len(notifications)} notifications...")
        # ANTI-DETECTION: Per-run limit (also respects daily limit)
        max_invites_per_run = self.config_manager.get("notification_agent.max_invites_per_run", 10)
        # Use the smaller of per-run limit and remaining daily limit
        max_invites = min(max_invites_per_run, remaining_today)
        self.log(f"This run limit: {max_invites} invites (per-run: {max_invites_per_run}, daily remaining: {remaining_today})")
        
        for notif in notifications:
            if self.invites_sent >= max_invites:
                self.log(f"\nReached max invites per run ({max_invites}). Stopping.")
                break
            
            self.log(f"\n--- {notif['engagement_type'].upper()}: {notif['text'][:50]}...")
            
            for profile in notif["profiles"]:
                if self.invites_sent >= max_invites:
                    break
                
                self.notifications_processed += 1

                profile_url = profile["profile_url"]
                name = profile["name"]
                
                # Skip if already processed
                if profile_url in history["invited_profiles"]:
                    self.log(f"  Skipping {name} - already invited previously")
                    continue
                
                if profile_url in history["already_connected"]:
                    self.log(f"  Skipping {name} - already connected")
                    continue
                
                if profile_url in history["skipped_profiles"]:
                    self.log(f"  Skipping {name} - previously skipped")
                    continue
                
                # Check connection status
                status = await self.check_connection_status(profile_url)
                
                if status == "connected":
                    self.log(f"  {name} - Already connected ✓")
                    history["already_connected"].append(profile_url)
                    self.already_connected += 1
                
                elif status == "pending":
                    self.log(f"  {name} - Invite already pending")
                    history["skipped_profiles"].append(profile_url)
                    self.already_invited += 1
                
                elif status == "not_connected":
                    # Send invite!
                    try:
                        success = await self.send_connection_invite(profile_url, name)
                    except WeeklyLimitReachedError:
                        self.log("\n" + "!"*60)
                        self.log("STOPPING AGENT: Weekly Invitation Limit Reached.")
                        self.log("!"*60 + "\n")
                        return
                    
                    if success:
                        history["invited_profiles"][profile_url] = {
                            "name": name,
                            "invited_at": datetime.now().isoformat(),
                            "engagement_type": notif["engagement_type"]
                        }
                        self.invites_sent += 1
                        
                        # Increment daily invite count
                        new_daily_count = self.increment_daily_invite_count(history)
                        self.log(f"  Progress: {self.invites_sent}/{max_invites} this run | {new_daily_count}/{DAILY_INVITE_LIMIT} today")
                        
                        # ANTI-DETECTION: Use rate limiter for human-like pacing
                        # (5-15s regular delay + 30-60s break every 3 invites)
                        if self.invites_sent < max_invites:
                            await self.rate_limiter.wait(self.log)
                    else:
                        self.errors += 1
                        history["skipped_profiles"].append(profile_url)
                
                elif status == "follow_only":
                    self.log(f"  {name} - Only Follow available (no Connect option)")
                    history["skipped_profiles"].append(profile_url)
                
                else:
                    self.log(f"  {name} - Status unknown, skipping")
                    history["skipped_profiles"].append(profile_url)
                    self.errors += 1
                
                # Save history after each profile
                self.save_history(history)
        
        
        # Navigate back to notifications page

        # Navigate back to notifications page
        await self.page.goto(NOTIFICATIONS_URL, wait_until="domcontentloaded")
    
    async def stop(self):
        """Clean up browser resources and terminate Chrome if launched by agent."""
        self.log("\nCleaning up...")
        
        # Step 1: Close all pages created by this agent
        try:
            if self.page and not self.page.is_closed():
                self.log("  Closing agent page...")
                await self.page.close()
        except Exception as e:
            self.log(f"  Error closing page: {e}")
        
        # Step 2: Close any other pages in the context created by agent
        try:
            if self.context:
                pages = self.context.pages
                for page in pages:
                    try:
                        if not page.is_closed():
                            self.log(f"  Closing additional page: {page.url[:50]}...")
                            await page.close()
                    except Exception as e:
                        self.log(f"  Error closing additional page: {e}")
        except Exception as e:
            self.log(f"  Error accessing context pages: {e}")
        
        # Step 3: Stop Playwright
        try:
            if self.playwright:
                self.log("  Stopping Playwright...")
                await self.playwright.stop()
        except Exception as e:
            self.log(f"  Error stopping Playwright: {e}")
        
        # Step 4: Terminate Chrome if we launched it
        if self.chrome_pid:
            self.log(f"  Terminating Chrome process (PID: {self.chrome_pid})...")
            try:
                result = subprocess.run(
                    ['taskkill', '/F', '/PID', str(self.chrome_pid)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    self.log(f"  Chrome process terminated successfully.")
                else:
                    self.log(f"  Chrome termination result: {result.stderr.strip() or 'Process may have already exited'}")
            except subprocess.TimeoutExpired:
                self.log("  Warning: Chrome termination timed out")
            except Exception as e:
                self.log(f"  Error terminating Chrome: {e}")
        
        # Step 5: Save final run statistics to history
        try:
            history = self.load_history()
            run_stats = {
                "timestamp": datetime.now().isoformat(),
                "notifications_processed": self.notifications_processed,
                "invites_sent": self.invites_sent,
                "already_connected": self.already_connected,
                "already_invited": self.already_invited,
                "errors": self.errors
            }
            
            # Initialize run_history list if not present
            if "run_history" not in history:
                history["run_history"] = []
            
            # Keep only the last 50 run records
            history["run_history"].append(run_stats)
            history["run_history"] = history["run_history"][-50:]
            
            self.save_history(history)
            self.log("  Run statistics saved to history.")
        except Exception as e:
            self.log(f"  Error saving run statistics: {e}")
        
        self.log("Agent stopped.")
    
    async def run(self):
        """Main entry point for the agent."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.log(f"Starting run (Attempt {attempt+1}/{max_retries})...")
                await self.start()
                
                if not await self.navigate_to_notifications():
                    self.log("Failed to navigate to notifications. Exiting.")
                    return
                
                # Detect user's profile URL for comment-specific filtering
                await self.detect_user_profile()
                
                await self.process_notifications()

                # Save metrics for optimization
                self.save_metrics()
                
                # Print summary
                self.log("\n" + "=" * 60)
                self.log("RUN SUMMARY")
                self.log("=" * 60)
                self.log(f"  Notifications processed: {self.notifications_processed}")
                self.log(f"  Connection invites sent: {self.invites_sent}")
                self.log(f"  Already connected: {self.already_connected}")
                self.log(f"  Already pending: {self.already_invited}")
                self.log(f"  Errors/Skipped: {self.errors}")
                self.log("=" * 60)
                
                break # Success, exit loop
                
            except Exception as e:
                is_target_closed = "Target page, context or browser has been closed" in str(e)
                if is_target_closed and attempt < max_retries - 1:
                    self.log(f"Browser closed unexpectedly (Attempt {attempt+1}). Retrying...")
                    await self.stop()
                    await asyncio.sleep(5)
                else:
                    self.log(f"CRITICAL ERROR: {e}")
                    import traceback
                    self.log(traceback.format_exc())
                    break
            finally:
                await self.stop()


if __name__ == "__main__":
    agent = NotificationAgent()
    asyncio.run(agent.run())
