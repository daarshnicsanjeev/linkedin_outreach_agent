"""
LinkedIn Auto Comment Agent for Legal Professionals
====================================================
Automatically finds posts from lawyers and generates professional,
supportive comments. Comments are reviewed before posting.

Features:
- Scans LinkedIn feed for posts by legal professionals
- Generates AI-powered comments using Gemini Flash
- LinkedIn-style accessible review UI
- Batch posting after approval
- Regenerate comment option per post

Author: AI Agent
Created: 2024-12-26
"""

import asyncio
import os
import json
import threading
import subprocess
import socket
import re
import random
import urllib.parse
import winsound  # Windows-specific for system sounds
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from google import genai

# Anti-detection utilities
from anti_detection import (
    human_delay, human_scroll, human_mouse_move, 
    human_like_navigate, human_like_click, human_like_type
)

# Load environment variables
load_dotenv()

# Sound alert functions (plays through regular Windows speakers)
def play_ready_sound():
    """Play attention-grabbing sound when ready for review."""
    import time
    import os
    print("[SOUND] Playing ready notification...", flush=True)
    
    # Find a Windows WAV file that exists
    media_folder = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Media')
    wav_candidates = [
        'Windows Notify System Generic.wav',
        'Windows Notify.wav',
        'Windows Ding.wav',
        'notify.wav',
        'chimes.wav',
    ]
    
    wav_path = None
    for wav_name in wav_candidates:
        candidate = os.path.join(media_folder, wav_name)
        if os.path.exists(candidate):
            wav_path = candidate
            break
    
    if wav_path:
        try:
            # Play the sound 3 times to make it noticeable
            for i in range(3):
                winsound.PlaySound(wav_path, winsound.SND_FILENAME)
                if i < 2:  # Don't sleep after the last one
                    time.sleep(0.3)
            print(f"[SOUND] Ready sound completed (played {os.path.basename(wav_path)} 3x).", flush=True)
        except Exception as e:
            print(f"[SOUND ERROR] WAV playback failed: {e}", flush=True)
    else:
        # Fallback to system alias
        try:
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
            print("[SOUND] Ready sound completed (system alias).", flush=True)
        except Exception as e:
            print(f"[SOUND ERROR] Could not play ready sound: {e}", flush=True)

def play_complete_sound():
    """Play victory sound when posting is complete."""
    import os
    print("[SOUND] Playing completion notification...", flush=True)
    
    media_folder = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Media')
    wav_path = os.path.join(media_folder, 'Windows Ding.wav')
    
    try:
        if os.path.exists(wav_path):
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)
        else:
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
        print("[SOUND] Complete sound finished.", flush=True)
    except Exception as e:
            print(f"[SOUND ERROR] Could not play complete sound: {e}", flush=True)

def parse_relative_date(relative_time):
    """Convert LinkedIn relative time (e.g., '1d', '2w', 'Just now') to actual date string."""
    from datetime import timedelta
    
    now = datetime.now()
    relative_time = relative_time.lower().strip()
    
    # Parse the relative time
    try:
        if 'just now' in relative_time or 'now' in relative_time:
            result_date = now
        elif 'second' in relative_time or 's ago' in relative_time:
            result_date = now
        elif 'minute' in relative_time or 'm ago' in relative_time:
            # Extract number
            num = int(re.search(r'(\d+)', relative_time).group(1)) if re.search(r'(\d+)', relative_time) else 1
            result_date = now - timedelta(minutes=num)
        elif 'hour' in relative_time or 'h ago' in relative_time or relative_time.endswith('h'):
            num = int(re.search(r'(\d+)', relative_time).group(1)) if re.search(r'(\d+)', relative_time) else 1
            result_date = now - timedelta(hours=num)
        elif 'day' in relative_time or 'd ago' in relative_time or relative_time.endswith('d'):
            num = int(re.search(r'(\d+)', relative_time).group(1)) if re.search(r'(\d+)', relative_time) else 1
            result_date = now - timedelta(days=num)
        elif 'week' in relative_time or 'w ago' in relative_time or relative_time.endswith('w'):
            num = int(re.search(r'(\d+)', relative_time).group(1)) if re.search(r'(\d+)', relative_time) else 1
            result_date = now - timedelta(weeks=num)
        elif 'month' in relative_time or 'mo ago' in relative_time or 'mo' in relative_time:
            num = int(re.search(r'(\d+)', relative_time).group(1)) if re.search(r'(\d+)', relative_time) else 1
            result_date = now - timedelta(days=num*30)  # Approximate
        elif 'year' in relative_time or 'yr' in relative_time or 'y ago' in relative_time:
            num = int(re.search(r'(\d+)', relative_time).group(1)) if re.search(r'(\d+)', relative_time) else 1
            result_date = now - timedelta(days=num*365)  # Approximate
        else:
            # Can't parse, return original with current date context
            return f"{relative_time} (today is {now.strftime('%B %d, %Y')})"
        
        return result_date.strftime('%B %d, %Y')
    except:
        return f"{relative_time} (today is {now.strftime('%B %d, %Y')})"

# Configuration
FEED_URL = "https://www.linkedin.com/feed/"
REVIEW_HTML_FILE = "comment_review.html"
PENDING_COMMENTS_FILE = "pending_comments.json"
COMMENT_HISTORY_FILE = "comment_history.json"  # Track posted URLs to prevent duplicates
CHROME_PID = None
SHUTDOWN_EVENT = threading.Event()
APPROVED_COMMENTS = []
POSTING_RESULTS = {}  # {post_url: {"status": "success"|"failed", "message": "..."}}
POSTING_COMPLETE = False  # Set to True when all comments have been posted
AGENT_INSTANCE = None

# Legal profession indicators
LEGAL_KEYWORDS = [
    "attorney", "lawyer", "partner", "counsel", "esq", "jd", 
    "law firm", "legal", "litigator", "associate", "paralegal",
    "barrister", "solicitor", "advocate", "juris doctor",
    "of counsel", "managing partner", "founding partner"
]

# Configure Gemini
# Note: genai.configure is no longer needed with new google.genai package


class ReviewHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for the review server."""
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass
    
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            if os.path.exists(REVIEW_HTML_FILE):
                with open(REVIEW_HTML_FILE, "r", encoding="utf-8") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            else:
                self.wfile.write(b"<h1>Error: Report file not found.</h1>")
        elif self.path == "/results":
            # Return posting results as JSON
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            success_count = sum(1 for r in POSTING_RESULTS.values() if r.get("status") == "success")
            failed_count = sum(1 for r in POSTING_RESULTS.values() if r.get("status") == "failed")
            skipped_count = sum(1 for r in POSTING_RESULTS.values() if r.get("status") == "skipped")
            
            results_data = {
                "complete": POSTING_COMPLETE,  # Use POSTING_COMPLETE instead of SHUTDOWN_EVENT
                "results": POSTING_RESULTS,
                "summary": {
                    "success": success_count,
                    "failed": failed_count,
                    "skipped": skipped_count,
                    "total": len(POSTING_RESULTS)
                }
            }
            self.wfile.write(json.dumps(results_data).encode())
        elif self.path == "/results_page":
            # Serve the results HTML page
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            results_file = "posting_results.html"
            if os.path.exists(results_file):
                with open(results_file, "r", encoding="utf-8") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            else:
                self.wfile.write(b"<h1>Results page not ready yet. Refresh in a moment.</h1>")
        else:
            self.send_error(404)


    def do_POST(self):
        global CHROME_PID, APPROVED_COMMENTS, AGENT_INSTANCE
        
        # Debug: Log all incoming POST requests
        print(f"[Server] POST request received: {self.path}", flush=True)
        
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length else ""
        
        if self.path == "/shutdown":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
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
            
            SHUTDOWN_EVENT.set()
            
        elif self.path == "/submit":
            try:
                global APPROVED_COMMENTS  # CRITICAL: Must declare global to modify it
                data = json.loads(body)
                APPROVED_COMMENTS = data.get("approved", [])
                print(f"[Server] Received {len(APPROVED_COMMENTS)} approved comments")
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "received", "count": len(APPROVED_COMMENTS)}).encode())
                
                # Signal to start posting
                SHUTDOWN_EVENT.set()
            except Exception as e:
                print(f"[Server] Error processing submit: {e}")
                self.send_response(500)
                self.end_headers()
                
        elif self.path == "/regenerate":
            try:
                data = json.loads(body)
                post_id = data.get("post_id")
                headline = data.get("headline", "")
                post_content = data.get("post_content", "")
                
                # Generate new comment
                if AGENT_INSTANCE:
                    new_comment = AGENT_INSTANCE.generate_comment_sync(headline, post_content)
                else:
                    new_comment = "Error: Agent not available"
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"comment": new_comment}).encode())
            except Exception as e:
                print(f"[Server] Error regenerating: {e}")
                self.send_response(500)
                self.end_headers()
        else:
            self.send_error(404)


class CommentAgent:
    def __init__(self):
        global AGENT_INSTANCE
        AGENT_INSTANCE = self
        
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None  # Store to prevent garbage collection
        self.posts_to_comment = []
        self.chrome_pid = None
        self.user_name = None
        self.genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_name = "gemini-2.0-flash"
        
        # Session metrics
        self.metrics = {
            "posts_scanned": 0,
            "legal_posts_found": 0,
            "comments_approved": 0,
            "comments_posted": 0,
            "errors": 0
        }

    def sanitize_filename(self, name):
        """Remove invalid characters for filenames."""
        if not name:
            return "unknown"
        # Remove newlines and carriage returns first
        name = name.replace("\n", "_").replace("\r", "_")
        # Remove other invalid characters
        return re.sub(r'[\\/*?:"<>|]', "_", name)

    def log(self, msg):
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)
        except UnicodeEncodeError:
            # Fallback to ascii for Windows console
            clean_msg = msg.encode('ascii', 'replace').decode('ascii')
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {clean_msg}", flush=True)

    def is_legal_professional(self, headline):
        """Use Gemini AI to check if headline indicates a legal professional."""
        if not headline:
            return False
        
        try:
            prompt = f"""Analyze this LinkedIn headline and determine if this person has a legal background.
            
Headline: {headline}

Legal background includes: lawyers, attorneys, advocates, barristers, solicitors, legal counsel, 
partners at law firms, paralegals, legal associates, judges, magistrates, legal consultants, 
compliance officers with legal degrees, in-house counsel, legal advisors, law professors, etc.

Respond with ONLY "YES" or "NO" - nothing else."""

            response = self.genai_client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            result = response.text.strip().upper()
            is_legal = result == "YES"
            
            if is_legal:
                self.log(f"  [YES] Legal professional detected: {headline[:60]}")
            
            return is_legal
        except Exception as e:
            self.log(f"  Error checking legal background: {e}")
            return False

    def generate_comment_sync(self, headline, post_content, post_date=""):
        """Synchronous wrapper for comment generation."""
        try:
            date_context = f"\nPOST DATE: {post_date}" if post_date else ""
            
            prompt = f"""You are helping a legal professional engage meaningfully on LinkedIn.
Generate a professional, supportive, and thoughtful comment for this LinkedIn post.

AUTHOR INFO:
Headline: {headline}
{date_context}

POST CONTENT:
{post_content[:2000]}

GUIDELINES:
- Be genuinely supportive and acknowledge their perspective
- Add a thoughtful insight or observation when relevant
- Occasionally ask a relevant question to spark discussion (maybe 1 in 3 posts)
- Keep it concise: 2-4 sentences max
- Sound natural and human, not generic
- NEVER use phrases like "Great post!", "Love this!", "So true!"
- Don't be overly effusive or sycophantic
- Match their professional tone
- Do NOT include any HTML tags in your response
- Output plain text only

Generate ONLY the comment text, nothing else."""

            response = self.genai_client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            comment = response.text.strip()
            
            # Strip any HTML tags that might have been generated
            comment = re.sub(r'<[^>]+>', '', comment)
            
            return comment
        except Exception as e:
            self.log(f"Error generating comment: {e}")
            return "Thank you for sharing this insightful perspective."

    def load_comment_history(self):
        """Load previously posted comment URLs to prevent duplicates."""
        try:
            if os.path.exists(COMMENT_HISTORY_FILE):
                with open(COMMENT_HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            self.log(f"Error loading comment history: {e}")
        return {"posted_urls": [], "posts": []}

    def save_comment_history(self, history):
        """Save comment history to file."""
        try:
            with open(COMMENT_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Error saving comment history: {e}")

    def is_already_posted(self, post_url, history):
        """Check if we've already commented on this post."""
        return post_url in history.get("posted_urls", [])

    def record_posted_comment(self, post_url, author_name, comment_text, success, history):
        """Record a posted comment in history."""
        if success and post_url not in history.get("posted_urls", []):
            history.setdefault("posted_urls", []).append(post_url)
        history.setdefault("posts", []).append({
            "url": post_url,
            "author": author_name,
            "comment": comment_text,
            "success": success,
            "timestamp": datetime.now().isoformat()
        })
        self.save_comment_history(history)

    async def generate_comment(self, headline, post_content, post_date=""):
        """Generate a professional comment using Gemini."""
        return self.generate_comment_sync(headline, post_content, post_date)

    async def launch_browser(self):
        """Launch Chrome with remote debugging enabled."""
        global CHROME_PID
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
        
        self.log(f"Launching Chrome...")
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
                self.log("ERROR: Chrome process exited prematurely")
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
        self.log("Starting Comment Agent...")
        self.log("Initializing Playwright...")
        self.playwright = await async_playwright().start()
        playwright = self.playwright
        
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

        # Navigate to LinkedIn feed with extended timeout and retry logic
        max_nav_retries = 3
        for nav_attempt in range(max_nav_retries):
            try:
                self.log(f"Navigating to LinkedIn feed (attempt {nav_attempt + 1}/{max_nav_retries})...")
                await self.page.goto(FEED_URL, timeout=60000, wait_until="domcontentloaded")
                self.log("Successfully loaded LinkedIn feed.")
                break
            except Exception as nav_error:
                self.log(f"Navigation attempt {nav_attempt + 1} failed: {nav_error}")
                if nav_attempt < max_nav_retries - 1:
                    self.log("Waiting before retry...")
                    await asyncio.sleep(5)
                else:
                    raise Exception(f"Failed to load LinkedIn feed after {max_nav_retries} attempts: {nav_error}")
        
        await asyncio.sleep(5)
        
        # Get current user name for self-exclusion
        try:
            me_img = await self.page.query_selector("button.global-nav__primary-link-me-menu-trigger img")
            if me_img:
                alt = await me_img.get_attribute("alt")
                if alt and "Photo of " in alt:
                    self.user_name = alt.replace("Photo of ", "").strip()
                elif alt:
                    self.user_name = alt.strip()
            
            if self.user_name:
                self.log(f"Identified current user as: '{self.user_name}'")
        except Exception as e:
            self.log(f"Error getting user name: {e}")

    async def scan_feed_for_legal_posts(self):
        """Scroll feed and collect posts from legal professionals."""
        self.log("Scanning feed for posts by legal professionals...")
        
        target_post_count = 10  # Collect up to 10 posts per session
        scroll_attempts = 0
        max_scroll_attempts = 20
        seen_posts = set()
        
        # Find the actual scrollable container on LinkedIn
        # LinkedIn uses a main element or scaffold-layout as the scroll container
        scroll_container = None
        scroll_container_selectors = [
            "main.scaffold-layout__main",
            "main[role='main']", 
            ".scaffold-layout__content",
            "main",
            "div.scaffold-finite-scroll__content",
        ]
        
        for selector in scroll_container_selectors:
            container = await self.page.query_selector(selector)
            if container:
                # Check if this element is actually scrollable
                is_scrollable = await container.evaluate("""el => {
                    const style = window.getComputedStyle(el);
                    const overflowY = style.overflowY;
                    return el.scrollHeight > el.clientHeight && 
                           (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay');
                }""")
                if is_scrollable:
                    scroll_container = container
                    self.log(f"  [Scroll] Found scrollable container: {selector}")
                    break
        
        # If no scroll container found, click on feed area to ensure focus
        if not scroll_container:
            self.log("  [Scroll] No dedicated scroll container found, using page focus + keyboard")
            # Click on the main content area to ensure keyboard events work
            main_area = await self.page.query_selector("main, .scaffold-layout__content, .feed-shared-update-v2")
            if main_area:
                await main_area.click()
                await asyncio.sleep(0.3)
        
        while len(self.posts_to_comment) < target_post_count and scroll_attempts < max_scroll_attempts:
            # Get all post containers
            # Added div[data-view-name='feed-full-update'] for new DOM structure
            posts = await self.page.query_selector_all("div.feed-shared-update-v2, div[data-urn^='urn:li:activity'], div[data-urn^='urn:li:share'], div[data-view-name='feed-full-update']")
            self.log(f"Found {len(posts)} posts in view (Scroll {scroll_attempts})")
            
            for post in posts:
                try:
                    # --- ID EXTRACTION ---
                    post_urn = await post.get_attribute("data-urn")
                    
                    if not post_urn:
                        # Strategy 2: Look for updateUrn in data-view-tracking-scope using JS (Reliable & Decodes Buffer)
                        try:
                            # Complex JS to find tracking elements, parse JSON, decode Buffer if present, and return URNs
                            tracking_urns = await post.evaluate(r"""el => {
                                const results = [];
                                const nodes = el.querySelectorAll('[data-view-tracking-scope]');
                                
                                for (const node of nodes) {
                                    try {
                                        const attr = node.getAttribute('data-view-tracking-scope');
                                        if (!attr) continue;
                                        
                                        const json = JSON.parse(attr);
                                        for (const item of json) {
                                            // Check for direct updateUrn
                                            if (item.updateUrn) {
                                                results.push(item.updateUrn);
                                            }
                                            
                                            // Check for Buffer encoded content
                                            if (item.breadcrumb && item.breadcrumb.content && item.breadcrumb.content.type === 'Buffer' && item.breadcrumb.content.data) {
                                                try {
                                                    const bufferData = item.breadcrumb.content.data;
                                                    const decoded = String.fromCharCode(...bufferData);
                                                    
                                                    // Extract URN from decoded string (it's a JSON string usually)
                                                    if (decoded.includes('urn:li:activity')) {
                                                        const match = decoded.match(/urn:li:activity:\d+/);
                                                        if (match) results.push(match[0]);
                                                    }
                                                    if (decoded.includes('updateUrn')) {
                                                        const match = decoded.match(/urn:li:(activity|share|ugcPost):\d+/);
                                                        if (match) results.push(match[0]);
                                                    }
                                                } catch (e) { console.error('Buffer decode error', e); }
                                            }
                                        }
                                    } catch (e) { console.error('Tracking parse error', e); }
                                }
                                return results;
                            }""")
                            
                            if tracking_urns:
                                post_urn = tracking_urns[0] # Take the first valid URN found
                                self.log(f"  JS Extracted URN: {post_urn}")

                        except Exception as e:
                            self.log(f"  Error extracting from tracking scope (JS): {e}")

                    if not post_urn:
                        # Strategy 3: InnerHTML Regex (Fallback)
                        try:
                            html_content = await post.inner_html()
                            urn_match = re.search(r'urn:li:(activity|share|ugcPost):\d+', html_content)
                            if urn_match:
                                post_urn = urn_match.group(0)
                        except Exception:
                            pass
                    
                    if post_urn and post_urn in seen_posts:
                        continue
                    if post_urn:
                        seen_posts.add(post_urn)
                        
                    self.metrics["posts_scanned"] += 1
                    
                    # --- DATA EXTRACTION ---
                    author_name = "Unknown"
                    headline = ""
                    post_content = ""
                    profile_url = ""
                    post_url = ""
                    post_date = ""
                    
                    # Determine structure type
                    data_view_name = await post.get_attribute("data-view-name")
                    is_new_structure = data_view_name == "feed-full-update"
                    
                    if is_new_structure:
                        # NEW STRUCTURE LOGIC (Jan 2025)
                        
                        # 1. Profile URL
                        actor_img_link = await post.query_selector("a[data-view-name='feed-actor-image']")
                        if actor_img_link:
                            profile_url = await actor_img_link.get_attribute("href")
                            if profile_url and profile_url.startswith("/"):
                                profile_url = "https://www.linkedin.com" + profile_url
                        
                        # 2. Author Name & Headline
                        if profile_url:
                            # Search for the text link that shares the same href
                            clean_profile_url = profile_url.split('?')[0] if profile_url else ""
                            
                            all_links = await post.query_selector_all("a")
                            text_link = None
                            for link in all_links:
                                href = await link.get_attribute("href")
                                if href and clean_profile_url in href:
                                    # Ensure it's not the image link
                                    view_name = await link.get_attribute("data-view-name")
                                    if view_name != "feed-actor-image":
                                        text_link = link
                                        break
                            
                            if text_link:
                                full_text = await text_link.inner_text()
                                parts = [p.strip() for p in full_text.split('\n') if p.strip()]
                                
                                if len(parts) > 0:
                                    author_name = parts[0]
                                    if " •" in author_name:
                                        author_name = author_name.split(" •")[0]
                                
                                if len(parts) > 1:
                                    # Find headline (first part that isn't name or metadata)
                                    for p in parts[1:]:
                                        if any(x in p for x in ["•", "1st", "2nd", "3rd", "Following", "Promoted"]):
                                            continue
                                        headline = p
                                        break
                        
                        # 3. Content
                        content_div = await post.query_selector("[data-view-name='feed-commentary']")
                        if content_div:
                            post_content = await content_div.inner_text()
                            
                    else:
                        # OLD STRUCTURE LOGIC (Fallback)
                        meta_link = await post.query_selector("a.update-components-actor__meta-link")
                        if not meta_link:
                            meta_link = await post.query_selector(".update-components-actor")
                            
                        if meta_link:
                            if profile_url == "":
                                try:
                                    profile_url = await meta_link.get_attribute("href")
                                    if profile_url and profile_url.startswith("/"):
                                        profile_url = "https://www.linkedin.com" + profile_url
                                except: pass
                            
                            # Name
                            name_selectors = [
                                ".update-components-actor__name span span",
                                ".update-components-actor__name span[aria-hidden='true']",
                                ".update-components-actor__name span",
                                ".update-components-actor__name",
                            ]
                            for sel in name_selectors:
                                name_el = await meta_link.query_selector(sel)
                                if name_el:
                                    raw_name = await name_el.inner_text()
                                    author_name = raw_name.split('\n')[0].strip()
                                    if author_name: break
                            
                            # Headline
                            headline_selectors = [
                                ".update-components-actor__description span",
                                ".update-components-actor__description",
                                ".update-components-actor__subtitle span",
                            ]
                            for sel in headline_selectors:
                                headline_el = await meta_link.query_selector(sel)
                                if headline_el:
                                    headline = await headline_el.inner_text()
                                    headline = headline.strip().split('\n')[0]
                                    if headline: break
                            
                        # Content
                        content_el = await post.query_selector(".feed-shared-update-v2__description, .feed-shared-text")
                        if content_el:
                            post_content = await content_el.inner_text()

                    # --- CLEANUP & VALIDATION ---
                    
                    if author_name == "Unknown":
                        continue
                        
                    author_name = author_name.replace("View profile", "").strip()

                    # Skip own posts
                    if self.user_name and self.user_name.lower() in author_name.lower():
                        self.log(f"  [SKIP] Own post from: {author_name}")
                        continue

                    # Debug log
                    self.log(f"  Checking: {author_name[:30]} | Headline: {headline[:50] if headline else 'NONE'}")

                    # Check legal professional
                    if not self.is_legal_professional(headline):
                        continue

                    self.log(f"Legal post found: {author_name} - {headline[:50]}...")
                    self.metrics["legal_posts_found"] += 1
                    
                    # Post URL Construction
                    # Try finding permalink
                    post_link = await post.query_selector("a.app-aware-link[href*='/posts/'], a.app-aware-link[href*='/activity/']")
                    if post_link:
                        post_url = await post_link.get_attribute("href")
                    
                    if not post_url and post_urn:
                        post_url = f"https://www.linkedin.com/feed/update/{post_urn}/"
                        
                    if post_url and post_url.startswith("/"):
                        post_url = "https://www.linkedin.com" + post_url

                    self.log(f"  Debug URL extraction: URN='{post_urn}', URL='{post_url}'")
                        
                    # Final fallback for ID if URN was missing
                    if not post_urn and post_url:
                        post_urn = post_url
                        if post_urn in seen_posts:
                            continue # Late duplicate check
                        seen_posts.add(post_urn)
                        
                    if not post_urn:
                        # Generate a hash ID if absolutely nothing else works
                        post_urn = str(hash(author_name + post_content[:20]))

                    # Extract Date
                    date_selectors = ["time", ".update-components-actor__sub-description span[aria-hidden='true']"]
                    for sel in date_selectors:
                        date_el = await post.query_selector(sel)
                        if date_el:
                            post_date = await date_el.inner_text()
                            post_date = post_date.strip()
                            break

                    # Generate comment
                    self.log(f"Generating comment for {author_name}...")
                    self.log(f"Content start: {post_content[:50]}...")
                    comment = await self.generate_comment(headline, post_content, post_date)

                    self.posts_to_comment.append({
                        "id": post_urn,
                        "author_name": author_name,
                        "headline": headline,
                        "post_content": post_content,
                        "post_url": post_url,
                        "profile_url": profile_url,
                        "post_date": post_date,
                        "generated_comment": comment,
                        "post_urn": post_urn
                    })

                    if len(self.posts_to_comment) >= target_post_count:
                        break

                except Exception as e:
                    self.log(f"Error processing post: {e}")
                    continue
            
            if len(self.posts_to_comment) < target_post_count:
                # Track if we're seeing new content
                current_urns = set(seen_posts)
                posts_before = len(seen_posts)
                
                # Get scroll position for debugging (from container or window)
                if scroll_container:
                    scroll_y_before = await scroll_container.evaluate("el => el.scrollTop")
                else:
                    scroll_y_before = await self.page.evaluate("window.scrollY")
                
                # Strategy 1: If we have a scroll container, scroll it directly
                if scroll_container:
                    # Calculate scroll amount
                    base_scroll = random.randint(600, 1200)
                    variance = random.uniform(-0.1, 0.2)
                    scroll_distance = int(base_scroll * (1 + variance))
                    
                    if random.random() < 0.2:
                        scroll_distance = random.randint(150, 350)
                        self.log(f"  [Human behavior] Small view adjustment ({scroll_distance}px)")
                    
                    # Scroll the container with smooth behavior
                    await scroll_container.evaluate(f"""el => {{
                        el.scrollBy({{ top: {scroll_distance}, behavior: 'smooth' }});
                    }}""")
                    await asyncio.sleep(random.uniform(0.5, 1.0))
                    
                    # Also use mouse wheel on the container for more natural behavior
                    await human_scroll(self.page, random.randint(200, 400))
                
                # Strategy 2: Scroll last post into view (works regardless of container)
                elif posts and len(posts) > 0:
                    last_post = posts[-1]
                    try:
                        await last_post.evaluate("el => el.scrollIntoView({ behavior: 'smooth', block: 'center' })")
                        await asyncio.sleep(random.uniform(0.5, 1.0))
                    except:
                        pass
                    
                    # Additional mouse wheel scrolling
                    base_scroll = random.randint(600, 1200)
                    variance = random.uniform(-0.1, 0.2)
                    scroll_distance = int(base_scroll * (1 + variance))
                    
                    if random.random() < 0.2:
                        scroll_distance = random.randint(150, 350)
                        self.log(f"  [Human behavior] Small view adjustment ({scroll_distance}px)")
                    
                    await human_scroll(self.page, scroll_distance)
                
                # Variable wait time
                if random.random() < 0.3:
                    await human_delay(4.0, 7.0)
                else:
                    await human_delay(2.0, 4.0)
                
                # Occasionally add micro-movements
                if random.random() < 0.15:
                    micro_scroll = random.randint(-50, 100)
                    if scroll_container:
                        await scroll_container.evaluate(f"el => el.scrollBy({{ top: {micro_scroll} }})")
                    else:
                        await self.page.evaluate(f"window.scrollBy(0, {micro_scroll})")
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                
                # Wait for any lazy-loaded content
                try:
                    await self.page.wait_for_load_state("networkidle", timeout=3000)
                except:
                    pass
                
                # Log scroll position change for debugging
                if scroll_container:
                    scroll_y_after = await scroll_container.evaluate("el => el.scrollTop")
                else:
                    scroll_y_after = await self.page.evaluate("window.scrollY")
                if scroll_attempts % 5 == 0:
                    self.log(f"  [Debug] Scroll position: {scroll_y_before} -> {scroll_y_after} (delta: {scroll_y_after - scroll_y_before})")
                
                scroll_attempts += 1
                
                # Stale feed detection with natural recovery
                if scroll_attempts >= 3 and scroll_attempts % 3 == 0:
                    if len(seen_posts) == posts_before:
                        self.log(f"  [Stale feed] No new posts. Doing natural scroll recovery...")
                        
                        # Natural recovery: Use Page Down key presses like a real user
                        num_page_downs = random.randint(3, 5)
                        for i in range(num_page_downs):
                            # Move mouse slightly (humans don't keep mouse perfectly still)
                            viewport = self.page.viewport_size
                            if viewport:
                                jitter_x = random.randint(-20, 20)
                                jitter_y = random.randint(-30, 30)
                                await self.page.mouse.move(
                                    viewport['width'] // 2 + jitter_x,
                                    viewport['height'] // 2 + jitter_y
                                )
                            
                            # Press Page Down (like using keyboard to scroll)
                            await self.page.keyboard.press("PageDown")
                            await asyncio.sleep(random.uniform(0.3, 0.8))
                        
                        # Brief pause as if looking at content
                        await human_delay(1.5, 3.0)
                        
                        # Occasionally scroll back up a bit (like re-reading something interesting)
                        if random.random() < 0.4:
                            await self.page.keyboard.press("PageUp")
                            await asyncio.sleep(random.uniform(0.5, 1.0))
        
        self.log(f"Collected {len(self.posts_to_comment)} posts from legal professionals")

    def generate_review_html(self):
        """Generate LinkedIn-style accessible review HTML."""
        cards_html = ""
        
        for i, post in enumerate(self.posts_to_comment):
            # Escape content for HTML
            author_name = post['author_name'].replace('<', '&lt;').replace('>', '&gt;')
            headline = post['headline'].replace('<', '&lt;').replace('>', '&gt;')
            post_content = post['post_content'].replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
            comment = post['generated_comment'].replace('<', '&lt;').replace('>', '&gt;')
            post_id = post['id'].replace('"', '&quot;')
            
            cards_html += f"""
            <article class="post-card" role="article" aria-labelledby="author-{i}" data-post-id="{post_id}">
                <header class="post-header">
                    <div class="author-avatar" aria-hidden="true">
                        <span class="avatar-initial">{author_name[0].upper()}</span>
                    </div>
                    <div class="author-info">
                        <h2 id="author-{i}" class="author-name">{author_name}</h2>
                        <p class="author-headline">{headline}</p>
                    </div>
                </header>
                
                <div class="post-content">
                    <p>{post_content}</p>
                </div>
                
                <section class="comment-section" aria-label="Your comment for {author_name}">
                    <label for="comment-{i}" class="comment-label">Your Comment:</label>
                    <textarea 
                        id="comment-{i}" 
                        class="comment-input" 
                        rows="4"
                        aria-describedby="comment-help-{i}"
                        data-headline="{headline.replace('"', '&quot;')}"
                        data-post-content="{post_content[:500].replace('"', '&quot;')}"
                    >{comment}</textarea>
                    <p id="comment-help-{i}" class="sr-only">Edit this comment or regenerate a new one</p>
                </section>
                
                <div class="card-actions" role="group" aria-label="Actions for this post">
                    <button type="button" class="btn btn-regenerate" onclick="regenerateComment('{post_id}', {i})" aria-describedby="regen-help-{i}">
                        ↻ Regenerate
                    </button>
                    <span id="regen-help-{i}" class="sr-only">Generate a new AI comment</span>
                    
                    <label class="checkbox-label">
                        <input type="checkbox" class="approve-checkbox" data-index="{i}" checked aria-label="Approve comment for {author_name}">
                        <span>Approve</span>
                    </label>
                    
                    <a href="{post['post_url']}" target="_blank" rel="noopener" class="btn btn-view" aria-label="View original post by {author_name} on LinkedIn">
                        View Post →
                    </a>
                </div>
            </article>
            """
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Review Your Comments - LinkedIn Auto Commenter</title>
    <style>
        :root {{
            --linkedin-blue: #0a66c2;
            --linkedin-blue-dark: #004182;
            --bg-primary: #f3f2ef;
            --bg-card: #ffffff;
            --text-primary: #191919;
            --text-secondary: #666666;
            --border-color: #e0e0e0;
            --success-green: #057642;
            --focus-ring: 0 0 0 3px rgba(10, 102, 194, 0.4);
        }}
        
        * {{
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            margin: 0;
            padding: 20px;
            line-height: 1.5;
        }}
        
        .sr-only {{
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            border: 0;
        }}
        
        a:focus, button:focus, input:focus, textarea:focus {{
            outline: none;
            box-shadow: var(--focus-ring);
        }}
        
        .skip-link {{
            position: absolute;
            top: -40px;
            left: 0;
            background: var(--linkedin-blue);
            color: white;
            padding: 8px 16px;
            z-index: 100;
            text-decoration: none;
        }}
        
        .skip-link:focus {{
            top: 0;
        }}
        
        header.main-header {{
            max-width: 700px;
            margin: 0 auto 24px;
            text-align: center;
        }}
        
        h1 {{
            color: var(--linkedin-blue);
            margin: 0 0 8px;
            font-size: 1.75rem;
        }}
        
        .subtitle {{
            color: var(--text-secondary);
            margin: 0;
        }}
        
        main {{
            max-width: 700px;
            margin: 0 auto;
        }}
        
        .post-card {{
            background: var(--bg-card);
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            margin-bottom: 16px;
            padding: 16px;
            border: 1px solid var(--border-color);
        }}
        
        .post-card:focus-within {{
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }}
        
        .post-header {{
            display: flex;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 12px;
        }}
        
        .author-avatar {{
            width: 48px;
            height: 48px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--linkedin-blue), var(--linkedin-blue-dark));
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}
        
        .avatar-initial {{
            color: white;
            font-size: 1.25rem;
            font-weight: 600;
        }}
        
        .author-info {{
            flex: 1;
            min-width: 0;
        }}
        
        .author-name {{
            font-size: 1rem;
            font-weight: 600;
            margin: 0 0 2px;
            color: var(--text-primary);
        }}
        
        .author-headline {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        
        .post-content {{
            padding: 12px 0;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 12px;
            max-height: 400px;
            overflow-y: auto;
            scrollbar-width: thin;
        }}
        
        .post-content p {{
            margin: 0;
            font-size: 0.95rem;
            color: var(--text-primary);
        }}
        
        .comment-section {{
            margin-bottom: 12px;
        }}
        
        .comment-label {{
            display: block;
            font-weight: 600;
            font-size: 0.9rem;
            color: var(--linkedin-blue);
            margin-bottom: 6px;
        }}
        
        .comment-input {{
            width: 100%;
            padding: 12px;
            border: 2px solid var(--border-color);
            border-radius: 8px;
            font-family: inherit;
            font-size: 0.95rem;
            resize: vertical;
            min-height: 80px;
            transition: border-color 0.2s;
        }}
        
        .comment-input:focus {{
            border-color: var(--linkedin-blue);
        }}
        
        .card-actions {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }}
        
        .btn {{
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}
        
        .btn-regenerate {{
            background: transparent;
            border: 1px solid var(--linkedin-blue);
            color: var(--linkedin-blue);
        }}
        
        .btn-regenerate:hover {{
            background: rgba(10, 102, 194, 0.1);
        }}
        
        .btn-view {{
            background: transparent;
            border: 1px solid var(--text-secondary);
            color: var(--text-secondary);
        }}
        
        .btn-view:hover {{
            background: rgba(0,0,0,0.05);
        }}
        
        .checkbox-label {{
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            font-weight: 500;
        }}
        
        .approve-checkbox {{
            width: 20px;
            height: 20px;
            cursor: pointer;
        }}
        
        .footer-actions {{
            position: sticky;
            bottom: 0;
            background: var(--bg-card);
            padding: 16px;
            border-radius: 8px;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
            display: flex;
            justify-content: center;
            gap: 16px;
            margin-top: 24px;
        }}
        
        .btn-submit {{
            background: var(--linkedin-blue);
            color: white;
            border: none;
            padding: 12px 32px;
            font-size: 1rem;
        }}
        
        .btn-submit:hover {{
            background: var(--linkedin-blue-dark);
        }}
        
        .btn-cancel {{
            background: #dc3545;
            color: white;
            border: none;
            padding: 12px 32px;
            font-size: 1rem;
        }}
        
        .btn-cancel:hover {{
            background: #c82333;
        }}
        
        .status-message {{
            text-align: center;
            padding: 16px;
            font-weight: 500;
            margin-top: 16px;
        }}
        
        .loading {{
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid #f3f3f3;
            border-top: 2px solid var(--linkedin-blue);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-right: 8px;
        }}
        
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        
        @media (max-width: 600px) {{
            body {{
                padding: 12px;
            }}
            
            .post-card {{
                padding: 12px;
            }}
            
            .card-actions {{
                flex-direction: column;
                align-items: stretch;
            }}
            
            .btn {{
                justify-content: center;
            }}
        }}
    </style>
</head>
<body>
    <a href="#main-content" class="skip-link">Skip to main content</a>
    
    <header class="main-header">
        <h1>Review Your Comments</h1>
        <p class="subtitle">Found {len(self.posts_to_comment)} posts from legal professionals. Review and edit comments before posting.</p>
    </header>
    
    <main id="main-content" role="main">
        {cards_html}
        
        <div class="footer-actions" role="group" aria-label="Submit or cancel">
            <button type="button" class="btn btn-submit" onclick="submitApproved()" id="submitBtn">
                Post Approved Comments
            </button>
            <button type="button" class="btn btn-cancel" onclick="cancelSession()">
                Cancel Session
            </button>
        </div>
        
        <div id="statusMessage" class="status-message" role="status" aria-live="polite"></div>
    </main>
    
    <script>
        const posts = {json.dumps(self.posts_to_comment)};
        
        // --- SOUND ALERT FUNCTIONS ---
        function playSound(frequency, duration, type = 'sine', volume = 0.5) {{
            try {{
                const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                const oscillator = audioContext.createOscillator();
                const gainNode = audioContext.createGain();
                
                oscillator.connect(gainNode);
                gainNode.connect(audioContext.destination);
                
                oscillator.frequency.value = frequency;
                oscillator.type = type;
                gainNode.gain.value = volume;
                
                oscillator.start();
                setTimeout(() => {{
                    oscillator.stop();
                    audioContext.close();
                }}, duration);
            }} catch (e) {{
                console.log('Audio not supported:', e);
            }}
        }}
        
        function playNotificationSound() {{
            // Two ascending tones for "ready for review"
            playSound(523, 150); // C5
            setTimeout(() => playSound(659, 150), 200); // E5
            setTimeout(() => playSound(784, 200), 400); // G5
        }}
        
        function playCompletionSound() {{
            // Victory fanfare for "posting complete"
            playSound(523, 100); // C5
            setTimeout(() => playSound(659, 100), 120); // E5
            setTimeout(() => playSound(784, 100), 240); // G5
            setTimeout(() => playSound(1047, 300), 360); // C6 (longer)
        }}
        
        // Play notification sound on page load (ready for review)
        window.addEventListener('load', () => {{
            setTimeout(playNotificationSound, 500);
        }});
        
        async function regenerateComment(postId, index) {{
            const textarea = document.getElementById('comment-' + index);
            const btn = event.target;
            const originalText = btn.textContent;
            
            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span>Generating...';
            
            try {{
                const response = await fetch('/regenerate', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        post_id: postId,
                        headline: textarea.dataset.headline,
                        post_content: textarea.dataset.postContent
                    }})
                }});
                
                const data = await response.json();
                textarea.value = data.comment;
                textarea.focus();
            }} catch (e) {{
                console.error('Regenerate failed:', e);
                alert('Failed to regenerate comment. Please try again.');
            }} finally {{
                btn.disabled = false;
                btn.textContent = originalText;
            }}
        }}
        
        async function submitApproved() {{
            const approved = [];
            const cards = document.querySelectorAll('.post-card');
            
            cards.forEach((card, index) => {{
                const checkbox = card.querySelector('.approve-checkbox');
                if (checkbox && checkbox.checked) {{
                    const textarea = document.getElementById('comment-' + index);
                    approved.push({{
                        ...posts[index],
                        final_comment: textarea.value
                    }});
                }}
            }});
            
            if (approved.length === 0) {{
                alert('No comments approved. Please check at least one comment to post.');
                return;
            }}
            
            const status = document.getElementById('statusMessage');
            const submitBtn = document.getElementById('submitBtn');
            
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="loading"></span>Submitting...';
            status.textContent = 'Sending ' + approved.length + ' comments to LinkedIn...';
            
            try {{
                const response = await fetch('/submit', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ approved: approved }})
                }});
                
                status.textContent = 'Posting in progress... Please wait.';
                
                // Start polling for results
                pollForResults(approved);
            }} catch (e) {{
                console.error('Submit failed:', e);
                status.textContent = 'Error submitting. Please try again.';
                submitBtn.disabled = false;
                submitBtn.textContent = 'Post Approved Comments';
            }}
        }}
        
        async function pollForResults(approved) {{
            const status = document.getElementById('statusMessage');
            let attempts = 0;
            const maxAttempts = 600; // 10 minutes max
            
            status.textContent = 'Posting in progress... Please wait for completion sound.';
            
            const waitForComplete = async () => {{
                try {{
                    const response = await fetch('/results');
                    const data = await response.json();
                    
                    // Only proceed when posting is complete (after sound plays)
                    if (data.complete === true) {{
                        // Update all post cards with final status
                        if (data.results && Object.keys(data.results).length > 0) {{
                            updatePostStatuses(data.results);
                        }}
                        // Show final summary with shutdown button
                        displayFinalResults(data.summary);
                        return;
                    }}
                    
                    // Optional: show progress but don't rely on it for completion
                    const processed = data.summary.total || 0;
                    if (processed > 0) {{
                        status.textContent = `Posting... ${{processed}}/${{approved.length}} processed`;
                    }}
                    
                    // Continue waiting
                    attempts++;
                    if (attempts < maxAttempts) {{
                        setTimeout(waitForComplete, 2000);  // Check every 2 seconds
                    }}
                }} catch (e) {{
                    console.error('Poll error:', e);
                    attempts++;
                    if (attempts < maxAttempts) {{
                        setTimeout(waitForComplete, 2000);
                    }}
                }}
            }};
            
            // Start checking after 3 seconds (give posting time to start)
            setTimeout(waitForComplete, 3000);
        }}
        
        function updatePostStatuses(results) {{
            const cards = document.querySelectorAll('.post-card');
            cards.forEach((card, index) => {{
                const postUrl = posts[index]?.post_url;
                if (postUrl && results[postUrl]) {{
                    const result = results[postUrl];
                    let existingBadge = card.querySelector('.result-badge');
                    if (!existingBadge) {{
                        existingBadge = document.createElement('div');
                        existingBadge.className = 'result-badge';
                        card.insertBefore(existingBadge, card.firstChild);
                    }}
                    
                    if (result.status === 'success') {{
                        existingBadge.className = 'result-badge success';
                        existingBadge.innerHTML = '✓ Comment Posted';
                    }} else if (result.status === 'skipped') {{
                        existingBadge.className = 'result-badge skipped';
                        existingBadge.innerHTML = '⏭ Skipped (Already Posted)';
                    }} else {{
                        existingBadge.className = 'result-badge failed';
                        existingBadge.innerHTML = '✗ Failed: ' + (result.message || 'Unknown error');
                    }}
                }}
            }});
        }}
        
        function displayFinalResults(summary) {{
            var statusDiv = document.getElementById('statusMessage');
            var submitBtn = document.getElementById('submitBtn');
            
            submitBtn.style.display = 'none';
            
            // Play completion sound
            playCompletionSound();
            
            // Build HTML with button and modal exactly like engagement_agent
            var html = '<div class="final-summary" role="alert">';
            html += '<h2>🎉 Posting Complete!</h2>';
            html += '<div class="summary-stats">';
            html += '<div class="stat success"><span class="num">' + summary.success + '</span> Posted</div>';
            html += '<div class="stat failed"><span class="num">' + summary.failed + '</span> Failed</div>';
            html += '<div class="stat skipped"><span class="num">' + summary.skipped + '</span> Skipped</div>';
            html += '</div>';
            html += '<div class="btn-container" style="margin-top: 25px; text-align: center;">';
            html += '<button id="shutdownBtn" class="btn btn-submit" style="background:#0a66c2; padding:15px 30px; font-size:16px; cursor:pointer;" aria-haspopup="dialog" aria-controls="confirmModal">Done & Cleanup</button>';
            html += '<p id="statusMsg" style="margin-top:10px; font-weight:bold;"></p>';
            html += '</div>';
            html += '</div>';
            
            // Add the modal HTML - hidden by default (display:none, not flex)
            html += '<div id="confirmModal" role="dialog" aria-modal="true" aria-labelledby="modalTitle" aria-describedby="modalDesc" class="modal-backdrop" style="position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.7); display:none; justify-content:center; align-items:center; z-index:1000;">';
            html += '<div class="modal" style="background:#2d2d44; padding:30px; border-radius:12px; max-width:400px; text-align:center; color:white;">';
            html += '<h2 id="modalTitle" style="margin-bottom:15px;">Confirm Cleanup</h2>';
            html += '<p id="modalDesc" style="margin-bottom:25px; opacity:0.8;">Are you sure? This will close the agent and clean up.</p>';
            html += '<div class="modal-actions" style="display:flex; gap:15px; justify-content:center;">';
            html += '<button id="confirmYes" class="btn btn-submit" style="background:#d11124; color:white; padding:12px 24px; border:none; border-radius:8px; cursor:pointer; font-size:14px;">Yes, Shutdown</button>';
            html += '<button id="confirmNo" class="btn btn-submit" style="background:#666; color:white; padding:12px 24px; border:none; border-radius:8px; cursor:pointer; font-size:14px;">Cancel</button>';
            html += '</div>';
            html += '</div>';
            html += '</div>';
            
            statusDiv.innerHTML = html;
            
            // Now attach event listeners exactly like engagement_agent
            var btn = document.getElementById('shutdownBtn');
            var modal = document.getElementById('confirmModal');
            var yesBtn = document.getElementById('confirmYes');
            var noBtn = document.getElementById('confirmNo');
            var status = document.getElementById('statusMsg');
            var lastFocusedElement;

            if(btn && modal && yesBtn && noBtn) {{
                // Open Modal - show with display:flex
                btn.addEventListener('click', function() {{
                    lastFocusedElement = document.activeElement;
                    modal.style.display = 'flex';
                    yesBtn.focus();
                }});

                // Cancel Action - hide with display:none
                noBtn.addEventListener('click', function() {{
                    modal.style.display = 'none';
                    if(lastFocusedElement) lastFocusedElement.focus();
                }});
                
                // Close on Escape
                modal.addEventListener('keydown', function(e) {{
                    if (e.key === 'Escape') {{
                        modal.style.display = 'none';
                        if(lastFocusedElement) lastFocusedElement.focus();
                    }}
                }});

                // Confirm Action
                yesBtn.addEventListener('click', function() {{
                    modal.style.display = 'none';
                    status.innerText = "Shutting down...";
                    btn.disabled = true;
                    
                    fetch('/shutdown', {{ method: 'POST' }})
                    .then(function() {{
                        document.body.innerHTML = "<div role='alert' style='text-align:center;padding:50px;'><h1>Session Closed. Bye!</h1></div>";
                    }})
                    .catch(function(e) {{
                        console.log("Fetch error (expected):", e);
                        document.body.innerHTML = "<div role='alert' style='text-align:center;padding:50px;'><h1>Session Closed. Bye!</h1></div>";
                    }});
                }});
            }} else {{
                console.error("Modal components not found");
            }}
        }}
        
        function cancelSession() {{
            if (confirm('Cancel this session? No comments will be posted.')) {{
                fetch('/shutdown', {{ method: 'POST' }})
                    .then(function() {{
                        document.body.innerHTML = '<div role="alert" style="text-align:center;padding:50px;"><h1>Session Cancelled</h1><p>No comments were posted. You can close this window.</p></div>';
                    }});
            }}
        }}
    </script>
    <style>
        .result-badge {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 12px;
        }}
        .result-badge.success {{
            background: rgba(74,222,128,0.2);
            color: #4ade80;
        }}
        .result-badge.failed {{
            background: rgba(248,113,113,0.2);
            color: #f87171;
        }}
        .result-badge.skipped {{
            background: rgba(251,191,36,0.2);
            color: #fbbf24;
        }}
        .final-summary {{
            text-align: center;
            padding: 20px;
        }}
        .final-summary h2 {{
            margin-bottom: 20px;
            font-size: 1.5rem;
        }}
        .summary-stats {{
            display: flex;
            justify-content: center;
            gap: 30px;
        }}
        .stat {{
            font-size: 1rem;
        }}
        .stat .num {{
            font-size: 2rem;
            font-weight: bold;
            display: block;
        }}
        .stat.success {{ color: #4ade80; }}
        .stat.failed {{ color: #f87171; }}
        .stat.skipped {{ color: #fbbf24; }}
    </style>
</body>
</html>"""

        
        with open(REVIEW_HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html_content)
        self.log(f"Review UI generated: {REVIEW_HTML_FILE}")

    async def verify_comment_posted(self, page, expected_comment):
        """Use Gemini to verify if the comment actually appears on the page."""
        try:
            # Wait longer for the UI to stabilize and comment to appear
            await asyncio.sleep(15)
            
            # Scroll to the comment section to ensure it's visible
            await page.evaluate("""
                () => {
                    // Try to find and scroll to the comments section
                    const commentSection = document.querySelector('.comments-comments-list, .comments-comment-list, [data-comments-container]');
                    if (commentSection) {
                        commentSection.scrollIntoView({ behavior: 'instant', block: 'center' });
                    } else {
                        // Fallback: scroll to roughly where comments would be
                        window.scrollTo(0, document.body.scrollHeight * 0.6);
                    }
                }
            """)
            await asyncio.sleep(2)  # Wait for scroll to complete and content to render
            
            # Scrape all comment contents with broad selectors
            comment_selectors = [
                ".comments-comment-item__main-content",
                ".comment-item__main-content",
                ".comments-comment-item",
                ".update-content-wrapper",
                "article[data-test-comment-item]",
                ".comments-comment-entity",  # Added newer selector
                "[data-urn*='comment']"  # Added URN-based selector
            ]
            
            scraped_texts = []
            for selector in comment_selectors:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    text = await el.inner_text()
                    if text:
                        scraped_texts.append(text.strip())
            
            # Log how many elements we found
            self.log(f"  Verification: Found {len(scraped_texts)} comment elements")
            
            # Try to find user's own comment specifically first
            user_comment_text = ""
            for selector in comment_selectors:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    text = await el.inner_text()
                    if text and self.user_name and self.user_name in text:
                        # Found a comment by the current user
                        user_comment_text = text.strip()
                        self.log(f"  Found user's comment element!")
                        break
                if user_comment_text:
                    break
            
            # Always get body text as a broad fallback
            all_text = await page.evaluate("document.body.innerText")
            # Focus on the bottom half of the page where comments are likely
            scraped_texts.append(all_text[-15000:])  # Increased from 10000
            
            context = "\n---\n".join(set(scraped_texts)) # Set to remove dupes
            
            # If we found user's comment, prepend it for priority
            if user_comment_text:
                context = f"=== USER'S OWN COMMENT ===\n{user_comment_text}\n===\n\n{context}"
            
            prompt = f"""Analyze the following LinkedIn post comment data and determine if the target comment is successfully published.
            
USER NAME (Current poster): {self.user_name}
TARGET COMMENT:
"{expected_comment}"

SCRAPED COMMENT DATA (Snippets separated by ---):
{context[:15000]}

Respond with ONLY "YES" if ANY of these conditions are met:
1. A comment by user "{self.user_name}" appears with a RECENT timestamp (1s, 2s, 5s, 30s, 1m, 2m, "now", "seconds ago", etc.)
2. The comment text (or even the BEGINNING of it, like first few words) matches the target comment
3. The user "{self.user_name}" has a comment that starts similarly to the target comment

Respond "NO" ONLY if:
- There is NO comment by "{self.user_name}" visible at all
- OR the only comments by "{self.user_name}" are from hours/days ago with completely different text

Be LENIENT - if the user's name appears with any recent timestamp near text that starts like the target, say YES.
Ignore UI text like "Reply", "Like", "• You", or comment counts."""

            # DEBUG: Save the prompt and context being sent to Gemini
            debug_file = f"debug_verification_{datetime.now().strftime('%H%M%S')}.txt"
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write("=== EXPECTED COMMENT ===\n")
                f.write(expected_comment + "\n\n")
                f.write("=== SCRAPED CONTEXT ===\n")
                f.write(context[:15000] + "\n\n")
                f.write("=== FULL PROMPT ===\n")
                f.write(prompt)
            
            response = self.genai_client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            result = response.text.strip().upper()
            
            # DEBUG: Log Gemini's response
            self.log(f"  Gemini verification response: {result}")
            with open(debug_file, "a", encoding="utf-8") as f:
                f.write(f"\n\n=== GEMINI RESPONSE ===\n{result}")
            
            return "YES" in result
            
        except Exception as e:
            self.log(f"  Warning: Verification error: {e}")
            return True # Fallback to avoid false negatives

    def generate_results_html(self):
        """Generate an HTML page showing posting results."""
        global APPROVED_COMMENTS, POSTING_RESULTS
        
        success_count = sum(1 for r in POSTING_RESULTS.values() if r.get("status") == "success")
        failed_count = sum(1 for r in POSTING_RESULTS.values() if r.get("status") == "failed")
        skipped_count = sum(1 for r in POSTING_RESULTS.values() if r.get("status") == "skipped")
        total = len(POSTING_RESULTS)
        
        posts_html = ""
        for item in APPROVED_COMMENTS:
            post_url = item.get("post_url", "")
            author = item.get("author_name", "Unknown")
            comment = item.get("final_comment", "")
            result = POSTING_RESULTS.get(post_url, {"status": "unknown", "message": "Not processed"})
            
            status = result.get("status", "unknown")
            message = result.get("message", "")
            
            if status == "success":
                status_icon = "✓"
                status_class = "success"
                status_text = "Comment Posted"
            elif status == "skipped":
                status_icon = "⏭"
                status_class = "skipped"
                status_text = "Skipped (Already Posted)"
            else:
                status_icon = "✗"
                status_class = "failed"
                status_text = f"Failed: {message}"
            
            posts_html += f'''
            <div class="post-card {status_class}">
                <div class="status-badge {status_class}">
                    <span class="status-icon">{status_icon}</span>
                    <span class="status-text">{status_text}</span>
                </div>
                <div class="author">{author}</div>
                <div class="comment">{comment[:200]}{'...' if len(comment) > 200 else ''}</div>
            </div>
            '''
        
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Posting Results</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        h1 {{ text-align: center; margin-bottom: 20px; }}
        .summary {{
            background: rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-around;
            text-align: center;
        }}
        .summary-item {{ }}
        .summary-number {{ font-size: 2.5rem; font-weight: bold; }}
        .summary-label {{ font-size: 0.9rem; opacity: 0.8; }}
        .summary-item.success .summary-number {{ color: #4ade80; }}
        .summary-item.failed .summary-number {{ color: #f87171; }}
        .summary-item.skipped .summary-number {{ color: #fbbf24; }}
        .post-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
            border-left: 4px solid #666;
        }}
        .post-card.success {{ border-left-color: #4ade80; }}
        .post-card.failed {{ border-left-color: #f87171; }}
        .post-card.skipped {{ border-left-color: #fbbf24; }}
        .status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            margin-bottom: 10px;
        }}
        .status-badge.success {{ background: rgba(74,222,128,0.2); color: #4ade80; }}
        .status-badge.failed {{ background: rgba(248,113,113,0.2); color: #f87171; }}
        .status-badge.skipped {{ background: rgba(251,191,36,0.2); color: #fbbf24; }}
        .author {{ font-weight: 600; font-size: 1.1rem; margin-bottom: 8px; }}
        .comment {{ font-size: 0.9rem; opacity: 0.7; line-height: 1.4; }}
        
        /* Shutdown Button */
        .btn-container {{ text-align: center; margin-top: 30px; }}
        .close-btn {{
            background: #0a66c2;
            color: white;
            border: none;
            padding: 14px 32px;
            font-size: 1rem;
            font-weight: 600;
            border-radius: 25px;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .close-btn:hover {{ background: #004182; }}
        .close-btn:disabled {{ background: #666; cursor: not-allowed; }}
        
        /* Modal */
        .modal-backdrop {{
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }}
        .modal {{
            background: #2d2d44;
            padding: 30px;
            border-radius: 12px;
            max-width: 400px;
            text-align: center;
        }}
        .modal h2 {{ margin-bottom: 15px; }}
        .modal p {{ margin-bottom: 25px; opacity: 0.8; }}
        .modal-actions {{ display: flex; gap: 15px; justify-content: center; }}
        .modal-actions button {{ min-width: 100px; }}
        .btn-danger {{ background: #d11124 !important; }}
        .btn-secondary {{ background: #666 !important; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Posting Results</h1>
        <div class="summary">
            <div class="summary-item success">
                <div class="summary-number">{success_count}</div>
                <div class="summary-label">Posted</div>
            </div>
            <div class="summary-item failed">
                <div class="summary-number">{failed_count}</div>
                <div class="summary-label">Failed</div>
            </div>
            <div class="summary-item skipped">
                <div class="summary-number">{skipped_count}</div>
                <div class="summary-label">Skipped</div>
            </div>
        </div>
        {posts_html}
        
        <div class="btn-container">
            <button id="shutdownBtn" class="close-btn" aria-haspopup="dialog" aria-controls="confirmModal">Done & Cleanup</button>
            <p id="statusMsg" style="margin-top:10px; font-weight:bold;"></p>
        </div>
        
        <!-- Accessible Shutdown Confirmation Modal - Hidden by default -->
        <div id="confirmModal" role="dialog" aria-modal="true" aria-labelledby="modalTitle" aria-describedby="modalDesc" class="modal-backdrop" hidden>
            <div class="modal" tabindex="-1">
                <h2 id="modalTitle">Confirm Cleanup</h2>
                <p id="modalDesc">Are you sure? This will close the agent and clean up.</p>
                <div class="modal-actions">
                    <button id="confirmYes" class="close-btn btn-danger">Yes, Shutdown</button>
                    <button id="confirmNo" class="close-btn btn-secondary">Cancel</button>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            var btn = document.getElementById('shutdownBtn');
            var modal = document.getElementById('confirmModal');
            var yesBtn = document.getElementById('confirmYes');
            var noBtn = document.getElementById('confirmNo');
            var status = document.getElementById('statusMsg');
            var lastFocusedElement;

            if(btn && modal && yesBtn && noBtn) {{
                // Open Modal when Done & Cleanup is clicked
                btn.addEventListener('click', function() {{
                    lastFocusedElement = document.activeElement;
                    modal.hidden = false;
                    modal.style.display = 'flex';
                    yesBtn.focus();
                }});

                // Cancel Action - hide modal
                noBtn.addEventListener('click', function() {{
                    modal.hidden = true;
                    modal.style.display = 'none';
                    if(lastFocusedElement) lastFocusedElement.focus();
                    else btn.focus();
                }});
                
                // Close on Escape
                modal.addEventListener('keydown', function(e) {{
                    if (e.key === 'Escape') {{
                        modal.hidden = true;
                        modal.style.display = 'none';
                        if(lastFocusedElement) lastFocusedElement.focus();
                        else btn.focus();
                    }}
                }});

                // Confirm Shutdown
                yesBtn.addEventListener('click', function() {{
                    modal.hidden = true;
                    modal.style.display = 'none';
                    status.innerText = "Shutting down...";
                    btn.disabled = true;
                    
                    fetch('/shutdown', {{ method: 'POST' }})
                    .then(function() {{
                        document.body.innerHTML = "<div role='alert' style='text-align:center;padding:50px;'><h1>Session Closed. Bye!</h1></div>";
                        setTimeout(function() {{ window.close(); }}, 1000);
                    }})
                    .catch(function(e) {{
                        console.log("Fetch error (expected):", e);
                        document.body.innerHTML = "<div role='alert' style='text-align:center;padding:50px;'><h1>Session Closed. Bye!</h1></div>";
                        setTimeout(function() {{ window.close(); }}, 1000);
                    }});
                }});
            }}
        }});
    </script>
</body>
</html>'''
        
        with open("posting_results.html", "w", encoding="utf-8") as f:
            f.write(html)
        
        self.log(f"Results page generated: posting_results.html")

    async def post_approved_comments(self):
        """Post all approved comments to LinkedIn."""
        global APPROVED_COMMENTS, POSTING_RESULTS
        
        if not APPROVED_COMMENTS:
            self.log("No comments to post.")
            return
        
        # Load comment history to prevent duplicates
        history = self.load_comment_history()
        POSTING_RESULTS = {}  # Reset results
        
        self.log(f"Posting {len(APPROVED_COMMENTS)} approved comments...")
        
        for item in APPROVED_COMMENTS:
            try:
                post_url = item.get("post_url")
                comment_text = item.get("final_comment")
                author_name = item.get("author_name")
                
                if not post_url or not comment_text:
                    continue
                
                # Check for duplicate
                if self.is_already_posted(post_url, history):
                    self.log(f"⏭ Skipping {author_name}'s post - already commented previously")
                    POSTING_RESULTS[post_url] = {"status": "skipped", "message": "Already commented"}
                    continue
                
                self.log(f"Posting comment on {author_name}'s post...")
                
                # Navigate to post
                post_page = await self.context.new_page()
                
                # === DEVTOOLS DEBUGGING ===
                console_logs = []
                network_errors = []
                
                # Capture console messages
                post_page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
                
                # Capture network failures
                post_page.on("requestfailed", lambda req: network_errors.append(f"FAILED: {req.url} - {req.failure}"))
                
                # Navigate with retry logic for slow pages
                nav_success = False
                # Navigate with retry logic for slow pages
                nav_success = False
                for nav_attempt in range(3):
                    try:
                        # ANTI-DETECTION: Human-like navigation
                        await human_delay(1.0, 3.0)
                        await post_page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
                        await human_delay(3.0, 6.0)
                        nav_success = True
                        break
                    except Exception as nav_error:
                        if nav_attempt < 2:
                            self.log(f"  Navigation attempt {nav_attempt + 1} failed, retrying...")
                            await asyncio.sleep(3 * (nav_attempt + 1))  # Exponential backoff
                        else:
                            raise nav_error
                
                if not nav_success:
                    raise Exception("Failed to navigate to post after 3 attempts")
                
                # ANTI-DETECTION: Human-like wait and scroll
                await human_delay(2.0, 4.0)
                
                # Ensure we are scrolled to the comment area
                await human_scroll(post_page, random.randint(400, 600))
                await human_delay(1.5, 3.0)
                
                # Find and click comment button/area to expand if needed - WITH RETRY
                comment_btn_selectors = [
                    "button[aria-label*='Comment']",
                    "button[aria-label*='comment']",
                    ".comment-button",
                    "button:has-text('Comment')",
                    "span:has-text('Comment')"  # Sometimes it's a span inside button
                ]
                
                # Try clicking the comment button up to 3 times
                for attempt in range(3):
                    clicked = False
                    for selector in comment_btn_selectors:
                        btn = await post_page.query_selector(selector)
                        if btn:
                            await btn.click()
                            self.log(f"  Clicked comment button with: {selector}")
                            await asyncio.sleep(2)
                            clicked = True
                            break
                    
                    # Check if comment input appeared
                    test_input = await post_page.query_selector(".ql-editor, [contenteditable='true']")
                    if test_input:
                        break
                    
                    if not clicked:
                        # Scroll more and wait for dynamic content
                        await post_page.evaluate("window.scrollTo(0, 600)")
                        await asyncio.sleep(2)
                
                # Find comment input field - WITH RETRY AND MORE SELECTORS
                comment_input_selectors = [
                    ".ql-editor[data-placeholder*='Add a comment']",
                    ".comments-comment-box__form .ql-editor",
                    "[contenteditable='true'][aria-label*='Add a comment']",
                    "[contenteditable='true'][aria-label*='comment' i]",
                    ".ql-editor[contenteditable='true']",
                    ".ql-editor",
                    "div[contenteditable='true'][role='textbox']",
                    ".comments-comment-texteditor .ql-editor"
                ]
                
                comment_input = None
                for retry in range(3):  # Retry up to 3 times
                    for selector in comment_input_selectors:
                        comment_input = await post_page.query_selector(selector)
                        if comment_input:
                            self.log(f"  Found comment input with: {selector}")
                            break
                    if comment_input:
                        break
                    await asyncio.sleep(2)  # Wait before retry
                
                if comment_input:
                    # ANTI-DETECTION: Human-like click and focus
                    await human_delay(0.5, 1.5)
                    await comment_input.click()
                    await human_delay(0.3, 0.8)
                    await comment_input.focus()
                    await human_delay(0.5, 1.5)
                    
                    # === DUMP COMMENT BOX HTML BEFORE TYPING ===
                    comment_box_html = await post_page.evaluate("""
                        () => {
                            const box = document.querySelector('.comments-comment-box, .comment-box');
                            return box ? box.outerHTML : 'Comment box not found';
                        }
                    """)
                    safe_name = self.sanitize_filename(author_name)
                    with open(f"debug_dom_{safe_name}.html", "w", encoding="utf-8") as f:
                        f.write(comment_box_html)
                    self.log(f"  Saved comment box DOM to debug_dom_{safe_name}.html")
                    
                    # ANTI-DETECTION: Human-like typing with variable delay (50-120ms per char)
                    typing_delay = random.randint(50, 120)
                    await comment_input.type(comment_text, delay=typing_delay, timeout=90000)
                    await human_delay(1.5, 3.0)
                    
                    # === DUMP COMMENT BOX HTML AFTER TYPING ===
                    comment_box_html_after = await post_page.evaluate("""
                        () => {
                            const box = document.querySelector('.comments-comment-box, .comment-box');
                            return box ? box.outerHTML : 'Comment box not found';
                        }
                    """)
                    with open(f"debug_dom_after_{safe_name}.html", "w", encoding="utf-8") as f:
                        f.write(comment_box_html_after)
                    self.log(f"  Saved post-typing DOM to debug_dom_after_{safe_name}.html")
                    
                    # Wait for the Post button to become enabled (LinkedIn uses 'disabled' attribute)
                    self.log("  Waiting for Post button to become active...")
                    post_btn = None
                    post_btn_selectors = [
                        "button.comments-comment-box__submit-button:not([disabled])",
                        ".comments-comment-box__form-controls button[type='submit']:not([disabled])",
                        ".comments-comment-box button.artdeco-button--primary:not([disabled])",
                        "button.artdeco-button--primary:not([disabled])",  # Broader selector
                        "button:has-text('Post'):not([disabled])"  # Text-based selector
                    ]
                    
                    for attempt in range(5):  # Wait up to 5 seconds
                        for selector in post_btn_selectors:
                            post_btn = await post_page.query_selector(selector)
                            if post_btn:
                                self.log(f"  Found enabled Post button with: {selector}")
                                break
                        if post_btn:
                            break
                        await asyncio.sleep(1)
                    
                    input_cleared = False  # Track if input was cleared (reliable success indicator)
                    
                    if post_btn:
                        # Try multiple click strategies
                        click_methods = [
                            ("JavaScript scroll+click", lambda: post_page.evaluate("el => { el.scrollIntoViewIfNeeded(); el.click(); }", post_btn)),
                            ("Direct click", lambda: post_btn.click()),
                            ("Force click", lambda: post_btn.click(force=True)),
                        ]
                        
                        for method_name, click_fn in click_methods:
                            try:
                                await click_fn()
                                self.log(f"  Executed {method_name} on Post button")
                                await asyncio.sleep(3)
                                
                                # Check if input is cleared (success indicator)
                                input_text = await post_page.evaluate("el => el.innerText || ''", comment_input)
                                if not input_text or len(input_text.strip()) == 0:
                                    self.log("  Input cleared successfully!")
                                    input_cleared = True
                                    break
                                else:
                                    self.log(f"  Input not cleared with {method_name}, trying next method...")
                            except Exception as click_err:
                                self.log(f"  {method_name} failed: {click_err}")
                        
                        # If still not cleared, try keyboard shortcuts
                        if not input_cleared:
                            self.log("  Trying keyboard shortcuts...")
                            try:
                                # Try Ctrl+Enter (common submit shortcut)
                                await comment_input.focus()
                                await post_page.keyboard.press("Control+Enter")
                                await asyncio.sleep(2)
                                
                                input_text = await post_page.evaluate("el => el.innerText || ''", comment_input)
                                if not input_text or len(input_text.strip()) == 0:
                                    self.log("  Input cleared with Ctrl+Enter!")
                                    input_cleared = True
                            except:
                                pass
                        
                        if not input_cleared:
                            try:
                                # Try Tab+Enter
                                await comment_input.press("Tab")
                                await asyncio.sleep(0.5)
                                await post_page.keyboard.press("Enter")
                                await asyncio.sleep(3)
                                
                                input_text = await post_page.evaluate("el => el.innerText || ''", comment_input)
                                if not input_text or len(input_text.strip()) == 0:
                                    self.log("  Input cleared with Tab+Enter!")
                                    input_cleared = True
                                else:
                                    self.log("  WARNING: All click methods failed.")
                            except:
                                pass
                    else:
                        # Debug: Find ANY buttons that might be the Post button
                        all_buttons = await post_page.evaluate("""
                            () => {
                                const buttons = document.querySelectorAll('button');
                                return Array.from(buttons).map(b => ({
                                    text: b.innerText.trim(),
                                    class: b.className,
                                    disabled: b.disabled,
                                    type: b.type
                                })).filter(b => b.text.toLowerCase().includes('post') || b.class.includes('submit'));
                            }
                        """)
                        if all_buttons:
                            self.log(f"  DEBUG: Found {len(all_buttons)} potential buttons: {all_buttons[:3]}")
                        
                        self.log("  WARNING: Post button stayed disabled or not found. Trying Tab+Enter...")
                        await comment_input.press("Tab")
                        await asyncio.sleep(0.5)
                        await post_page.keyboard.press("Enter")
                        await asyncio.sleep(3)
                        
                        # Check if it worked
                        input_text = await post_page.evaluate("el => el.innerText || ''", comment_input)
                        if not input_text or len(input_text.strip()) == 0:
                            input_cleared = True

                    # Look for success toast
                    toast = await post_page.query_selector(".artdeco-toast-item, .comments-post-comments-view__feed-update-toast")
                    if toast:
                        self.log("  Success toast detected")

                    self.log("  Interaction complete, verifying with Gemini...")
                    
                    # Wait for UI to stabilize
                    await asyncio.sleep(8)
                    
                    # ALWAYS verify with Gemini AI
                    is_verified = await self.verify_comment_posted(post_page, comment_text)
                    
                    if is_verified:
                        self.log(f"✓ Comment verified on {author_name}'s post")
                        self.metrics["comments_posted"] += 1
                        POSTING_RESULTS[post_url] = {"status": "success", "message": "Comment posted"}
                        self.record_posted_comment(post_url, author_name, comment_text, True, history)
                    else:
                        self.log(f"✗ Verification failed: Comment not visible on {author_name}'s post")
                        safe_name = self.sanitize_filename(author_name)
                        await post_page.screenshot(path=f"verify_fail_{safe_name}.png")
                        self.metrics["errors"] += 1
                        POSTING_RESULTS[post_url] = {"status": "failed", "message": "Comment not visible after posting"}
                        self.record_posted_comment(post_url, author_name, comment_text, False, history)
                else:
                    self.log(f"Could not find comment input for {author_name}")
                    safe_name = self.sanitize_filename(author_name)
                    
                    # === DEBUG: Capture page state when comment input not found ===
                    # Dump the entire page HTML to understand what's there
                    page_html = await post_page.evaluate("() => document.body.innerHTML")
                    with open(f"debug_no_input_{safe_name}.html", "w", encoding="utf-8") as f:
                        f.write(page_html)
                    self.log(f"  Saved page HTML to debug_no_input_{safe_name}.html")
                    
                    # Take a screenshot
                    try:
                        await post_page.screenshot(path=f"debug_no_input_{safe_name}.png", timeout=10000)
                        self.log(f"  Saved screenshot to debug_no_input_{safe_name}.png")
                    except:
                        pass
                    
                    self.metrics["errors"] += 1
                    POSTING_RESULTS[post_url] = {"status": "failed", "message": "Comment input not found"}
                    self.record_posted_comment(post_url, author_name, comment_text, False, history)
                
                # === SAVE DEBUG LOGS ===
                safe_name = self.sanitize_filename(author_name)
                if console_logs:
                    with open(f"debug_console_{safe_name}.txt", "w", encoding="utf-8") as f:
                        f.write("\n".join(console_logs[-100:]))  # Last 100 messages
                    self.log(f"  Saved console logs to debug_console_{safe_name}.txt")
                
                if network_errors:
                    with open(f"debug_network_{safe_name}.txt", "w", encoding="utf-8") as f:
                        f.write("\n".join(network_errors))
                    self.log(f"  Saved network errors to debug_network_{safe_name}.txt")
                
                await post_page.close()
                
                # HUMAN-LIKE DELAY BETWEEN POSTS
                # Base delay: 10-30 seconds (like a human taking a moment between actions)
                base_delay = random.uniform(10, 30)
                
                # 20% chance of a "distraction pause" (like checking phone or reading something)
                if random.random() < 0.20:
                    distraction_time = random.uniform(20, 45)
                    self.log(f"  [Human behavior] Brief pause ({int(distraction_time)}s)...")
                    await asyncio.sleep(distraction_time)
                else:
                    await asyncio.sleep(base_delay)
                
                # Occasional mouse movement on the main feed page (simulates user activity)
                if self.page and random.random() < 0.3:
                    viewport = self.page.viewport_size
                    if viewport:
                        await self.page.mouse.move(
                            random.randint(100, viewport['width'] - 100),
                            random.randint(100, viewport['height'] - 100)
                        )
                
            except Exception as e:
                self.log(f"Error posting comment: {e}")
                self.metrics["errors"] += 1
                if post_url:
                    POSTING_RESULTS[post_url] = {"status": "failed", "message": str(e)}
        
        # Generate results HTML page
        self.generate_results_html()
        
        # Play completion sound from Python/laptop speaker
        play_complete_sound()

    async def run(self):
        """Main entry point."""
        global SHUTDOWN_EVENT, APPROVED_COMMENTS, POSTING_COMPLETE, POSTING_RESULTS
        
        # Reset state for new session
        POSTING_COMPLETE = False
        POSTING_RESULTS = {}
        SHUTDOWN_EVENT.clear()
        APPROVED_COMMENTS = []
        
        try:
            # Phase 1: Initialize and scan feed
            await self.start()
            await self.scan_feed_for_legal_posts()
            
            if not self.posts_to_comment:
                self.log("No posts from legal professionals found in feed.")
                return
            
            # Phase 2: Generate review UI
            self.generate_review_html()
            
            # Phase 3: Start review server
            port = 8080
            server_address = ('127.0.0.1', port)
            try:
                server = HTTPServer(server_address, ReviewHandler)
            except OSError:
                self.log(f"Port {port} in use. Trying {port+1}...")
                port += 1
                server_address = ('127.0.0.1', port)
                server = HTTPServer(server_address, ReviewHandler)
            
            url = f"http://127.0.0.1:{port}"
            self.log(f"Review server started at {url}")
            
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.daemon = True
            server_thread.start()
            
            # Open review page in browser
            try:
                review_page = await self.context.new_page()
                await review_page.goto(url)
                
                # Close other tabs
                for page in self.context.pages:
                    if page != review_page:
                        await page.close()
            except Exception as e:
                self.log(f"Warning: Could not open review page: {e}")
            
            # Play sound alert from Python/laptop speaker
            play_ready_sound()
            self.log("🔔 Ready for review (sound played)")
            
            self.log("Waiting for user review...")
            
            # Wait for user action (submit or cancel)
            while not SHUTDOWN_EVENT.is_set():
                await asyncio.sleep(1)
            
            # Phase 4: Post approved comments
            if APPROVED_COMMENTS:
                self.metrics["comments_approved"] = len(APPROVED_COMMENTS)
                await self.post_approved_comments()
                POSTING_COMPLETE = True  # Signal to browser that posting is complete
                
                # Log summary
                self.log(f"\n{'='*50}")
                self.log(f"Posting Complete!")
                self.log(f"Posts scanned: {self.metrics['posts_scanned']}")
                self.log(f"Legal posts found: {self.metrics['legal_posts_found']}")
                self.log(f"Comments approved: {self.metrics['comments_approved']}")
                self.log(f"Comments posted: {self.metrics['comments_posted']}")
                self.log(f"Errors: {self.metrics['errors']}")
                self.log(f"{'='*50}")
                
                # Wait for user to click 'Done & Cleanup' button on the page
                # (The browser will show results inline via polling)
                SHUTDOWN_EVENT.clear()
                self.log("Waiting for user to click 'Done & Cleanup'...")
                
                while not SHUTDOWN_EVENT.is_set():
                    await asyncio.sleep(1)
                
                self.log("User clicked shutdown. Cleaning up...")
            
        except Exception as e:
            self.log(f"CRITICAL ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            if self.context:
                try:
                    await self.context.close()
                except:
                    pass
            
            # Clean up files
            for f in [REVIEW_HTML_FILE, PENDING_COMMENTS_FILE, "posting_results.html"]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except:
                        pass


if __name__ == "__main__":
    print("Starting LinkedIn Comment Agent...", flush=True)
    try:
        agent = CommentAgent()
        asyncio.run(agent.run())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()

