"""
LinkedIn Post Creation Agent
=============================
Automates LinkedIn post creation using Opal.google for content generation.
Reads content from CSV, generates posts via Opal, and creates LinkedIn drafts.

Features:
- Reads content schedule from contend.csv
- Uses Opal.google to generate posts with images
- Downloads generated content
- Creates LinkedIn post drafts with images and alt text
- Plays notification sound when ready

Author: AI Agent
Created: 2026-01-09
"""

import asyncio
import os
import csv
import re
import socket
import subprocess
import winsound
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from google import genai

# Load environment variables
load_dotenv()

# Configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(SCRIPT_DIR, "contend.csv")
OPAL_URL = "https://opal.google/?flow=drive:/1ts3HOs0wvb0gMQ_l66ViVEqpODDLKfrQ&mode=canvas"
LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"
LOG_FILE = os.path.join(SCRIPT_DIR, "post_creation_log.txt")

# Chrome automation profile
CHROME_USER_DATA_DIR = r"C:\ChromeAutomationProfile"


def play_notification_sound():
    """Play ascending tones when post is ready for review."""
    try:
        winsound.Beep(523, 200)   # C5
        winsound.Beep(659, 200)   # E5
        winsound.Beep(784, 200)   # G5
        winsound.Beep(1047, 400)  # C6 (longer)
    except Exception as e:
        print(f"Could not play sound: {e}")


class PostCreationAgent:
    """Agent that creates LinkedIn posts using Opal.google for content generation."""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.chrome_pid = None
        self.post_content = None
        self.post_image_path = None
        self.post_alt_text = None
        
        # Gemini AI client
        self.genai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_name = "gemini-2.0-flash"
        
        # Content tracking
        self.current_topic = None
        self.generated_content = None
        self.generated_image_path = None

    def log(self, msg):
        """Log message to console and file."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_msg = f"[{timestamp}] {msg}"
        print(log_msg, flush=True)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_msg + "\n")
        except Exception:
            pass

    def load_csv_content(self):
        """Load content from CSV file."""
        content_rows = []
        try:
            with open(CSV_FILE, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    content_rows.append(row)
            self.log(f"Loaded {len(content_rows)} content rows from CSV")
        except Exception as e:
            self.log(f"Error loading CSV: {e}")
        return content_rows

    def get_todays_content(self):
        """Get the content row for today's date."""
        content_rows = self.load_csv_content()
        today = datetime.now()
        today_str = today.strftime("%b %d")  # e.g., "Jan 09"
        
        for row in content_rows:
            date_str = row.get("Date", "")
            if today_str in date_str:
                self.log(f"Found today's content: {row.get('Topic', 'Unknown')}")
                return row
        
        # If no match for today, return first row
        if content_rows:
            self.log(f"No content for today, using first row: {content_rows[0].get('Topic', 'Unknown')}")
            return content_rows[0]
        
        return None

    async def launch_browser(self):
        """Launch Chrome with remote debugging enabled."""
        self.log("Checking for existing Chrome processes on port 9222...")
        
        # Check and kill any existing process on port 9222
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

        cmd = [
            chrome_path,
            "--remote-debugging-port=9222",
            f"--user-data-dir={CHROME_USER_DATA_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-client-side-phishing-detection",
            "--disable-hang-monitor",
            "--start-maximized",
            "--window-size=1920,1080",
            "--window-position=0,0"
        ]

        self.log("Launching Chrome...")
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
            except Exception:
                pass

        self.log("WARNING: Chrome launched but port 9222 not detected after 15s")
        return False

    def kill_stale_chrome(self):
        """Kill any Chrome process listening on port 9222."""
        self.log("Checking for stale Chrome processes...")
        try:
            # Find PID using port 9222
            cmd = "netstat -ano | findstr :9222"
            try:
                output = subprocess.check_output(cmd, shell=True).decode()
                for line in output.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 5 and "LISTENING" in line:
                        pid = parts[-1]
                        self.log(f"Killing stale Chrome PID {pid}")
                        subprocess.run(f"taskkill /PID {pid} /F", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                pass # No process found
        except Exception as e:
            self.log(f"Error checking stale chrome: {e}")

    async def start(self):
        """Initialize browser connection - always launch fresh."""
        self.log("Starting Post Creation Agent...")
        self.kill_stale_chrome()
        
        self.log("Initializing Playwright...")
        self.playwright = await async_playwright().start()

        self.log("Launching new Chrome instance...")
        if not await self.launch_browser():
            raise Exception("Could not launch Chrome")

        # Connect to the newly launched browser
        for attempt in range(5):
            await asyncio.sleep(3)
            try:
                self.log(f"Connection attempt {attempt + 1}/5...")
                self.browser = await self.playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
                self.context = self.browser.contexts[0]
                self.page = await self.context.new_page()
                self.log("Connected to launched Chrome.")
                
                # Bring to front hack
                await self.page.evaluate("window.focus()")
                return
            except Exception as e2:
                self.log(f"Attempt {attempt + 1} failed: {e2}")
                if attempt == 4:
                    raise e2

    async def navigate_to_opal(self):
        """Navigate to Opal.google and handle sign-in if needed."""
        self.log("Navigating to Opal.google...")
        try:
            await self.page.goto(OPAL_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(10)  # Wait for page to fully load
            
            # Check if sign-in is required
            sign_in_btn = await self.page.query_selector("button#sign-in-button, button:has-text('Sign in with Google')")
            if sign_in_btn:
                self.log("Sign-in required. Clicking Sign in with Google...")
                await sign_in_btn.click()
                await asyncio.sleep(15)  # Wait for sign-in flow and page reload
            
            self.log("Opal page loaded successfully.")
            return True
        except Exception as e:
            self.log(f"Error navigating to Opal: {e}")
            return False

    async def click_start_button(self):
        """Find and click the Start button on Opal (handles Shadow DOM)."""
        self.log("Looking for Start button (with Shadow DOM support)...")
        
        # Use JavaScript to find and click the button in shadow DOM
        js_code = """
        (() => {
            function findDeep(root, id) {
                if (root.id === id) return root;
                if (root.querySelector) {
                    const el = root.querySelector('#' + id);
                    if (el) return el;
                }
                
                // Check shadow roots
                const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                for (const node of all) {
                    if (node.shadowRoot) {
                        const found = findDeep(node.shadowRoot, id);
                        if (found) return found;
                    }
                }
                
                // Check iframes
                const iframes = root.querySelectorAll ? root.querySelectorAll('iframe') : [];
                for (const iframe of iframes) {
                    try {
                        const found = findDeep(iframe.contentDocument || iframe.contentWindow.document, id);
                        if (found) return found;
                    } catch (e) {}
                }
                
                return null;
            }

            const btn = findDeep(document, 'run');
            if (btn) {
                btn.click();
                return { success: true, text: btn.textContent };
            }
            return { success: false };
        })()
        """
        
        try:
            result = await self.page.evaluate(js_code)
            if result.get("success"):
                self.log(f"Clicked Start button via JavaScript: {result.get('text', 'Start')}")
                await asyncio.sleep(5)  # Wait for first input to appear
                return True
            else:
                self.log("Start button not found via JavaScript search")
        except Exception as e:
            self.log(f"JavaScript click failed: {e}")
        
        self.log("Could not find Start button. Taking screenshot for debugging...")
        await self.page.screenshot(path=os.path.join(SCRIPT_DIR, "opal_debug.png"))
        return False

    async def input_content(self, content_row):
        """Input content from CSV row into Opal interface (handles Shadow DOM)."""
        self.current_topic = content_row.get("Topic", "Untitled")
        self.log(f"Inputting content for topic: {self.current_topic}")
        
        # Opal workflow fields in order: Date, Topic, Hook, Content Instructions, CTA
        fields = [
            ("Date", content_row.get("Date", "")),
            ("Topic", content_row.get("Topic", "")),
            ("Hook", content_row.get("Hook", "")),
            ("Content Instructions", content_row.get("Content Instructions", "")),
            ("CTA", content_row.get("CTA", ""))
        ]
        
        self.log(f"Total fields to process: {len(fields)}")
        for i, (field_name, value) in enumerate(fields):
            self.log(f"Processing field {i+1}/{len(fields)}: {field_name}")
            if not value:
                self.log(f"  Skipping {field_name} - empty value")
                continue
            
            self.log(f"Entering {field_name}: {value[:50]}...")
            
            # Use JavaScript to find and fill input in shadow DOM
            js_input = f"""
            (() => {{
                function findDeep(root, id) {{
                    if (root.id === id) return root;
                    if (root.querySelector) {{
                        const el = root.querySelector('#' + id);
                        if (el) return el;
                    }}
                    const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                    for (const node of all) {{
                        if (node.shadowRoot) {{
                            const found = findDeep(node.shadowRoot, id);
                            if (found) return found;
                        }}
                    }}
                    const iframes = root.querySelectorAll ? root.querySelectorAll('iframe') : [];
                    for (const iframe of iframes) {{
                        try {{
                            const found = findDeep(iframe.contentDocument || iframe.contentWindow.document, id);
                            if (found) return found;
                        }} catch (e) {{}}
                    }}
                    return null;
                }}

                const input = findDeep(document, 'text-input');
                if (input) {{
                    input.focus();
                    input.value = {repr(value)};
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    return {{ success: true }};
                }}
                return {{ success: false }};
            }})()
            """
            
            try:
                result = await self.page.evaluate(js_input)
                if result.get("success"):
                    self.log(f"Entered {field_name} via JavaScript")
                    await asyncio.sleep(1)
                    
                    # Click Continue/Next after each input
                    await self.click_next_button()
                else:
                    self.log(f"Could not find input field for {field_name}")
            except Exception as e:
                self.log(f"Error inputting {field_name}: {e}")

    async def click_next_button(self):
        """Click the Continue/Next button (handles Shadow DOM)."""
        self.log("Clicking Continue button...")
        
        # Use JavaScript to find and click button in shadow DOM
        js_code = """
        (() => {
            function findDeep(root, id) {
                if (root.id === id) return root;
                if (root.querySelector) {
                    const el = root.querySelector('#' + id);
                    if (el) return el;
                }
                const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                for (const node of all) {
                    if (node.shadowRoot) {
                        const found = findDeep(node.shadowRoot, id);
                        if (found) return found;
                    }
                }
                const iframes = root.querySelectorAll ? root.querySelectorAll('iframe') : [];
                for (const iframe of iframes) {
                    try {
                        const found = findDeep(iframe.contentDocument || iframe.contentWindow.document, id);
                        if (found) return found;
                    } catch (e) {}
                }
                return null;
            }

            const btn = findDeep(document, 'continue');
            if (btn) {
                btn.click();
                return { success: true };
            }
            return { success: false };
        })()
        """
        
        try:
            result = await self.page.evaluate(js_code)
            if result.get("success"):
                self.log("Clicked Continue button via JavaScript")
                await asyncio.sleep(3)  # Wait for next input to appear
                return True
            else:
                self.log("Continue button not found via JavaScript")
        except Exception as e:
            self.log(f"JavaScript click failed: {e}")
        
        return False

    async def wait_for_generation(self):
        """Wait for post generation to complete (handles Shadow DOM)."""
        self.log("Waiting for post generation...")
        
        max_wait = 180  # 3 minutes max (AI generation can take time)
        wait_interval = 10
        total_waited = 0
        
        # JavaScript to check for download button in shadow DOM
        js_check = """
        (() => {
            function findDeep(root, id) {
                if (root.id === id) return root;
                if (root.querySelector) {
                    const el = root.querySelector('#' + id);
                    if (el) return el;
                }
                const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                for (const node of all) {
                    if (node.shadowRoot) {
                        const found = findDeep(node.shadowRoot, id);
                        if (found) return found;
                    }
                }
                const iframes = root.querySelectorAll ? root.querySelectorAll('iframe') : [];
                for (const iframe of iframes) {
                    try {
                        const found = findDeep(iframe.contentDocument || iframe.contentWindow.document, id);
                        if (found) return found;
                    } catch (e) {}
                }
                return null;
            }

            const btn = findDeep(document, 'export-output-button');
            return { found: !!btn };
        })()
        """
        
        while total_waited < max_wait:
            try:
                await asyncio.sleep(wait_interval)
                total_waited += wait_interval
                self.log(f"Checking for completion... ({total_waited}s)")
                
                try:
                    result = await self.page.evaluate(js_check)
                    if result and result.get("found"):
                        self.log("Generation complete! Found export-output-button")
                        await asyncio.sleep(5)  # Extra wait to ensure content is fully rendered
                        return True
                    else:
                        self.log(f"Still generating... ({total_waited}s)")
                except Exception as js_err:
                    self.log(f"JavaScript evaluation error: {js_err}")
                    # Continue waiting even if JS fails
            except Exception as loop_err:
                self.log(f"Wait loop error: {loop_err}")
                # Don't break, continue waiting
        
        self.log("Generation timeout. Taking screenshot...")
        await self.page.screenshot(path=os.path.join(SCRIPT_DIR, "opal_timeout.png"))
        return False

    async def download_post(self):
        """Extract the generated post content directly from Opal (handles frames)."""
        self.log("Extracting generated post content...")
        
        # Take a preview screenshot first
        safe_topic = re.sub(r'[\\/*?:"<>|]', "_", self.current_topic)
        preview_path = os.path.join(SCRIPT_DIR, f"{safe_topic}_preview.png")
        await self.page.screenshot(path=preview_path)
        self.log(f"Saved preview screenshot to: {safe_topic}_preview.png")
        
        all_text_found = []
        
        # Method 1: Try to get text from main page
        try:
            main_text = await self.page.inner_text("body")
            if main_text:
                all_text_found.append(("main", main_text))
                self.log(f"Main page text: {len(main_text)} chars")
        except Exception as e:
            self.log(f"Main page text extraction failed: {e}")
        
        # Method 2: Try all frames
        try:
            frames = self.page.frames
            self.log(f"Found {len(frames)} frames")

            for i, frame in enumerate(frames):
                try:
                    frame_text = await frame.inner_text("body")
                    if frame_text and len(frame_text) > 50:
                        all_text_found.append((f"frame_{i}", frame_text))
                        self.log(f"Frame {i} text: {len(frame_text)} chars")
                except Exception:
                    pass
        except Exception as e:
            self.log(f"Frame extraction failed: {e}")
        
        # Method 3: Try Playwright's locator with text content
        try:
            # Try to find paragraphs
            paragraphs = await self.page.locator("p").all_inner_texts()
            if paragraphs:
                para_text = "\n\n".join([p for p in paragraphs if len(p) > 50])
                if para_text:
                    all_text_found.append(("paragraphs", para_text))
                    self.log(f"Paragraphs: {len(para_text)} chars")
        except Exception as e:
            self.log(f"Paragraph extraction failed: {e}")
        
        # Method 4: Try divs
        try:
            divs = await self.page.locator("div").all_inner_texts()
            if divs:
                # Filter for post-like content
                post_divs = [d for d in divs if len(d) > 100 and 
                            '.' in d and 
                            'contents:' not in d and 
                            '{...}' not in d and
                            'role:' not in d]
                if post_divs:
                    all_text_found.append(("divs", "\n\n".join(post_divs[:5])))
                    self.log(f"Filtered divs: {len(post_divs)} items")
        except Exception as e:
            self.log(f"Div extraction failed: {e}")
        
        # Find the best content from all extracted text
        post_content = ""
        for source, text in all_text_found:
            # Filter out JSON/debug content
            lines = text.split('\n')
            good_lines = []
            for line in lines:
                line = line.strip()
                # Skip JSON/debug patterns
                if not line or len(line) < 30:
                    continue
                # Skip JSON/API patterns
                if any(x in line for x in ['contents:', '{...}', '[...]', 'role:', 
                       'safetySettings', 'HARM_CATEGORY', 'fileUri', 'mimeType',
                       'threshold:', 'generationConfig', '0:', '1:', '2:']):
                    continue
                # Skip CSS/JavaScript code patterns
                if any(x in line for x in ['card-bg', 'rgba(', 'document.addEventListener',
                       'classList', 'DOMContentLoaded', '=>', '//', 'function(',
                       'const ', 'let ', 'var ', '};', '});', 'querySelector',
                       'background:', 'font-size:', 'margin:', 'padding:']):
                    continue
                # Skip lines that look like code (contain multiple special chars)
                code_chars = sum(1 for c in line if c in '{}[]();=>')
                if code_chars > 3:
                    continue
                # Keep lines that look like post content
                if '.' in line or '!' in line or '?' in line:
                    good_lines.append(line)
            
            filtered = '\n\n'.join(good_lines)
            if len(filtered) > len(post_content):
                post_content = filtered
                self.log(f"Best content from {source}: {len(filtered)} chars")
        
        if post_content and len(post_content) > 100:
            self.log(f"Final extracted content: {len(post_content)} chars")
            
            # Store and save content
            self.post_content = post_content
            content_path = os.path.join(SCRIPT_DIR, f"{safe_topic}_content.txt")
            with open(content_path, 'w', encoding='utf-8') as f:
                f.write(post_content)
            self.log(f"Saved content to: {content_path}")
            
            # Extract image from frames
            self.log("Searching for post image in frames...")
            self.post_image_path = None
            
            try:
                frames = self.page.frames
                candidates = []
                
                for i, frame in enumerate(frames):
                    try:
                        # Find all images in this frame
                        images = await frame.locator("img").all()
                        for img in images:
                            try:
                                src = await img.get_attribute("src")
                                if not src:
                                    continue
                                
                                # Get attributes
                                alt_txt = await img.get_attribute("alt")
                                aria_label = await img.get_attribute("aria-label")
                                title = await img.get_attribute("title")
                                
                                # Determine effective alt text
                                effective_alt = alt_txt or aria_label or title or ""
                                
                                # Skip small icons/avatars/profile pics (Google User Content)
                                if any(x in src.lower() for x in ['icon', 'logo', 'avatar', 'data:', 'lh3.googleusercontent.com']):
                                    continue

                                # Skip if alt text looks like a URL (common in some frames)
                                if effective_alt.startswith("http") or len(effective_alt) < 5:
                                     # Still a candidate image, but low quality alt
                                     pass
                                
                                candidates.append({
                                    "frame_index": i,
                                    "src": src,
                                    "alt": effective_alt
                                })
                                self.log(f"Candidate frame {i}: {src[:30]}... | Alt: {effective_alt[:50]}...")
                                    
                            except Exception as img_err:
                                continue
                    except Exception:
                        pass
                
                # Select best candidate
                best_candidate = None
                for cand in candidates:
                    # Prefer candidate with meaningful alt text
                    if cand["alt"] and not cand["alt"].startswith("http") and " " in cand["alt"]:
                         if best_candidate is None or len(cand["alt"]) > len(best_candidate["alt"]):
                             best_candidate = cand
                
                # If no good alt text, just take the first valid image
                if not best_candidate and candidates:
                    best_candidate = candidates[0]
                
                if best_candidate:
                    self.log(f"Selected best image from frame {best_candidate['frame_index']}")
                    import urllib.request
                    image_path = os.path.join(SCRIPT_DIR, f"{safe_topic}_image.png")
                    
                    if best_candidate["src"].startswith("http"):
                        urllib.request.urlretrieve(best_candidate["src"], image_path)
                        self.post_image_path = image_path
                        self.post_alt_text = best_candidate["alt"]
                        self.log(f"Saved image to: {image_path}")
                        if self.post_alt_text:
                            self.log(f"Found explicit Alt Text: {self.post_alt_text}")

            except Exception as e:
                self.log(f"Image extraction failed: {e}")
            
            if not self.post_image_path:
                self.log("No downloadable image found in frames")
            
            return content_path
        
        self.log(f"Could not extract meaningful content. Total text sources found: {len(all_text_found)}")
        if all_text_found:
            for source, text in all_text_found[:2]:
                self.log(f"  {source}: first 200 chars: {text[:200]}...")
        
        self.log("Taking debug screenshot...")
        await self.page.screenshot(path=os.path.join(SCRIPT_DIR, "opal_content_debug.png"))
        return None

    async def extract_content_from_page(self, html_path):
        """Open downloaded HTML and extract post text and image."""
        self.log(f"Extracting content from: {html_path}")
        
        try:
            # Open the downloaded HTML in a new page
            extraction_page = await self.context.new_page()
            await extraction_page.goto(f"file:///{html_path.replace(os.sep, '/')}", timeout=30000)
            await asyncio.sleep(3)
            
            # Extract text content
            content_selectors = [
                ".post-content",
                ".generated-text",
                ".content-body",
                "article",
                "main",
                "body"
            ]
            
            post_text = ""
            for selector in content_selectors:
                try:
                    el = await extraction_page.query_selector(selector)
                    if el:
                        post_text = await el.inner_text()
                        if post_text and len(post_text) > 50:
                            self.log(f"Extracted text ({len(post_text)} chars)")
                            break
                except Exception:
                    continue
            
            # Extract image
            img_selectors = [
                "img.post-image",
                "img.generated-image",
                "img:not([src^='data:'])",
                "img"
            ]
            
            image_src = None
            for selector in img_selectors:
                try:
                    img = await extraction_page.query_selector(selector)
                    if img:
                        image_src = await img.get_attribute("src")
                        if image_src:
                            self.log(f"Found image: {image_src[:50]}...")
                            break
                except Exception:
                    continue
            
            # Extract alt text
            alt_text = ""
            if image_src:
                try:
                    img = await extraction_page.query_selector(f"img[src='{image_src}']")
                    if img:
                        alt_text = await img.get_attribute("alt") or ""
                except Exception:
                    pass
            
            await extraction_page.close()
            
            self.generated_content = post_text
            return {
                "text": post_text,
                "image_src": image_src,
                "alt_text": alt_text
            }
            
        except Exception as e:
            self.log(f"Error extracting content: {e}")
            return None

    async def save_image(self, image_src):
        """Save the image with topic name."""
        if not image_src:
            self.log("No image source to save")
            return None
        
        safe_topic = re.sub(r'[\\/*?:"<>|]', "_", self.current_topic)
        image_path = os.path.join(SCRIPT_DIR, f"{safe_topic}.png")
        
        try:
            # If it's a data URL, decode and save
            if image_src.startswith("data:image"):
                import base64
                header, data = image_src.split(",", 1)
                img_data = base64.b64decode(data)
                with open(image_path, "wb") as f:
                    f.write(img_data)
                self.log(f"Saved image to: {image_path}")
            elif image_src.startswith("http"):
                # Download from URL
                import urllib.request
                urllib.request.urlretrieve(image_src, image_path)
                self.log(f"Downloaded image to: {image_path}")
            elif os.path.exists(image_src):
                # Copy local file
                import shutil
                shutil.copy(image_src, image_path)
                self.log(f"Copied image to: {image_path}")
            
            self.generated_image_path = image_path
            return image_path
            
        except Exception as e:
            self.log(f"Error saving image: {e}")
            return None

    async def navigate_to_linkedin(self):
        """Navigate to LinkedIn."""
        self.log("Navigating to LinkedIn...")
        try:
            await self.page.goto(LINKEDIN_FEED_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5)
            self.log("LinkedIn feed loaded.")
            return True
        except Exception as e:
            self.log(f"Error navigating to LinkedIn: {e}")
            return False

    async def click_start_post(self):
        """Click 'Start a post' button on LinkedIn."""
        self.log("Looking for 'Start a post' button...")
        
        start_post_selectors = [
            "[data-view-name='share-sharebox-focus']",  # Primary - most stable
            "div[role='button'][data-view-name='share-sharebox-focus']",
            "button.share-box-feed-entry__trigger",
            "button:has-text('Start a post')",
            "div.share-box-feed-entry__trigger",
            "[data-control-name='share.start_share']",
            "button[aria-label*='Start a post']"
        ]
        
        for selector in start_post_selectors:
            try:
                btn = await self.page.query_selector(selector)
                if btn:
                    self.log(f"Found Start Post button: {selector}")
                    await btn.click()
                    await asyncio.sleep(3)
                    return True
            except Exception:
                continue
        
        self.log("Could not find Start Post button")
        return False

    def optimize_for_mobile(self, text):
        """Optimize text for mobile readability - minimal formatting."""
        if not text:
            return ""
        
        # Clean up the text first
        text = text.strip()
        
        # Replace multiple newlines with double newline (paragraph break)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        # Split into paragraphs
        paragraphs = text.split('\n\n')
        
        optimized_paragraphs = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # Replace single newlines with spaces (keep paragraphs together)
            para = re.sub(r'\n', ' ', para)
            
            # If paragraph is very long (>300 chars), add a break at a sentence boundary
            if len(para) > 300:
                # Find a good break point around the middle
                mid = len(para) // 2
                # Look for sentence end near the middle
                best_break = -1
                for i in range(mid - 50, mid + 50):
                    if i >= 0 and i < len(para) - 1:
                        if para[i] in '.!?' and para[i+1] == ' ':
                            best_break = i + 1
                            break
                
                if best_break > 0:
                    para = para[:best_break].strip() + '\n\n' + para[best_break:].strip()
            
            optimized_paragraphs.append(para)
        
        # Join paragraphs with double newline
        return '\n\n'.join(optimized_paragraphs)

    async def paste_content(self, text):
        """Paste content into LinkedIn post editor."""
        self.log("Pasting content into post editor...")
        
        # Optimize for mobile
        optimized_text = self.optimize_for_mobile(text)
        self.log(f"Optimized text ({len(optimized_text)} chars)")
        
        # Find the post editor
        editor_selectors = [
            ".ql-editor",
            "[data-placeholder='What do you want to talk about?']",
            "[contenteditable='true']",
            ".share-creation-state__text-editor",
            "div[aria-label='Text editor for creating content']"
        ]
        
        for selector in editor_selectors:
            try:
                editor = await self.page.query_selector(selector)
                if editor:
                    self.log(f"Found editor: {selector}")
                    await editor.click()
                    await asyncio.sleep(0.5)
                    await editor.fill(optimized_text)
                    await asyncio.sleep(1)
                    self.log("Content pasted successfully")
                    return True
            except Exception as e:
                self.log(f"Editor attempt failed: {e}")
                continue
        
        self.log("Could not find post editor")
        return False

    async def attach_image(self, image_path):
        """Attach image to LinkedIn post, handling native file dialogs."""
        if not image_path or not os.path.exists(image_path):
            self.log(f"Image not found: {image_path}")
            return False
        
        # Ensure absolute path
        image_path = os.path.abspath(image_path)
        self.log(f"Attaching image: {image_path}")
        
        # Wait for the media selection screen to load/stabilize
        await asyncio.sleep(2)
        
        media_selectors = [
            "button[aria-label='Add media']",
            "button[aria-label='Add a photo']",
            "button:has-text('Photo')",
        ]
        
        # Attempt to find the button first
        target_btn = None
        for selector in media_selectors:
            try:
                btn = await self.page.query_selector(selector)
                if btn:
                    self.log(f"Found media button: {selector}")
                    target_btn = btn
                    break
            except Exception:
                continue
                
        if not target_btn:
            self.log("Could not find media button")
            return False

        # Attempt to click with file chooser interception
        file_attached = False
        try:
            self.log("Clicking media button with FileChooser expectation...")
            async with self.page.expect_file_chooser(timeout=5000) as fc_info:
                await target_btn.click()
            
            # If we get here, a file chooser was triggered
            file_chooser = await fc_info.value
            await file_chooser.set_files(image_path)
            self.log("File attached via FileChooser (dialog closed)")
            file_attached = True
            
        except Exception as e:
            self.log(f"FileChooser event not triggered (or timeout): {e}")
            self.log("Falling back to direct input setting...")
            
            # Fallback: The dialog might not have opened, or it's a non-native picker.
            # Try setting input files directly if generic input exists.
            try:
                await self.page.set_input_files("input[type='file']", image_path)
                self.log("Set file via page.set_input_files() fallback")
                file_attached = True
            except Exception as e2:
                self.log(f"Direct input set failed: {e2}")
                # Try shadow DOM fallback
                try:
                    # Get the file input ID from shadow DOM
                    file_input_id = await self.page.evaluate("""
                        () => {
                            const outlet = document.getElementById('interop-outlet');
                            if (outlet && outlet.shadowRoot) {
                                const input = outlet.shadowRoot.querySelector("input[type='file']");
                                if (input && input.id) {
                                    return input.id;
                                }
                            }
                            return null;
                        }
                    """)
                    
                    if file_input_id:
                        self.log(f"Found file input with ID: {file_input_id}")
                        await self.page.set_input_files(f"#interop-outlet >> input#{file_input_id}", image_path)
                        self.log("Set file via shadow piercing selector")
                        file_attached = True
                except Exception as e3:
                    self.log(f"Shadow piercing failed: {e3}")
        
        if not file_attached:
            self.log("Failed to attach image.")
            return False
            
        await asyncio.sleep(3)
        
        # Step 3: Click "Next" button if it appeared
        try:
            next_clicked = await self.page.evaluate("""
                () => {
                    const findNext = (root) => {
                         if (!root) return null;
                         const buttons = Array.from(root.querySelectorAll('button'));
                         const nextBtn = buttons.find(b => b.innerText.trim() === 'Next');
                         if (nextBtn) {
                             nextBtn.click();
                             return true;
                         }
                         // Check shadow roots
                         const children = Array.from(root.querySelectorAll('*'));
                         for (const child of children) {
                             if (child.shadowRoot) {
                                 if (findNext(child.shadowRoot)) return true;
                             }
                         }
                         return false;
                    };
                    return findNext(document.body) || findNext(document.getElementById('interop-outlet')?.shadowRoot);
                }
            """)
            
            if next_clicked:
                self.log("Clicked 'Next' button")
                await asyncio.sleep(2)
        except Exception as e:
            self.log(f"Error clicking Next: {e}")

        self.log("Image attached successfully")
        return True

    async def add_alt_text(self, alt_text):
        """Add alt text using correct flow: Edit media preview → ALT → fill → Add."""
        if not alt_text:
            alt_text = f"Image for: {self.current_topic}"
        
        self.log(f"Adding alt text: {alt_text[:50]}...")
        
        # Wait for the main post editor to stabilize
        await asyncio.sleep(2)
        
        # Step 1: Click "Edit" or "Edit media preview" button
        self.log("Step 1: Looking for 'Edit' button...")
        try:
            edit_clicked = await self.page.evaluate("""
                () => {
                    const walk = (root) => {
                        if (!root) return null;
                        const els = root.querySelectorAll ? Array.from(root.querySelectorAll('button, [role="button"]')) : [];
                        for (const el of els) {
                            const label = (el.getAttribute('aria-label') || '').toLowerCase();
                            const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                            
                            // Check for "Edit", "Edit media", "Edit image"
                            if (label.includes('edit media') || label.includes('edit image') || 
                                text === 'edit' || text === 'edit media' || text.includes('edit')) {
                                el.click();
                                return text || label;
                            }
                        }
                        const children = root.querySelectorAll ? Array.from(root.querySelectorAll('*')) : [];
                        for (const child of children) {
                            if (child.shadowRoot) {
                                const result = walk(child.shadowRoot);
                                if (result) return result;
                            }
                        }
                        return null;
                    };
                    return walk(document.body);
                }
            """)
            
            if edit_clicked:
                self.log(f"Clicked '{edit_clicked}'")
                await asyncio.sleep(4)  # Wait for editor to open (may be slow)
            else:
                self.log("'Edit' button not found")
        except Exception as e:
            self.log(f"Error clicking edit media: {e}")
        
        # Step 2: Click "Alternative text" or "ALT" button
        self.log("Step 2: Looking for 'Alternative text' button...")
        alt_found = False
        for attempt in range(3):
            try:
                alt_clicked = await self.page.evaluate("""
                    () => {
                        const walk = (root) => {
                            if (!root) return null;
                            const els = root.querySelectorAll ? Array.from(root.querySelectorAll('button, [role="button"]')) : [];
                            for (const el of els) {
                                const text = (el.innerText || el.textContent || '').trim().toUpperCase();
                                const label = (el.getAttribute('aria-label') || '').toLowerCase();
                                
                                // Check for "ALT", "Alternative text"
                                if (text === 'ALT' || text === 'ALTERNATIVE TEXT' || 
                                    label.includes('alternative text') || label.includes('alt text')) {
                                    el.click();
                                    return true;
                                }
                            }
                            const children = root.querySelectorAll ? Array.from(root.querySelectorAll('*')) : [];
                            for (const child of children) {
                                if (child.shadowRoot) {
                                    const result = walk(child.shadowRoot);
                                    if (result) return result;
                                }
                            }
                            return null;
                        };
                        return walk(document.body);
                    }
                """)
                
                if alt_clicked:
                    self.log("Clicked 'Alternative text' button")
                    alt_found = True
                    await asyncio.sleep(2)
                    break
                else:
                    self.log(f"Attempt {attempt+1}: 'Alternative text' button not found, waiting...")
                    await asyncio.sleep(2)
            except Exception as e:
                self.log(f"Error clicking ALT: {e}")
        
        if not alt_found:
            self.log("Failed to find 'Alternative text' button after 3 attempts")
            await self.page.screenshot(path=os.path.join(SCRIPT_DIR, "debug_alt_text_missing.png"))
            return False
            
        # Step 3: Fill the textarea and click Save/Add
        self.log("Step 3: Filling textarea and clicking Save/Add...")
        try:
            result = await self.page.evaluate("""
                (altText) => {
                    const walk = (root) => {
                         if (!root) return null;
                         
                         // Try to find textarea in this root
                         const textarea = root.querySelector('textarea');
                         if (textarea) return { root, textarea };
                         
                         const children = root.querySelectorAll ? Array.from(root.querySelectorAll('*')) : [];
                         for (const child of children) {
                             if (child.shadowRoot) {
                                 const res = walk(child.shadowRoot);
                                 if (res) return res;
                             }
                         }
                         return null;
                    };
                    
                    const found = walk(document.body);
                    if (!found) return { success: false, error: 'Textarea not found' };
                    
                    const { root, textarea } = found;
                    
                    // Fill textarea
                    textarea.value = altText;
                    textarea.dispatchEvent(new Event('input', { bubbles: true }));
                    textarea.dispatchEvent(new Event('change', { bubbles: true }));
                    textarea.focus();
                    
                    // Find Save or Add or Done button in the SAME root or nearby
                    // The button might be 'Save', 'Add', 'Done', 'Apply'
                    const buttons = Array.from(root.querySelectorAll('button'));
                    const saveBtn = buttons.find(b => {
                        const t = (b.innerText || b.textContent).trim().toLowerCase();
                        return ['save', 'add', 'done', 'apply'].includes(t);
                    });
                    
                    if (saveBtn) {
                        setTimeout(() => saveBtn.click(), 500);
                        return { success: true, btnClicked: saveBtn.innerText };
                    }
                    
                    return { success: true, btnClicked: false, message: 'Filled but Save button not found' };
                }
            """, alt_text)
            
            self.log(f"Alt text result: {result}")
            
            if result.get('success'):
                self.log("Alt text added successfully!")
                await asyncio.sleep(2)
                return True
            else:
                self.log(f"Failed: {result.get('error')}")
                return False

        except Exception as e:
            self.log(f"Error filling textarea: {e}")
            return False

    async def stop(self):
        """Clean up resources."""
        self.log("Cleaning up...")
        try:
            # Don't close page/browser so user can review
            # if self.page:
            #     await self.page.close()
            # if self.browser:
            #     await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            self.log(f"Cleanup error: {e}")

    async def optimize_post_text(self, text):
        """Optimize the post content for mobile reading using Gemini Flash."""
        self.log("Optimizing post text for mobile reading...")
        try:
            prompt = f"""Optimize the following LinkedIn post text for mobile reading.

RULES:
1. Break long paragraphs into short, punchy ones (1-2 sentences max).
2. Use bullet points where appropriate (e.g. for lists or key points).
3. Ensure the hook (first sentence/paragraph) is catchy and separated by a line break.
4. Remove hashtags.
5. Do NOT change the core message, tone, or meaning. Just strictly reformat for readability.
6. Return ONLY the optimized text.

TEXT TO OPTIMIZE:
{text}"""

            response = self.genai_client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            optimized_text = response.text.strip()
            self.log("Text optimization complete.")
            return optimized_text
            
        except Exception as e:
            self.log(f"Optimization failed: {e}")
            return text  # Fallback to original text

    async def validate_image_and_alt_text(self, post_text, image_path, alt_text):
        """Validate the image and alt text using Gemini Vision."""
        self.log("Validating image and alt text with Gemini Vision...")
        try:
            # Read image
            import base64
            with open(image_path, "rb") as f:
                image_bytes = f.read()
                
            from google.genai import types
            
            prompt = f"""Analyze this LinkedIn post context and the attached image.
            
POST TEXT:
{post_text[:500]}... (truncated)

ALT TEXT:
{alt_text}

Verify the following:
1. Is the image relevant to the post topic?
2. Does the Alt Text accurately describe the image?
3. Is the Alt Text concise and helpful for screen readers?

Provide a JSON response:
{{
  "relevant": true/false,
  "alt_text_accurate": true/false,
  "quality_score": 1-10,
  "feedback": "Short explanation"
}}"""

            response = self.genai_client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    prompt
                ]
            )
            
            # Simple parsing of response (expecting JSON-like text)
            result = response.text.replace("```json", "").replace("```", "").strip()
            self.log(f"Validation Result: {result}")
            return result
            
        except Exception as e:
            self.log(f"Validation failed: {e}")
            return None

    async def run(self):
        """Main execution loop."""
        try:
            # Initialize
            await self.start()
            
            # Get today's content
            content = self.get_todays_content()
            if not content:
                self.log("No content found to process")
                return
            
            # === OPAL WORKFLOW ===
            self.log("=" * 50)
            self.log("STARTING OPAL WORKFLOW")
            self.log("=" * 50)
            
            # Navigate to Opal
            if not await self.navigate_to_opal():
                self.log("Failed to navigate to Opal")
                return
            
            # Click Start
            if not await self.click_start_button():
                self.log("Failed to click Start button")
                return
            
            # Input content
            await self.input_content(content)
            
            # Wait for generation
            if not await self.wait_for_generation():
                self.log("Post generation timed out")
                return
            
            # Download post
            html_path = await self.download_post()
            if not html_path:
                self.log("Failed to download post")
                return
            
            # Extract content
            extracted = await self.extract_content_from_page(html_path)
            if not extracted:
                self.log("Failed to extract content")
                return
            
            # Save image (use either extracted image or frame-extracted image)
            image_path = await self.save_image(extracted.get("image_src"))
            if not image_path and hasattr(self, 'post_image_path') and self.post_image_path:
                image_path = self.post_image_path
                self.log(f"Using frame-extracted image: {image_path}")
            
            # === LINKEDIN WORKFLOW ===
            self.log("=" * 50)
            self.log("STARTING LINKEDIN WORKFLOW")
            self.log("=" * 50)
            
            # Navigate to LinkedIn
            if not await self.navigate_to_linkedin():
                self.log("Failed to navigate to LinkedIn")
                return
            
            # Click Start Post
            if not await self.click_start_post():
                self.log("Failed to click Start Post button")
                return
            
            # Optimize content
            raw_text = extracted.get("text", "")
            if raw_text:
                optimized_text = await self.optimize_post_text(raw_text)
            else:
                optimized_text = ""

            # Paste content
            if not await self.paste_content(optimized_text):
                self.log("Failed to paste content")
            
            # Attach image if available
            if image_path and os.path.exists(image_path):
                self.log(f"Attaching image: {image_path}")
                await self.attach_image(image_path)
                
                # Generate and add alt text
                alt_text = extracted.get("alt_text")
                
                # Fallback to frame-extracted alt text
                if not alt_text and hasattr(self, 'post_alt_text') and self.post_alt_text:
                    alt_text = self.post_alt_text
                    self.log(f"Using frame-extracted alt text: {alt_text}")
                    
                if not alt_text:
                    # Generate a simple alt text based on the topic
                    alt_text = f"AI-generated LinkedIn post image about {self.current_topic}"
                self.log(f"Adding alt text: {alt_text}")
                await self.add_alt_text(alt_text)
                
                # Verify logic
                if hasattr(self, 'validate_image_and_alt_text'):
                     await self.validate_image_and_alt_text(optimized_text, image_path, alt_text)

            else:
                self.log("No image to attach")
            
            # Play notification sound
            self.log("=" * 50)
            self.log("POST READY FOR REVIEW!")
            self.log("=" * 50)
            play_notification_sound()
            
            # Wait for user to review (don't auto-close)
            self.log("Waiting for user to review and post manually...")
            self.log("Press Ctrl+C to exit when done.")
            
            while True:
                await asyncio.sleep(10)
                
        except KeyboardInterrupt:
            self.log("User interrupted. Exiting...")
        except Exception as e:
            self.log(f"Error in main loop: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.stop()


if __name__ == "__main__":
    agent = PostCreationAgent()
    asyncio.run(agent.run())
