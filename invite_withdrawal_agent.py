"""
LinkedIn Invite Withdrawal Agent
================================
Withdraws sent connection invites that are older than 1 month.
Processes invites from oldest to newest (scrolls to end first).

Author: AI Agent
Created: 2024-12-17
"""

import asyncio
import os
import subprocess
import socket
import re
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
SENT_INVITES_URL = "https://www.linkedin.com/mynetwork/invitation-manager/sent/"
MIN_AGE_DAYS = 31  # Only withdraw invites older than this (> 1 month)
DELAY_BETWEEN_WITHDRAWALS = 2  # seconds between withdrawals to avoid rate limits
MAX_WITHDRAWALS_PER_RUN = 100  # Safety limit

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "invite_withdrawal_log.txt")


class InviteWithdrawalAgent:
    """Agent that withdraws old sent LinkedIn connection invites."""
    
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self.chrome_pid = None
        
        # Statistics
        self.total_invites = 0
        self.withdrawn_count = 0
        self.skipped_count = 0
        self.errors = 0
        
    def log(self, msg):
        """Log message to console and file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {msg}"
        print(log_line)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    
    def parse_time_ago(self, text):
        """
        Parse LinkedIn's "Sent X ago" text and return age in days.
        
        Examples:
        - "Sent 2 weeks ago" -> 14
        - "Sent 1 month ago" -> 30
        - "Sent 2 months ago" -> 60
        - "Sent 3 months ago" -> 90
        
        Returns: int (days) or -1 if parsing fails
        """
        text_lower = text.lower().strip()
        
        # Look for patterns like "X weeks ago", "X months ago"
        patterns = [
            (r'(\d+)\s*day', 1),           # X days
            (r'(\d+)\s*week', 7),          # X weeks
            (r'(\d+)\s*month', 30),        # X months
            (r'(\d+)\s*year', 365),        # X years
        ]
        
        for pattern, multiplier in patterns:
            match = re.search(pattern, text_lower)
            if match:
                value = int(match.group(1))
                return value * multiplier
        
        # Special cases
        if "yesterday" in text_lower:
            return 1
        if "today" in text_lower or "hour" in text_lower or "minute" in text_lower:
            return 0
        
        return -1  # Unknown
    
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
        self.log("LinkedIn Invite Withdrawal Agent Starting")
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
    
    async def navigate_to_sent_invites(self):
        """Navigate to LinkedIn sent invitations page."""
        self.log(f"Navigating to sent invites: {SENT_INVITES_URL}")
        await self.page.goto(SENT_INVITES_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        if not await self.check_login_required():
            return False
        
        # Wait for invite cards to load
        try:
            await self.page.wait_for_selector(
                "li.invitation-card, div.invitation-card, ul.mn-invitation-list",
                timeout=10000
            )
            self.log("Sent invitations page loaded.")
            return True
        except:
            self.log("WARNING: Could not detect invitation cards. Page may be empty or have different structure.")
            return True
    
    async def scroll_to_end(self):
        """
        Click 'Load more' button repeatedly to load all sent invites.
        LinkedIn uses a 'Load more' button instead of infinite scroll.
        """
        self.log("Loading all invites by clicking 'Load more' button...")
        load_more_clicks = 0
        max_clicks = 100  # Safety limit for 800+ invites (loads ~10 per click)
        consecutive_failures = 0
        max_failures = 3  # Allow a few retries before giving up
        
        while load_more_clicks < max_clicks and consecutive_failures < max_failures:
            # Scroll down to make Load more button visible
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)  # Increased wait for scroll to complete
            
            # Try multiple methods to find the Load more button
            load_more_btn = None
            
            # Method 1: Use JavaScript to find button by text content (most reliable)
            load_more_btn = await self.page.evaluate_handle("""
                () => {
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const text = (btn.innerText || btn.textContent || '').toLowerCase().trim();
                        if (text.includes('load more') || text === 'show more results') {
                            return btn;
                        }
                    }
                    return null;
                }
            """)
            
            # Check if we got a valid element
            if load_more_btn:
                try:
                    element = load_more_btn.as_element()
                    if element:
                        load_more_btn = element
                    else:
                        load_more_btn = None
                except:
                    load_more_btn = None
            
            # Method 2: Fallback to Playwright selector
            if not load_more_btn:
                load_more_btn = await self.page.query_selector("button:has-text('Load more')")
            
            if not load_more_btn:
                load_more_btn = await self.page.query_selector("button:has-text('load more')")
            
            # Method 3: Try aria-label based selector
            if not load_more_btn:
                load_more_btn = await self.page.query_selector("button[aria-label*='Load more']")
            
            # Method 4: Look for any button at the bottom of the list
            if not load_more_btn:
                load_more_btn = await self.page.query_selector("main button.artdeco-button--secondary:last-of-type")
            
            if not load_more_btn:
                consecutive_failures += 1
                if consecutive_failures >= max_failures:
                    self.log(f"No Load more button found after {consecutive_failures} attempts. All invites likely loaded after {load_more_clicks} clicks.")
                    break
                else:
                    self.log(f"  Button not found, retrying... ({consecutive_failures}/{max_failures})")
                    await asyncio.sleep(2)  # Wait before retry
                    continue
            
            # Check if button is visible/enabled
            try:
                is_visible = await load_more_btn.is_visible()
                if not is_visible:
                    consecutive_failures += 1
                    self.log(f"  Button not visible, retrying... ({consecutive_failures}/{max_failures})")
                    await asyncio.sleep(1)
                    continue
            except:
                consecutive_failures += 1
                continue
            
            # Click the button
            try:
                await load_more_btn.click()
                load_more_clicks += 1
                consecutive_failures = 0  # Reset failure counter on success
                
                # Wait for new content to load (increased for reliability)
                await asyncio.sleep(2)
                
                # Progress logging every 5 clicks for 800+ invites
                if load_more_clicks % 5 == 0:
                    # Count current buttons to show progress
                    current_buttons = await self.page.query_selector_all("button:has-text('Withdraw')")
                    self.log(f"  Clicked 'Load more' {load_more_clicks} times... ({len(current_buttons)} invites loaded)")
                    
            except Exception as e:
                self.log(f"  Error clicking Load more: {e}")
                consecutive_failures += 1
                if consecutive_failures >= max_failures:
                    self.log(f"Too many consecutive errors. Stopping after {load_more_clicks} clicks.")
                    break
                await asyncio.sleep(2)
        
        if load_more_clicks >= max_clicks:
            self.log(f"Reached max clicks limit ({max_clicks}). Some invites may not be loaded.")
        
        # Final count
        final_buttons = await self.page.query_selector_all("button:has-text('Withdraw')")
        self.log(f"Loading complete: {len(final_buttons)} invites loaded after {load_more_clicks} clicks.")
        
        # Scroll back to top
        await self.page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)
        
        self.log("All invites loaded. Ready to process.")
    
    async def extract_all_invites(self):
        """
        Extract all invite cards with their age information.
        LinkedIn uses a flat DOM structure where each invite is NOT in a container.
        Strategy: Find all Withdraw buttons as anchor points, then look at preceding elements.
        """
        invites = []
        
        self.log("Searching for Withdraw buttons as anchor points...")
        
        # Find all Withdraw buttons in main content
        withdraw_buttons = await self.page.query_selector_all("main button:has-text('Withdraw')")
        
        if not withdraw_buttons:
            # Try alternative selectors
            withdraw_buttons = await self.page.query_selector_all("button:has-text('Withdraw')")
        
        if not withdraw_buttons:
            self.log("No Withdraw buttons found on the page.")
            
            # Debug: check page structure
            page_title = await self.page.title()
            self.log(f"  Page title: {page_title}")
            all_buttons = await self.page.query_selector_all("button")
            self.log(f"  Total buttons on page: {len(all_buttons)}")
            
            # Log first few button texts
            for i, btn in enumerate(all_buttons[:5]):
                try:
                    btn_text = await btn.inner_text()
                    self.log(f"    Button {i+1}: '{btn_text[:30]}'")
                except:
                    pass
            
            return []
        
        self.log(f"Found {len(withdraw_buttons)} Withdraw buttons")
        self.total_invites = len(withdraw_buttons)
        
        # For each Withdraw button, extract associated invite info
        # We'll use JavaScript to get preceding sibling elements
        
        # DEBUG: Enhanced DOM exploration to find time text location
        if withdraw_buttons:
            debug_info = await self.page.evaluate("""
                (button) => {
                    let info = {
                        buttonTagName: button.tagName,
                        buttonText: button.innerText,
                        parentTagName: button.parentElement ? button.parentElement.tagName : 'NONE',
                        parentClassName: button.parentElement ? button.parentElement.className : 'NONE',
                        prevSibling: null,
                        parentPrevSiblings: [],
                        grandparentTagName: 'NONE',
                        grandparentClassName: 'NONE',
                        foundTimeText: '',
                        timeLocation: '',
                        ancestorChain: []
                    };
                    
                    // Get grandparent info
                    if (button.parentElement && button.parentElement.parentElement) {
                        info.grandparentTagName = button.parentElement.parentElement.tagName;
                        info.grandparentClassName = button.parentElement.parentElement.className;
                    }
                    
                    // Get prev sibling info of button itself
                    let prev = button.previousElementSibling;
                    if (prev) {
                        info.prevSibling = {
                            tag: prev.tagName,
                            class: prev.className,
                            text: (prev.innerText || '').substring(0, 100)
                        };
                    }
                    
                    // Get PARENT's previous siblings
                    if (button.parentElement) {
                        let current = button.parentElement.previousElementSibling;
                        for (let i = 0; i < 8 && current; i++) {
                            info.parentPrevSiblings.push({
                                tag: current.tagName,
                                class: (current.className || '').substring(0, 50),
                                text: (current.innerText || current.textContent || '').substring(0, 120)
                            });
                            current = current.previousElementSibling;
                        }
                    }
                    
                    // CRITICAL: Search up the ancestor tree for "Sent" or "ago" text
                    let ancestor = button.parentElement;
                    let depth = 0;
                    while (ancestor && depth < 6) {
                        let text = ancestor.innerText || '';
                        info.ancestorChain.push({
                            depth: depth,
                            tag: ancestor.tagName,
                            textSnippet: text.substring(0, 200)
                        });
                        
                        // Look for time text in this ancestor
                        let patterns = [
                            /Sent\s+(\d+\s*(?:day|week|month|year)s?\s+ago)/i,
                            /Sent\s+today/i,
                            /Sent\s+yesterday/i,
                            /(\d+\s*(?:week|month|year)s?\s+ago)/i
                        ];
                        for (let p of patterns) {
                            let m = text.match(p);
                            if (m && !info.foundTimeText) {
                                info.foundTimeText = m[0];
                                info.timeLocation = `ancestor depth ${depth} (${ancestor.tagName})`;
                                break;
                            }
                        }
                        
                        ancestor = ancestor.parentElement;
                        depth++;
                    }
                    
                    return info;
                }
            """, withdraw_buttons[0])
            
            self.log(f"DEBUG: First button structure:")
            self.log(f"  Button: {debug_info.get('buttonTagName')} - '{debug_info.get('buttonText')}'")
            self.log(f"  Parent: {debug_info.get('parentTagName')} class='{str(debug_info.get('parentClassName'))[:50]}'")
            self.log(f"  Grandparent: {debug_info.get('grandparentTagName')} class='{str(debug_info.get('grandparentClassName'))[:50]}'")
            
            # Log time text finding result
            found_time = debug_info.get('foundTimeText', '')
            time_loc = debug_info.get('timeLocation', '')
            if found_time:
                self.log(f"  FOUND TIME TEXT: '{found_time}' at {time_loc}")
            else:
                self.log(f"  TIME TEXT NOT FOUND in ancestor chain!")
            
            # Log ancestor chain for debugging
            self.log(f"  Ancestor chain:")
            for anc in debug_info.get('ancestorChain', [])[:4]:
                snippet = anc.get('textSnippet', '')[:100].replace('\\n', ' ')
                self.log(f"    Depth {anc.get('depth')}: {anc.get('tag')} - '{snippet}'")
        
        for i, btn in enumerate(withdraw_buttons):
            try:
                # Get invite info using JavaScript to traverse the DOM
                # IMPORTANT: Button is inside a wrapper div, so we need to look at
                # button.parentElement.previousElementSibling to find name/time
                invite_info = await self.page.evaluate("""
                    (button) => {
                        let name = '';
                        let timeText = '';
                        let profileUrl = '';
                        
                        // Get the button's parent (wrapper div)
                        let buttonParent = button.parentElement;
                        if (!buttonParent) return { name: '', timeText: '', profileUrl: '' };
                        
                        // Walk backwards from button's PARENT using previousElementSibling
                        let current = buttonParent.previousElementSibling;
                        let elementCount = 0;
                        
                        while (current && elementCount < 10) {
                            elementCount++;
                            
                            let text = current.innerText || current.textContent || '';
                            let tagName = current.tagName;
                            
                            // If it's a DIV, extract the first line as name (usually name\\nheadline)
                            if (tagName === 'DIV' && !name) {
                                let lines = text.split('\\n').filter(l => l.trim());
                                if (lines.length > 0) {
                                    let firstName = lines[0].trim();
                                    // Make sure it's a reasonably short name (not a full headline)
                                    if (firstName.length > 1 && firstName.length < 50) {
                                        name = firstName;
                                    }
                                }
                                
                                // Also check for time pattern in the text
                                let lowerText = text.toLowerCase();
                                if (!timeText && (lowerText.includes('sent') || lowerText.includes('ago'))) {
                                    let patterns = [
                                        /Sent\\s+(\\d+\\s*(?:day|week|month|year)s?\\s+ago)/i,
                                        /(\\d+\\s*(?:day|week|month|year)s?\\s+ago)/i,
                                        /(Sent\\s+today)/i,
                                        /(Sent\\s+yesterday)/i
                                    ];
                                    for (let p of patterns) {
                                        let m = text.match(p);
                                        if (m) { timeText = m[0]; break; }
                                    }
                                }
                            }
                            
                            // If it's a link with profile URL, get the name from there
                            if (tagName === 'A' || (current.querySelector && current.querySelector('a[href*="/in/"]'))) {
                                let link = tagName === 'A' ? current : current.querySelector('a[href*="/in/"]');
                                if (link) {
                                    let href = link.getAttribute('href') || '';
                                    if (href.includes('/in/') && !profileUrl) {
                                        profileUrl = href;
                                        // Name might be in the link or after it
                                        let linkText = (link.innerText || '').trim();
                                        if (linkText.length > 1 && linkText.length < 50 && !name) {
                                            name = linkText;
                                        }
                                    }
                                }
                            }
                            
                            current = current.previousElementSibling;
                        }
                        
                        return { name, timeText, profileUrl };
                    }
                """, btn)
                
                name = invite_info.get("name", "") if invite_info else ""
                time_text = invite_info.get("timeText", "") if invite_info else ""
                
                # Fallback: get text from around the button and parse
                if not name or not time_text:
                    # Get parent's text content and try to parse
                    parent_text = await btn.evaluate("btn => btn.parentElement ? btn.parentElement.innerText : ''")
                    
                    if not time_text and parent_text:
                        match = re.search(r'(?:Sent\s+)?(\d+\s*(?:day|week|month|year)s?\s+ago|today|yesterday)', parent_text, re.IGNORECASE)
                        if match:
                            time_text = match.group(0)
                
                age_days = self.parse_time_ago(time_text)
                
                if i < 15:  # Log first 15 for debugging
                    self.log(f"  [{i+1}] {name[:30] if name else 'NO NAME':30} | Time: '{time_text[:25] if time_text else 'NO TIME':25}' | Age: {age_days} days")
                
                invites.append({
                    "button": btn,  # Store button instead of card
                    "name": name if name else f"Unknown-{i+1}",
                    "age_days": age_days,
                    "time_text": time_text
                })
                
            except Exception as e:
                self.log(f"  Error extracting invite {i+1}: {e}")
                continue
        
        return invites
    
    async def withdraw_invite(self, invite):
        """
        Click the Withdraw button for an invite.
        Now we already have the button reference from extract_all_invites.
        Returns True if successful.
        """
        import time
        start_ts = time.time()
        
        withdraw_btn = invite["button"]  # We already have the button
        name = invite["name"]
        
        self.log(f"    [P] Starting withdrawal for {name}...")
        
        try:
            # RETRY LOOP for clicking the initial 'Withdraw' button
            # It might be blocked by a previous dialog that hasn't fully closed
            max_retries = 3
            clicked = False
            
            for attempt in range(max_retries):
                try:
                    # First, dismiss any existing dialogs that might be blocking
                    # Use a very short timeout for check, don't wait if not there
                    if attempt > 0:
                        self.log(f"    [P] Retry {attempt+1}: Attempting to clear blockers...")
                        # If we failed once, try to clear blockers aggressively
                        await self.page.keyboard.press("Escape")
                        await asyncio.sleep(0.5)
                        
                        try:
                            close_btn = await self.page.query_selector("dialog button[aria-label='Dismiss'], dialog button:has-text('Cancel')")
                            if close_btn and await close_btn.is_visible():
                                await close_btn.click()
                                await asyncio.sleep(0.5)
                        except:
                            pass
                    
                    # Try to click with a short timeout (3s instead of default 30s)
                    # This allows us to fail fast and try to clear blockers
                    t0 = time.time()
                    await withdraw_btn.click(timeout=3000)
                    t1 = time.time()
                    self.log(f"    [P] Clicked initial withdraw button (took {t1-t0:.2f}s)")
                    clicked = True
                    break
                    
                except Exception as e:
                    elapsed = time.time() - t0
                    self.log(f"    [P] Click failed after {elapsed:.2f}s: {str(e)[:100]}")
                    if "intercepts pointer events" in str(e) or "Timeout" in str(e):
                        if attempt < max_retries - 1:
                            self.log(f"    - Click blocked, attempting to clear dialogs (Attempt {attempt+1})...")
                            await asyncio.sleep(1)
                            continue
                    
                    # If it's another error or we're out of retries
                    self.log(f"    - Failed to click withdraw button: {e}")
                    return False
            
            if not clicked:
                return False

            await asyncio.sleep(0.5)
            
            # Handle confirmation dialog - LinkedIn shows a dialog asking to confirm
            try:
                # Wait for confirmation dialog to appear
                t2 = time.time()
                dialog = await self.page.wait_for_selector("dialog[data-testid='dialog']", state="visible", timeout=3000)
                t3 = time.time()
                if dialog:
                    self.log(f"    [P] Dialog appeared (took {t3-t2:.2f}s)")
                if dialog:
                    self.log(f"    [P] Dialog appeared (took {t3-t2:.2f}s)")
                    # Find the Withdraw button inside the dialog
                    dialog_withdraw_btn = await dialog.query_selector("button:has-text('Withdraw')")
                    if dialog_withdraw_btn:
                        await dialog_withdraw_btn.click()
                        self.log(f"    [P] Clicked dialog withdraw button")
                    else:
                        # Try to find any primary/confirm button
                        confirm_btn = await dialog.query_selector("button.artdeco-button--primary")
                        if confirm_btn:
                            # Log the text of the button we found
                            btn_text = await confirm_btn.inner_text()
                            await confirm_btn.click()
                            self.log(f"    [P] Clicked dialog confirm button: '{btn_text}'")
                        else:
                            self.log(f"    [P] WARNING: No button found in dialog!")
                            # Dump dialog content for debugging
                            try:
                                html = await dialog.inner_html()
                                self.log(f"    [P] Dialog HTML snippet: {html[:300]}")
                            except:
                                pass
                    
                    await asyncio.sleep(0.5)
                else:
                    self.log(f"    [P] Dialog not found (timeout?)")
            except Exception as e:
                 self.log(f"    [P] Error waiting for dialog: {str(e)[:100]}")
                 pass  # No confirmation dialog appeared (or we missed it)
            
            # Verify by waiting for dialog to close
            try:
                # Check if dialog is still visible
                t4 = time.time()
                is_dialog_visible = await self.page.is_visible("dialog[data-testid='dialog']")
                if is_dialog_visible:
                     self.log(f"    [P] Waiting for dialog to close...")
                     await self.page.wait_for_selector("dialog[data-testid='dialog']", state="hidden", timeout=2000)
                     t5 = time.time()
                     self.log(f"    [P] Dialog closed (took {t5-t4:.2f}s)")
            except:
                # If dialog is still there, try to dismiss it
                try:
                    self.log(f"    [P] Dialog still visible, forcing dismiss...")
                    await self.page.keyboard.press("Escape")
                    dismiss_btn = await self.page.query_selector("dialog button[aria-label='Dismiss']")
                    if dismiss_btn:
                        await dismiss_btn.click()
                    await asyncio.sleep(0.5)
                except:
                    pass
            
            total_time = time.time() - start_ts
            self.log(f"    ✓ Withdrawn: {name} ({invite['time_text']}) - Total time: {total_time:.2f}s")
            return True
            
        except Exception as e:
            self.log(f"    ✗ Error withdrawing invite for {name}: {e}")
            # Try to close any blocking dialog
            try:
                await self.page.keyboard.press("Escape")
            except:
                pass
            return False
    
    async def process_invites(self):
        """Main processing loop - withdraw old invites in reverse order."""
        self.log("=" * 60)
        self.log("Processing Sent Invites")
        self.log(f"Will withdraw invites older than {MIN_AGE_DAYS} days (> 1 month)")
        self.log("=" * 60)
        
        # Navigate to sent invites page
        if not await self.navigate_to_sent_invites():
            self.log("Failed to navigate to sent invites page.")
            return
        
        # Scroll to load all invites
        await self.scroll_to_end()
        
        # Extract all invites
        invites = await self.extract_all_invites()
        
        if not invites:
            self.log("No invites found to process.")
            return
        
        # Filter invites older than MIN_AGE_DAYS
        old_invites = [inv for inv in invites if inv["age_days"] > MIN_AGE_DAYS]
        
        self.log(f"\nTotal invites: {len(invites)}")
        self.log(f"Invites older than {MIN_AGE_DAYS} days: {len(old_invites)}")
        self.log(f"Invites to skip (≤ {MIN_AGE_DAYS} days): {len(invites) - len(old_invites)}")
        
        if not old_invites:
            self.log("\nNo invites older than 1 month. Nothing to withdraw.")
            return
        
        # Reverse order - oldest first (they're at the bottom of the list)
        old_invites.reverse()
        
        self.log(f"\nStarting withdrawal from oldest to newest...")
        self.log("-" * 40)
        
        for i, invite in enumerate(old_invites):
            if i >= MAX_WITHDRAWALS_PER_RUN:
                self.log(f"\nReached max withdrawals per run ({MAX_WITHDRAWALS_PER_RUN}). Stopping.")
                break
            
            self.log(f"[{i+1}/{len(old_invites)}] Processing: {invite['name']} ({invite['age_days']} days old)")
            
            # Scroll to make button visible
            try:
                await invite["button"].scroll_into_view_if_needed()
                await asyncio.sleep(0.5)
            except:
                pass
            
            if await self.withdraw_invite(invite):
                self.withdrawn_count += 1
            else:
                self.errors += 1
            
            # Delay between withdrawals
            await asyncio.sleep(DELAY_BETWEEN_WITHDRAWALS)
        
        self.skipped_count = len(invites) - len(old_invites)
    
    async def stop(self):
        """Clean up browser resources."""
        self.log("\n" + "=" * 60)
        self.log("Invite Withdrawal Agent Stopping")
        self.log("=" * 60)
        self.log(f"Total invites found: {self.total_invites}")
        self.log(f"Withdrawn: {self.withdrawn_count}")
        self.log(f"Skipped (≤ 1 month): {self.skipped_count}")
        self.log(f"Errors: {self.errors}")
        
        try:
            if self.page:
                await self.page.close()
        except:
            pass
        
        try:
            if self.browser:
                await self.browser.close()
        except:
            pass
        
        try:
            if self.playwright:
                await self.playwright.stop()
        except:
            pass
        
        # Terminate Chrome if we launched it
        if self.chrome_pid:
            try:
                subprocess.run(['taskkill', '/F', '/PID', str(self.chrome_pid)], capture_output=True)
                self.log(f"Terminated Chrome process (PID: {self.chrome_pid})")
            except:
                pass
        
        self.log("Cleanup complete.")
    
    async def run(self):
        """Main entry point for the agent."""
        try:
            await self.start()
            await self.process_invites()
        except Exception as e:
            self.log(f"CRITICAL ERROR: {e}")
            import traceback
            self.log(traceback.format_exc())
        finally:
            await self.stop()


if __name__ == "__main__":
    agent = InviteWithdrawalAgent()
    asyncio.run(agent.run())
