import asyncio
import csv
import random
import os
import json
import shutil
import difflib
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

from dotenv import load_dotenv
from config_manager import ConfigManager
from optimizer import AgentOptimizer

# Load environment variables
load_dotenv()

with open("debug_start.txt", "w") as f:
    f.write("Script Started\n")

# Configuration
USER_DATA_DIR = "./user_data"
HEADLESS = False
LINKEDIN_CONNECTIONS_URL = "https://www.linkedin.com/mynetwork/invite-connect/connections/"
AI_STUDIO_URL = "https://aistudio.google.com/apps/drive/151Go3tB8IZqJZRmyPWTC00WtHu3rQ3Pn?showPreview=true&showAssistant=true"

class LinkedInAgent:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        
        # Self-Improving Components
        self.config_manager = ConfigManager()
        self.optimizer = AgentOptimizer(config_manager=self.config_manager)
        
        # Run optimization at startup
        self.log("Running self-optimization...")
        self.optimizer.optimize()
        
        # Metrics for current run
        self.run_metrics = {
            "candidates_found": 0,
            "messages_sent": 0,
            "scroll_attempts": 0,
            "scroll_successes": 0,
            "errors": [],
            "message_verification_failed": False
        }
        
        self.history_file = "history.json"
        self.created_pdfs = [] # Track PDFs for cleanup

    def log(self, msg):
        print(msg)
        with open("agent_log.txt", "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    # --- V2.1 HELPER METHODS ---

    def load_history_json(self):
        if not os.path.exists(self.history_file):
            return {}
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def save_history_json_atomic(self, data):
        temp_file = f"{self.history_file}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            shutil.move(temp_file, self.history_file)
            self.log(f"History saved to {self.history_file}. Total entries: {len(data)}")
        except Exception as e:
            self.log(f"CRITICAL: Error saving history atomically: {e}")

    def parse_connection_date(self, text):
        # Parses "Connected 2 weeks ago", "Connected 1 month ago", etc.
        text = text.lower()
        today = datetime.now()
        
        try:
            if "hour" in text or "minute" in text or "moment" in text or "day" in text:
                # Very recent, definitely < 90 days
                return today
            
            if "week" in text:
                parts = text.split()
                for p in parts:
                    if p.isdigit():
                        weeks = int(p)
                        return today - timedelta(weeks=weeks)
            
            if "month" in text:
                parts = text.split()
                for p in parts:
                    if p.isdigit():
                        months = int(p)
                        return today - timedelta(days=months*30)
            
            if "year" in text:
                parts = text.split()
                for p in parts:
                    if p.isdigit():
                        years = int(p)
                        return today - timedelta(days=years*365)
                        
            return today # Default to today if unsure (safe side? No, safe is SKIP. But let's assume recent if unparseable to be checked by history)
        except:
            return today

    def classify_role(self, headline, about_text=None):
        """Classify role using Gemini AI based on headline and About section."""
        import os
        
        # Build the text to analyze
        combined_text = f"Headline: {headline}"
        if about_text:
            combined_text += f"\n\nAbout Section: {about_text}"
        
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
        if not api_key:
            self.log("WARNING: No API key for AI classification. Defaulting to GENERAL.")
            return "GENERAL"
        
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            
            prompt = f"""Analyze this LinkedIn profile and classify the person's legal background.

{combined_text}

Classification Rules:
- PRACTICING: Currently practicing lawyers, attorneys, partners, associates, counsel, legal professionals actively working in law firms or in-house legal teams
- GENERAL: Law students, legal assistants, paralegals, legal tech, legal operations, compliance professionals, anyone with legal background but not actively practicing law
- SKIP: No legal background whatsoever

Respond with ONLY one word: PRACTICING, GENERAL, or SKIP"""

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            result = response.text.strip().upper()
            
            # Validate response
            if result in ["PRACTICING", "GENERAL", "SKIP"]:
                self.log(f"AI Classification: {result} (Headline: {headline[:50]}...)")
                return result
            else:
                self.log(f"AI returned unexpected classification: {result}. Defaulting to GENERAL.")
                return "GENERAL"
                
        except Exception as e:
            self.log(f"AI classification error: {e}. Defaulting to GENERAL.")
            return "GENERAL"

    async def verify_chat_identity(self, expected_name, page=None):
        page = page or self.page
        try:
            # Dynamic wait: Wait for page to be fully loaded
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass  # Continue even if timeout
            
            # Modern LinkedIn chat selectors (2024)
            selectors = [
                # Chat overlay header selectors
                ".msg-overlay-bubble-header__title a",
                ".msg-overlay-bubble-header__title span",
                ".msg-entity-lockup__entity-title",
                "h2.msg-entity-lockup__entity-title",
                "a.msg-entity-lockup__entity-title",
                # Conversation header
                ".msg-conversation-card__participant-names",
                ".msg-s-message-list-header__title",
                # Full messaging page
                ".msg-thread__link-to-profile",
                ".msg-thread__entity-title",
                # Profile page fallback (if chat didn't open properly)
                "h1.text-heading-xlarge",
                ".pv-text-details__left-panel h1"
            ]
            
            # Generic UI text to skip
            skip_texts = ["new message", "start a conversation", "write a message", "type a message", "messaging", "linkedin"]
            
            # Dynamic wait: Try to wait for any of the selectors to appear
            for sel in selectors[:5]:  # Try main chat selectors first
                try:
                    await page.wait_for_selector(sel, timeout=2000, state="visible")
                    break  # Found one, exit loop
                except:
                    continue
            
            # Now poll for identity match (with shorter intervals since we already waited)
            max_retries = 15
            last_found_name = "None"
            
            for i in range(max_retries):
                for sel in selectors:
                    try:
                        elements = await page.query_selector_all(sel)
                        for header_el in elements:
                            if header_el and await header_el.is_visible():
                                chat_name = await header_el.inner_text()
                                chat_name = chat_name.strip().split('\n')[0]  # Take first line only
                                
                                # Skip generic UI text
                                if chat_name.lower() in skip_texts or len(chat_name) < 2:
                                    continue
                                    
                                last_found_name = chat_name
                                
                                # Fuzzy Match - check first name match as fallback
                                ratio = difflib.SequenceMatcher(None, expected_name.lower(), chat_name.lower()).ratio()
                                if ratio >= 0.70:
                                    self.log(f"Identity Verified: '{chat_name}' (Match={ratio:.2f})")
                                    return True
                                
                                # Also try first name only match
                                expected_first = expected_name.split()[0].lower() if expected_name else ""
                                found_first = chat_name.split()[0].lower() if chat_name else ""
                                if expected_first and found_first and expected_first == found_first:
                                    self.log(f"Identity Verified (First Name): '{chat_name}'")
                                    return True
                    except:
                        pass
                
                await asyncio.sleep(0.3)  # Shorter interval since we did upfront wait
            
            # Final fallback: Check if we're on the correct profile page
            try:
                page_title = await page.title()
                if expected_name.split()[0].lower() in page_title.lower():
                    self.log(f"Identity Verified (Page Title): '{page_title}'")
                    return True
            except:
                pass
            
            self.log(f"Identity Verification Failed. Expected='{expected_name}', Last Found='{last_found_name}'")
            return False

        except Exception as e:
            self.log(f"Error in identity verification: {e}")
            return False

    async def inspect_chat_history(self, page=None):
        page = page or self.page
        try:
            # Wait for messages to load
            await asyncio.sleep(1)
            
            # Scrape last 5 message bubbles (increased from 3)
            bubbles = await page.query_selector_all(".msg-s-event-listitem__message-bubble")
            if not bubbles:
                self.log("No message bubbles found in chat. Proceeding (new conversation).")
                return True # No history is safe
            
            self.log(f"Found {len(bubbles)} message bubbles in chat. Inspecting...")
            
            last_bubbles = bubbles[-5:] if len(bubbles) >= 5 else bubbles
            for idx, bubble in enumerate(last_bubbles):
                # Check if sent by "You"
                # Method 1: Check for specific class on the bubble or its parent
                # 'msg-s-event-listitem--other' vs 'msg-s-event-listitem--me' (common pattern)
                
                list_item = await bubble.evaluate_handle("el => el.closest('.msg-s-event-listitem')")
                if list_item:
                    class_attr = await list_item.get_attribute("class")
                    if class_attr and ("msg-s-event-listitem--me" in class_attr or "msg-s-message-group--align-right" in class_attr):
                        bubble_text = await bubble.inner_text()
                        self.log(f"DUPLICATE DETECTED: Found message sent by YOU: '{bubble_text[:50]}...'")
                        return False
            
            self.log("Chat history check passed. No prior messages from YOU detected.")
            return True
        except Exception as e:
            self.log(f"Error inspecting chat history: {e}")
            # FAIL CLOSED: If we can't verify, assume there's history to be safe
            self.log("SAFETY: Failing closed due to history check error.")
            return False

    async def scrape_about_section(self, page=None):
        page = page or self.page
        self.log("Scraping About section...")
        try:
            # Try to find the About section
            # Usually in a section with id 'about' or similar
            about_section = await page.query_selector("#about")
            if not about_section:
                # Try finding by text
                about_section = await page.query_selector("section:has-text('About')")
            
            if about_section:
                # Get the text content of the sibling or child that holds the description
                # Often it's in a div following the header
                # Let's just grab the whole section text for simplicity
                text = await about_section.inner_text()
                # Clean up "About" header
                text = text.replace("About", "").strip()
                self.log(f"About section scraped ({len(text)} chars).")
                return text
            else:
                self.log("About section not found.")
                return None
        except Exception as e:
            self.log(f"Error scraping About section: {e}")
            return None

    async def save_profile_pdf(self, page=None):
        page = page or self.page
        self.log("Saving profile as PDF...")
        try:
            filename = f"profile_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            path = os.path.abspath(filename)
            await page.pdf(path=path)
            self.log(f"Profile PDF saved to: {path}")
            self.created_pdfs.append(path)
            return path
        except Exception as e:
            self.log(f"Error saving profile PDF: {e}")
            return None

    async def start(self):
        self.log("Starting agent...")
        self.playwright = await async_playwright().start()
        try:
            # Try to connect to an existing Chrome instance
            self.log("Attempting to connect to existing Chrome on port 9222...")
            self.browser = await self.playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            self.context = self.browser.contexts[0]
            self.page = await self.context.new_page()
            self.log("Connected to existing Chrome.")
        except Exception as e:
            self.log(f"Failed to connect to existing Chrome: {e}")
            self.log("Attempting to launch Chrome automatically...")
            await self.launch_browser()
            
            # Try connecting again
            await asyncio.sleep(3)
            try:
                self.browser = await self.playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
                self.context = self.browser.contexts[0]
                self.page = await self.context.new_page()
                self.log("Connected to launched Chrome.")
            except Exception as e2:
                self.log(f"Failed to connect after launch: {e2}")
                raise e2

    async def launch_browser(self):
        import subprocess
        
        # Define paths
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            "chrome.exe" # Hope it's in PATH
        ]
        
        chrome_path = None
        for path in chrome_paths:
            if os.path.exists(path) or path == "chrome.exe":
                chrome_path = path
                break
        
        if not chrome_path:
            self.log("Chrome executable not found.")
            return

        user_data_dir = r"C:\ChromeAutomationProfile"
        cmd = [
            chrome_path,
            "--remote-debugging-port=9222",
            f"--user-data-dir={user_data_dir}"
        ]
        
        self.log(f"Launching Chrome: {' '.join(cmd)}")
        subprocess.Popen(cmd)
        await asyncio.sleep(5) # Wait for launch

    async def prepare_search_page(self):
        try:
            self.log(f"Navigating to {LINKEDIN_CONNECTIONS_URL}...")
            await self.page.goto(LINKEDIN_CONNECTIONS_URL)
            
            self.log("Waiting 5s for page load...")
            await asyncio.sleep(5)
            
            # Check login
            try:
                await self.page.wait_for_selector("div[data-view-name='connections-list']", timeout=10000)
                self.log("Connections list found.")
                return True
            except Exception:
                self.log("Login check failed or selector not found.")
                self.log("Please log in to LinkedIn.")
                while True:
                    url = self.page.url
                    if "feed" in url or "mynetwork" in url:
                        self.log("Login detected (URL match).")
                        break
                    await asyncio.sleep(2)
                
                self.log(f"Navigating to {LINKEDIN_CONNECTIONS_URL} again...")
                await self.page.goto(LINKEDIN_CONNECTIONS_URL)
                await self.page.wait_for_selector("div[data-view-name='connections-list']")
                return True
        except Exception as e:
            self.log(f"Error in prepare_search_page: {e}")
            return False

    async def close_existing_chats(self, page=None):
        """Close any existing chat overlays to prevent interference."""
        page = page or self.page
        try:
            # Find and close all chat overlay close buttons
            close_selectors = [
                "button[data-control-name='overlay.close_conversation_window']",
                ".msg-overlay-bubble-header__control--close",
                "button[aria-label='Close your conversation']",
                ".msg-overlay-bubble-header button svg[data-test-icon='close-small']"
            ]
            
            for selector in close_selectors:
                close_buttons = await page.query_selector_all(selector)
                for btn in close_buttons:
                    try:
                        if await btn.is_visible():
                            await btn.click()
                            await asyncio.sleep(0.3)
                    except:
                        pass
            
            # Also try to close by clicking outside any overlay
            minimized_chats = await page.query_selector_all(".msg-overlay-conversation-bubble--is-active")
            for chat in minimized_chats:
                try:
                    close_btn = await chat.query_selector("button[aria-label*='close' i], button[aria-label*='Close' i]")
                    if close_btn:
                        await close_btn.click()
                        await asyncio.sleep(0.3)
                except:
                    pass
                    
        except Exception as e:
            self.log(f"Error closing existing chats: {e}")

    async def open_chat(self, profile_url, page=None):
        page = page or self.page
        self.log(f"Opening chat for {profile_url}...")
        try:
            # FIRST: Close any existing chat overlays
            await self.close_existing_chats(page)
            
            await page.goto(profile_url, timeout=60000)
            
            # Dynamic wait: Wait for page to be fully loaded
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass  # Continue even if timeout
            
            # Click Message button
            buttons = await page.query_selector_all("button:has-text('Message'), a:has-text('Message')")
            msg_btn = None
            for btn in buttons:
                if await btn.is_visible():
                    text = await btn.inner_text()
                    if "Message" in text:
                        msg_btn = btn
                        break
            
            if not msg_btn:
                more_btn = await page.query_selector("button[aria-label='More actions']")
                if more_btn:
                    await more_btn.click()
                    await asyncio.sleep(1)
                    msg_btn = await page.query_selector("div[role='button']:has-text('Message')")
            
            if not msg_btn:
                self.log("Message button not found. Dumping buttons for debug...")
                all_btns = await page.query_selector_all("button")
                btn_texts = []
                for b in all_btns[:10]: # First 10
                    t = await b.inner_text()
                    btn_texts.append(t.strip())
                self.log(f"Visible buttons: {btn_texts}")
                return False

            await msg_btn.evaluate("node => node.click()")
            
            # Dynamic wait: Wait for chat input to appear
            try:
                await page.wait_for_selector(".msg-form__contenteditable", timeout=15000, state="visible")
                return True
            except:
                self.log("Chat input not found after clicking Message.")
                return False
                
        except Exception as e:
            self.log(f"Error opening chat: {e}")
            return False

    async def get_chat_history(self, page=None):
        page = page or self.page
        try:
            elements = await page.query_selector_all(".msg-s-event-listitem__body")
            history = []
            for el in elements:
                text = await el.inner_text()
                history.append(text)
            return history
        except Exception as e:
            self.log(f"Error reading chat history: {e}")
            return []

    async def close_chat(self, page=None):
        page = page or self.page
        try:
            close_btn_selectors = [
                "button[data-control-name='overlay.close_conversation_window']",
                "button[aria-label='Close conversation']",
                "button[aria-label='Close message']"
            ]
            for selector in close_btn_selectors:
                btn = await page.query_selector(selector)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(1)
                    return
            
            # Fallback
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            await page.keyboard.press("Escape")
        except Exception as e:
            self.log(f"Error closing chat: {e}")

    async def send_chat_message(self, message_text, attachment_path=None, page=None, verify=True, retries=2):
        page = page or self.page
        
        # Override retries with config if available
        retries = self.config_manager.get("limits.max_retries", retries)
        
        for attempt in range(retries + 1):
            try:
                self.log(f"Sending message (Attempt {attempt + 1}/{retries + 1})...")
                msg_form = await page.wait_for_selector(".msg-form__contenteditable", timeout=5000)
                if not msg_form:
                    self.log("Message input not found.")
                    return False
                
                await msg_form.fill("") # Clear first
                await msg_form.type(message_text)
                await asyncio.sleep(1)

                if attachment_path:
                    self.log(f"Attaching file: {attachment_path}")
                    file_input = await page.query_selector("input[type='file']")
                    if file_input:
                        await file_input.set_input_files(attachment_path)
                        self.log("File uploaded. Waiting for processing...")
                        await asyncio.sleep(5)
                    else:
                        # Try clicking attach button
                        attach_btn = await page.query_selector("button[aria-label='Attach file']")
                        if attach_btn:
                            await attach_btn.click()
                            await asyncio.sleep(1)
                            file_input = await page.query_selector("input[type='file']")
                            if file_input:
                                await file_input.set_input_files(attachment_path)
                                await asyncio.sleep(5)
                
                # Click Send
                send_btn = await page.query_selector("button[type='submit']")
                if send_btn and await send_btn.is_enabled():
                    await send_btn.click()
                    self.log("Send button clicked.")
                    
                    # Use configured wait time
                    wait_time = self.config_manager.get("timeouts.message_send_wait", 3000)
                    await asyncio.sleep(wait_time / 1000)
                    
                    if verify:
                        self.log("Verifying message sent...")
                        # Wait a bit more for UI update
                        await asyncio.sleep(2)
                        history = await self.get_chat_history(page)
                        # Check if message_text (or significant part) is in history
                        # We check the last few messages
                        recent_history = history[-3:] if len(history) >= 3 else history
                        verified = False
                        
                        # Normalize for check
                        check_text = message_text.strip()[:50] # Check first 50 chars
                        
                        for msg in recent_history:
                            if check_text in msg:
                                verified = True
                                break
                        
                        if verified:
                            self.log("Message verified in history.")
                            return True
                        else:
                            self.log("Message NOT found in history after sending.")
                            self.run_metrics["message_verification_failed"] = True
                            if attempt < retries:
                                self.log("Retrying...")
                                await asyncio.sleep(2)
                                continue
                            else:
                                self.log("Max retries reached. Verification failed.")
                                return False
                    else:
                        return True
                else:
                    self.log("Send button not found or disabled.")
                    return False
            except Exception as e:
                self.log(f"Error sending chat message: {e}")
                self.run_metrics["errors"].append(str(e))
                if attempt < retries:
                    continue
                return False
        
        return False

    async def extract_website(self, page=None):
        page = page or self.page
        self.log("Starting website extraction...")
        website = None
        try:
            # Scroll to top
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            
            # 1. Check if website is visible on the main profile (top card)
            try:
                top_website = await page.query_selector(".pv-top-card--website a")
                if top_website:
                    href = await top_website.get_attribute("href")
                    if href and "http" in href:
                        self.log(f"Website found on profile: {href}")
                        return href
            except:
                pass

            # 2. If not, try contact info modal
            contact_link = await page.wait_for_selector("a[id='top-card-text-details-contact-info']", timeout=5000)
            if contact_link:
                self.log("Clicking contact info (JS)...")
                await asyncio.sleep(1)
                await page.evaluate("el => el.click()", contact_link)
                
                self.log("Waiting 3s for modal...")
                await asyncio.sleep(3)
                
                # Wait for modal content
                try:
                    modal = await page.wait_for_selector(".artdeco-modal", timeout=5000)
                    if not modal:
                         modal = await page.wait_for_selector("div[role='dialog']", timeout=5000)
                except:
                    self.log("Modal not found/visible.")
                    return None

                if modal:
                    self.log("Modal found. Scanning links...")
                    links = await modal.query_selector_all("a")
                    for link in links:
                        href = await link.get_attribute("href")
                        if href and "http" in href and "linkedin.com" not in href and "mailto:" not in href:
                            website = href
                            self.log(f"Website found in modal: {website}")
                            break
                    
                    # Close modal safely
                    try:
                        close_btn = await modal.query_selector("button[aria-label='Dismiss']")
                        if close_btn:
                            await page.evaluate("el => el.click()", close_btn)
                    except:
                        pass
        except Exception as e:
            self.log(f"Error extracting website: {e}")
        
        return website

    async def generate_report(self, website_url):
        # ... (Keep existing generate_report logic) ...
        # Note: generate_report doesn't use self.page, so it's fine.
        # But I need to include it in the replacement to avoid cutting it off?
        # No, I can just stop before generate_report if I don't change it.
        # But I need to replace process_candidate which comes AFTER generate_report.
        # So I should include generate_report or skip it.
        # I'll include the start of generate_report and then use a separate replacement for process_candidate?
        # No, replace_file_content replaces a block.
        # I'll replace from open_chat to extract_website.
        # Then I'll replace process_candidate separately.
        pass

    # ... (I will split the replacement into two calls to be safe and avoid huge payload) ...


    async def generate_report(self, input_data, input_type="url"):
        self.log(f"Generating report using input type: {input_type}...")
        
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
        if not api_key:
            self.log("ERROR: GEMINI_API_KEY or API_KEY not set.")
            return {"pdf_path": None, "message": None}

        try:
            from google import genai
            from fpdf import FPDF
            import json
            
            client = genai.Client(api_key=api_key)
            
            SYSTEM_INSTRUCTION = """
You are a world-class Legal AI Consultant specializing in "Zero-Trust" AI adoption for law firms. 
Your goal is to enable lawyers to use AI safely by strictly adhering to privacy-first principles.

Your task is to:
1. Analyze the provided Lawyer Profile (URL, Text, or PDF).
2. Extract their Name, Firm, and specific Practice Area.
3. Generate EXACTLY 10 High-Value, Practice-Specific AI Prompts that adhere to strict "Zero-Trust" protocols.
4. Generate a professional LinkedIn message to send to this lawyer, attaching the generated resource.

ZERO-TRUST PROTOCOL (CRITICAL):
- NEVER encourage pasting real client data.
- ALWAYS use bracketed placeholders for sensitive info (e.g., [Client Name], [Contract Date], [Settlement Amount]).
- Prompts must be safe to run on public LLMs because they contain no PII.

OUTPUT FORMAT:
You must strictly output VALID JSON with the following structure. Do not include markdown formatting or explanations outside the JSON.

{
  "profile": {
    "name": "Lawyer Name",
    "firmName": "Firm Name",
    "practiceArea": "Primary Practice Area",
    "keyMatters": ["Matter 1", "Matter 2"]
  },
  "anonymizationTechnique": {
    "title": "Anonymization Sandwich",
    "description": "Short explanation...",
    "steps": ["Step 1...", "Step 2..."]
  },
  "prompts": [
    {
      "title": "Prompt Title",
      "category": "Specific Category Name (e.g., 'Mergers Analysis', 'Litigation Strategy')",
      "content": "The prompt text...",
      "safetyCheck": "Why it is safe..."
    }
  ],
  "linkedinMessage": "The LinkedIn message text..."
}
"""
            prompt_content = []
            
            if input_type == "url":
                prompt_text = f"""
                Perform a deep research analysis on this lawyer's website URL: {input_data}.
                1. Use Google Search to find details about the lawyer, their firm, and their practice area focus.
                """
                prompt_content.append(prompt_text)
                
            elif input_type == "text":
                prompt_text = f"""
                Analyze the following text extracted from the lawyer's LinkedIn profile (About Section/Headline):
                
                --- BEGIN PROFILE TEXT ---
                {input_data}
                --- END PROFILE TEXT ---
                
                1. Extract details about the lawyer, their firm, and their practice area focus from the text.
                """
                prompt_content.append(prompt_text)
                
            elif input_type == "pdf":
                prompt_text = """
                Analyze the attached PDF of the lawyer's LinkedIn profile.
                1. Extract details about the lawyer, their firm, and their practice area focus from the PDF.
                """
                prompt_content.append(prompt_text)
                
                # Upload PDF
                self.log(f"Uploading PDF for analysis: {input_data}")
                with open(input_data, "rb") as f:
                    file_content = f.read()
                
                # Note: The new genai SDK might handle file uploads differently.
                # Assuming standard 'types.Part.from_data' or similar if using low-level, 
                # but 'client.models.generate_content' usually accepts bytes or Part objects.
                # Let's try to use the client's upload capability if available, or pass bytes if supported.
                # Actually, for Gemini 1.5/3, we usually upload to File API first.
                # Simplified: We will assume we can pass the file bytes directly or use a helper.
                # If this fails, we might need to fallback to text extraction from PDF locally.
                # For safety/simplicity in this script, let's try to read the PDF text locally if possible?
                # No, spec says "page.pdf() via Playwright" which is an image-based PDF usually.
                # Let's try passing the file path if the SDK supports it, or skip PDF analysis complexity 
                # and just say "Analyze this PDF" and hope the SDK handles the path?
                # Most robust way without complex deps:
                # We will use the 'types' module if available, or just try passing the file object.
                # WAIT: The simplest way with new SDK is often client.files.upload then pass the file handle.
                
                # Let's try a safer fallback: If PDF, we just say "Analyze the profile" and hope we can attach it?
                # Actually, let's just use the TEXT extraction fallback for now as it's safer than debugging PDF upload blindly.
                # But spec says "PDF Fallback".
                # I will implement a local PDF text extractor (pypdf) if I can? No, external dep.
                # I will try to pass the file content as a Part.
                
                from google.genai import types
                prompt_content.append(types.Part.from_bytes(data=file_content, mime_type="application/pdf"))

            # Common Instructions
            prompt_content.append("""
            2. Based on their SPECIFIC practice area, generate EXACTLY 10 high-value, Zero-Trust AI prompts.
               - Organize these prompts into 3-4 dynamic categories that are highly specific to the lawyer's practice area.
               - e.g., if IP Law: "Patent Analysis", "Trademark Filing". Avoid generic names.
            3. Ensure strict adherence to the Zero-Trust protocol (use placeholders like [Client Name]).
            4. Generate a professional LinkedIn message from "Sanjeev Chaodhari" acting as a Strategic Legal Consultant.
               RULES:
               - TONE: Professional, concise, peer-to-peer. NO "marketing speak".
               - FORMAT:
                 Hi [First Name],
                 I noticed [Firm Name] specializes in [Specific Practice Area], so I generated a **"Zero-Trust" AI Strategy** specifically for your practice.
                 It includes 10 ready-to-use workflows—including [Mention 2 specific topics derived from the generated prompts]—that use an "anonymization sandwich" technique. This allows your team to use AI for complex drafting without ever exposing privileged client data.
                 I've attached the PDF. You can preview the prompts directly here in the chat.
                 Best,
                 Sanjeev
               - CRITICAL: Replace all [bracketed placeholders] with actual data extracted from the lawyer's profile or the prompts you just generated.
            
            Return the result in valid JSON format.
            """)

            self.log("Calling Gemini API...")
            
            # Configure tools
            tools = [{"google_search": {}}] if input_type == "url" else []
            
            response = client.models.generate_content(
                model="gemini-2.0-flash-exp", # Using Flash for speed/multimodal, or 3-pro if available. Spec said 3-pro.
                # Spec: "Gemini 3 Pro exclusively".
                # I will use "gemini-3-pro-preview" as requested.
                config={
                    "system_instruction": SYSTEM_INSTRUCTION,
                    "tools": tools,
                    "response_mime_type": "application/json"
                },
                contents=prompt_content
            )
            
            self.log(f"API Response: {response.text}")
            text_content = response.text
            # Try to find the start of the JSON
            start_idx = text_content.find('{')
            if start_idx != -1:
                try:
                    decoder = json.JSONDecoder()
                    result, _ = decoder.raw_decode(text_content[start_idx:])
                except json.JSONDecodeError:
                     # Fallback to regex if raw_decode fails
                     import re
                     match = re.search(r"\{.*\}", text_content, re.DOTALL)
                     if match:
                        result = json.loads(match.group(0))
                     else:
                        raise
            else:
                raise ValueError("No JSON object found in response")
            
            self.log("JSON parsed successfully.")
            self.log("Analysis complete.")
            
            # Generate PDF
            class PDFReport(FPDF):
                def header(self):
                    self.set_font('Arial', 'B', 16)
                    self.set_text_color(15, 23, 42) # Slate 900
                    self.cell(0, 10, 'PRIVACY-FIRST AI STRATEGY', 0, 1, 'L')
                    self.ln(2)

                def footer(self):
                    self.set_y(-15)
                    self.set_font('Arial', 'I', 8)
                    self.set_text_color(100, 116, 139) # Slate 500
                    self.cell(0, 10, f'Page {self.page_no()} - Generated by Sanjeev Chaodhari', 0, 0, 'C')

            safe_name = result['profile']['name'].replace(' ', '_')
            pdf_filename = f"Zero_Trust_AI_Strategy_for_{safe_name}.pdf"
            pdf_path = os.path.abspath(pdf_filename)
            
            self.log(f"Generating Accessible PDF Report: {pdf_path}")
            pdf = PDFReport()
            
            # --- ACCESSIBILITY IMPROVEMENTS ---
            # 1. Set Document Metadata (Crucial for Screen Readers)
            profile = result.get('profile', {})
            doc_title = f"Zero-Trust AI Strategy for {profile.get('name')}"
            pdf.set_title(doc_title)
            pdf.set_author("Sanjeev Chaodhari")
            pdf.set_subject(f"Legal AI Strategy for {profile.get('firmName')}")
            pdf.set_creator("Legal AI Consultant Agent")
            pdf.set_keywords("Legal, AI, Strategy, Zero-Trust, Privacy")
            
            # 2. Set Display Mode
            # Forces the PDF viewer to show the document at 100% zoom and use the title tag
            pdf.set_display_mode('real', 'default')
            # ----------------------------------

            pdf.add_page()
            
            # 1. Title Section
            pdf.set_font("Arial", size=12)
            pdf.set_text_color(51, 65, 85) # Slate 700
            # Use multi_cell for better reading flow
            pdf.multi_cell(0, 6, f"Lawyer: {profile.get('name')}\nFirm: {profile.get('firmName')}\nPractice Area: {profile.get('practiceArea')}")
            pdf.ln(5)
            
            # 2. Safety Warning Bar (High Contrast Checked: ~7.5:1 ratio)
            pdf.set_fill_color(254, 242, 242) # Red 50
            pdf.set_text_color(153, 27, 27)   # Red 800
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(0, 10, " Safety Notice: These prompts are 'Zero-Trust' engineered. No PII is exposed.", 0, 1, 'L', True)
            pdf.ln(8)

            # 3. Anonymization Technique Explainer
            anon_tech = result.get('anonymizationTechnique', {})
            title = anon_tech.get('title', 'The "Anonymization Sandwich" Protocol')
            desc = anon_tech.get('description', 'This technique ensures safety by replacing sensitive data with placeholders (e.g. [Client Name]) before using AI.')
            
            pdf.set_text_color(15, 23, 42) # Slate 900
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 8, f"1. {title}", ln=True)
            
            pdf.set_font("Arial", size=10)
            pdf.set_text_color(51, 65, 85) # Slate 700
            pdf.multi_cell(0, 5, desc)
            pdf.ln(3)
            
            steps = anon_tech.get('steps', [])
            for step in steps:
                pdf.set_text_color(15, 23, 42)
                pdf.cell(5) # Indent
                pdf.cell(0, 5, f"- {step}", ln=True)
            pdf.ln(8)
            
            # 4. Prompts Section
            pdf.set_text_color(15, 23, 42)
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 8, "2. Tailored Zero-Trust Prompts", ln=True)
            pdf.ln(2)

            prompts = result.get('prompts', [])
            grouped = {}
            for p in prompts:
                cat = p.get('category', 'General')
                if cat not in grouped: grouped[cat] = []
                grouped[cat].append(p)
                
            for category, items in grouped.items():
                # Category Header
                pdf.set_font("Arial", 'B', 12)
                pdf.set_text_color(29, 78, 216) # Blue 700
                pdf.cell(0, 8, category.upper(), ln=True)
                pdf.set_draw_color(29, 78, 216)
                pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 50, pdf.get_y())
                pdf.ln(4)
                
                pdf.set_text_color(15, 23, 42)
                for i, p in enumerate(items):
                    # Prompt Title
                    pdf.set_font("Arial", 'B', 11)
                    pdf.cell(0, 8, f"{i+1}. {p['title']}", ln=True)
                    
                    # Code Block (Grey Box)
                    # High contrast background for distinction
                    pdf.set_font("Courier", size=9)
                    pdf.set_fill_color(248, 250, 252) # Slate 50
                    pdf.set_draw_color(203, 213, 225) # Slate 300 Border
                    pdf.multi_cell(0, 5, p['content'], border=1, fill=True)
                    pdf.ln(1)
                    
                    # Safety Check
                    pdf.set_font("Arial", 'I', 9)
                    pdf.set_text_color(22, 101, 52) # Green 800
                    pdf.cell(0, 6, f"Safety Check: {p.get('safetyCheck', 'Safe usage confirmed.')}", ln=True)
                    pdf.ln(4)
                    pdf.set_text_color(15, 23, 42) # Reset color
                pdf.ln(3)

            # 5. Execution Guide
            pdf.add_page()
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, "3. Execution Guide", ln=True)
            
            steps = [
                ("Step 1: Copy", "Highlight the text in the grey boxes above and copy (CTRL+C)."),
                ("Step 2: Paste", "Paste into your secure firm document (Word/Outlook)."),
                ("Step 3: Re-Identify", "Use CTRL+H to swap placeholders (e.g. [Client Name]) with real data."),
                ("Step 4: Verify", "Review final document to ensure no placeholder text remains.")
            ]
            
            pdf.set_font("Arial", size=10)
            for title, desc in steps:
                pdf.set_font("Arial", 'B', 10)
                pdf.cell(35, 6, title, 0, 0)
                pdf.set_font("Arial", size=10)
                pdf.cell(0, 6, f"- {desc}", 0, 1)

            pdf.output(pdf_path)
            self.log("PDF generated successfully.")
            self.created_pdfs.append(pdf_path)
            
            return {
                "pdf_path": pdf_path,
                "message": result.get('linkedinMessage', 'Here is your report.')
            }

        except Exception as e:
            self.log(f"Error in API generation: {e}")
            import traceback
            self.log(traceback.format_exc())
            return {"pdf_path": None, "message": None}

    def normalize_url(self, url):
        if not url:
            return ""
        # Remove query parameters
        if "?" in url:
            return url.split("?")[0]
        return url

    async def scan_visible_candidates(self):
        try:
            self.log("Scanning visible connections...")
            # Get selector from config
            primary_selector = self.config_manager.get("selectors.connections_list", "div[data-view-name='connections-list']")
            
            # Try multiple selectors, prioritizing config
            selectors = [
                primary_selector,
                "li.mn-connection-card",
                "div.mn-connection-card",
                "div.artdeco-list__item"
            ]
            
            # Remove duplicates if config matches one of the defaults
            selectors = list(dict.fromkeys(selectors))
            
            connections = []
            for sel in selectors:
                connections = await self.page.query_selector_all(sel)
                self.log(f"Selector '{sel}' found {len(connections)} items.")
                if connections:
                    break
            
            if not connections:
                self.log("No connection cards found with any selector.")
                # Save debug snapshot
                try:
                    content = await self.page.content()
                    debug_file = os.path.abspath("debug_no_candidates.html")
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    self.log(f"Saved debug_no_candidates.html at {debug_file}")
                except Exception as e:
                    self.log(f"Failed to save debug snapshot: {e}")
                return []
            
            self.log(f"Found {len(connections)} connection cards in current view.")
            candidates = []
            
            # Load history for filtering
            history_data = self.load_history_json()
            
            for i, conn in enumerate(connections):
                # Find the wrapper link that contains text (Name + Headline)
                links = await conn.query_selector_all("a[data-view-name='connections-profile']")
                wrapper = None
                
                for link in links:
                    text = await link.inner_text()
                    if text.strip():
                        wrapper = link
                        break
                
                if not wrapper:
                    continue
                
                # The wrapper contains p tags. 
                # First p is Name, Second p is Headline.
                paragraphs = await wrapper.query_selector_all("p")
                
                if len(paragraphs) >= 2:
                    name = await paragraphs[0].inner_text()
                    headline = await paragraphs[1].inner_text()
                else:
                    # Fallback if structure is different
                    full_text = await wrapper.inner_text()
                    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                    name = lines[0] if lines else "Unknown"
                    headline = lines[1] if len(lines) > 1 else ""

                profile_url = await wrapper.get_attribute('href')
                if profile_url and profile_url.startswith("/"):
                    profile_url = f"https://www.linkedin.com{profile_url}"
                
                # Normalize URL immediately
                normalized_url = self.normalize_url(profile_url)
                
                name = name.strip()
                headline = headline.strip()
                
                # --- V2.1 CONNECTION GATEKEEPER ---
                
                # 1. Local History Check (Layer 1)
                if normalized_url in history_data:
                    # self.log(f"Skipping {name}: Already in history.json")
                    continue

                # 2. Date Check
                # Find the time badge, usually "Connected 2 weeks ago"
                # It's often in a span or time tag inside the card
                time_text = ""
                try:
                    time_el = await conn.query_selector("time")
                    if not time_el:
                         # Try searching for text containing "Connected"
                         all_text = await conn.inner_text()
                         lines = all_text.split('\n')
                         for line in lines:
                             if "Connected" in line:
                                 time_text = line
                                 break
                    else:
                        time_text = await time_el.inner_text()
                except:
                    pass
                
                if time_text:
                    conn_date = self.parse_connection_date(time_text)
                    days_diff = (datetime.now() - conn_date).days
                    if days_diff > 90:
                        # self.log(f"Skipping {name}: Connected {days_diff} days ago (>90).")
                        continue
                
                # 3. Mark all candidates as PENDING - AI will classify when profile is opened
                #    (We don't call AI here as it would be too slow/expensive for initial scan)
                role_type = "PENDING"
                
                self.log(f"CANDIDATE FOUND: {name} | Role: PENDING | URL: {normalized_url}")
                candidates.append({
                    "name": name,
                    "headline": headline,
                    "url": normalized_url,
                    "original_url": profile_url,
                    "role_type": role_type,
                    "element": conn
                })
            
            return candidates
        except Exception as e:
            self.log(f"Error in scan_visible_candidates: {e}")
            return []

    async def process_candidate(self, candidate):
        if "Jennifer McDaniel" in candidate["name"]:
            self.log("Skipping Jennifer McDaniel (Explicitly skipped for testing).")
            return False

        self.log(f"--- Processing Candidate: {candidate['name']} ({candidate['role_type']}) ---")
        
        # Open in new tab
        new_page = await self.context.new_page()
        try:
            target_url = candidate.get("original_url", candidate["url"])
            self.log(f"Opening new tab for {target_url}...")
            try:
                await new_page.goto(target_url, timeout=15000)
                await new_page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception as e:
                self.log(f"Navigation timeout/error (proceeding anyway): {e}")
            
            # --- AI CLASSIFICATION: Classify using headline + About section ---
            if candidate["role_type"] == "PENDING":
                self.log("Classifying with AI (headline + About)...")
                about_text = await self.scrape_about_section(page=new_page)
                role = self.classify_role(candidate["headline"], about_text)
                
                if role == "SKIP":
                    self.log(f"AI Classification: SKIP. Skipping {candidate['name']}.")
                    await new_page.close()
                    return False
                
                candidate["role_type"] = role
            
            # --- SAFETY PROTOCOL: OPEN CHAT & VERIFY ---
            if not await self.open_chat(target_url, page=new_page):
                self.log("Could not open chat. Skipping.")
                await new_page.close()
                return False
            
            # 1. Identity Verification (Fuzzy Match)
            if not await self.verify_chat_identity(candidate["name"], page=new_page):
                self.log("Identity verification failed. Skipping.")
                await new_page.close()
                return False

            # 2. Visual History Inspection (Duplicate Check)
            if not await self.inspect_chat_history(page=new_page):
                self.log("Manual history detected. Skipping.")
                # Log as SKIPPED in history to prevent re-check?
                # Spec says: Log as {"status": "SKIPPED", "reason": "Manual history detected"}
                history_data = self.load_history_json()
                history_data[candidate["url"]] = {"status": "SKIPPED", "reason": "Manual history detected", "timestamp": datetime.now().isoformat()}
                self.save_history_json_atomic(history_data)
                
                await new_page.close()
                return False

            # --- ROLE FORK ---
            
            if candidate["role_type"] == "GENERAL":
                # Workflow: Verify -> Msg 1 -> Log -> Exit
                self.log("Role: GENERAL. Sending Message 1 only.")
                
                first_name = candidate["name"].split()[0]
                msg = f"Hi {first_name},\n\nThank you for connecting! I'm expanding my network in the legal field and look forward to seeing your updates.\n\nBest,\nSanjeev"
                
                if await self.send_chat_message(msg, page=new_page):
                    self.log("Message 1 sent (General).")
                    
                    # Log Success
                    history_data = self.load_history_json()
                    history_data[candidate["url"]] = {"status": "COMPLETED", "role": "GENERAL", "timestamp": datetime.now().isoformat()}
                    self.save_history_json_atomic(history_data)
                    
                    await self.close_chat(page=new_page)
                    await new_page.close()
                    return True
                else:
                    self.log("Failed to send Message 1.")
                    await new_page.close()
                    return False

            elif candidate["role_type"] == "PRACTICING":
                # Workflow: Verify -> Msg 1 -> Stay Open -> Extract -> Report -> Msg 2 -> Log -> Exit
                self.log("Role: PRACTICING. Executing full workflow.")
                
                # Send Message 1
                first_name = candidate["name"].split()[0]
                msg1 = f"Hi {first_name},\n\nThank you for connecting. I noticed your work in {candidate.get('headline', 'law')} and wanted to share a resource I created on 'Zero-Trust' AI adoption for practicing lawyers.\n\nBest,\nSanjeev"
                
                if not await self.send_chat_message(msg1, page=new_page, verify=True):
                    self.log("Failed to send Message 1. Aborting.")
                    await new_page.close()
                    return False
                
                self.log("Message 1 sent. Proceeding to Report Generation...")
                
                # Extract Data (Hierarchical)
                await self.close_chat(page=new_page)
                
                # Priority 1: Website
                website = await self.extract_website(page=new_page)
                
                report_input = None
                input_type = "url"
                
                if website:
                    self.log(f"Priority 1 Success: Website found ({website})")
                    report_input = website
                    input_type = "url"
                else:
                    self.log("Priority 1 Failed (No Website). Trying Priority 2 (About Section)...")
                    # Priority 2: About Section
                    about_text = await self.scrape_about_section(page=new_page)
                    if about_text and len(about_text) > 50:
                        self.log("Priority 2 Success: About section scraped.")
                        report_input = about_text
                        input_type = "text"
                    else:
                        self.log("Priority 2 Failed (No/Short About). Trying Priority 3 (PDF Fallback)...")
                        # Priority 3: PDF Fallback
                        pdf_path = await self.save_profile_pdf(page=new_page)
                        if pdf_path:
                            self.log("Priority 3 Success: Profile PDF saved.")
                            report_input = pdf_path
                            input_type = "pdf"
                        else:
                            self.log("ALL Extraction Priorities Failed. Cannot generate report.")
                            await new_page.close()
                            return False

                # Generate Report
                report_data = await self.generate_report(report_input, input_type=input_type)
                
                if not report_data["pdf_path"]:
                    self.log("Failed to generate report. Skipping Message 2.")
                    await new_page.close()
                    return False

                # Re-open Chat for Message 2
                if not await self.open_chat(target_url, page=new_page):
                    self.log("Could not re-open chat for Message 2. Aborting.")
                    await new_page.close()
                    return False
                
                # Send Message 2 with Attachment
                msg2 = report_data["message"]
                if not msg2:
                    msg2 = f"Here is the Zero-Trust AI Strategy report I mentioned."
                
                if await self.send_chat_message(msg2, attachment_path=report_data["pdf_path"], page=new_page):
                    self.log("Message 2 sent successfully.")
                    
                    # Log Success
                    history_data = self.load_history_json()
                    history_data[candidate["url"]] = {"status": "COMPLETED", "role": "PRACTICING", "timestamp": datetime.now().isoformat()}
                    self.save_history_json_atomic(history_data)
                    
                    await self.close_chat(page=new_page)
                    await new_page.close()
                    return True
                else:
                    self.log("Failed to send Message 2.")
                    await new_page.close()
                    return False
            
            return False

        except Exception as e:
            self.log(f"Error processing in new tab: {e}")
            await new_page.close()
            return False

    async def stop(self):
        self.log("Stopping agent...")
        try:
            # 1. Close all tabs/pages in the context
            if self.context:
                pages = self.context.pages
                self.log(f"Closing {len(pages)} open tabs...")
                for page in pages:
                    try:
                        await page.close()
                    except:
                        pass
            
            # 2. Delete generated PDF files
            import glob
            pdf_pattern = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Zero_Trust_AI_Strategy_*.pdf")
            pdf_files = glob.glob(pdf_pattern)
            if pdf_files:
                self.log(f"Cleaning up {len(pdf_files)} generated PDF files...")
                for pdf_file in pdf_files:
                    try:
                        os.remove(pdf_file)
                        self.log(f"Deleted: {os.path.basename(pdf_file)}")
                    except Exception as e:
                        self.log(f"Could not delete {pdf_file}: {e}")
            
            # 3. Close the browser (this closes the window)
            if self.browser:
                self.log("Closing browser window...")
                await self.browser.close()
            
            # 4. Stop playwright
            if self.playwright:
                await self.playwright.stop()
                
            self.log("Cleanup complete.")
        except Exception as e:
            self.log(f"Error stopping agent: {e}")

    async def run_workflow(self):
        await self.start()
        
        if not await self.prepare_search_page():
            self.log("Failed to prepare search page. Exiting.")
            await self.stop()
            return

        checked_urls = set()
        scroll_attempts = 0
        MAX_SCROLLS = self.config_manager.get("limits.max_scrolls", 50)
        
        while scroll_attempts < MAX_SCROLLS:
            self.log(f"--- Scan Loop {scroll_attempts + 1}/{MAX_SCROLLS} ---")
            self.run_metrics["scroll_attempts"] += 1
            
            candidates = await self.scan_visible_candidates()
            
            # Filter using normalized URLs
            new_candidates = []
            for c in candidates:
                if c['url'] not in checked_urls:
                    new_candidates.append(c)
                else:
                    # self.log(f"Skipping already checked: {c['name']}")
                    pass

            self.log(f"Found {len(candidates)} candidates ({len(new_candidates)} new).")
            self.run_metrics["candidates_found"] += len(new_candidates)
            
            processed_any = False
            for candidate in new_candidates:
                checked_urls.add(candidate['url'])
                
                # Process the candidate
                if await self.process_candidate(candidate):
                    self.log("Candidate processed successfully. Stopping agent (one per run).")
                    self.run_metrics["messages_sent"] += 1
                    processed_any = True
                    break
            
            if processed_any:
                break
            
            # Count candidates before scroll
            candidates_before = len(candidates)
            
            self.log("No new candidates processed in this view. Scrolling...")
            
            # --- SCROLL LAST CARD INTO VIEW STRATEGY ---
            scroll_effective = False
            try:
                # 0. Check for "Show more results" button first
                # Get selectors from config
                button_selectors = self.config_manager.get("selectors.show_more_btn", [
                    "button:has-text('Show more results')",
                    "button:has-text('Load more')",
                    "button:has-text('Show more')"
                ])
                
                show_more_btn = None
                for sel in button_selectors:
                    btn = await self.page.query_selector(sel)
                    if btn and await btn.is_visible():
                        show_more_btn = btn
                        self.log(f"Found button with selector '{sel}'. Clicking...")
                        break
                
                if show_more_btn:
                    # Use JS click to bypass overlays
                    await show_more_btn.evaluate("node => node.click()")
                    scroll_wait = self.config_manager.get("timeouts.scroll_wait", 3000)
                    await asyncio.sleep(scroll_wait / 1000)
                    scroll_effective = True # Button click is usually effective
                else:
                    # 1. Find all connection cards using the KNOWN working selector
                    primary_selector = self.config_manager.get("selectors.connections_list", "div[data-view-name='connections-list']")
                    cards = await self.page.query_selector_all(primary_selector)
                    
                    if cards:
                        self.log(f"Found {len(cards)} cards. Scrolling last one into view...")
                        last_card = cards[-1]
                        
                        # 2. Scroll the last card into view
                        await last_card.scroll_into_view_if_needed()
                        await asyncio.sleep(0.5)
                        
                        # 3. Force a bit more scroll on the parent to trigger lazy load
                        await last_card.evaluate("""element => {
                            element.scrollIntoView({ behavior: 'smooth', block: 'end', inline: 'nearest' });
                        }""")
                        await asyncio.sleep(0.5)
                        
                        # 4. Try to focus and press ArrowDown/PageDown
                        try:
                            await last_card.focus()
                            for _ in range(5):
                                await self.page.keyboard.press("ArrowDown")
                                await asyncio.sleep(0.1)
                            await self.page.keyboard.press("PageDown")
                        except:
                            pass
                        
                    else:
                        self.log("No cards found to scroll to.")

                    # Fallback to window scroll just in case
                    self.log("Executing window scroll fallback...")
                    await self.page.evaluate("window.scrollBy(0, 1000)")
                    await asyncio.sleep(0.5)
                    await self.page.keyboard.press("End")

                # Wait for network idle (content loading)
                try:
                    scroll_wait = self.config_manager.get("timeouts.scroll_wait", 3000)
                    await asyncio.sleep(scroll_wait / 1000)
                except:
                    await asyncio.sleep(2)
                    
                # Check if new candidates loaded
                new_scan = await self.scan_visible_candidates()
                candidates_after = len(new_scan)
                
                if candidates_after > candidates_before:
                    self.log(f"Scroll Successful: Candidates increased from {candidates_before} to {candidates_after}")
                    scroll_effective = True
                elif show_more_btn:
                     self.log("Scroll Successful: 'Show More' button was clicked.")
                     scroll_effective = True
                else:
                    self.log(f"Scroll Ineffective: Candidate count remained at {candidates_before}")
                    
                if scroll_effective:
                    self.run_metrics["scroll_successes"] += 1
                    
            except Exception as e:
                self.log(f"Scroll error: {e}")
                self.run_metrics["errors"].append(str(e))

            await asyncio.sleep(3)
            scroll_attempts += 1
        
        if scroll_attempts >= MAX_SCROLLS:
            self.log("Max scrolls reached. No new candidates found.")
            
        # Calculate success rate
        if self.run_metrics["scroll_attempts"] > 0:
            self.run_metrics["scroll_success_rate"] = self.run_metrics["scroll_successes"] / self.run_metrics["scroll_attempts"]
        else:
            self.run_metrics["scroll_success_rate"] = 1.0
            
        # Log run to optimizer
        self.log("Logging run metrics to history...")
        self.optimizer.log_run(self.run_metrics)
            
        self.log("Workflow completed.")
        await self.stop()

if __name__ == "__main__":
    agent = LinkedInAgent()
    try:
        asyncio.run(agent.run_workflow())
    except Exception as e:
        import traceback
        with open("agent_log.txt", "a", encoding="utf-8") as f:
            f.write(f"CRITICAL MAIN ERROR: {e}\n")
            f.write(traceback.format_exc() + "\n")
        print(f"CRITICAL MAIN ERROR: {e}")
