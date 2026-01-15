"""
LinkedIn Outreach Agent
======================
Scans LinkedIn connections, identifies legal professionals, 
and sends personalized outreach messages with PDF reports.

Features:
- Scans connections page for recent connections
- AI-powered role classification (PRACTICING, GENERAL, SKIP)
- Generates professional PDF reports
- Sends personalized chat messages with attachments
- Resume state for interrupted runs
- Self-optimization based on run history

Refactored: 2026-01-11 - Now uses BaseAgent for shared functionality

Author: AI Agent
Created: 2024-12-09
"""

import asyncio
import csv
import random
import os
import json
import shutil
import subprocess
import sys
import difflib
import re
from datetime import datetime, timedelta

from dotenv import load_dotenv

from ..agents.base_agent import BaseAgent
from ..utils.anti_detection import (
    human_delay, human_scroll, human_mouse_move, 
    human_like_navigate, human_like_click, human_like_type
)

# Load environment variables
load_dotenv()

# Configuration
LINKEDIN_CONNECTIONS_URL = "https://www.linkedin.com/mynetwork/invite-connect/connections/"
LOCK_FILE = "agent.lock"


class OutreachAgent(BaseAgent):
    """
    Outreach agent that scans LinkedIn connections, identifies legal professionals,
    and sends personalized messages with PDF reports.
    
    Inherits from BaseAgent for:
    - Browser management
    - Logging
    - Configuration
    - History management
    - Debug capture
    """
    
    def get_agent_name(self) -> str:
        return "OutreachAgent"
    
    def __init__(self, config_path: str = "config.json"):
        super().__init__(config_path)
        
        self.history_file = "history.json"
        self.created_pdfs = []
        self.agent_pages = []
        
        # Metrics for optimization
        self.run_metrics.update({
            "candidates_found": 0,
            "messages_sent": 0,
            "scroll_attempts": 0,
            "scroll_successes": 0,
            "message_verification_failed": False,
            "chat_open_failed": False,
            "identity_verification_failed": False,
            "file_upload_failed": False,
            "agent_type": "outreach_agent"
        })
    
    async def run(self):
        """Main outreach agent workflow."""
        self.log("=" * 60)
        self.log("LinkedIn Outreach Agent Starting")
        self.log("=" * 60)
        
        try:
            # Navigate to connections page
            if not await self._prepare_connections_page():
                self.log("Failed to prepare connections page. Exiting.")
                return
            
            # Load resume state
            resume_state = self.load_history("resume_state.json") or {}
            resume_position = resume_state.get("last_connections_count", 0)
            
            # Process connections
            await self._process_connections(resume_position)
            
            # Save metrics
            self.optimizer.log_run(self.run_metrics)
            
            # Print summary
            self._print_summary()
            
        except Exception as e:
            self.log(f"CRITICAL ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self._cleanup()
    
    async def _prepare_connections_page(self) -> bool:
        """Navigate to connections page and ensure it's ready."""
        self.log(f"Navigating to connections: {LINKEDIN_CONNECTIONS_URL}")
        
        await human_like_navigate(self.page, LINKEDIN_CONNECTIONS_URL)
        await asyncio.sleep(3)
        
        # Check for login
        current_url = self.page.url
        if "login" in current_url or "authwall" in current_url:
            self.log("LOGIN REQUIRED - Please log in to LinkedIn")
            self.play_ready_sound()
            self.show_notification("Login Required", "Please log in to LinkedIn")
            
            # Wait for login
            for _ in range(60):
                await asyncio.sleep(5)
                current_url = self.page.url
                if "login" not in current_url and "authwall" not in current_url:
                    self.log("Login detected. Continuing...")
                    await asyncio.sleep(3)
                    break
            else:
                self.log("ERROR: Login timeout.")
                return False
        
        # Close any chat popups
        await self.close_chat_popups()
        
        # Verify page loaded
        try:
            await self.page.wait_for_selector(
                "div[data-view-name='connections-list']",
                timeout=10000
            )
            self.log("Connections page loaded.")
            return True
        except:
            self.log("WARNING: Could not verify connections list loaded.")
            return True
    
    async def _process_connections(self, resume_position: int):
        """Main loop for processing connections."""
        checked_urls = set()
        scroll_attempts = 0
        max_scrolls = self.get_config("limits.max_scrolls", 50)
        max_connections = 0
        
        # Fast-forward if resuming
        if resume_position > 0:
            self.log(f"Resuming from position {resume_position}...")
            current = await self._fast_forward(resume_position)
            max_connections = current
        
        while scroll_attempts < max_scrolls:
            # Scan visible candidates
            candidates = await self._scan_visible_candidates()
            
            # Process each candidate
            for candidate in candidates:
                url = candidate.get("url")
                if url in checked_urls:
                    continue
                checked_urls.add(url)
                
                # Process this candidate
                await self._process_candidate(candidate)
                
                # Update max position
                current_count = await self._get_connection_count()
                if current_count > max_connections:
                    max_connections = current_count
            
            # Scroll for more
            await human_scroll(self.page, random.randint(600, 1000))
            await human_delay(2.0, 4.0)
            scroll_attempts += 1
            
            if scroll_attempts % 5 == 0:
                self.log(f"Scroll progress: {scroll_attempts}/{max_scrolls}")
        
        # Save resume state
        self.save_history("resume_state.json", {
            "last_connections_count": max_connections,
            "last_run_timestamp": datetime.now().isoformat()
        })
    
    async def _fast_forward(self, target_count: int) -> int:
        """Fast-forward to resume position by clicking Load More."""
        self.log(f"Fast-forwarding to position {target_count}...")
        
        button_selectors = self.get_config("selectors.show_more_btn", [
            "button:has-text('Show more results')",
            "button:has-text('Load more')",
            "button:has-text('Show more')"
        ])
        
        clicks = 0
        max_clicks = (target_count // 10) + 5
        
        while clicks < max_clicks:
            current = await self._get_connection_count()
            if current >= target_count:
                break
            
            # Find and click load more
            for sel in button_selectors:
                btn = await self.page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.evaluate("node => node.click()")
                    await asyncio.sleep(1.5)
                    clicks += 1
                    break
            else:
                break
        
        return await self._get_connection_count()
    
    async def _get_connection_count(self) -> int:
        """Get current number of visible connections."""
        cards = await self.page.query_selector_all("div[data-view-name='connections-list']")
        return len(cards)
    
    async def _scan_visible_candidates(self) -> list:
        """Scan visible connection cards and extract candidate info."""
        candidates = []
        
        cards = await self.page.query_selector_all("div[data-view-name='connections-list'] li")
        
        for card in cards[:20]:  # Process up to 20 at a time
            try:
                # Get profile link
                link = await card.query_selector("a[href*='/in/']")
                if not link:
                    continue
                
                url = await link.get_attribute("href")
                if url and url.startswith("/"):
                    url = "https://www.linkedin.com" + url
                
                # Get name
                name_el = await card.query_selector(".mn-connection-card__name")
                name = await name_el.inner_text() if name_el else "Unknown"
                name = self._strip_emojis(name)
                
                # Get headline
                headline_el = await card.query_selector(".mn-connection-card__occupation")
                headline = await headline_el.inner_text() if headline_el else ""
                
                # Get connection date
                date_el = await card.query_selector(".time-badge")
                date_text = await date_el.inner_text() if date_el else ""
                
                candidates.append({
                    "name": name,
                    "url": url,
                    "headline": headline,
                    "connection_date": date_text
                })
                
            except Exception as e:
                continue
        
        self.run_metrics["candidates_found"] += len(candidates)
        return candidates
    
    async def _process_candidate(self, candidate: dict):
        """Process a single candidate - classify, generate report, send message."""
        name = candidate.get("name", "Unknown")
        url = candidate.get("url", "")
        headline = candidate.get("headline", "")
        
        # Check history
        history = self.load_history(self.history_file) or {}
        if url in history:
            self.log(f"Skipping {name} - already processed")
            return
        
        self.log(f"Processing: {name}")
        
        # Classify role
        role = self._classify_role(headline)
        
        if role == "SKIP":
            self.log(f"  Skipping {name} - not relevant")
            history[url] = {"name": name, "status": "skipped", "reason": "not_relevant"}
            self.save_history(self.history_file, history)
            return
        
        # Navigate to profile
        profile_page = await self.context.new_page()
        self.agent_pages.append(profile_page)
        
        try:
            await profile_page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            # Extract website
            website = await self._extract_website(profile_page)
            
            # Scrape About section
            about_text = await self._scrape_about(profile_page)
            
            # Generate PDF report
            pdf_path = await self._generate_report(website or url, name)
            
            # Open chat and send message
            if pdf_path:
                success = await self._send_outreach_message(
                    profile_page, name, role, pdf_path
                )
                
                if success:
                    self.run_metrics["messages_sent"] += 1
                    history[url] = {
                        "name": name,
                        "status": "messaged",
                        "role": role,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    history[url] = {"name": name, "status": "message_failed"}
            else:
                history[url] = {"name": name, "status": "report_failed"}
            
            self.save_history(self.history_file, history)
            
        except Exception as e:
            self.log(f"  Error processing {name}: {e}")
            self.record_error(str(e))
        finally:
            await profile_page.close()
    
    def _classify_role(self, headline: str) -> str:
        """Classify role using Gemini AI."""
        if not headline:
            return "GENERAL"
        
        try:
            prompt = f"""Analyze this LinkedIn headline and classify the person's legal background.

Headline: {headline}

Classification Rules:
- PRACTICING: Currently practicing lawyers, attorneys, partners, associates, counsel
- GENERAL: Law students, paralegals, legal tech, compliance, legal background but not practicing
- SKIP: No legal background

Respond with ONLY one word: PRACTICING, GENERAL, or SKIP"""

            response = self.gemini.generate(prompt)
            result = response.strip().upper()
            
            if result in ["PRACTICING", "GENERAL", "SKIP"]:
                self.log(f"  AI Classification: {result}")
                return result
            return "GENERAL"
            
        except Exception as e:
            self.log(f"  Classification error: {e}")
            return "GENERAL"
    
    async def _extract_website(self, page) -> str:
        """Extract website URL from profile."""
        try:
            # Try contact info section
            contact_btn = await page.query_selector("a#top-card-text-details-contact-info")
            if contact_btn:
                await contact_btn.click()
                await asyncio.sleep(2)
                
                website_link = await page.query_selector("a[href*='http']:not([href*='linkedin'])")
                if website_link:
                    url = await website_link.get_attribute("href")
                    
                    # Close modal
                    close_btn = await page.query_selector("button[aria-label='Dismiss']")
                    if close_btn:
                        await close_btn.click()
                    
                    return url
        except:
            pass
        
        return ""
    
    async def _scrape_about(self, page) -> str:
        """Scrape About section from profile."""
        try:
            about_selectors = [
                "section[data-section='summary'] div.full-width",
                "#about ~ .pvs-list div.full-width",
                ".pv-about__summary-text",
                "div[id*='about'] span[aria-hidden='true']"
            ]
            
            for sel in about_selectors:
                el = await page.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    if text and len(text) > 20:
                        return text[:2000]
        except:
            pass
        
        return ""
    
    async def _generate_report(self, input_data: str, candidate_name: str) -> str:
        """Generate a PDF report using Gemini analysis."""
        try:
            self.log(f"  Generating report for {candidate_name}...")
            
            # Use Gemini to analyze
            prompt = f"""Analyze this law firm website or lawyer profile and create a brief professional summary.

URL/Data: {input_data}

Create a 2-3 paragraph summary covering:
1. Firm/lawyer overview and specialization
2. Key practice areas
3. Notable achievements or differentiators

Keep it professional and concise."""

            response = self.gemini.generate(prompt)
            
            # Create simple PDF
            from fpdf import FPDF
            
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            pdf.cell(0, 10, f"Legal Practice Summary", ln=True, align="C")
            pdf.set_font("Arial", "", 11)
            pdf.ln(10)
            
            # Clean text for PDF
            clean_text = self._sanitize_for_pdf(response)
            pdf.multi_cell(0, 6, clean_text)
            
            # Save PDF
            safe_name = self._sanitize_filename(candidate_name)
            pdf_path = f"{safe_name}_Report.pdf"
            pdf.output(pdf_path)
            
            self.created_pdfs.append(pdf_path)
            self.log(f"  Report saved: {pdf_path}")
            
            return pdf_path
            
        except Exception as e:
            self.log(f"  Report generation error: {e}")
            return ""
    
    async def _send_outreach_message(self, page, name: str, role: str, pdf_path: str) -> bool:
        """Open chat and send outreach message with PDF attachment."""
        try:
            # Find and click Message button
            msg_btn = await page.query_selector("button:has-text('Message')")
            if not msg_btn:
                self.log(f"  Message button not found for {name}")
                return False
            
            await human_like_click(page, msg_btn)
            await asyncio.sleep(2)
            
            # Verify chat identity
            if not await self._verify_chat_identity(page, name):
                self.log(f"  Chat identity verification failed for {name}")
                self.run_metrics["identity_verification_failed"] = True
                return False
            
            # Find message input
            input_selectors = [
                "div.msg-form__contenteditable",
                "div[contenteditable='true'][role='textbox']",
                "div.msg-form__message-texteditor div[contenteditable='true']"
            ]
            
            msg_input = None
            for sel in input_selectors:
                msg_input = await page.query_selector(sel)
                if msg_input and await msg_input.is_visible():
                    break
            
            if not msg_input:
                self.log(f"  Message input not found for {name}")
                return False
            
            # Type message
            message = self._get_outreach_message(name, role)
            await msg_input.click()
            await asyncio.sleep(0.5)
            await human_like_type(page, msg_input, message)
            await asyncio.sleep(1)
            
            # Attach PDF
            file_input = await page.query_selector("input[type='file']")
            if file_input and pdf_path and os.path.exists(pdf_path):
                await file_input.set_input_files(os.path.abspath(pdf_path))
                await asyncio.sleep(2)
            
            # Click send
            send_btn = await page.query_selector("button.msg-form__send-button")
            if send_btn and await send_btn.is_enabled():
                await human_like_click(page, send_btn)
                await asyncio.sleep(2)
                self.log(f"  ✓ Message sent to {name}")
                return True
            else:
                self.log(f"  Send button not enabled for {name}")
                return False
                
        except Exception as e:
            self.log(f"  Error sending message: {e}")
            return False
    
    async def _verify_chat_identity(self, page, expected_name: str) -> bool:
        """Verify the chat is open for the correct person."""
        try:
            selectors = [
                ".msg-overlay-bubble-header__title a",
                ".msg-overlay-bubble-header__title span",
                "h2.msg-entity-lockup__entity-title"
            ]
            
            for _ in range(10):
                for sel in selectors:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        chat_name = await el.inner_text()
                        chat_name = chat_name.strip().split('\n')[0]
                        
                        # Fuzzy match
                        ratio = difflib.SequenceMatcher(
                            None, expected_name.lower(), chat_name.lower()
                        ).ratio()
                        
                        if ratio >= 0.70:
                            return True
                        
                        # First name match
                        expected_first = expected_name.split()[0].lower()
                        found_first = chat_name.split()[0].lower()
                        if expected_first == found_first:
                            return True
                
                await asyncio.sleep(0.3)
            
            return False
            
        except:
            return False
    
    def _get_outreach_message(self, name: str, role: str) -> str:
        """Get personalized outreach message based on role."""
        first_name = name.split()[0] if name else "there"
        
        if role == "PRACTICING":
            return f"""Hi {first_name},

Thank you for connecting! I noticed your legal background and thought you might find this helpful.

I've attached a brief analysis of your practice - I hope it provides some useful insights.

Looking forward to staying in touch!

Best regards"""
        else:
            return f"""Hi {first_name},

Thank you for connecting! I noticed your legal background and wanted to reach out.

I've attached some information I thought might be relevant to your work.

Best regards"""
    
    def _strip_emojis(self, text: str) -> str:
        """Remove emojis from text."""
        if not text:
            return ""
        
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F900-\U0001F9FF"
            "\U00002702-\U000027B0"
            "\U0001F1E0-\U0001F1FF"
            "]+", 
            flags=re.UNICODE
        )
        return emoji_pattern.sub('', text).strip()
    
    def _sanitize_for_pdf(self, text: str) -> str:
        """Convert text to Latin-1 compatible for FPDF."""
        if not text:
            return ""
        
        replacements = {
            '\u2013': '-', '\u2014': '--', '\u2018': "'", '\u2019': "'",
            '\u201c': '"', '\u201d': '"', '\u2026': '...', '\u2022': '*',
            '\u00a0': ' ', '\u2010': '-', '\u2011': '-', '\u2012': '-'
        }
        
        for char, repl in replacements.items():
            text = text.replace(char, repl)
        
        return text.encode('latin-1', errors='replace').decode('latin-1')
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize string for use as filename."""
        if not name:
            return "Unknown"
        
        # Remove Windows-illegal characters
        for char in r'\/:*?"<>|':
            name = name.replace(char, '')
        
        name = re.sub(r'[\s_]+', '_', name).strip('_.')
        return name if name else "Unknown"
    
    async def _cleanup(self):
        """Clean up resources."""
        self.log("Cleaning up...")
        
        # Close agent pages
        for page in self.agent_pages:
            try:
                if not page.is_closed():
                    await page.close()
            except:
                pass
        
        # Delete created PDFs
        for pdf in self.created_pdfs:
            try:
                if os.path.exists(pdf):
                    os.remove(pdf)
            except:
                pass
        
        self.log("Cleanup complete.")
    
    def _print_summary(self):
        """Print run summary."""
        self.log("\n" + "=" * 60)
        self.log("RUN SUMMARY")
        self.log("=" * 60)
        self.log(f"  Candidates found: {self.run_metrics['candidates_found']}")
        self.log(f"  Messages sent: {self.run_metrics['messages_sent']}")
        self.log(f"  Errors: {self.errors_encountered}")
        self.log("=" * 60)


# Lock file management
def acquire_lock():
    """Acquire lock to prevent multiple instances."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                old_pid = int(f.read().strip())
            
            # Check if process is still running
            import psutil
            if psutil.pid_exists(old_pid):
                print(f"Another instance is running (PID: {old_pid})")
                return False
        except:
            pass
    
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True


def release_lock():
    """Release lock file."""
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
        except:
            pass


# Entry point
async def main():
    agent = OutreachAgent()
    await agent.execute()


if __name__ == "__main__":
    if not acquire_lock():
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        release_lock()
