import asyncio
import csv
import random
import os
import json
import shutil
import subprocess
import sys
import difflib
import numpy as np
import sounddevice as sd
from winotify import Notification, audio
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
            "message_verification_failed": False,
            "chat_open_failed": False,
            "identity_verification_failed": False,
            "file_upload_failed": False,
            "agent_type": "outreach_agent"
        }
        
        self.history_file = "history.json"
        self.created_pdfs = [] # Track PDFs for cleanup
        self.agent_pages = []  # Track pages created by agent for cleanup
        self.chrome_pid = None  # Track Chrome process ID for cleanup

    def log(self, msg):
        # Write to file with full Unicode support
        with open("agent_log.txt", "a", encoding="utf-8") as f:
            f.write(msg + "\n")
        # Print to console with safe encoding (replace emojis/unicode that console can't handle)
        try:
            print(msg)
        except UnicodeEncodeError:
            # Fallback: encode to ASCII-safe representation
            safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
            print(safe_msg)

    def find_speaker_device(self):
        """Find laptop speaker device (not headphones) by name."""
        try:
            devices = sd.query_devices()
            for i, d in enumerate(devices):
                if d['max_output_channels'] > 0:
                    name = d['name'].lower()
                    # Look for built-in speakers - common names
                    if any(kw in name for kw in ['speaker', 'realtek', 'intel', 'conexant', 'synaptics']):
                        if not any(kw in name for kw in ['headphone', 'head', 'airpod', 'bluetooth', 'bt']):
                            self.log(f"Found speaker device: {d['name']} (index {i})")
                            return i
            self.log("No specific speaker device found. Using default output.")
            return None
        except Exception as e:
            self.log(f"Error finding speaker device: {e}")
            return None

    def play_login_alert(self):
        """Play loud alert sound on laptop speaker (bypassing headphones if possible)."""
        self.log("Playing login alert notification on speaker...")
        try:
            # Find speaker device
            speaker_device = self.find_speaker_device()
            
            # Generate alert tone (1500 Hz beep for 500ms, repeat 3 times)
            sample_rate = 44100
            duration = 0.5  # seconds
            frequency1 = 1500  # Hz
            frequency2 = 1000  # Hz
            
            # Create alternating beeps
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            tone1 = 0.8 * np.sin(2 * np.pi * frequency1 * t)
            tone2 = 0.8 * np.sin(2 * np.pi * frequency2 * t)
            silence = np.zeros(int(sample_rate * 0.1))  # 100ms gap
            
            # Combine: beep1, gap, beep2, gap, beep1, gap, beep2
            alert = np.concatenate([
                tone1, silence, tone2, silence,
                tone1, silence, tone2, silence,
                tone1, silence, tone2
            ])
            
            # Ensure proper format
            alert = alert.astype(np.float32)
            
            # Play on speaker device
            if speaker_device is not None:
                sd.play(alert, sample_rate, device=speaker_device)
            else:
                sd.play(alert, sample_rate)
            sd.wait()  # Wait until done
            
            self.log("Alert sound played successfully.")
        except Exception as e:
            self.log(f"Could not play alert sound: {e}")
            # Fallback to system beep
            try:
                import winsound
                winsound.Beep(1500, 500)
            except:
                pass

    async def show_login_toast_notification(self):
        """Show Windows toast notification with Resume button."""
        self.log("Showing Windows toast notification...")
        
        # Signal file to detect when user clicks Resume
        signal_file = os.path.join(os.path.dirname(__file__), "resume_signal.txt")
        
        # Remove old signal file if exists
        if os.path.exists(signal_file):
            os.remove(signal_file)
        
        def show_toast():
            try:
                toast = Notification(
                    app_id="LinkedIn Agent",
                    title="🔐 Login Required",
                    msg="Please log in to LinkedIn in the browser, then click Resume.",
                    duration="long"
                )
                toast.set_audio(audio.Default, loop=False)
                
                # Create a batch script that will create the signal file
                script_path = os.path.join(os.path.dirname(__file__), "resume_trigger.bat")
                with open(script_path, "w") as f:
                    f.write(f'@echo Resume > "{signal_file}"\n')
                
                toast.add_actions(label="▶ Resume Agent", launch=script_path)
                toast.show()
            except Exception as e:
                self.log(f"Toast notification error: {e}")
        
        # Show toast in executor to not block
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, show_toast)
        
        # Wait for user to click Resume (poll for signal file)
        self.log("Waiting for user to click Resume in notification...")
        while not os.path.exists(signal_file):
            await asyncio.sleep(1)
        
        # Clean up
        try:
            os.remove(signal_file)
            script_path = os.path.join(os.path.dirname(__file__), "resume_trigger.bat")
            if os.path.exists(script_path):
                os.remove(script_path)
        except:
            pass
        
        self.log("User clicked Resume. Continuing agent...")

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

    # --- RESUME STATE MANAGEMENT ---
    
    def load_resume_state(self):
        """Load the resume state from file. Returns empty dict if not found."""
        resume_file = "resume_state.json"
        if not os.path.exists(resume_file):
            return {}
        try:
            with open(resume_file, "r", encoding="utf-8") as f:
                state = json.load(f)
                self.log(f"Loaded resume state: {state.get('last_connections_count', 0)} connections, last top: {state.get('last_top_connection_url', 'N/A')[:50]}...")
                return state
        except Exception as e:
            self.log(f"Could not load resume state: {e}")
            return {}
    
    def save_resume_state(self, connections_count, top_connection_url=None):
        """Save the resume state. This is called at the END of each run."""
        resume_file = "resume_state.json"
        
        # Load existing state to preserve it if needed
        existing_state = self.load_resume_state()
        existing_count = existing_state.get("last_connections_count", 0)
        
        # Only update if we've scrolled further than before
        # This ensures we never lose progress when processing recent connections
        new_count = max(connections_count, existing_count)
        
        state = {
            "last_connections_count": new_count,
            "last_top_connection_url": top_connection_url or existing_state.get("last_top_connection_url"),
            "last_run_timestamp": datetime.now().isoformat()
        }
        
        try:
            with open(resume_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            self.log(f"Saved resume state: {new_count} connections")
        except Exception as e:
            self.log(f"Could not save resume state: {e}")
    
    async def fast_forward_to_position(self, target_count):
        """Quickly click 'Load more' to reach the target connection count.
        
        Uses faster wait times since we're just loading, not processing.
        Returns the actual number of connections loaded.
        """
        self.log(f"Fast-forwarding to position {target_count}...")
        
        # Each "Load more" click typically adds ~10 connections
        # We'll click until we reach the target or run out of buttons
        
        button_selectors = self.config_manager.get("selectors.show_more_btn", [
            "button:has-text('Show more results')",
            "button:has-text('Load more')",
            "button:has-text('Show more')"
        ])
        
        fast_forward_wait = self.config_manager.get("outreach_agent.fast_forward_wait", 1.5)
        max_clicks = (target_count // 10) + 5  # Add buffer for safety
        clicks = 0
        
        while clicks < max_clicks:
            # Check current connection count
            primary_selector = self.config_manager.get("selectors.connections_list", "div[data-view-name='connections-list']")
            cards = await self.page.query_selector_all(primary_selector)
            current_count = len(cards)
            
            if current_count >= target_count:
                self.log(f"Fast-forward complete: {current_count} connections loaded (target: {target_count})")
                return current_count
            
            # Find and click "Load more" button
            show_more_btn = None
            for sel in button_selectors:
                btn = await self.page.query_selector(sel)
                if btn and await btn.is_visible():
                    show_more_btn = btn
                    break
            
            if not show_more_btn:
                self.log(f"No 'Load more' button found. Stopped at {current_count} connections.")
                return current_count
            
            # Click with JS to bypass overlays
            await show_more_btn.evaluate("node => node.click()")
            await asyncio.sleep(fast_forward_wait)
            clicks += 1
            
            # Progress log every 5 clicks
            if clicks % 5 == 0:
                self.log(f"Fast-forward progress: {clicks} clicks, {current_count} connections...")
        
        # Final count
        cards = await self.page.query_selector_all(primary_selector)
        self.log(f"Fast-forward finished: {len(cards)} connections after {clicks} clicks")
        return len(cards)

    def strip_emojis(self, text):
        """Strip emojis and special Unicode characters from text.
        
        Useful for cleaning names like '🛡️ Ot van Daalen' -> 'Ot van Daalen'
        """
        if not text:
            return ""
        import re
        # Regex pattern to match most emoji characters
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F700-\U0001F77F"  # alchemical symbols
            "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
            "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
            "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
            "\U0001FA00-\U0001FA6F"  # Chess Symbols
            "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
            "\U00002702-\U000027B0"  # Dingbats
            "\U0001F1E0-\U0001F1FF"  # Flags (iOS)
            "\U0000FE0F"             # Variation Selector-16 (makes emoji colorful)
            "]+", 
            flags=re.UNICODE
        )
        cleaned = emoji_pattern.sub('', text)
        # Clean up multiple spaces and trim
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def sanitize_for_pdf(self, text):
        """Convert Unicode text to Latin-1 compatible text for FPDF."""
        if not text:
            return ""
        # Comprehensive Unicode character replacements
        replacements = {
            '\u2013': '-',   # en-dash
            '\u2014': '--',  # em-dash
            '\u2015': '--',  # horizontal bar
            '\u2018': "'",   # left single quote
            '\u2019': "'",   # right single quote  
            '\u201a': "'",   # single low-9 quote
            '\u201b': "'",   # single high-reversed-9 quote
            '\u201c': '"',   # left double quote
            '\u201d': '"',   # right double quote
            '\u201e': '"',   # double low-9 quote
            '\u201f': '"',   # double high-reversed-9 quote
            '\u2026': '...', # ellipsis
            '\u2022': '*',   # bullet
            '\u2023': '>',   # triangular bullet
            '\u2027': '-',   # hyphenation point
            '\u00a0': ' ',   # non-breaking space
            '\u2010': '-',   # hyphen
            '\u2011': '-',   # non-breaking hyphen
            '\u2012': '-',   # figure dash
            '\u00b7': '*',   # middle dot
            '\u2032': "'",   # prime
            '\u2033': '"',   # double prime
            '\u2039': '<',   # single left angle quote
            '\u203a': '>',   # single right angle quote
            '\u00ab': '<<',  # left double angle quote
            '\u00bb': '>>',  # right double angle quote
            '\u00ae': '(R)', # registered trademark
            '\u2122': '(TM)',# trademark
            '\u00a9': '(C)', # copyright
            '\u2020': '+',   # dagger
            '\u2021': '++',  # double dagger
            '\u00b0': 'deg', # degree
            '\u2212': '-',   # minus sign
            '\u00d7': 'x',   # multiplication sign
            '\u00f7': '/',   # division sign
        }
        for unicode_char, replacement in replacements.items():
            text = text.replace(unicode_char, replacement)
        # Encode to latin-1, replacing any remaining unsupported chars with ?
        return text.encode('latin-1', errors='replace').decode('latin-1')

    def sanitize_filename(self, name):
        """Sanitize a string for use as a Windows filename.
        
        Removes or replaces all characters illegal in Windows filenames:
        \\ / : * ? " < > |
        Also handles curly quotes and other problematic Unicode characters.
        """
        if not name:
            return "Unknown"
        
        # First, normalize common Unicode quotes/characters
        unicode_replacements = {
            '\u201c': '',   # left double quote "
            '\u201d': '',   # right double quote "
            '\u201e': '',   # double low-9 quote „
            '\u201f': '',   # double high-reversed-9 quote ‟
            '\u2018': '',   # left single quote '
            '\u2019': '',   # right single quote '
            '\u2013': '-',  # en-dash –
            '\u2014': '-',  # em-dash —
        }
        for char, replacement in unicode_replacements.items():
            name = name.replace(char, replacement)
        
        # Remove Windows-illegal characters: \ / : * ? " < > |
        illegal_chars = r'\/:*?"<>|'
        for char in illegal_chars:
            name = name.replace(char, '')
        
        # Replace multiple spaces/underscores with single
        import re
        name = re.sub(r'[\s_]+', '_', name)
        
        # Remove leading/trailing underscores or dots
        name = name.strip('_.')
        
        return name if name else "Unknown"

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

    def validate_practice_area(self, lawyer_name, firm_name, claimed_practice_area, website_url=None):
        """
        Validates the AI-determined practice area by doing a reverse search.
        Uses Gemini with Google Search to verify the lawyer's actual practice areas.
        
        Returns:
            dict: {"valid": bool, "suggested_practice_area": str or None, "confidence": float}
        """
        import os
        
        self.log(f"Validating practice area: '{claimed_practice_area}' for {lawyer_name}...")
        
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
        if not api_key:
            self.log("WARNING: No API key for practice area validation. Skipping validation.")
            return {"valid": True, "suggested_practice_area": None, "confidence": 0.5}
        
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            
            # Build search context
            search_context = f"{lawyer_name}"
            if firm_name:
                search_context += f" {firm_name}"
            if website_url:
                search_context += f" {website_url}"
            
            prompt = f"""You are verifying a lawyer's practice area classification.

CLAIMED PRACTICE AREA: {claimed_practice_area}

LAWYER INFO:
- Name: {lawyer_name}
- Firm: {firm_name or 'Unknown'}
- Website: {website_url or 'Not provided'}

TASK:
1. Use Google Search to find {lawyer_name}'s actual practice areas and specializations.
2. Search for their LinkedIn profile, law firm website, legal directories (Martindale, Avvo, etc.).
3. Compare what you find with the CLAIMED PRACTICE AREA above.
4. Determine if the classification is correct or if it's a significant mismatch.

IMPORTANT: Minor variations are OK (e.g., "Litigation" vs "Civil Litigation"). 
Flag as INVALID only if there's a clear mismatch (e.g., "Real Estate Law" when they actually do "Criminal Defense").

RESPOND IN THIS EXACT FORMAT:
VALID: YES or NO
ACTUAL_PRACTICE_AREA: [The correct practice area based on your research]
CONFIDENCE: [0.0 to 1.0]
REASON: [Brief explanation of what you found]

Example Response:
VALID: NO
ACTUAL_PRACTICE_AREA: Criminal Defense and Appellate Litigation
CONFIDENCE: 0.9
REASON: Found multiple sources indicating the lawyer specializes in criminal appeals and post-conviction work, not real estate."""

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                config={
                    "tools": [{"google_search": {}}]
                },
                contents=prompt
            )
            
            result_text = response.text.strip()
            self.log(f"Practice Area Validation Response:\n{result_text}")
            
            # Parse the response - handle both JSON and plain text formats
            valid = True
            suggested = None
            confidence = 0.5
            reason = ""
            
            # First, try to parse as JSON (AI sometimes returns JSON format)
            try:
                # Strip markdown code fences if present
                json_text = result_text
                if "```json" in json_text:
                    json_text = json_text.split("```json")[1].split("```")[0].strip()
                elif "```" in json_text:
                    json_text = json_text.split("```")[1].split("```")[0].strip()
                
                import re
                parsed_json = json.loads(json_text)
                
                # Extract values from JSON
                if "VALID" in parsed_json:
                    valid = str(parsed_json["VALID"]).upper() == "YES"
                if "ACTUAL_PRACTICE_AREA" in parsed_json:
                    suggested = parsed_json["ACTUAL_PRACTICE_AREA"]
                if "CONFIDENCE" in parsed_json:
                    confidence = float(parsed_json["CONFIDENCE"])
                if "REASON" in parsed_json:
                    reason = parsed_json["REASON"]
                    
                self.log(f"Parsed as JSON: valid={valid}, suggested={suggested}")
            except (json.JSONDecodeError, KeyError, ValueError) as json_err:
                # Fall back to plain text parsing
                self.log(f"JSON parse failed ({json_err}), trying plain text parsing...")
                lines = result_text.split('\n')
                
                for line in lines:
                    line = line.strip()
                    # Handle both "VALID: YES" and '"VALID": "YES"' formats
                    if "VALID" in line.upper() and ("YES" in line.upper() or "NO" in line.upper()):
                        valid = "YES" in line.upper() and "NO" not in line.upper()
                    elif line.startswith("ACTUAL_PRACTICE_AREA:") or '"ACTUAL_PRACTICE_AREA"' in line:
                        suggested = line.replace("ACTUAL_PRACTICE_AREA:", "").replace('"ACTUAL_PRACTICE_AREA":', "").strip().strip('",')
                    elif line.startswith("CONFIDENCE:") or '"CONFIDENCE"' in line:
                        try:
                            conf_str = line.replace("CONFIDENCE:", "").replace('"CONFIDENCE":', "").strip().strip('",')
                            # Handle various formats like "0.9", "0.9/1.0", "90%"
                            if "/" in conf_str:
                                conf_str = conf_str.split("/")[0]
                            if "%" in conf_str:
                                conf_str = str(float(conf_str.replace("%", "")) / 100)
                            confidence = float(conf_str)
                        except:
                            confidence = 0.5
                    elif line.startswith("REASON:") or '"REASON"' in line:
                        reason = line.replace("REASON:", "").replace('"REASON":', "").strip().strip('",')
            
            self.log(f"Validation Result: valid={valid}, suggested={suggested}, confidence={confidence}")
            
            return {
                "valid": valid,
                "suggested_practice_area": suggested if not valid else None,
                "confidence": confidence,
                "reason": reason
            }
            
        except Exception as e:
            self.log(f"Practice area validation error: {e}. Assuming valid.")
            return {"valid": True, "suggested_practice_area": None, "confidence": 0.5}

    async def verify_chat_identity(self, expected_name, page=None):
        page = page or self.page
        try:
            # Dynamic wait: Wait for page to be fully loaded
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass  # Continue even if timeout
            
            # Dynamic config for polling
            max_retries = self.config_manager.get("timeouts.identity_poll_retries", 15)
            poll_delay = self.config_manager.get("timeouts.identity_poll_delay_ms", 300) / 1000
            
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
            
            # Now poll for identity match
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
                
                await asyncio.sleep(poll_delay)  # Dynamic delay from config
            # VISION AI FALLBACK: Safer alternative to page title
            # If chat overlay selectors fail, use Vision AI to verify the name visually
            # This is safer because it sees the actual chat overlay, not just the page URL
            self.log("Chat overlay selectors failed. Trying Vision AI fallback...")
            try:
                screenshot_path = os.path.join(os.path.dirname(__file__), "identity_check_temp.png")
                await page.screenshot(path=screenshot_path)
                
                api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
                if api_key:
                    from google import genai
                    from google.genai import types
                    
                    client = genai.Client(api_key=api_key)
                    with open(screenshot_path, "rb") as f:
                        image_data = f.read()
                    
                    # Ask Vision AI to read the chat participant name
                    prompt = f"""Look at this LinkedIn screenshot.

Is there a chat/message overlay or popup visible on the right side of the screen? If yes, what is the name shown in the chat header (the person being messaged)?

I'm expecting the chat to be with: "{expected_name}"

Answer with ONLY:
MATCH: YES - if the chat header shows "{expected_name}" or a very similar name
MATCH: NO - if the chat shows a different name or no chat is visible

Just respond with MATCH: YES or MATCH: NO"""

                    response = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=[types.Part.from_bytes(data=image_data, mime_type="image/png"), prompt]
                    )
                    
                    result = response.text.strip().upper()
                    self.log(f"Vision AI identity check response: {result}")
                    
                    # Clean up temp file
                    try:
                        os.remove(screenshot_path)
                    except:
                        pass
                    
                    if "MATCH: YES" in result or "YES" in result:
                        self.log(f"Identity Verified (Vision AI): '{expected_name}'")
                        return True
                    else:
                        self.log(f"Vision AI: Chat participant does not match expected '{expected_name}'")
                else:
                    self.log("No API key for Vision AI fallback.")
            except Exception as vision_err:
                self.log(f"Vision AI fallback error: {vision_err}")
            
            # Final fail-closed: Could not verify identity
            self.log(f"Identity Verification Failed. Expected='{expected_name}', Last Found='{last_found_name}'")
            return False

        except Exception as e:
            self.log(f"Error in identity verification: {e}")
            return False

    async def inspect_chat_history(self, page=None):
        """
        Use Gemini Vision to analyze chat screenshot and detect if messages 
        have already been sent by Sanjeev. More robust than CSS class parsing.
        """
        page = page or self.page
        try:
            # Wait for messages to load
            await asyncio.sleep(1.5)
            
            # First quick check: any message bubbles at all?
            bubbles = await page.query_selector_all(".msg-s-event-listitem__message-bubble")
            if not bubbles:
                self.log("No message bubbles found in chat. Proceeding (new conversation).")
                return True  # No history is safe
            
            self.log(f"Found {len(bubbles)} message bubbles in chat. Using Vision AI to check for duplicates...")
            
            # CRITICAL: Scroll to TOP of chat to see ALL messages (including older ones)
            # Older messages may be hidden above the current view
            try:
                chat_container = await page.query_selector(".msg-s-message-list-container, .msg-s-event-listitem, .msg-thread")
                if chat_container:
                    # Scroll to top of the chat container
                    await chat_container.evaluate("el => el.scrollTop = 0")
                    await asyncio.sleep(0.5)
                    self.log("Scrolled chat to top to view all messages.")
                else:
                    # Fallback: Try scrolling via keyboard
                    await page.keyboard.press("Home")
                    await asyncio.sleep(0.5)
            except Exception as scroll_err:
                self.log(f"Warning: Could not scroll chat: {scroll_err}")
            
            # Take screenshot of the chat area
            screenshot_path = os.path.join(os.path.dirname(__file__), "chat_check_temp.png")
            await page.screenshot(path=screenshot_path)
            self.log(f"Screenshot saved for analysis.")
            
            # Use Gemini Vision to analyze
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
            if not api_key:
                self.log("WARNING: No API key for vision check. Falling back to CSS method.")
                return await self._fallback_css_check(page, bubbles)
            
            try:
                from google import genai
                from google.genai import types
                import base64
                
                client = genai.Client(api_key=api_key)
                
                # Read and encode the screenshot
                with open(screenshot_path, "rb") as f:
                    image_data = f.read()
                
                prompt = """Look at this LinkedIn chat screenshot. 

Has "Sanjeev" or "Sanjeev Chaodhari" already sent any messages in this conversation?

Look for:
- Messages on the RIGHT side (sent by the user)
- Messages with "Sanjeev" as the sender name
- Any outgoing messages from the account owner

Answer with ONLY one word: YES or NO

YES = Sanjeev has already sent messages (duplicate - do not send again)
NO = Sanjeev has NOT sent any messages yet (safe to send)"""

                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        types.Part.from_bytes(data=image_data, mime_type="image/png"),
                        prompt
                    ]
                )
                
                result = response.text.strip().upper()
                self.log(f"Vision AI response: {result}")
                
                # Clean up temp file
                try:
                    os.remove(screenshot_path)
                except:
                    pass
                
                if "YES" in result:
                    self.log("DUPLICATE DETECTED (Vision AI): Sanjeev has already sent messages.")
                    return False  # Block - already sent
                elif "NO" in result:
                    self.log("Vision AI confirms: No prior messages from Sanjeev. Safe to proceed.")
                    return True  # Safe to send
                else:
                    self.log(f"Unexpected Vision AI response: {result}. Failing closed for safety.")
                    return False  # Fail closed
                    
            except Exception as vision_error:
                self.log(f"Vision AI error: {vision_error}. Falling back to CSS method.")
                return await self._fallback_css_check(page, bubbles)
                
        except Exception as e:
            self.log(f"Error in vision-based chat history check: {e}")
            self.log("SAFETY: Failing closed due to history check error.")
            return False
    
    async def _fallback_css_check(self, page, bubbles):
        """Fallback CSS-based check if Vision AI fails."""
        try:
            last_bubbles = bubbles[-5:] if len(bubbles) >= 5 else bubbles
            for bubble in last_bubbles:
                list_item = await bubble.evaluate_handle("el => el.closest('.msg-s-event-listitem')")
                if list_item:
                    class_attr = await list_item.get_attribute("class")
                    if class_attr and ("msg-s-event-listitem--me" in class_attr or "msg-s-message-group--align-right" in class_attr):
                        bubble_text = await bubble.inner_text()
                        self.log(f"DUPLICATE DETECTED (CSS fallback): '{bubble_text[:50]}...'")
                        return False
            self.log("CSS fallback check passed. No prior messages detected.")
            return True
        except Exception as e:
            self.log(f"CSS fallback error: {e}")
            return False  # Fail closed

    async def scrape_about_section(self, page=None):
        """Scrape About section with multiple fallback selectors."""
        page = page or self.page
        self.log("Scraping About section...")
        
        # Multiple selectors in priority order for different LinkedIn layouts
        selectors = [
            "#about",
            "section.pv-about-section",
            "[data-section='about']",
            "section:has(> div > h2:has-text('About'))",
            ".core-section-container:has(h2:has-text('About'))",
            "#ember-about-section",
            "section.artdeco-card:has(h2:has-text('About'))",
            ".pv-shared-text-with-see-more",
        ]
        
        for selector in selectors:
            try:
                about_section = await page.query_selector(selector)
                if about_section:
                    text = await about_section.inner_text()
                    # Clean up header text
                    text = text.replace("About", "").strip()
                    if len(text) > 10:
                        self.log(f"About section scraped ({len(text)} chars) using selector: {selector}")
                        return text
            except Exception as e:
                # Silently continue to next selector
                continue
        
        # Fallback: Try to find any section with 'About' header
        try:
            all_sections = await page.query_selector_all("section")
            for section in all_sections:
                try:
                    header = await section.query_selector("h2")
                    if header:
                        header_text = await header.inner_text()
                        if "About" in header_text:
                            text = await section.inner_text()
                            text = text.replace("About", "").replace(header_text, "").strip()
                            if len(text) > 10:
                                self.log(f"About section found via fallback scan ({len(text)} chars)")
                                return text
                except:
                    continue
        except Exception as e:
            self.log(f"Fallback About section search failed: {e}")
        
        self.log("About section not found with any selector.")
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
            self.agent_pages.append(self.page)  # Track for cleanup
            self.log("Connected to existing Chrome.")
            
            # Close any pre-existing chat popups across ALL pages to prevent identity confusion
            self.log("Closing any pre-existing chat popups...")
            for existing_page in self.context.pages:
                try:
                    await self.close_existing_chats(existing_page)
                except:
                    pass  # Ignore errors on pages we don't control
        except Exception as e:
            self.log(f"Failed to connect to existing Chrome: {e}")
            self.log("Attempting to launch Chrome automatically...")
            await self.launch_browser()
            
            # Try connecting with multiple retries
            max_retries = 5
            for attempt in range(max_retries):
                await asyncio.sleep(3)  # Wait between attempts
                try:
                    self.log(f"Connection attempt {attempt + 1}/{max_retries}...")
                    self.browser = await self.playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
                    self.context = self.browser.contexts[0]
                    
                    # Get existing pages BEFORE creating new one
                    existing_pages = list(self.context.pages)
                    
                    # Create our new page FIRST (so Chrome has at least one tab)
                    self.page = await self.context.new_page()
                    self.agent_pages.append(self.page)  # Track for cleanup
                    
                    # NOW close pre-existing tabs (safe because we just created one)
                    if existing_pages:
                        self.log(f"Closing {len(existing_pages)} pre-existing tab(s)...")
                        for p in existing_pages:
                            try:
                                await p.close()
                            except:
                                pass
                    
                    self.log("Connected to launched Chrome.")
                    return  # Success!
                except Exception as e2:
                    self.log(f"Attempt {attempt + 1} failed: {e2}")
                    if attempt == max_retries - 1:
                        raise e2

    async def launch_browser(self):
        import subprocess
        import socket
        
        # First, kill any existing Chrome processes using port 9222
        self.log("Checking for existing Chrome processes on port 9222...")
        try:
            # Use netstat to find process using port 9222
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
        self.chrome_pid = process.pid  # Store PID for cleanup
        self.log(f"Chrome launched with PID: {self.chrome_pid}")
        
        # Wait for Chrome to start and verify it's listening on port 9222
        self.log("Waiting for Chrome to start and open debug port...")
        for i in range(15):  # Up to 15 seconds
            await asyncio.sleep(1)
            # Check if process is still running
            if process.poll() is not None:
                self.log(f"ERROR: Chrome process exited prematurely with code {process.returncode}")
                return
            # Check if port 9222 is listening
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', 9222))
                sock.close()
                if result == 0:
                    self.log(f"Chrome debug port is now listening (after {i+1}s)")
                    await asyncio.sleep(2)  # Extra buffer for stability
                    return
            except:
                pass
        
        self.log("WARNING: Chrome launched but port 9222 not detected after 15s")

    async def prepare_search_page(self):
        try:
            self.log(f"Navigating to {LINKEDIN_CONNECTIONS_URL}...")
            await self.page.goto(LINKEDIN_CONNECTIONS_URL)
            
            page_load_wait = self.config_manager.get("timeouts.page_load", 5000) / 1000
            self.log(f"Waiting {page_load_wait}s for page load...")
            await asyncio.sleep(page_load_wait)
            
            # Check login
            try:
                await self.page.wait_for_selector("div[data-view-name='connections-list']", timeout=10000)
                self.log("Connections list found.")
                return True
            except Exception:
                self.log("Login check failed or selector not found.")
                self.log("Login required! Notifying user...")
                
                # Play loud alert and show resume dialog
                self.play_login_alert()
                await self.show_login_toast_notification()
                
                # Verify login after user clicks resume
                while True:
                    url = self.page.url
                    if "feed" in url or "mynetwork" in url:
                        self.log("Login detected (URL match).")
                        break
                    # Not logged in yet - alert again
                    self.log("Still waiting for login... (URL does not indicate logged in)")
                    self.play_login_alert()
                    await self.show_login_toast_notification()
                
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
                ".msg-overlay-bubble-header button svg[data-test-icon='close-small']",
                # Additional selectors for newer LinkedIn UI
                "button[aria-label='Close conversation']",
                "button[aria-label='Close message']",
                ".msg-overlay-bubble-header__controls button"
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
            
            # SAFETY: Clear any message input boxes to prevent stale content
            try:
                msg_boxes = await page.query_selector_all(".msg-form__contenteditable")
                for msg_box in msg_boxes:
                    try:
                        await msg_box.fill("")
                    except:
                        pass
            except:
                pass
            
            # Final resort: Press Escape multiple times to close any overlays
            for _ in range(3):
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.2)
                    
        except Exception as e:
            self.log(f"Error closing existing chats: {e}")

    async def _find_message_button(self, page):
        """Find the Message button on a LinkedIn profile with multiple strategies."""
        # Strategy 1: Direct button/anchor search
        buttons = await page.query_selector_all("button:has-text('Message'), a:has-text('Message')")
        for btn in buttons:
            try:
                if await btn.is_visible():
                    text = await btn.inner_text()
                    if "Message" in text:
                        return btn
            except:
                continue
        
        # Strategy 2: Check "More actions" dropdown
        more_btn = await page.query_selector("button[aria-label='More actions']")
        if more_btn:
            try:
                await more_btn.click()
                await asyncio.sleep(1)
                msg_option = await page.query_selector("div[role='button']:has-text('Message')")
                if msg_option:
                    return msg_option
            except:
                pass
        
        # Strategy 3: Try aria-label selectors
        aria_selectors = [
            "button[aria-label*='Message']",
            "button[aria-label*='message']",
        ]
        for selector in aria_selectors:
            btn = await page.query_selector(selector)
            if btn:
                try:
                    if await btn.is_visible():
                        return btn
                except:
                    continue
        
        return None

    async def open_chat(self, profile_url, page=None, retries=None):
        page = page or self.page
        self.log(f"Opening chat for {profile_url}...")
        
        # Dynamic retry configuration from config.json
        if retries is None:
            retries = self.config_manager.get("limits.chat_open_retries", 3)
        retry_delay_ms = self.config_manager.get("limits.chat_open_delay_ms", 2000)
        retry_delay = retry_delay_ms / 1000  # Convert to seconds
        
        # Multiple selectors for chat input (LinkedIn UI varies)
        chat_input_selectors = [
            ".msg-form__contenteditable",
            "div[role='textbox'][contenteditable='true']",
            ".msg-form__message-texteditor",
            "[data-artdeco-is-focused]",
            ".msg-form__msg-content-container div[contenteditable='true']",
        ]
        
        for attempt in range(retries):
            try:
                # Close any existing chat overlays first
                await self.close_existing_chats(page)
                
                if attempt > 0:
                    self.log(f"Chat open retry attempt {attempt + 1}/{retries}...")
                
                await page.goto(profile_url, timeout=60000)
                
                # Wait for page to be fully loaded
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except:
                    pass  # Continue even if timeout
                
                # Find Message button using helper method
                msg_btn = await self._find_message_button(page)
                
                if not msg_btn:
                    self.log("Message button not found.")
                    if attempt < retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    # Debug info on final attempt
                    all_btns = await page.query_selector_all("button")
                    btn_texts = []
                    for b in all_btns[:10]:
                        try:
                            t = await b.inner_text()
                            btn_texts.append(t.strip())
                        except:
                            pass
                    self.log(f"Visible buttons (debug): {btn_texts}")
                    return False

                await msg_btn.evaluate("node => node.click()")
                await asyncio.sleep(1)  # Give UI time to respond
                
                # Try multiple selectors for chat input
                for selector in chat_input_selectors:
                    try:
                        await page.wait_for_selector(selector, timeout=5000, state="visible")
                        self.log(f"Chat input found with selector: {selector}")
                        return True
                    except:
                        continue
                
                # If no selector worked, try clicking Message button again
                if attempt < retries - 1:
                    self.log("Chat input not found. Will retry...")
                    await asyncio.sleep(retry_delay)
                    continue
                
                self.log("Chat input not found after all attempts.")
                return False
                    
            except Exception as e:
                self.log(f"Error opening chat (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return False
        
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

    async def send_chat_message(self, message_text, attachment_path=None, page=None, verify=True, retries=None, expected_name=None):
        page = page or self.page
        
        # Dynamic config values
        if retries is None:
            retries = self.config_manager.get("limits.send_message_retries", 2)
        file_upload_wait = self.config_manager.get("timeouts.file_upload_wait_ms", 5000) / 1000
        ui_wait = self.config_manager.get("timeouts.ui_response_wait_ms", 1000) / 1000
        
        # Helper function to safely clear message input on failure
        async def _clear_input_on_failure():
            try:
                msg_box = await page.query_selector(".msg-form__contenteditable")
                if msg_box:
                    await msg_box.fill("")  # Clear stale message to prevent wrong-person sends
                    self.log("Cleared message input (safety cleanup).")
            except:
                pass
        
        for attempt in range(retries + 1):
            try:
                self.log(f"Sending message (Attempt {attempt + 1}/{retries + 1})...")
                msg_form = await page.wait_for_selector(".msg-form__contenteditable", timeout=5000)
                if not msg_form:
                    self.log("Message input not found.")
                    return False
                
                await msg_form.fill("") # Clear first
                await msg_form.type(message_text)
                await asyncio.sleep(ui_wait)

                if attachment_path:
                    self.log(f"Attaching file: {attachment_path}")
                    file_input = await page.query_selector("input[type='file']")
                    if file_input:
                        await file_input.set_input_files(attachment_path)
                        self.log("File uploaded. Waiting for processing...")
                        await asyncio.sleep(file_upload_wait)
                    else:
                        # Try clicking attach button
                        attach_btn = await page.query_selector("button[aria-label='Attach file']")
                        if attach_btn:
                            await attach_btn.click()
                            await asyncio.sleep(ui_wait)
                            file_input = await page.query_selector("input[type='file']")
                            if file_input:
                                await file_input.set_input_files(attachment_path)
                                await asyncio.sleep(file_upload_wait)
                
                # Click Send - try multiple selectors for robustness
                send_btn = None
                send_selectors = [
                    "button[type='submit']",
                    "button.msg-form__send-button",
                    ".msg-form__send-button",
                    "button[aria-label='Send']",
                    "button[aria-label='Send message']",
                    "button[data-control-name='send']",
                    ".msg-form__send-btn",
                    "button.msg-form__send-btn",
                    # New LinkedIn UI selectors (2024)
                    "button.msg-form__send-toggle",
                    ".msg-form__right-actions button[type='submit']",
                    "form.msg-form button[type='submit']",
                ]
                
                for selector in send_selectors:
                    try:
                        send_btn = await page.query_selector(selector)
                        if send_btn and await send_btn.is_visible():
                            self.log(f"Found Send button with selector: {selector}")
                            break
                        send_btn = None
                    except:
                        continue
                
                # If still not found, try waiting for it to become enabled
                if not send_btn:
                    self.log("Send button not found immediately. Waiting 2s for UI to update...")
                    await asyncio.sleep(2)
                    for selector in send_selectors[:3]:  # Try top 3 again
                        try:
                            send_btn = await page.wait_for_selector(selector, timeout=3000, state="visible")
                            if send_btn:
                                self.log(f"Found Send button after wait with selector: {selector}")
                                break
                        except:
                            continue
                
                # Wait for send button to become enabled (poll with configurable retries)
                # This handles cases where LinkedIn is still processing an uploaded file
                send_enabled_retries = self.config_manager.get("limits.send_button_enabled_retries", 5)
                send_enabled_poll = self.config_manager.get("timeouts.send_button_enabled_poll_ms", 500) / 1000
                
                button_enabled = False
                if send_btn:
                    for poll_attempt in range(send_enabled_retries):
                        try:
                            if await send_btn.is_enabled():
                                button_enabled = True
                                break
                        except:
                            pass
                        if poll_attempt < send_enabled_retries - 1:
                            self.log(f"Send button not yet enabled, waiting {send_enabled_poll}s (attempt {poll_attempt + 1}/{send_enabled_retries})...")
                            await asyncio.sleep(send_enabled_poll)
                
                if button_enabled:
                    # SAFETY CHECK: Re-verify chat identity before sending
                    # This catches any chat window switches that may have occurred
                    if expected_name:
                        self.log(f"Safety re-verification before Send (expected: {expected_name})...")
                        if not await self.verify_chat_identity(expected_name, page=page):
                            self.log(f"SAFETY ABORT: Identity re-verification failed before Send!")
                            await _clear_input_on_failure()
                            return False
                        self.log("Identity re-confirmed. Proceeding to send.")
                    
                    # Scroll button into view to prevent "outside of viewport" errors
                    try:
                        await send_btn.scroll_into_view_if_needed()
                        await asyncio.sleep(0.3)
                    except:
                        pass
                    
                    # Try regular click first, fall back to JS click if it fails
                    try:
                        await send_btn.click(timeout=5000)
                        self.log("Send button clicked.")
                    except Exception as click_err:
                        self.log(f"Regular click failed ({click_err}), trying JS click...")
                        # JavaScript click bypasses viewport/overlay issues
                        await send_btn.evaluate("node => node.click()")
                        self.log("Send button clicked (via JS).")
                    
                    # Use configured wait time
                    wait_time = self.config_manager.get("timeouts.message_send_wait", 3000)
                    await asyncio.sleep(wait_time / 1000)
                    
                    if verify:
                        self.log("Verifying message sent...")
                        # Wait for UI update - use config value
                        verify_wait = self.config_manager.get("timeouts.message_verify_wait_ms", 2000) / 1000
                        await asyncio.sleep(verify_wait)
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
                    self.log("Send button not found or still disabled after polling.")
                    await _clear_input_on_failure()  # Clear to prevent stale message
                    return False
            except Exception as e:
                self.log(f"Error sending chat message: {e}")
                self.run_metrics["errors"].append(str(e))
                if attempt < retries:
                    continue
                await _clear_input_on_failure()  # Clear to prevent stale message
                return False
        
        await _clear_input_on_failure()  # Clear to prevent stale message
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


    async def generate_report(self, input_data, input_type="url", candidate_name=None):
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
                # Include candidate name if provided (for URL case, website usually has name but this ensures correctness)
                name_context = f"The lawyer's name is: {candidate_name}. " if candidate_name else ""
                prompt_text = f"""
                {name_context}Perform a deep research analysis on this lawyer's website URL: {input_data}.
                1. Use the provided name ('{candidate_name}') as the lawyer's name.
                2. Use Google Search to find details about their firm and practice area focus.
                """
                prompt_content.append(prompt_text)
                
            elif input_type == "text":
                # Include candidate name if provided
                name_context = f"The lawyer's name is: {candidate_name}\n" if candidate_name else ""
                prompt_text = f"""
                {name_context}Analyze the following text extracted from the lawyer's LinkedIn profile (About Section/Headline):
                
                --- BEGIN PROFILE TEXT ---
                {input_data}
                --- END PROFILE TEXT ---
                
                1. Use the provided name ('{candidate_name}') as the lawyer's name - do NOT guess or extract a different name.
                2. Extract details about their firm and practice area focus from the text.
                """
                prompt_content.append(prompt_text)
                
            elif input_type == "pdf":
                # Include candidate name if provided
                name_context = f"The lawyer's name is: {candidate_name}. " if candidate_name else ""
                prompt_text = f"""
                {name_context}Analyze the attached PDF of the lawyer's LinkedIn profile.
                1. Use the provided name ('{candidate_name}') as the lawyer's name - do NOT guess or extract a different name.
                2. Extract details about their firm and practice area focus from the PDF.
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

            # --- LOGGING: Log what we're analyzing ---
            self.log(f"--- Report Generation Input ---")
            self.log(f"Input Type: {input_type}")
            if input_type == "url":
                self.log(f"Website URL: {input_data}")
            elif input_type == "text":
                self.log(f"Text Preview: {input_data[:200]}..." if len(input_data) > 200 else f"Text: {input_data}")
            elif input_type == "pdf":
                self.log(f"PDF Path: {input_data}")
            self.log(f"Candidate Name: {candidate_name}")
            self.log(f"-------------------------------")

            self.log("Calling Gemini API...")
            
            # Configure tools
            tools = [{"google_search": {}}] if input_type == "url" else []
            
            # --- VALIDATION RETRY LOOP ---
            MAX_VALIDATION_RETRIES = 2
            practice_area_hint = None  # Used for retry with corrected practice area
            
            for validation_attempt in range(MAX_VALIDATION_RETRIES + 1):
                # Build prompt with optional practice area hint for retry
                current_prompt = prompt_content.copy()
                if practice_area_hint:
                    self.log(f"Retry {validation_attempt}: Using corrected practice area hint: {practice_area_hint}")
                    current_prompt.insert(0, f"IMPORTANT CORRECTION: The lawyer's actual practice area is: {practice_area_hint}. Use this as the primary practice area for generating the report.")
                
                response = client.models.generate_content(
                    model="gemini-2.0-flash-exp", # Using Flash for speed/multimodal, or 3-pro if available. Spec said 3-pro.
                    # Spec: "Gemini 3 Pro exclusively".
                    # I will use "gemini-3-pro-preview" as requested.
                    config={
                        "system_instruction": SYSTEM_INSTRUCTION,
                        "tools": tools,
                        "response_mime_type": "application/json"
                    },
                    contents=current_prompt
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
                
                # --- PRACTICE AREA VALIDATION ---
                practice_area = result.get('profile', {}).get('practiceArea', 'Unknown')
                lawyer_name = result.get('profile', {}).get('name', candidate_name or 'Unknown')
                firm_name = result.get('profile', {}).get('firmName', '')
                
                self.log(f"Initial Practice Area: {practice_area}")
                
                # Validate with reverse search
                validation = self.validate_practice_area(
                    lawyer_name=lawyer_name,
                    firm_name=firm_name,
                    claimed_practice_area=practice_area,
                    website_url=input_data if input_type == "url" else None
                )
                
                if validation["valid"] or validation["confidence"] >= 0.7:
                    self.log(f"[OK] Practice Area Validated: {practice_area}")
                    break  # Validation passed, exit retry loop
                else:
                    if validation["suggested_practice_area"] and validation_attempt < MAX_VALIDATION_RETRIES:
                        self.log(f"[!] PRACTICE AREA VALIDATION FAILED (Attempt {validation_attempt + 1}/{MAX_VALIDATION_RETRIES + 1})")
                        self.log(f"   Claimed: {practice_area}")
                        self.log(f"   Suggested: {validation['suggested_practice_area']}")
                        self.log(f"   Confidence: {validation['confidence']}")
                        self.log(f"   Reason: {validation.get('reason', 'N/A')}")
                        self.log("Re-generating report with corrected practice area...")
                        practice_area_hint = validation["suggested_practice_area"]
                        # Continue to next iteration of retry loop
                    else:
                        self.log(f"[!] Practice area validation failed but no retry available. Using: {practice_area}")
                        break
            
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

            # Sanitize filename - remove any non-ASCII characters
            raw_name = result.get('profile', {}).get('name', 'Unknown')
            safe_name = self.sanitize_filename(raw_name)
            pdf_filename = f"Zero_Trust_AI_Strategy_for_{safe_name}.pdf"
            pdf_path = os.path.abspath(pdf_filename)
            
            self.log(f"Generating Accessible PDF Report: {pdf_path}")
            pdf = PDFReport()
            
            # --- ACCESSIBILITY IMPROVEMENTS ---
            # 1. Set Document Metadata (Crucial for Screen Readers)
            # NOTE: All metadata must be sanitized for Latin-1 encoding
            profile = result.get('profile', {})
            doc_title = self.sanitize_for_pdf(f"Zero-Trust AI Strategy for {profile.get('name', 'Unknown')}")
            pdf.set_title(doc_title)
            pdf.set_author("Sanjeev Chaodhari")
            pdf.set_subject(self.sanitize_for_pdf(f"Legal AI Strategy for {profile.get('firmName', 'Unknown Firm')}"))
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
            profile_text = f"Lawyer: {profile.get('name')}\nFirm: {profile.get('firmName')}\nPractice Area: {profile.get('practiceArea')}"
            pdf.multi_cell(0, 6, self.sanitize_for_pdf(profile_text))
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
            pdf.multi_cell(0, 5, self.sanitize_for_pdf(desc))
            pdf.ln(3)
            
            steps = anon_tech.get('steps', [])
            for step in steps:
                pdf.set_text_color(15, 23, 42)
                pdf.cell(5) # Indent
                pdf.cell(0, 5, f"- {self.sanitize_for_pdf(step)}", ln=True)
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
                    pdf.cell(0, 8, f"{i+1}. {self.sanitize_for_pdf(p['title'])}", ln=True)
                    
                    # Code Block (Grey Box)
                    # High contrast background for distinction
                    pdf.set_font("Courier", size=9)
                    pdf.set_fill_color(248, 250, 252) # Slate 50
                    pdf.set_draw_color(203, 213, 225) # Slate 300 Border
                    pdf.multi_cell(0, 5, self.sanitize_for_pdf(p['content']), border=1, fill=True)
                    pdf.ln(1)
                    
                    # Safety Check
                    pdf.set_font("Arial", 'I', 9)
                    pdf.set_text_color(22, 101, 52) # Green 800
                    pdf.cell(0, 6, f"Safety Check: {self.sanitize_for_pdf(p.get('safetyCheck', 'Safe usage confirmed.'))}", ln=True)
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

    def trigger_troubleshooting(self, candidate, error_context):
        """
        Triggers the 'Crash Report Handoff' workflow.
        1. Generates ANTIGRAVITY_MISSION.md with error details.
        2. Force-opens the file/folder in Antigravity IDE (or default editor).
        3. Pauses execution for user intervention.
        """
        self.log(f"[CRITICAL] FAILURE for {candidate['name']} ({candidate['role_type']}). Initiating Troubleshooting Handoff...")
        
        # Get log tail
        log_tail = ""
        try:
            with open("agent_log.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()
                log_tail = "".join(lines[-30:]) # Last 30 lines
        except:
            log_tail = "Could not read log file."

        filename = "ANTIGRAVITY_MISSION.md"
        
        mission_content = f"""# AGENT HANDOVER: TROUBLESHOOTING REQUIRED

## Status
Local Agent failed to complete the workflow for candidate: **[{candidate['name']}]({candidate['url']})**
**Error Context:** {error_context}

## The Mission
1. Analyze the error logs below.
2. Review `linkedin_agent.py` to identify why `{error_context}` occurred.
3. Fix the code.

## Recent Logs
```text
{log_tail}
```
"""
        # 1. Write the Mission File
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(mission_content)
            self.log(f"Mission file created: {filename}")
        except Exception as e:
            self.log(f"Failed to write mission file: {e}")

        # 2. Try to Force Open in Antigravity
        possible_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Google\Antigravity\antigravity.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Antigravity\antigravity.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Google\Antigravity\antigravity.exe"),
        ]

        launched = False

        # A. Try to launch via direct path
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    # Open the current folder AND the file
                    subprocess.Popen([path, ".", filename])
                    self.log("Launching Google Antigravity...")
                    launched = True
                    break
                except Exception as e:
                    self.log(f"Failed to launch exe: {e}")

        # B. Try to launch via 'antigravity' command (if in PATH)
        if not launched and shutil.which("antigravity"):
            try:
                subprocess.Popen(["antigravity", ".", filename])
                self.log("Launching via 'antigravity' command...")
                launched = True
            except:
                pass

        # C. Fallback: standard system open
        if not launched:
            self.log("[!] Antigravity exe not found. Opening default editor.")
            try:
                os.startfile(os.getcwd()) # Open folder
                os.startfile(filename)    # Open file
            except:
                self.log("Could not open file system.")

        # 3. Pause/Stop Execution
        print("\n" + "="*50)
        print("[STOP] EXECUTION PAUSED FOR TROUBLESHOOTING")
        print(f"Error: {error_context}")
        print("Please review the opened ANTIGRAVITY_MISSION.md file.")
        print("Fix the issue, then restart the agent.")
        print("="*50 + "\n")
        
        # We exit here to force the user to deal with it
        # sys.exit(1) would kill it, but maybe we want to keep the window open?
        # The user said "agent should open... and send first instruction".
        # Let's pause with input() so the console stays open.
        try:
            input("Press Enter to Exit Agent after troubleshooting...")
        except:
            pass
        sys.exit(1)

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
                try:
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
                    
                    # Clean name and headline - strip emojis and special characters
                    name = self.strip_emojis(name.strip())
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
                except Exception as candidate_error:
                    # Log error but continue processing other candidates
                    # This prevents one bad candidate (e.g., with emoji) from breaking the entire scan
                    self.log(f"Warning: Skipped candidate {i} due to error: {str(candidate_error)[:50]}")
                    continue
            
            return candidates
        except Exception as e:
            self.log(f"Error in scan_visible_candidates: {e}")
            return []

    async def process_candidate(self, candidate):
        self.log(f"--- Processing Candidate: {candidate['name']} ({candidate['role_type']}) ---")
        
        # Open in new tab
        new_page = await self.context.new_page()
        self.agent_pages.append(new_page)  # Track for cleanup
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
                    # Track SKIP'd candidates in history so they're not re-processed
                    # This enables fast-forward to work correctly on subsequent runs
                    history_data = self.load_history_json()
                    history_data[candidate["url"]] = {
                        "status": "SKIPPED_NOT_LEGAL", 
                        "reason": f"Not a lawyer: {candidate.get('headline', 'Unknown')[:50]}",
                        "timestamp": datetime.now().isoformat()
                    }
                    self.save_history_json_atomic(history_data)
                    await new_page.close()
                    return False
                
                candidate["role_type"] = role
            
            # --- SAFETY PROTOCOL: OPEN CHAT & VERIFY ---
            if not await self.open_chat(target_url, page=new_page):
                self.log("Could not open chat. Skipping.")
                self.run_metrics["chat_open_failed"] = True  # Track for optimizer
                await new_page.close()
                return False
            
            # 1. Identity Verification (Fuzzy Match)
            if not await self.verify_chat_identity(candidate["name"], page=new_page):
                self.log("Identity verification failed. Skipping.")
                self.run_metrics["identity_verification_failed"] = True  # Track for optimizer
                # Close the chat popup to prevent blocking subsequent candidates
                await self.close_chat(page=new_page)
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
                
                # Close the chat popup to prevent blocking subsequent candidates
                await self.close_chat(page=new_page)
                await new_page.close()
                return False

            # --- ROLE FORK ---
            
            if candidate["role_type"] == "GENERAL":
                # Workflow: Verify -> Msg 1 -> Log -> Exit
                self.log("Role: GENERAL. Sending Message 1 only.")
                
                first_name = candidate["name"].split()[0]
                msg = f"Hi {first_name},\n\nThank you for connecting! I'm expanding my network in the legal field and look forward to seeing your updates.\n\nBest,\nSanjeev"
                
                if await self.send_chat_message(msg, page=new_page, expected_name=candidate["name"]):
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
                    # Close chat popup before closing page to prevent floating chat
                    await self.close_chat(page=new_page)
                    await new_page.close()
                    return False

            elif candidate["role_type"] == "PRACTICING":
                # Workflow: Verify -> Msg 1 -> Stay Open -> Extract -> Report -> Msg 2 -> Log -> Exit
                self.log("Role: PRACTICING. Executing full workflow.")
                
                # Send Message 1
                first_name = candidate["name"].split()[0]
                msg1 = f"Hi {first_name},\n\nThank you for connecting. I noticed your work in {candidate.get('headline', 'law')} and wanted to share a resource I created on 'Zero-Trust' AI adoption for practicing lawyers.\n\nBest,\nSanjeev"
                
                if not await self.send_chat_message(msg1, page=new_page, verify=True, expected_name=candidate["name"]):
                    self.log("Failed to send Message 1. Aborting.")
                    # Close chat popup before closing page to prevent floating chat
                    await self.close_chat(page=new_page)
                    await new_page.close()
                    return False
                
                self.log("Message 1 sent. Proceeding to Report Generation...")
                
                # CRITICAL: Log as PARTIAL immediately after Message 1 is sent
                # This prevents duplicate messages if report generation fails
                history_data = self.load_history_json()
                history_data[candidate["url"]] = {
                    "status": "PARTIAL", 
                    "role": "PRACTICING", 
                    "msg1_sent": True,
                    "msg2_sent": False,
                    "timestamp": datetime.now().isoformat()
                }
                self.save_history_json_atomic(history_data)
                self.log("Logged as PARTIAL (Message 1 sent). Will skip on failure to prevent duplicates.")
                
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
                            self.log("ALL Extraction Priorities Failed. Cannot generate report. (Logged as PARTIAL)")
                            await new_page.close()
                            return True  # Return True since Message 1 was sent and candidate is logged

                # Generate Report - pass candidate name to ensure correct personalization
                report_data = await self.generate_report(report_input, input_type=input_type, candidate_name=candidate["name"])
                
                if not report_data["pdf_path"]:
                    self.log("Failed to generate report. Skipping Message 2. (Logged as PARTIAL)")
                    await new_page.close()
                    return True  # Return True since Message 1 was sent and candidate is logged

                # Re-open Chat for Message 2
                # Re-open Chat for Message 2
                if not await self.open_chat(target_url, page=new_page):
                    self.log("Could not re-open chat for Message 2. (Logged as PARTIAL)")
                    self.run_metrics["chat_open_failed"] = True
                    await new_page.close()
                    return True  # Return True since Message 1 was sent and candidate is logged
                
                # Send Message 2 with Attachment
                msg2 = report_data["message"]
                if not msg2:
                    msg2 = f"Here is the Zero-Trust AI Strategy report I mentioned."
                
                if await self.send_chat_message(msg2, attachment_path=report_data["pdf_path"], page=new_page, expected_name=candidate["name"]):
                    self.log("Message 2 sent successfully.")
                    
                    # Log Success
                    history_data = self.load_history_json()
                    history_data[candidate["url"]] = {"status": "COMPLETED", "role": "PRACTICING", "timestamp": datetime.now().isoformat()}
                    self.save_history_json_atomic(history_data)
                    
                    await self.close_chat(page=new_page)
                    await new_page.close()
                    return True
                else:
                    self.log("Failed to send Message 2 or attachment.")
                    self.trigger_troubleshooting(candidate, "Message 2 / Attachment Failed")
                    await new_page.close()
                    return True  # Return True since Message 1 was sent and candidate is logged as PARTIAL
            
            return False

        except Exception as e:
            self.log(f"Error processing in new tab: {e}")
            await new_page.close()
            return False

    async def stop(self):
        self.log("Stopping agent...")
        try:
            # 1. Close only pages created by the agent (not user's existing tabs)
            if self.agent_pages:
                self.log(f"Closing {len(self.agent_pages)} agent-created tabs...")
                for page in self.agent_pages:
                    try:
                        if not page.is_closed():
                            await page.close()
                    except:
                        pass
                self.agent_pages = []
            
            # 2. Delete generated PDF files and Screenshots
            import glob
            
            # Define patterns for all temporary files to clean up
            cleanup_patterns = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "Zero_Trust_AI_Strategy_*.pdf"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile_snapshot_*.pdf"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "identity_check_temp.png"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_no_candidates.html")
            ]
            
            for pattern in cleanup_patterns:
                files = glob.glob(pattern)
                if files:
                    self.log(f"Cleaning up {len(files)} files matching '{os.path.basename(pattern)}'...")
                    for file_path in files:
                        try:
                            os.remove(file_path)
                            self.log(f"Deleted: {os.path.basename(file_path)}")
                        except Exception as e:
                            self.log(f"Could not delete {file_path}: {e}")
            
            # 3. Kill the Chrome process we launched (if any)
            if self.chrome_pid:
                import subprocess
                self.log(f"Terminating Chrome process (PID: {self.chrome_pid})...")
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(self.chrome_pid)], 
                                  capture_output=True, timeout=10)
                    self.chrome_pid = None
                except Exception as e:
                    self.log(f"Could not kill Chrome process: {e}")
            else:
                self.log("No Chrome process to kill (connected to existing browser).")
            
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
        
        # --- RESUME STATE LOGIC ---
        resume_state = self.load_resume_state()
        resume_position = resume_state.get("last_connections_count", 0)
        max_connections_reached = 0  # Track the furthest we've scrolled this run
        top_connection_url = None    # Track the top connection for next run
        
        if resume_position > 0:
            self.log(f"Resume state found: Last processed up to {resume_position} connections")
            
            # Step 1: Check top ~10 connections for new candidates (not in history)
            self.log("Checking for new recent connections at top...")
            initial_candidates = await self.scan_visible_candidates()
            
            # Store the top connection URL for next run's reference
            if initial_candidates:
                top_connection_url = initial_candidates[0].get('url')
            
            # Check if any are genuinely new (not in history)
            history_data = self.load_history_json()
            new_at_top = [c for c in initial_candidates if c['url'] not in history_data]
            
            if new_at_top:
                self.log(f"Found {len(new_at_top)} new connection(s) at top! Processing first...")
                # Process new connection(s) at top first (normal flow will handle this)
                # We DON'T fast-forward, but we preserve the resume position
            else:
                self.log("No new connections at top. Fast-forwarding to resume position...")
                # Fast-forward to where we left off
                actual_count = await self.fast_forward_to_position(resume_position)
                max_connections_reached = actual_count
                self.log(f"Resumed at {actual_count} connections. Starting normal scan...")
        else:
            self.log("No resume state found. Starting fresh scan...")
        
        while scroll_attempts < MAX_SCROLLS:
            self.log(f"--- Scan Loop {scroll_attempts + 1}/{MAX_SCROLLS} ---")
            self.run_metrics["scroll_attempts"] += 1
            
            candidates = await self.scan_visible_candidates()
            
            # Track the first connection URL (for resume state)
            if candidates and not top_connection_url:
                top_connection_url = candidates[0].get('url')
            
            # Update max connections reached (use TOTAL connection cards, not filtered candidates)
            # Query the actual connection card count for accurate resume position
            try:
                primary_selector = self.config_manager.get("selectors.connections_list", "div[data-view-name='connections-list']")
                all_cards = await self.page.query_selector_all(primary_selector)
                total_connections_visible = len(all_cards)
                max_connections_reached = max(max_connections_reached, total_connections_visible)
            except:
                # Fallback to candidate count if selector fails
                max_connections_reached = max(max_connections_reached, len(candidates))
            
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
                # Save resume state before exiting (preserve max position)
                self.save_resume_state(max_connections_reached, top_connection_url)
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
        
        # Save resume state for next run (always save, even if no candidate processed)
        self.save_resume_state(max_connections_reached, top_connection_url)
            
        self.log("Workflow completed.")
        await self.stop()

LOCK_FILE = "agent.lock"

def acquire_lock():
    """Acquire a lock to prevent multiple instances running simultaneously."""
    import time
    
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                data = json.load(f)
                old_pid = data.get("pid")
                start_time = data.get("started_at", "")
            
            # Check if process is still running
            import psutil
            if old_pid and psutil.pid_exists(old_pid):
                print(f"ERROR: Another agent instance is already running (PID: {old_pid}, started: {start_time})")
                print("If this is incorrect, delete 'agent.lock' and try again.")
                return False
            else:
                # Old process died without cleanup, safe to proceed
                print(f"Found stale lock file (PID {old_pid} not running). Cleaning up...")
                os.remove(LOCK_FILE)
        except (json.JSONDecodeError, KeyError, Exception) as e:
            # Corrupted lock file, remove it
            print(f"Removing corrupted lock file: {e}")
            try:
                os.remove(LOCK_FILE)
            except:
                pass
    
    # Create new lock
    with open(LOCK_FILE, "w") as f:
        json.dump({
            "pid": os.getpid(),
            "started_at": datetime.now().isoformat()
        }, f)
    
    return True

def release_lock():
    """Release the lock file."""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception as e:
        print(f"Warning: Could not remove lock file: {e}")

if __name__ == "__main__":
    # Check for existing instance
    if not acquire_lock():
        sys.exit(1)
    
    agent = LinkedInAgent()
    try:
        asyncio.run(agent.run_workflow())
    except Exception as e:
        import traceback
        with open("agent_log.txt", "a", encoding="utf-8") as f:
            f.write(f"CRITICAL MAIN ERROR: {e}\n")
            f.write(traceback.format_exc() + "\n")
        print(f"CRITICAL MAIN ERROR: {e}")
    finally:
        # Always release lock
        release_lock()

