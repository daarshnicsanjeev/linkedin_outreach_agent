import asyncio
import csv
import random
import os
from playwright.async_api import async_playwright

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
USER_DATA_DIR = "./user_data"
HEADLESS = False
LINKEDIN_CONNECTIONS_URL = "https://www.linkedin.com/mynetwork/invite-connect/connections/"
AI_STUDIO_URL = "https://aistudio.google.com/apps/drive/151Go3tB8IZqJZRmyPWTC00WtHu3rQ3Pn?showPreview=true&showAssistant=true"

KEYWORDS_ROLE = ["partner", "founder", "ceo", "director", "managing partner", "principal"]
KEYWORDS_INDUSTRY = ["law", "legal", "attorney", "firm", "litigation", "counsel"]

class LinkedInAgent:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

    def log(self, msg):
        print(msg)
        with open("agent_log.txt", "a", encoding="utf-8") as f:
            f.write(msg + "\n")

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

    async def stop(self):
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()

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

    async def open_chat(self, profile_url, page=None):
        page = page or self.page
        self.log(f"Opening chat for {profile_url}...")
        try:
            await page.goto(profile_url, timeout=60000)
            await page.wait_for_load_state("domcontentloaded", timeout=60000)
            
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
                self.log("Message button not found.")
                return False

            await msg_btn.evaluate("node => node.click()")
            await asyncio.sleep(5) # Wait for chat to open
            
            # Wait for input to be sure it's ready
            try:
                await page.wait_for_selector(".msg-form__contenteditable", timeout=10000)
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

    async def send_chat_message(self, message_text, attachment_path=None, page=None):
        page = page or self.page
        try:
            msg_form = await page.wait_for_selector(".msg-form__contenteditable", timeout=5000)
            if not msg_form:
                self.log("Message input not found.")
                return False
            
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
                self.log("Message sent.")
                await asyncio.sleep(2)
                return True
            else:
                self.log("Send button not found or disabled.")
                return False
        except Exception as e:
            self.log(f"Error sending chat message: {e}")
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


    async def generate_report(self, website_url):
        self.log(f"Generating report for {website_url} using Gemini API...")
        
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
        if not api_key:
            self.log("ERROR: GEMINI_API_KEY or API_KEY not set in environment variables.")
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
1. Research a lawyer based on a provided URL OR analyze their provided Resume/Bio PDF.
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
            prompt_text = f"""
            Perform a deep research analysis on this lawyer's website URL: {website_url}.
            
            1. Use Google Search to find details about the lawyer, their firm, and their practice area focus.
            2. Based on their SPECIFIC practice area, generate EXACTLY 10 high-value, Zero-Trust AI prompts.
               - Organize these prompts into 3-4 dynamic categories that are highly specific to the lawyer's practice area.
               - e.g., if IP Law: "Patent Analysis", "Trademark Filing". Avoid generic names.
            3. Ensure strict adherence to the Zero-Trust protocol (use placeholders like [Client Name]).
            4. Generate a professional LinkedIn message from "Sanjeev Chaodhari" acting as a Strategic Legal Consultant.
               RULES:
               - TONE: Professional, concise, peer-to-peer. NO "marketing speak".
               - FORMAT:
                 Hi [First Name],
                 I noticed [Firm Name] specializes in [Specific Practice Area], so I generated a **"Zero-Trust" AI Audit** specifically for your practice.
                 It includes 10 ready-to-use workflows—including [Mention 2 specific topics derived from the generated prompts]—that use an "anonymization sandwich" technique. This allows your team to use AI for complex drafting without ever exposing privileged client data.
                 I've attached the PDF. You can preview the prompts directly here in the chat.
                 Best,
                 Sanjeev
               - CRITICAL: Replace all [bracketed placeholders] with actual data extracted from the lawyer's profile or the prompts you just generated.
            
            Return the result in valid JSON format.
            """

            self.log("Calling Gemini API...")
            response = client.models.generate_content(
                model="gemini-3-pro-preview", 
                config={
                    "system_instruction": SYSTEM_INSTRUCTION,
                    "tools": [{"google_search": {}}],
                    "response_mime_type": "application/json"
                },
                contents=[prompt_text]
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
                    self.cell(0, 10, 'PRIVACY-FIRST AI AUDIT', 0, 1, 'L')
                    self.ln(2)

                def footer(self):
                    self.set_y(-15)
                    self.set_font('Arial', 'I', 8)
                    self.set_text_color(100, 116, 139) # Slate 500
                    self.cell(0, 10, f'Page {self.page_no()} - Generated by Sanjeev Chaodhari', 0, 0, 'C')

            safe_name = result['profile']['name'].replace(' ', '_')
            pdf_filename = f"Audit_{safe_name}_{random.randint(1000,9999)}.pdf"
            pdf_path = os.path.abspath(pdf_filename)
            
            self.log(f"Generating Accessible PDF Report: {pdf_path}")
            pdf = PDFReport()
            
            # --- ACCESSIBILITY IMPROVEMENTS ---
            # 1. Set Document Metadata (Crucial for Screen Readers)
            profile = result.get('profile', {})
            doc_title = f"Zero-Trust AI Audit for {profile.get('name')}"
            pdf.set_title(doc_title)
            pdf.set_author("Sanjeev Chaodhari")
            pdf.set_subject(f"Legal AI Audit for {profile.get('firmName')}")
            pdf.set_creator("Legal AI Consultant Agent")
            pdf.set_keywords("Legal, AI, Audit, Zero-Trust, Privacy")
            
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
            
            return {
                "pdf_path": pdf_path,
                "message": result.get('linkedinMessage', 'Here is your report.')
            }

        except Exception as e:
            self.log(f"Error in API generation: {e}")
            import traceback
            self.log(traceback.format_exc())
            return {"pdf_path": None, "message": None}

    async def scan_visible_candidates(self):
        try:
            self.log("Scanning visible connections...")
            # Try multiple selectors
            selectors = [
                "div[data-view-name='connections-list']",
                "li.mn-connection-card",
                "div.mn-connection-card",
                "div.artdeco-list__item"
            ]
            
            connections = []
            for sel in selectors:
                connections = await self.page.query_selector_all(sel)
                self.log(f"Selector '{sel}' found {len(connections)} items.")
                if connections:
                    break
            
            if not connections:
                self.log("No connection cards found with any selector.")
                # Save debug snapshot
                await self.page.content()
                with open("debug_no_candidates.html", "w", encoding="utf-8") as f:
                    f.write(await self.page.content())
                self.log("Saved debug_no_candidates.html")
                return []
            
            self.log(f"Found {len(connections)} connection cards in current view.")
            self.log(f"Found {len(connections)} connection cards in current view.")
            candidates = []
            
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
                
                name = name.strip()
                headline = headline.strip()
                
                # self.log(f"Checking [{i}]: {name} - {headline}")
                
                headline_lower = headline.lower()
                role_match = any(k in headline_lower for k in KEYWORDS_ROLE)
                industry_match = any(k in headline_lower for k in KEYWORDS_INDUSTRY)
                
                if role_match and industry_match:
                    self.log(f"MATCH FOUND: {name}")
                    candidates.append({
                        "name": name,
                        "headline": headline,
                        "url": profile_url,
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

        self.log(f"--- Processing Candidate: {candidate['name']} ---")
        
        # Open in new tab to preserve scroll on main page
        new_page = await self.context.new_page()
        try:
            self.log(f"Opening new tab for {candidate['url']}...")
            try:
                await new_page.goto(candidate["url"], timeout=15000)
                await new_page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception as e:
                self.log(f"Navigation timeout/error (proceeding anyway): {e}")
            
            # 2. Check Chat History & Decide
            if not await self.open_chat(candidate["url"], page=new_page):
                self.log("Could not open chat in new tab. Skipping.")
                await new_page.close()
                return False
            
            history = await self.get_chat_history(page=new_page)
            history_text = " ".join(history).lower()
            
            msg1_sent = "thank you for connecting" in history_text or "sanjeev chaodhari" in history_text
            msg2_sent = "privacy-first" in history_text or "zero-trust" in history_text or "brief report" in history_text
            
            self.log(f"History Check: Msg1 Sent={msg1_sent}, Msg2 Sent={msg2_sent}")

            # FORCE PROCESS FOR DEMO (Mitchell Chubb)
            if "Mitchell Chubb" in candidate["name"]:
                self.log("FORCING PROCESS for Mitchell Chubb (Demo Mode)")
                msg1_sent = False
                msg2_sent = False

            if msg1_sent and msg2_sent:
                self.log("All messages already sent. Skipping.")
                await self.close_chat(page=new_page)
                await new_page.close()
                return False # Already processed

            # 3. Send Message 1 if needed
            if not msg1_sent:
                self.log("Sending Message 1...")
                first_name = candidate["name"].split()[0]
                thank_you_msg = f"Hi {first_name},\n\nThank you for connecting with me. I look forward to following your work.\n\nBest,\nSanjeev Chaodhari"
                if await self.send_chat_message(thank_you_msg, page=new_page):
                    msg1_sent = True
                else:
                    self.log("Failed to send Message 1. Aborting this candidate.")
                    await self.close_chat(page=new_page)
                    await new_page.close()
                    return False
            else:
                self.log("Message 1 already sent. Skipping.")

            # 4. Send Message 2 if needed
            if not msg2_sent:
                # We need to generate the report.
                # Close chat to avoid interference with extraction
                await self.close_chat(page=new_page)
                
                # Extract Website (we are already on profile page in new tab)
                website = await self.extract_website(page=new_page)
                if not website:
                    self.log("No website found. Cannot generate report. Skipping.")
                    await new_page.close()
                    return False
                    
                self.log(f"Extracted Website: {website}")

                # Generate Report
                report_data = await self.generate_report(website)
                if not report_data["pdf_path"]:
                    self.log("Failed to generate report. Skipping.")
                    await new_page.close()
                    return False

                # Re-open chat
                if not await self.open_chat(candidate["url"], page=new_page):
                    self.log("Could not re-open chat. Skipping.")
                    await new_page.close()
                    return False
                
                self.log("Sending Message 2...")
                follow_up_msg = report_data["message"]
                if not follow_up_msg:
                    first_name = candidate["name"].split()[0]
                    follow_up_msg = f"Hi {first_name},\n\nI created a brief report based on your website. Please find it attached."
                
                if await self.send_chat_message(follow_up_msg, attachment_path=report_data["pdf_path"], page=new_page):
                     self.log("Message 2 sent successfully.")
                     await self.close_chat(page=new_page)
                     await new_page.close()
                     return True # Successfully processed new candidate
                else:
                     self.log("Failed to send Message 2.")
                     await self.close_chat(page=new_page)
                     await new_page.close()
                     return False
            else:
                self.log("Message 2 already sent. Skipping.")
                await self.close_chat(page=new_page)
                await new_page.close()
                return False # Nothing new done
        except Exception as e:
            self.log(f"Error processing in new tab: {e}")
            await new_page.close()
            return False

    async def run_workflow(self):
        await self.start()
        
        if not await self.prepare_search_page():
            self.log("Failed to prepare search page. Exiting.")
            await self.stop()
            return

        checked_urls = set()
        scroll_attempts = 0
        MAX_SCROLLS = 50
        
        while scroll_attempts < MAX_SCROLLS:
            self.log(f"--- Scan Loop {scroll_attempts + 1}/{MAX_SCROLLS} ---")
            
            candidates = await self.scan_visible_candidates()
            new_candidates = [c for c in candidates if c['url'] not in checked_urls]
            
            self.log(f"Found {len(candidates)} candidates ({len(new_candidates)} new).")
            
            processed_any = False
            for candidate in new_candidates:
                checked_urls.add(candidate['url'])
                
                # Process the candidate
                # If process_candidate returns True, it means we did something (sent a message).
                # If it returns False, it means they were already done or failed.
                if await self.process_candidate(candidate):
                    self.log("Candidate processed successfully. Stopping agent (one per run).")
                    processed_any = True
                    break
            
            if processed_any:
                break
            
            self.log("No new candidates processed in this view. Scrolling...")
            
            # Click to ensure focus
            try:
                await self.page.click("h1", timeout=1000)
            except:
                try:
                    await self.page.click("body", timeout=1000)
                except:
                    pass

            # Try multiple scroll methods
            # 1. Scroll the lazy column directly
            try:
                lazy_col = await self.page.query_selector("div[data-testid='lazy-column']")
                if lazy_col:
                    # Hover and scroll
                    await lazy_col.hover()
                    await self.page.mouse.wheel(0, 5000)
                    # Also try JS scroll
                    await lazy_col.evaluate("el => el.scrollTop += 5000")
                else:
                    await self.page.mouse.wheel(0, 5000)
            except:
                pass
            
            await asyncio.sleep(2)
            
            # 2. Keyboard End (ensure focus on body or list)
            try:
                await self.page.click("body")
                await self.page.keyboard.press("End")
            except:
                pass

            await asyncio.sleep(3)
            scroll_attempts += 1
        
        if scroll_attempts >= MAX_SCROLLS:
            self.log("Max scrolls reached. No new candidates found.")
            
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
