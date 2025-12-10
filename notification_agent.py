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
from datetime import datetime
from playwright.async_api import async_playwright


# Configuration
NOTIFICATIONS_URL = "https://www.linkedin.com/notifications/"
MAX_NOTIFICATIONS_PER_RUN = 100  # Process up to 100 notifications per run
MAX_INVITES_PER_RUN = 50  # Send up to 50 invites per run (LinkedIn daily limit ~100)
DELAY_BETWEEN_INVITES = 5  # seconds between invites to avoid rate limits

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(SCRIPT_DIR, "notification_history.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "notification_agent_log.txt")


class NotificationAgent:
    """Agent that monitors LinkedIn notifications and sends connection invites."""
    
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self.chrome_pid = None
        
        # Statistics
        self.notifications_processed = 0
        self.invites_sent = 0
        self.already_connected = 0
        self.already_invited = 0
        self.errors = 0
        
    def log(self, msg):
        """Log message to console and file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {msg}"
        print(log_line)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    
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
            "skipped_profiles": []
        }
    
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
    
    async def navigate_to_notifications(self):
        """Navigate to LinkedIn notifications page."""
        self.log(f"Navigating to notifications: {NOTIFICATIONS_URL}")
        await self.page.goto(NOTIFICATIONS_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        if not await self.check_login_required():
            return False
        
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
        self.log("Scrolling to load more notifications...")
        last_height = 0
        scroll_attempts = 0
        max_scroll_attempts = 15  # Scroll up to 15 times
        
        while scroll_attempts < max_scroll_attempts:
            # Scroll down
            await self.page.evaluate("window.scrollBy(0, 1000)")
            await asyncio.sleep(1.5)  # Wait for content to load
            
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
        
        # Scroll back to top
        await self.page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)
        
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
        
        for i, card in enumerate(cards[:MAX_NOTIFICATIONS_PER_RUN]):
            try:
                # Get notification text
                text = await card.inner_text()
                text_lower = text.lower()
                
                # DEBUG: Log first 10 notification texts to see more
                if i < 10:
                    # Clean up text for logging (remove excessive newlines)
                    clean_text = ' '.join(text.split())[:200]
                    self.log(f"  DEBUG [{i+1}]: {clean_text}")
                
                # Check if this is an engagement notification
                engagement_keywords = [
                    # Likes and reactions
                    "liked your", "likes your", "reacted to", "reactions on", "reaction on",
                    "liked a post", "liked a comment",
                    # Comments
                    "commented on", "comments on", "comment on", "replied to",
                    # Mentions
                    "mentioned you", "mentions you",
                    # Shares
                    "shared your", "reposted your",
                    # Profile views
                    "viewed your profile",
                    # Multi-person patterns
                    "and others liked", "and others commented", "and others reacted",
                    "and 1 other", "and 2 others", "and 3 others"
                ]
                
                is_engagement = any(kw in text_lower for kw in engagement_keywords)
                
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
                    name_lower = name.lower()
                    for sp in status_patterns:
                        if sp in name_lower:
                            # Name contains status, extract from URL instead
                            name = ""
                            break
                    
                    # Less aggressive noise filtering - only skip very specific noise
                    noise_words = ["see all", "unread", "notification settings"]
                    is_noise = any(nw in name.lower() for nw in noise_words) if name else False
                    
                    # Log each link for debugging
                    if len(links) <= 5:  # Only log if not too many
                        self.log(f"    Link: {name[:30] if name else 'NO NAME'} -> {href[:50] if href else 'NO HREF'}")
                    
                    if href and "/in/" in href:
                        # Normalize URL
                        if not href.startswith("http"):
                            href = "https://www.linkedin.com" + href
                        # Clean URL (remove query params)
                        href = href.split("?")[0]
                        
                        # Extract name from URL if name is empty, noise, or very short
                        if not name or is_noise or len(name) < 2:
                            # Extract from URL: /in/john-doe-123 -> John Doe
                            url_name = href.split("/in/")[-1].split("/")[0]
                            # URL decode
                            url_name = url_name.replace("%2D", "-").replace("%20", " ")
                            # Replace hyphens with spaces
                            url_name = url_name.replace("-", " ")
                            # Remove trailing numbers/IDs
                            url_name = re.sub(r'\s+[a-z0-9]{6,}$', '', url_name, flags=re.IGNORECASE)
                            url_name = re.sub(r'\s*\d+$', '', url_name)
                            name = url_name.strip().title()
                        
                        # Skip if name still looks like noise after extraction
                        if name and not any(nw in name.lower() for nw in noise_words):
                            profiles.append({
                                "name": name,
                                "profile_url": href
                            })
                
                if profiles:
                    # Deduplicate profiles by URL
                    seen_urls = set()
                    unique_profiles = []
                    for p in profiles:
                        if p["profile_url"] not in seen_urls:
                            seen_urls.add(p["profile_url"])
                            unique_profiles.append(p)
                    profiles = unique_profiles
                    
                    # Determine engagement type
                    engagement_type = "engaged"
                    if "viewed your profile" in text_lower:
                        engagement_type = "viewed"
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
                    
                    self.log(f"    ✓ Added {len(profiles)} profile(s): {', '.join([p['name'] for p in profiles[:3]])}")
                else:
                    self.log(f"    ✗ No valid profiles extracted from this notification")
                    
            except Exception as e:
                self.log(f"  Error extracting notification {i+1}: {e}")
                import traceback
                self.log(f"    {traceback.format_exc()}")
                continue
        
        self.log(f"Extracted {len(notifications)} engagement notifications")
        return notifications
    
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
            
            # Make sure we're on the profile page
            if profile_url not in self.page.url:
                await self.page.goto(profile_url, wait_until="domcontentloaded")
                await asyncio.sleep(2)
            
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
            
            await connect_btn.click()
            await asyncio.sleep(2)
            
            # Handle "Add a note?" modal - click "Send without a note"
            try:
                send_now_btn = await self.page.wait_for_selector(
                    "button:has-text('Send without a note'), " +
                    "button:has-text('Send now'), " +
                    "button[aria-label*='Send now']",
                    timeout=3000
                )
                if send_now_btn:
                    await send_now_btn.click()
                    await asyncio.sleep(1)
            except:
                # Modal might not appear, that's OK
                pass
            
            # Alternative: Just click Send if there's a modal
            try:
                send_btn = await self.page.query_selector(
                    "button:has-text('Send'):not(:has-text('without'))"
                )
                if send_btn:
                    await send_btn.click()
                    await asyncio.sleep(1)
            except:
                pass
            
            self.log(f"    ✓ Connection invite sent to {name}")
            return True
            
        except Exception as e:
            self.log(f"    Error sending invite: {e}")
            return False
    
    async def process_notifications(self):
        """Main processing loop for notifications."""
        history = self.load_history()
        notifications = await self.extract_notifications()
        
        if not notifications:
            self.log("No engagement notifications found.")
            return
        
        self.log(f"\nProcessing {len(notifications)} notifications...")
        self.log(f"Current invite count: {self.invites_sent}/{MAX_INVITES_PER_RUN}")
        
        for notif in notifications:
            if self.invites_sent >= MAX_INVITES_PER_RUN:
                self.log(f"\nReached max invites per run ({MAX_INVITES_PER_RUN}). Stopping.")
                break
            
            self.log(f"\n--- {notif['engagement_type'].upper()}: {notif['text'][:50]}...")
            
            for profile in notif["profiles"]:
                if self.invites_sent >= MAX_INVITES_PER_RUN:
                    break
                
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
                    success = await self.send_connection_invite(profile_url, name)
                    
                    if success:
                        history["invited_profiles"][profile_url] = {
                            "name": name,
                            "invited_at": datetime.now().isoformat(),
                            "engagement_type": notif["engagement_type"]
                        }
                        self.invites_sent += 1
                        self.log(f"  Progress: {self.invites_sent}/{MAX_INVITES_PER_RUN} invites sent")
                        
                        # Delay between invites
                        if self.invites_sent < MAX_INVITES_PER_RUN:
                            self.log(f"  Waiting {DELAY_BETWEEN_INVITES}s before next action...")
                            await asyncio.sleep(DELAY_BETWEEN_INVITES)
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
                self.notifications_processed += 1
        
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
        try:
            await self.start()
            
            if not await self.navigate_to_notifications():
                self.log("Failed to navigate to notifications. Exiting.")
                return
            
            await self.process_notifications()
            
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
            
        except Exception as e:
            self.log(f"CRITICAL ERROR: {e}")
            import traceback
            self.log(traceback.format_exc())
        finally:
            await self.stop()


if __name__ == "__main__":
    agent = NotificationAgent()
    asyncio.run(agent.run())
