"""
LinkedIn Boolean Search Agent for Legal Automation Freelancing
================================================================
Searches LinkedIn Jobs and Posts for freelancing opportunities
in legal field automation using multiple Boolean search combinations.

Features:
- Generates multiple Boolean search combinations automatically
- Searches both LinkedIn Jobs and Posts
- Deduplicates results across searches
- Presents results in accessible review UI
- Exports interested results to CSV

Author: AI Agent
Created: 2026-01-06
"""

import asyncio
import os
import json
import threading
import subprocess
import socket
import re
import csv
import random
import urllib.parse
import winsound
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from google import genai

# Load environment variables
load_dotenv()

# ============================================================================
# ANTI-DETECTION: Human-like behavior utilities
# ============================================================================

async def human_delay(min_seconds=1.5, max_seconds=4.0):
    """Add a random human-like delay to avoid detection."""
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)

async def human_scroll(page, scroll_amount=None):
    """Scroll in a human-like manner with variable speed and distance."""
    if scroll_amount is None:
        scroll_amount = random.randint(200, 500)
    
    # Scroll in smaller increments with pauses
    increments = random.randint(2, 4)
    per_increment = scroll_amount // increments
    
    for _ in range(increments):
        await page.evaluate(f"window.scrollBy(0, {per_increment + random.randint(-30, 30)})")
        await asyncio.sleep(random.uniform(0.3, 0.8))

async def human_mouse_move(page):
    """Simulate random mouse movements."""
    try:
        # Get viewport size
        viewport = page.viewport_size
        if viewport:
            x = random.randint(100, viewport['width'] - 100)
            y = random.randint(100, viewport['height'] - 100)
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.1, 0.3))
    except:
        pass

async def human_like_navigate(page, url, timeout=45000):
    """Navigate with human-like pre and post delays."""
    await human_delay(0.5, 1.5)
    await page.goto(url, timeout=timeout)
    await human_delay(2.0, 4.0)
    await human_mouse_move(page)

# ============================================================================

# Sound alert functions
def play_ready_sound():
    """Play ascending tones when results are ready for review."""
    try:
        winsound.Beep(523, 200)   # C5
        winsound.Beep(659, 200)   # E5  
        winsound.Beep(784, 300)   # G5
    except:
        pass

def play_complete_sound():
    """Play victory fanfare when done."""
    try:
        winsound.Beep(523, 150)   # C5
        winsound.Beep(659, 150)   # E5
        winsound.Beep(784, 150)   # G5
        winsound.Beep(1047, 400)  # C6
    except:
        pass

# Configuration
REVIEW_HTML_FILE = "search_review.html"
SEARCH_HISTORY_FILE = "search_history.json"
SEARCH_RESULTS_FILE = "search_results.json"
CHROME_PID = None
SHUTDOWN_EVENT = threading.Event()
INTERESTED_RESULTS = []
AGENT_INSTANCE = None


class BooleanSearchGenerator:
    """Generates Boolean search combinations for legal automation freelancing."""
    
    def __init__(self):
        # Legal focus keywords
        self.legal_focus = [
            '"legal automation"',
            '"legal tech"',
            '"legaltech"',
            '"legal AI"',
            '"law firm automation"',
            '"legal operations"',
            '"contract automation"',
            '"document automation"',
            '"legal workflow"',
            '"CLM"',  # Contract Lifecycle Management
            '"legal process"'
        ]
        
        # Work type keywords
        self.work_types = [
            'freelance',
            'contract',
            'consultant',
            'independent',
            '"project-based"',
            'contractor'
        ]
        
        # Skills/roles
        self.skills = [
            'automation',
            'developer',
            'specialist',
            'engineer',
            'consultant',
            'analyst'
        ]
        
        # Hiring indicators (for posts search)
        self.hiring_indicators = [
            'hiring',
            'seeking',
            'looking for',
            '"need help"',
            'opportunity',
            '"open position"',
            'recruiting'
        ]
        
        # Location
        self.locations = [
            'US',
            '"United States"',
            'remote',
            'USA'
        ]
    
    def generate_job_queries(self):
        """Generate Boolean queries for Jobs search - focused on AI automation."""
        queries = []
        
        # Core combinations - focused on AI + automation in legal
        queries.extend([
            '"legal AI" AND (freelance OR contract OR consultant)',
            '"legal automation" AND AI AND (freelance OR contract)',
            '"legal tech" AND AI AND (freelance OR consultant)',
            '("legaltech" OR "legal ops") AND "AI automation" AND freelance',
            '"contract automation" AND AI AND (developer OR specialist)',
            '"document automation" AND AI AND legal',
            '"AI automation" AND legal AND (freelance OR contract)',
            '"CLM" AND AI AND (freelance OR consultant)',
            '"legal operations" AND AI AND (automation OR workflow) AND freelance',
            'legal AND "AI automation" AND (RPA OR "process automation")',
            '"law firm" AND AI AND automation AND contract',
            'legal AND AI AND (Python OR developer) AND automation AND freelance',
            '"generative AI" AND legal AND (freelance OR contract)',
            '"AI agent" AND legal AND (freelance OR consultant)'
        ])
        
        return queries
    
    def generate_post_queries(self):
        """Generate Boolean queries for Posts search - focused on AI automation with hiring indicators."""
        queries = []
        
        # Post-specific combinations with AI automation focus and hiring language
        queries.extend([
            '"legal AI" AND (hiring OR "looking for" OR seeking OR need)',
            '"AI automation" AND legal AND (freelance OR contract OR project)',
            '"legal automation" AND AI AND (hiring OR seeking OR help)',
            '"legal tech" AND AI AND (freelance OR consultant OR need)',
            '("legaltech" OR "legal ops") AND AI AND (hiring OR freelancer)',
            '"contract automation" AND AI AND (developer OR specialist)',
            '"document automation" AND AI AND (project OR opportunity)',
            '"generative AI" AND legal AND (hiring OR freelance OR consultant)',
            '"AI agent" AND legal AND (developer OR hiring OR need)',
            '"law firm" AND AI AND automation AND (hiring OR seeking)',
            'legal AND "AI automation" AND (contractor OR freelancer)',
            '"CLM" AND AI AND (hiring OR consultant OR need)'
        ])
        
        return queries


class ReviewHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for the review server."""
    
    def log_message(self, format, *args):
        pass  # Suppress default logging
    
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            if os.path.exists(REVIEW_HTML_FILE):
                with open(REVIEW_HTML_FILE, "r", encoding="utf-8") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            else:
                self.wfile.write(b"<h1>Error: Review file not found.</h1>")
        elif self.path == "/status":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            status = {
                "interested_count": len(INTERESTED_RESULTS),
                "shutdown": SHUTDOWN_EVENT.is_set()
            }
            self.wfile.write(json.dumps(status).encode())
        else:
            self.send_error(404)
    
    def do_POST(self):
        global INTERESTED_RESULTS
        
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length else ""
        
        if self.path == "/shutdown":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Shutting down...")
            print("\n[Server] Shutdown signal received. Cleaning up...")
            
            if os.path.exists(REVIEW_HTML_FILE):
                try:
                    os.remove(REVIEW_HTML_FILE)
                    print(f"[Cleanup] Deleted {REVIEW_HTML_FILE}")
                except Exception as e:
                    print(f"[Cleanup] Error deleting file: {e}")
            
            SHUTDOWN_EVENT.set()
            
        elif self.path == "/mark_interested":
            try:
                data = json.loads(body)
                result_id = data.get("result_id")
                interested = data.get("interested", False)
                
                if interested:
                    if result_id not in [r.get("id") for r in INTERESTED_RESULTS]:
                        # Find the result and add it
                        if AGENT_INSTANCE:
                            for r in AGENT_INSTANCE.all_results:
                                if r.get("id") == result_id:
                                    INTERESTED_RESULTS.append(r)
                                    break
                else:
                    INTERESTED_RESULTS = [r for r in INTERESTED_RESULTS if r.get("id") != result_id]
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "count": len(INTERESTED_RESULTS)}).encode())
            except Exception as e:
                print(f"[Server] Error marking interested: {e}")
                self.send_response(500)
                self.end_headers()
                
        elif self.path == "/export_csv":
            try:
                if AGENT_INSTANCE:
                    csv_path = AGENT_INSTANCE.export_to_csv()
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "path": csv_path}).encode())
                else:
                    self.send_response(500)
                    self.end_headers()
            except Exception as e:
                print(f"[Server] Error exporting CSV: {e}")
                self.send_response(500)
                self.end_headers()
        else:
            self.send_error(404)


class SearchAgent:
    """LinkedIn Boolean Search Agent for legal automation freelancing."""
    
    def __init__(self):
        global AGENT_INSTANCE
        AGENT_INSTANCE = self
        
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self.chrome_pid = None
        
        self.search_generator = BooleanSearchGenerator()
        self.all_results = []  # All unique results
        self.job_results = []
        self.post_results = []
        self.seen_urls = set()  # For deduplication
        
        # Gemini client for post intent filtering
        self.genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_name = "gemini-2.0-flash"
        
        # Session metrics
        self.metrics = {
            "queries_executed": 0,
            "jobs_found": 0,
            "posts_found": 0,
            "posts_filtered": 0,
            "duplicates_skipped": 0
        }
    
    def log(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)
    
    def is_relevant_freelance_post(self, post_content, author_headline=""):
        """Use Gemini to determine if a post is about hiring for legal AI automation."""
        if not post_content or len(post_content.strip()) < 20:
            return False
        
        try:
            prompt = f"""Analyze this LinkedIn post and determine if it's relevant for someone looking for legal AI automation opportunities.

POST CONTENT:
{post_content[:1500]}

AUTHOR HEADLINE (if available):
{author_headline}

Respond "YES" if ANY of these are true:
- The author is hiring, seeking, or looking for help with legal AI, legal automation, legal tech, or legal operations
- The post mentions a job opening, project, gig, or opportunity in legal AI/automation
- Someone is looking for a freelancer, consultant, contractor, or developer for legal tech work
- A law firm or legal company is recruiting for automation/AI roles
- The post is about needing help with contract automation, document automation, CLM, or legal workflow automation

Respond "NO" only if:
- The post is just general discussion/thought leadership with no hiring intent
- It's someone looking FOR a job (not offering one)
- It's completely unrelated to legal AI/automation hiring

Respond with ONLY "YES" or "NO" - nothing else."""

            response = self.genai_client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            result = response.text.strip().upper()
            return "YES" in result
        except Exception as e:
            self.log(f"    Error checking post intent: {e}")
            # On error, include the post (less strict)
            return True
    
    def load_history(self):
        """Load previously seen result URLs."""
        try:
            if os.path.exists(SEARCH_HISTORY_FILE):
                with open(SEARCH_HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data.get("seen_urls", []))
        except Exception as e:
            self.log(f"Error loading history: {e}")
        return set()
    
    def save_history(self):
        """Save seen result URLs to history."""
        try:
            # Load existing history
            existing = self.load_history()
            # Merge with current seen URLs
            all_seen = existing.union(self.seen_urls)
            
            with open(SEARCH_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "seen_urls": list(all_seen),
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            self.log(f"Error saving history: {e}")
    
    def save_results(self):
        """Save current search results."""
        try:
            with open(SEARCH_RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "metrics": self.metrics,
                    "results": self.all_results
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Error saving results: {e}")
    
    def export_to_csv(self):
        """Export interested results to CSV."""
        csv_path = f"legal_automation_opportunities_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Type", "Title", "Company/Author", "Location", "Posted", "URL", "Query Used", "Description"])
                
                for r in INTERESTED_RESULTS:
                    writer.writerow([
                        r.get("type", ""),
                        r.get("title", ""),
                        r.get("company", r.get("author", "")),
                        r.get("location", ""),
                        r.get("posted_date", ""),
                        r.get("url", ""),
                        r.get("query", ""),
                        r.get("description", "")[:500]  # Truncate long descriptions
                    ])
            
            self.log(f"Exported {len(INTERESTED_RESULTS)} results to {csv_path}")
            return csv_path
        except Exception as e:
            self.log(f"Error exporting to CSV: {e}")
            return None
    
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
        self.log("Starting Search Agent...")
        self.log("Initializing Playwright...")
        self.playwright = await async_playwright().start()
        
        try:
            self.log("Attempting to connect to existing Chrome on port 9222...")
            self.browser = await self.playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
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
                    self.browser = await self.playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
                    self.context = self.browser.contexts[0]
                    self.page = await self.context.new_page()
                    self.log("Connected to launched Chrome.")
                    break
                except Exception as e2:
                    self.log(f"Attempt {attempt + 1} failed: {e2}")
                    if attempt == 4:
                        raise e2
        
        # Load history of previously seen results
        self.seen_urls = self.load_history()
        self.log(f"Loaded {len(self.seen_urls)} previously seen URLs from history")
    
    async def search_jobs(self, query):
        """Search LinkedIn Jobs with a Boolean query."""
        self.log(f"Searching jobs: {query}")
        
        # Encode and navigate to jobs search - REMOTE ONLY, GLOBAL (no location filter)
        encoded_query = urllib.parse.quote(query)
        jobs_url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_query}&f_WT=2"
        
        try:
            # ANTI-DETECTION: Use human-like navigation
            await human_like_navigate(self.page, jobs_url)
            
            # ANTI-DETECTION: Human-like scrolling with random pauses
            scroll_times = random.randint(2, 4)
            for _ in range(scroll_times):
                await human_scroll(self.page)
                await human_delay(1.0, 2.5)
            
            # Extract job listings
            job_cards = await self.page.query_selector_all("div.job-card-container, li.jobs-search-results__list-item")
            self.log(f"  Found {len(job_cards)} job cards")
            
            for card in job_cards[:20]:  # Limit per query
                try:
                    # Extract job URL - try multiple selectors
                    job_url = ""
                    title = ""
                    
                    # Try different link selectors
                    url_selectors = [
                        "a.job-card-container__link",
                        "a.job-card-list__title",
                        "a[data-control-name='jobcard_ghost_link']",
                        "a[data-tracking-control-name]",
                        ".job-card-container a"
                    ]
                    
                    for sel in url_selectors:
                        link_el = await card.query_selector(sel)
                        if link_el:
                            href = await link_el.get_attribute("href")
                            if href and href != "#" and "about:blank" not in href:
                                job_url = href
                                # Get title from link if available
                                link_text = await link_el.inner_text()
                                if link_text:
                                    title = link_text.strip().split('\n')[0]
                                break
                    
                    # Fallback: Try to get job ID from data attribute and construct URL
                    if not job_url or job_url == "#":
                        job_id = await card.get_attribute("data-job-id")
                        if not job_id:
                            job_id_el = await card.query_selector("[data-job-id]")
                            if job_id_el:
                                job_id = await job_id_el.get_attribute("data-job-id")
                        
                        if job_id:
                            job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
                    
                    # Ensure full URL
                    if job_url and job_url.startswith("/"):
                        job_url = "https://www.linkedin.com" + job_url
                    
                    # Clean URL - remove tracking params but keep job ID
                    if job_url and "?" in job_url:
                        base_url = job_url.split("?")[0]
                        # Keep the base URL which should have the job ID
                        job_url = base_url
                    
                    # Validate URL
                    if not job_url or "linkedin.com" not in job_url or job_url.endswith("/jobs/") or "about:blank" in job_url:
                        continue
                    
                    # Get title if we don't have it yet
                    if not title:
                        title_selectors = [
                            ".job-card-list__title",
                            ".job-card-container__link strong",
                            "strong",
                            "h3"
                        ]
                        for sel in title_selectors:
                            title_el = await card.query_selector(sel)
                            if title_el:
                                title = await title_el.inner_text()
                                title = title.strip().split('\n')[0]
                                if title:
                                    break
                    
                    # Skip if no valid title or URL
                    if not title or not job_url:
                        continue
                    
                    # Skip if already seen
                    if job_url in self.seen_urls:
                        self.metrics["duplicates_skipped"] += 1
                        continue
                    
                    # Company name - try multiple selectors
                    company = ""
                    company_selectors = [
                        "span.job-card-container__primary-description",
                        "a.job-card-container__company-name",
                        ".job-card-container__company-name",
                        ".artdeco-entity-lockup__subtitle span"
                    ]
                    for sel in company_selectors:
                        company_el = await card.query_selector(sel)
                        if company_el:
                            company = await company_el.inner_text()
                            company = company.strip()
                            if company:
                                break
                    
                    # Location - try multiple selectors
                    location = ""
                    location_selectors = [
                        "li.job-card-container__metadata-item",
                        "span.job-card-container__metadata-wrapper",
                        ".artdeco-entity-lockup__caption span"
                    ]
                    for sel in location_selectors:
                        location_el = await card.query_selector(sel)
                        if location_el:
                            location = await location_el.inner_text()
                            location = location.strip()
                            if location:
                                break
                    
                    # Posted date
                    date_el = await card.query_selector("time, span.job-card-container__listed-time")
                    posted_date = ""
                    if date_el:
                        posted_date = await date_el.inner_text()
                        posted_date = posted_date.strip()
                    
                    result = {
                        "id": f"job_{len(self.all_results)}",
                        "type": "job",
                        "title": title,
                        "company": company,
                        "location": location,
                        "posted_date": posted_date,
                        "url": job_url,
                        "query": query,
                        "description": "",
                        "found_at": datetime.now().isoformat()
                    }
                    
                    self.all_results.append(result)
                    self.job_results.append(result)
                    self.seen_urls.add(job_url)
                    self.metrics["jobs_found"] += 1
                    self.log(f"    ✓ {title[:50]} at {company[:30] if company else 'Unknown'}")
                        
                except Exception as e:
                    self.log(f"    Error extracting job: {e}")
                    continue
            
            self.metrics["queries_executed"] += 1
            
        except Exception as e:
            self.log(f"  Error searching jobs: {e}")
    
    async def search_posts(self, query):
        """Search LinkedIn Posts with a Boolean query."""
        self.log(f"Searching posts: {query}")
        
        # Encode and navigate to posts search
        encoded_query = urllib.parse.quote(query)
        posts_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&origin=GLOBAL_SEARCH_HEADER&sortBy=%22date_posted%22"
        
        try:
            # ANTI-DETECTION: Use human-like navigation
            await human_like_navigate(self.page, posts_url)
            
            # ANTI-DETECTION: Human-like scrolling with random pauses
            scroll_times = random.randint(2, 4)
            for _ in range(scroll_times):
                await human_scroll(self.page)
                await human_delay(1.0, 2.5)
            
            # Extract post results
            post_cards = await self.page.query_selector_all("div.feed-shared-update-v2, div.search-results__cluster-content div[data-urn]")
            self.log(f"  Found {len(post_cards)} post cards")
            
            for card in post_cards[:15]:  # Limit per query
                try:
                    # Get post URN for URL
                    post_urn = await card.get_attribute("data-urn")
                    post_url = ""
                    if post_urn:
                        post_url = f"https://www.linkedin.com/feed/update/{post_urn}/"
                    
                    # Skip if already seen
                    if post_url and post_url in self.seen_urls:
                        self.metrics["duplicates_skipped"] += 1
                        continue
                    
                    # Author name
                    author = "Unknown"
                    author_selectors = [
                        ".update-components-actor__name span span",
                        ".update-components-actor__name span",
                        ".update-components-actor__title span span",
                        "a.app-aware-link span span"
                    ]
                    for sel in author_selectors:
                        author_el = await card.query_selector(sel)
                        if author_el:
                            author = await author_el.inner_text()
                            author = author.strip().split('\n')[0]
                            if author:
                                break
                    
                    # Author headline
                    headline = ""
                    headline_selectors = [
                        ".update-components-actor__description span",
                        ".update-components-actor__description",
                        ".update-components-actor__subtitle span"
                    ]
                    for sel in headline_selectors:
                        headline_el = await card.query_selector(sel)
                        if headline_el:
                            headline = await headline_el.inner_text()
                            headline = headline.strip().split('\n')[0]
                            if headline:
                                break
                    
                    # Post content
                    content = ""
                    content_el = await card.query_selector(".feed-shared-update-v2__description, .feed-shared-text, .update-components-text")
                    if content_el:
                        content = await content_el.inner_text()
                        content = content.strip()
                    
                    # Posted time
                    posted_date = ""
                    date_selectors = [
                        ".update-components-actor__sub-description span[aria-hidden='true']",
                        "time",
                        ".update-components-actor__sub-description"
                    ]
                    for sel in date_selectors:
                        date_el = await card.query_selector(sel)
                        if date_el:
                            posted_date = await date_el.inner_text()
                            posted_date = posted_date.strip()
                            if posted_date:
                                break
                    
                    if post_url:
                        # Filter using Gemini - only include if actively looking for freelancer
                        self.log(f"    Checking post intent with Gemini: {author[:30]}...")
                        is_relevant = self.is_relevant_freelance_post(content, headline)
                        
                        if not is_relevant:
                            self.metrics["posts_filtered"] += 1
                            self.log(f"    ✗ Filtered out (not hiring freelancer): {author[:30]}")
                            continue
                        
                        result = {
                            "id": f"post_{len(self.all_results)}",
                            "type": "post",
                            "title": content[:100] + "..." if len(content) > 100 else content,
                            "author": author,
                            "headline": headline,
                            "location": "",  # Posts don't have explicit location
                            "posted_date": posted_date,
                            "url": post_url,
                            "query": query,
                            "description": content,
                            "found_at": datetime.now().isoformat()
                        }
                        
                        self.all_results.append(result)
                        self.post_results.append(result)
                        self.seen_urls.add(post_url)
                        self.metrics["posts_found"] += 1
                        self.log(f"    ✓ RELEVANT: Post by {author[:30]}: {content[:40]}...")
                        
                except Exception as e:
                    self.log(f"    Error extracting post: {e}")
                    continue
            
            self.metrics["queries_executed"] += 1
            
        except Exception as e:
            self.log(f"  Error searching posts: {e}")
    
    async def run_all_searches(self):
        """Execute all Boolean search combinations with anti-detection measures."""
        self.log("=" * 60)
        self.log("Starting Boolean Search for Legal Automation Opportunities")
        self.log("(Using human-like behavior to avoid detection)")
        self.log("=" * 60)
        
        # Get queries - limit to avoid too many in one session
        job_queries = self.search_generator.generate_job_queries()
        post_queries = self.search_generator.generate_post_queries()
        
        # ANTI-DETECTION: Limit queries per session to look more natural
        max_job_queries = min(len(job_queries), 6)  # Max 6 job searches
        max_post_queries = min(len(post_queries), 5)  # Max 5 post searches
        
        # Randomly select subset of queries for this session
        selected_job_queries = random.sample(job_queries, max_job_queries)
        selected_post_queries = random.sample(post_queries, max_post_queries)
        
        self.log(f"Will execute {len(selected_job_queries)} job queries and {len(selected_post_queries)} post queries")
        self.log("(Reduced from full set to avoid detection)")
        
        # Search Jobs with natural pacing
        self.log("\n--- JOBS SEARCH ---")
        for i, query in enumerate(selected_job_queries):
            await self.search_jobs(query)
            
            # ANTI-DETECTION: Variable delay between queries (5-15 seconds)
            delay = random.uniform(5, 15)
            self.log(f"  [Pause {delay:.1f}s before next search...]")
            await asyncio.sleep(delay)
            
            # ANTI-DETECTION: Extra long pause every 3 queries
            if (i + 1) % 3 == 0 and i + 1 < len(selected_job_queries):
                extra_pause = random.uniform(20, 40)
                self.log(f"  [Extended break {extra_pause:.0f}s...]")
                await asyncio.sleep(extra_pause)
        
        # ANTI-DETECTION: Long pause between job and post searches
        transition_pause = random.uniform(30, 60)
        self.log(f"\n[Transition pause {transition_pause:.0f}s before posts...]")
        await asyncio.sleep(transition_pause)
        
        # Search Posts with natural pacing
        self.log("\n--- POSTS SEARCH ---")
        for i, query in enumerate(selected_post_queries):
            await self.search_posts(query)
            
            # ANTI-DETECTION: Variable delay between queries (5-15 seconds)
            delay = random.uniform(5, 15)
            self.log(f"  [Pause {delay:.1f}s before next search...]")
            await asyncio.sleep(delay)
            
            # ANTI-DETECTION: Extra long pause every 3 queries
            if (i + 1) % 3 == 0 and i + 1 < len(selected_post_queries):
                extra_pause = random.uniform(20, 40)
                self.log(f"  [Extended break {extra_pause:.0f}s...]")
                await asyncio.sleep(extra_pause)
        
        # Save results and history
        self.save_results()
        self.save_history()
        
        self.log("\n" + "=" * 60)
        self.log("SEARCH COMPLETE")
        self.log(f"  Queries executed: {self.metrics['queries_executed']}")
        self.log(f"  Jobs found: {self.metrics['jobs_found']} (Remote only, Global)")
        self.log(f"  Posts found: {self.metrics['posts_found']} (Gemini-filtered as relevant)")
        self.log(f"  Posts filtered out: {self.metrics['posts_filtered']}")
        self.log(f"  Duplicates skipped: {self.metrics['duplicates_skipped']}")
        self.log(f"  Total unique results: {len(self.all_results)}")
        self.log("=" * 60)
    
    def generate_review_html(self):
        """Generate accessible HTML review page."""
        
        # Build job cards
        job_cards_html = ""
        for i, result in enumerate(self.job_results):
            title = result.get('title', '').replace('<', '&lt;').replace('>', '&gt;')
            company = result.get('company', '').replace('<', '&lt;').replace('>', '&gt;')
            location = result.get('location', '').replace('<', '&lt;').replace('>', '&gt;')
            posted = result.get('posted_date', '').replace('<', '&lt;').replace('>', '&gt;')
            query = result.get('query', '').replace('<', '&lt;').replace('>', '&gt;')
            url = result.get('url', '')
            result_id = result.get('id', f'job_{i}')
            
            job_cards_html += f'''
            <article class="result-card job-card" role="article" aria-labelledby="job-title-{i}" data-result-id="{result_id}">
                <div class="result-type-badge job-badge" aria-label="Job listing">📋 JOB</div>
                <header class="result-header">
                    <h3 id="job-title-{i}" class="result-title">{title}</h3>
                    <p class="result-meta"><strong>{company}</strong> | {location}</p>
                    <p class="result-date">Posted: {posted}</p>
                    <p class="result-query" aria-label="Found using query">Query: <code>{query}</code></p>
                </header>
                <div class="result-actions" role="group" aria-label="Actions for this job">
                    <label class="checkbox-label">
                        <input type="checkbox" class="interested-checkbox" data-id="{result_id}" aria-label="Mark as interested">
                        <span>★ Interested</span>
                    </label>
                    <a href="{url}" target="_blank" rel="noopener" class="btn btn-view" aria-label="View job on LinkedIn">
                        View on LinkedIn →
                    </a>
                </div>
            </article>
            '''
        
        # Build post cards
        post_cards_html = ""
        for i, result in enumerate(self.post_results):
            author = result.get('author', '').replace('<', '&lt;').replace('>', '&gt;')
            headline = result.get('headline', '').replace('<', '&lt;').replace('>', '&gt;')
            content = result.get('description', '')[:300].replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
            posted = result.get('posted_date', '').replace('<', '&lt;').replace('>', '&gt;')
            query = result.get('query', '').replace('<', '&lt;').replace('>', '&gt;')
            url = result.get('url', '')
            result_id = result.get('id', f'post_{i}')
            
            post_cards_html += f'''
            <article class="result-card post-card" role="article" aria-labelledby="post-title-{i}" data-result-id="{result_id}">
                <div class="result-type-badge post-badge" aria-label="LinkedIn post">📝 POST</div>
                <header class="result-header">
                    <h3 id="post-title-{i}" class="result-title">{author}</h3>
                    <p class="result-meta">{headline}</p>
                    <p class="result-date">Posted: {posted}</p>
                    <p class="result-query" aria-label="Found using query">Query: <code>{query}</code></p>
                </header>
                <div class="result-content">
                    <p>{content}...</p>
                </div>
                <div class="result-actions" role="group" aria-label="Actions for this post">
                    <label class="checkbox-label">
                        <input type="checkbox" class="interested-checkbox" data-id="{result_id}" aria-label="Mark as interested">
                        <span>★ Interested</span>
                    </label>
                    <a href="{url}" target="_blank" rel="noopener" class="btn btn-view" aria-label="View post on LinkedIn">
                        View on LinkedIn →
                    </a>
                </div>
            </article>
            '''
        
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Legal Automation Opportunities - LinkedIn Search Results</title>
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
            --warning-orange: #b24020;
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
            padding: 0;
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
        
        header.main-header {{
            background: linear-gradient(135deg, var(--linkedin-blue) 0%, var(--linkedin-blue-dark) 100%);
            color: white;
            padding: 24px;
            text-align: center;
        }}
        
        header.main-header h1 {{
            margin: 0 0 8px 0;
            font-size: 1.75rem;
        }}
        
        .stats-bar {{
            display: flex;
            justify-content: center;
            gap: 24px;
            flex-wrap: wrap;
            margin-top: 16px;
        }}
        
        .stat-item {{
            background: rgba(255,255,255,0.1);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9rem;
        }}
        
        main {{
            max-width: 900px;
            margin: 0 auto;
            padding: 24px;
        }}
        
        .section-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 32px 0 16px 0;
            padding-bottom: 8px;
            border-bottom: 2px solid var(--border-color);
        }}
        
        .section-header h2 {{
            margin: 0;
            font-size: 1.25rem;
        }}
        
        .result-card {{
            background: var(--bg-card);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            position: relative;
        }}
        
        .result-type-badge {{
            position: absolute;
            top: 12px;
            right: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 12px;
        }}
        
        .job-badge {{
            background: #e8f4fd;
            color: var(--linkedin-blue);
        }}
        
        .post-badge {{
            background: #fff3e8;
            color: var(--warning-orange);
        }}
        
        .result-header {{
            margin-bottom: 12px;
        }}
        
        .result-title {{
            margin: 0 0 8px 0;
            font-size: 1.1rem;
            color: var(--text-primary);
            padding-right: 80px;
        }}
        
        .result-meta {{
            margin: 0 0 4px 0;
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}
        
        .result-date {{
            margin: 0 0 4px 0;
            color: var(--text-secondary);
            font-size: 0.85rem;
        }}
        
        .result-query {{
            margin: 8px 0;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}
        
        .result-query code {{
            background: #f0f0f0;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.75rem;
        }}
        
        .result-content {{
            background: #f9f9f9;
            padding: 12px;
            border-radius: 8px;
            margin: 12px 0;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }}
        
        .result-actions {{
            display: flex;
            gap: 12px;
            align-items: center;
            flex-wrap: wrap;
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid var(--border-color);
        }}
        
        .checkbox-label {{
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            padding: 8px 16px;
            background: #f0f0f0;
            border-radius: 20px;
            transition: all 0.2s;
        }}
        
        .checkbox-label:hover {{
            background: #e0e0e0;
        }}
        
        .checkbox-label input:checked + span {{
            color: var(--success-green);
            font-weight: 600;
        }}
        
        .checkbox-label input {{
            width: 18px;
            height: 18px;
            cursor: pointer;
        }}
        
        .btn {{
            display: inline-flex;
            align-items: center;
            padding: 8px 16px;
            border-radius: 20px;
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 500;
            transition: all 0.2s;
        }}
        
        .btn:focus {{
            outline: none;
            box-shadow: var(--focus-ring);
        }}
        
        .btn-view {{
            background: var(--linkedin-blue);
            color: white;
        }}
        
        .btn-view:hover {{
            background: var(--linkedin-blue-dark);
        }}
        
        .bottom-actions {{
            display: flex;
            justify-content: center;
            gap: 16px;
            margin: 32px 0;
            padding: 24px;
            background: var(--bg-card);
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        
        .btn-primary {{
            background: var(--success-green);
            color: white;
            padding: 12px 24px;
            font-size: 1rem;
            border: none;
            cursor: pointer;
        }}
        
        .btn-primary:hover {{
            background: #045a35;
        }}
        
        .btn-secondary {{
            background: #666;
            color: white;
            padding: 12px 24px;
            font-size: 1rem;
            border: none;
            cursor: pointer;
        }}
        
        .btn-secondary:hover {{
            background: #444;
        }}
        
        .no-results {{
            text-align: center;
            padding: 40px;
            color: var(--text-secondary);
        }}
        
        #interested-count {{
            font-weight: 600;
        }}
        
        @media (max-width: 600px) {{
            .result-actions {{
                flex-direction: column;
                align-items: stretch;
            }}
            
            .bottom-actions {{
                flex-direction: column;
            }}
        }}
    </style>
</head>
<body>
    <header class="main-header" role="banner">
        <h1>🔍 Legal Automation Opportunities</h1>
        <p>LinkedIn Boolean Search Results (Gemini-Filtered)</p>
        <div class="stats-bar" role="status" aria-live="polite">
            <span class="stat-item">📝 Posts: {len(self.post_results)} (Hiring Freelancers)</span>
            <span class="stat-item">📋 Jobs: {len(self.job_results)} (Remote Global)</span>
            <span class="stat-item">⭐ Interested: <span id="interested-count">0</span></span>
        </div>
    </header>
    
    <main role="main">
        <section aria-labelledby="posts-section">
            <div class="section-header">
                <h2 id="posts-section">📝 Freelance Opportunities - LinkedIn Posts ({len(self.post_results)})</h2>
            </div>
            {post_cards_html if post_cards_html else '<p class="no-results">No relevant freelance hiring posts found.</p>'}
        </section>
        
        <section aria-labelledby="jobs-section">
            <div class="section-header">
                <h2 id="jobs-section">📋 Remote Job Listings - Global ({len(self.job_results)})</h2>
            </div>
            {job_cards_html if job_cards_html else '<p class="no-results">No job listings found.</p>'}
        </section>
        
        <div class="bottom-actions">
            <button class="btn btn-primary" onclick="exportCSV()" aria-describedby="export-help">
                📥 Export Interested to CSV
            </button>
            <span id="export-help" class="sr-only">Export all marked items to a CSV file</span>
            
            <button class="btn btn-secondary" onclick="shutdown()" aria-describedby="close-help">
                ✖ Done & Close
            </button>
            <span id="close-help" class="sr-only">Close the review screen</span>
        </div>
    </main>
    
    <script>
        let interestedCount = 0;
        
        // Handle checkbox changes
        document.querySelectorAll('.interested-checkbox').forEach(checkbox => {{
            checkbox.addEventListener('change', async function() {{
                const resultId = this.dataset.id;
                const interested = this.checked;
                
                try {{
                    const response = await fetch('/mark_interested', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{result_id: resultId, interested: interested}})
                    }});
                    const data = await response.json();
                    document.getElementById('interested-count').textContent = data.count;
                }} catch (e) {{
                    console.error('Error marking interested:', e);
                }}
            }});
        }});
        
        async function exportCSV() {{
            try {{
                const response = await fetch('/export_csv', {{method: 'POST'}});
                const data = await response.json();
                if (data.status === 'ok') {{
                    alert('Exported to: ' + data.path);
                }} else {{
                    alert('Export failed');
                }}
            }} catch (e) {{
                console.error('Export error:', e);
                alert('Export failed: ' + e.message);
            }}
        }}
        
        async function shutdown() {{
            if (confirm('Close the review screen?')) {{
                try {{
                    await fetch('/shutdown', {{method: 'POST'}});
                    window.close();
                }} catch (e) {{
                    window.close();
                }}
            }}
        }}
    </script>
</body>
</html>'''
        
        with open(REVIEW_HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        self.log(f"Generated review HTML: {REVIEW_HTML_FILE}")
    
    async def run(self):
        """Main entry point."""
        try:
            await self.start()
            await self.run_all_searches()
            
            if len(self.all_results) == 0:
                self.log("No results found. Exiting.")
                return
            
            # Generate review HTML
            self.generate_review_html()
            
            # Play sound alert
            play_ready_sound()
            
            # Start review server
            port = 8889
            server = HTTPServer(('127.0.0.1', port), ReviewHandler)
            server.timeout = 1
            
            self.log(f"\n★ Review ready at: http://127.0.0.1:{port}")
            self.log("  Opening in automation browser...")
            
            # Open in the SAME Chrome browser where search was performed
            review_url = f"http://127.0.0.1:{port}"
            try:
                # Create new tab in the automation browser
                review_page = await self.context.new_page()
                await review_page.goto(review_url)
                self.log("  Review page opened in automation Chrome.")
            except Exception as e:
                self.log(f"  Could not open in automation browser: {e}")
                self.log(f"  Please manually open: {review_url}")
            
            # Serve until shutdown
            while not SHUTDOWN_EVENT.is_set():
                server.handle_request()
            
            play_complete_sound()
            self.log("\nSearch session complete!")
            self.log(f"  Total unique results: {len(self.all_results)}")
            self.log(f"  Marked as interested: {len(INTERESTED_RESULTS)}")
            
        except Exception as e:
            self.log(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.browser:
                try:
                    await self.browser.close()
                except:
                    pass
            if self.playwright:
                try:
                    await self.playwright.stop()
                except:
                    pass


if __name__ == "__main__":
    print("DEBUG: Script started", flush=True)
    try:
        agent = SearchAgent()
        asyncio.run(agent.run())
    except Exception as e:
        print(f"DEBUG: Critical error in main: {e}", flush=True)
        import traceback
        traceback.print_exc()
