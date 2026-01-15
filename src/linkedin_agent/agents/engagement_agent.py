"""
LinkedIn Engagement Agent (Mentions & Replies)
==============================================
Monitors notifications specifically for mentions and replies.
Likes the content and generates an accessible review report.

Features:
- Filters for "mentioned you" or "replied to your comment"
- Likes the post/comment
- Generates accessible HTML report
- Launches local server for review
- One-click cleanup via UI

Refactored: 2026-01-11 - Now uses BaseAgent for shared functionality
"""

import asyncio
import os
import time
import json
import threading
import webbrowser
import signal
import subprocess
import socket
import re
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

from dotenv import load_dotenv

from ..agents.base_agent import BaseAgent
from ..utils.anti_detection import (
    human_delay, human_scroll, human_mouse_move, 
    human_like_navigate, human_like_click
)

# Load environment variables
load_dotenv()

# Configuration
NOTIFICATIONS_URL = "https://www.linkedin.com/notifications/"
REVIEW_HTML_FILE = "engagement_review.html"
SHUTDOWN_EVENT = threading.Event()

# Global reference for ReviewHandler
_current_agent = None


class ReviewHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for the review server."""
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            if os.path.exists(REVIEW_HTML_FILE):
                with open(REVIEW_HTML_FILE, "r", encoding="utf-8") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            else:
                self.wfile.write(b"<h1>Error: Report file not found.</h1>")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/shutdown":
            self.send_response(200)
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
            
            # Signal main loop to exit
            SHUTDOWN_EVENT.set()


class EngagementAgent(BaseAgent):
    """
    Engagement agent that monitors LinkedIn notifications for mentions and replies,
    likes the content, and generates a review report.
    
    Inherits from BaseAgent for:
    - Browser management
    - Logging
    - Configuration
    - History management  
    - Debug capture
    """
    
    def get_agent_name(self) -> str:
        return "EngagementAgent"
    
    def __init__(self, config_path: str = "config.json"):
        super().__init__(config_path)
        
        global _current_agent
        _current_agent = self
        
        self.processed_links = []
        self.user_name = None
        
        # Metrics
        self.run_metrics = {
            "mentions_found": 0,
            "replies_found": 0,
            "third_party_mentions_found": 0,
            "comments_on_post_found": 0,
            "actions_taken": 0,
            "errors": 0,
            "agent_type": "engagement_agent"
        }
        
        # History for notification tracking
        self.notification_history = self.load_history("processed_notifications.json")
        if not isinstance(self.notification_history, dict):
            self.notification_history = {"processed_ids": []}
        
        self.last_processed_id = self._load_last_state()
    
    def _load_last_state(self):
        """Load the ID of the last processed notification."""
        state = self.load_history("notification_state.json")
        return state.get("last_processed_id") if state else None

    def _save_last_state(self, notification_id):
        """Save the ID of the newest processed notification."""
        self.save_history("notification_state.json", {
            "last_processed_id": notification_id, 
            "timestamp": str(datetime.now())
        })

    async def run(self):
        """Main engagement agent logic."""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                self.log(f"Starting engagement run (Attempt {attempt+1}/{max_retries})...")
                
                # Navigate to feed first to get user name
                await self.navigate("https://www.linkedin.com/feed/")
                await asyncio.sleep(3)
                
                # Close any chat popups
                await self.close_chat_popups()
                
                # Get current user name for self-exclusion
                await self._identify_user_name()
                
                # Process notifications
                await self._process_notifications()
                
                # Generate report
                self._generate_report()
                
                # Start review server
                await self._start_review_server()
                
                break  # Success
                
            except Exception as e:
                is_target_closed = "Target page, context or browser has been closed" in str(e)
                if is_target_closed and attempt < max_retries - 1:
                    self.log(f"Browser closed unexpectedly (Attempt {attempt+1}). Retrying...")
                    await asyncio.sleep(5)
                else:
                    self.log(f"CRITICAL ERROR: {e}")
                    import traceback
                    traceback.print_exc()
                    break
    
    async def _identify_user_name(self):
        """Identify the current logged-in user's name."""
        try:
            # Try the nav me image (most reliable)
            me_img = await self.page.query_selector("button.global-nav__primary-link-me-menu-trigger img")
            if me_img:
                alt = await me_img.get_attribute("alt")
                if alt and "Photo of " in alt:
                    self.user_name = alt.replace("Photo of ", "").strip()
                elif alt:
                    self.user_name = alt.strip()
            
            if self.user_name:
                self.log(f"Identified current user as: '{self.user_name}'")
            else:
                self.log("WARNING: Could not identify current user name. Self-liking prevention may be limited.")
                
        except Exception as e:
            self.log(f"Error getting user name: {e}")
    
    async def _process_notifications(self):
        """Scan and process notifications."""
        self.log("Checking notifications...")
        
        # Navigate to notifications with human-like behavior
        await human_like_navigate(self.page, NOTIFICATIONS_URL)
        
        # Scroll to find notifications
        cards = []
        found_last_processed = False
        scroll_attempts = 0
        max_scroll_attempts = self.get_config("engagement_agent.max_scroll_attempts", 10)
        
        while not found_last_processed and scroll_attempts < max_scroll_attempts:
            cards = await self.page.query_selector_all("article.nt-card")
            self.log(f"Found {len(cards)} notification cards (Scroll {scroll_attempts})")
            
            # Check if last processed ID is in current view
            if self.last_processed_id:
                for card in cards:
                    link = await card.query_selector("a.nt-card__headline")
                    if link:
                        url = await link.get_attribute("href")
                        if url:
                            if url.startswith("/"): 
                                url = "https://www.linkedin.com" + url
                            
                            notif_id = self._extract_notification_id(url)
                            if notif_id == self.last_processed_id:
                                self.log(f"Found last processed notification. Stopping scroll.")
                                found_last_processed = True
                                break
            
            if not found_last_processed:
                await human_scroll(self.page, random.randint(600, 900))
                await human_delay(2.0, 4.0)
                scroll_attempts += 1
        
        # Process notifications
        max_processing = self.get_config("engagement_agent.max_notifications_per_run", 50)
        newest_notification_id = None
        
        for i, card in enumerate(cards[:max_processing]):
            await self._process_notification_card(card, i)
            
            # Capture newest ID
            link = await card.query_selector("a.nt-card__headline")
            if link and newest_notification_id is None:
                url = await link.get_attribute("href")
                if url:
                    if url.startswith("/"): 
                        url = "https://www.linkedin.com" + url
                    newest_notification_id = self._extract_notification_id(url)
        
        # Save state
        if newest_notification_id:
            self._save_last_state(newest_notification_id)
    
    def _extract_notification_id(self, url):
        """Extract unique notification ID from URL."""
        notification_id = url
        if "activity:" in url:
            match = re.search(r"activity:(\d+)", url)
            if match:
                notification_id = f"activity:{match.group(1)}"
        return notification_id
    
    async def _process_notification_card(self, card, index):
        """Process a single notification card."""
        try:
            raw_text = await card.inner_text()
            text = raw_text.lower()
            text_lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
            
            # Check notification type
            is_mention = "mentioned you" in text
            is_reply = "replied to your" in text
            is_third_party_mention = "comment that mentioned you" in text
            is_comment_on_post = "commented on your" in text
            
            if not (is_mention or is_reply or is_third_party_mention or is_comment_on_post):
                return
            
            self.log(f"Found relevant notification: {text[:50]}...")
            
            # Get link
            link = await card.query_selector("a.nt-card__headline")
            if not link:
                return
                
            url = await link.get_attribute("href")
            if url and url.startswith("/"):
                url = "https://www.linkedin.com" + url
            
            notification_id = self._extract_notification_id(url)
            
            # Skip if already processed
            if notification_id in self.notification_history.get("processed_ids", []):
                self.log(f"Skipping already processed: {notification_id}")
                return
            
            # Classify notification type
            notification_type, author = self._classify_notification(text)
            
            # Store for report
            notification_entry = {
                "type": notification_type,
                "text": text,
                "text_lines": text_lines,
                "url": url,
                "time": datetime.now().strftime("%H:%M"),
                "author": author,
                "like_status": "pending"
            }
            self.processed_links.append(notification_entry)
            entry_index = len(self.processed_links) - 1
            
            # Mark as processed
            if "processed_ids" not in self.notification_history:
                self.notification_history["processed_ids"] = []
            self.notification_history["processed_ids"].append(notification_id)
            self.save_history("processed_notifications.json", self.notification_history)
            
            # Perform the like action
            await self._perform_like_action(url, author, notification_type, entry_index)
            
            # Update metrics
            if is_third_party_mention: 
                self.run_metrics["third_party_mentions_found"] += 1
            if is_comment_on_post: 
                self.run_metrics["comments_on_post_found"] += 1
            if is_mention: 
                self.run_metrics["mentions_found"] += 1
            if is_reply: 
                self.run_metrics["replies_found"] += 1
                
        except Exception as e:
            self.log(f"Error processing notification card {index}: {e}")
            self.run_metrics["errors"] += 1
    
    def _classify_notification(self, text):
        """Classify notification type and extract author."""
        notification_type = "Notification"
        author = "Unknown"
        
        if "comment that mentioned you" in text:
            notification_type = "Reaction to Third-Party Mention"
            reaction_match = re.search(r'^(.*?)\s+(reacted|liked|loved|celebrated|found)', text)
            if reaction_match:
                author = reaction_match.group(1).strip()
            else:
                author = text.split("reacted")[0].strip() if "reacted" in text else "Unknown"
        elif "mentioned you" in text:
            notification_type = "Mention in Comment" if "comment" in text else "Mention in Post"
            author = text.split("mentioned you")[0].strip()
        elif "replied to your" in text:
            notification_type = "Reply to Comment"
            author = text.split("replied to your")[0].strip()
        elif "commented on your" in text:
            notification_type = "Comment on Post"
            author = text.split("commented on your")[0].strip()
        elif "reacted to your" in text:
            notification_type = "Reaction to Comment" if "comment" in text else "Reaction to Post"
            author = text.split("reacted to your")[0].strip()
        
        return notification_type, author
    
    async def _perform_like_action(self, url, author, notification_type, entry_index):
        """Navigate to the content and perform like action."""
        action_page = await self.context.new_page()
        
        try:
            await action_page.goto(url)
            await action_page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            
            # Find and click like button
            target_container = action_page
            
            # Try to find specific comment container if URL has comment ID
            if "commentUrn" in url or "replyUrn" in url:
                target_container = await self._find_comment_container(action_page, url) or action_page
            
            # Wait for like buttons
            try:
                await action_page.wait_for_selector(
                    "button[aria-label*='Like'], button[aria-label*='React']",
                    state="attached",
                    timeout=10000
                )
            except:
                self.log("Warning: Like buttons not found after 10s wait")
            
            # Find like buttons
            like_btns = await target_container.query_selector_all(
                "button[aria-label*='Like'], button[aria-label*='React'], button[aria-label*='reaction']"
            )
            
            self.log(f"Found {len(like_btns)} potential action buttons")
            
            # Find and click appropriate button
            clicked = await self._click_like_button(like_btns, author)
            
            # Update status
            if clicked:
                self.run_metrics["actions_taken"] += 1
                # Verify with Gemini
                like_status = await self._verify_like_posted(action_page, author, notification_type)
                self.processed_links[entry_index]["like_status"] = like_status
            else:
                self.processed_links[entry_index]["like_status"] = "failed"
                await self.capture_debug_screenshot(f"like_failed_{entry_index}")
                
        except Exception as e:
            self.log(f"Error performing like action: {e}")
            self.run_metrics["errors"] += 1
            self.processed_links[entry_index]["like_status"] = "error"
        finally:
            await action_page.close()
    
    async def _find_comment_container(self, page, url):
        """Find specific comment container from URL parameters."""
        try:
            target_urn_key = "replyUrn" if "replyUrn" in url else "commentUrn"
            pattern = f"{target_urn_key}=urn%3Ali%3Acomment%3A%28.+?%2C(\\d+)%29"
            match = re.search(pattern, url)
            
            if match:
                comment_id = match.group(1)
                selectors = [
                    f"article[data-urn*='{comment_id}']",
                    f"div[data-urn*='{comment_id}']",
                    f"div[data-id*='{comment_id}']",
                    f"li[data-urn*='{comment_id}']"
                ]
                
                for sel in selectors:
                    try:
                        el = await page.wait_for_selector(sel, state="attached", timeout=2000)
                        if el:
                            await el.scroll_into_view_if_needed()
                            await asyncio.sleep(2)
                            return el
                    except:
                        continue
        except Exception as e:
            self.log(f"Error finding comment container: {e}")
        
        return None
    
    async def _click_like_button(self, like_btns, author):
        """Find and click the appropriate like button."""
        # Clean author name
        author_clean = author.lower().strip()
        for prefix in ["status is online", "status is reachable", "status is away", "status is busy"]:
            author_clean = author_clean.replace(prefix, "").strip()
        author_clean = ' '.join(author_clean.split())
        
        target_btn = None
        
        # Pass 1: Find button matching author
        for btn in like_btns:
            label = await btn.get_attribute("aria-label") or ""
            label_lower = label.lower()
            pressed = await btn.get_attribute("aria-pressed")
            
            if not ("like" in label_lower or "react" in label_lower):
                continue
            
            # Skip self-like buttons
            if "your comment" in label_lower or "your reply" in label_lower:
                continue
            if self.user_name and self.user_name.lower() in label_lower:
                continue
            
            # Check author match
            if author_clean and author_clean != "unknown" and author_clean in label_lower:
                target_btn = btn
                break
        
        # Pass 2: Use first available if no match
        if not target_btn and like_btns:
            for btn in like_btns:
                label = await btn.get_attribute("aria-label") or ""
                label_lower = label.lower()
                pressed = await btn.get_attribute("aria-pressed")
                
                if not ("like" in label_lower or "react" in label_lower):
                    continue
                if "your comment" in label_lower or "your reply" in label_lower:
                    continue
                if self.user_name and self.user_name.lower() in label_lower:
                    continue
                    
                if pressed != "true":
                    target_btn = btn
                    break
        
        # Click the button
        if target_btn:
            pressed = await target_btn.get_attribute("aria-pressed")
            label = await target_btn.get_attribute("aria-label") or ""
            
            if pressed == "true":
                self.log(f"Button already pressed: '{label}'")
                return True
            
            try:
                await target_btn.click(timeout=5000)
                self.log(f"Clicked: '{label}'")
                await asyncio.sleep(2)
                return True
            except:
                try:
                    await target_btn.click(force=True, timeout=5000)
                    self.log(f"Force-clicked: '{label}'")
                    await asyncio.sleep(2)
                    return True
                except:
                    return False
        
        return False
    
    async def _verify_like_posted(self, page, author_name, notification_type):
        """Use Gemini to verify if the like was successfully applied."""
        try:
            await asyncio.sleep(3)
            
            # First try DOM check
            like_btns = await page.query_selector_all("button[aria-label*='Like'], button[aria-label*='React']")
            for btn in like_btns:
                label = await btn.get_attribute("aria-label") or ""
                pressed = await btn.get_attribute("aria-pressed")
                
                if "your comment" in label.lower() or "your reply" in label.lower():
                    continue
                if self.user_name and self.user_name.lower() in label.lower():
                    continue
                    
                if pressed == "true" and ("like" in label.lower() or "react" in label.lower()):
                    return "success"
            
            # Fallback: Use Gemini
            all_text = await page.evaluate("document.body.innerText")
            context = all_text[-10000:]
            
            prompt = f"""Analyze this LinkedIn page content and determine if a Like action was successfully performed.

CONTEXT:
- Notification type: {notification_type}
- Target author: {author_name}

PAGE CONTENT (partial):
{context}

Look for indicators that a like was successfully applied:
1. A "Liked" or reaction indicator visible
2. "You and X others" type text near reactions
3. Any filled/solid reaction icon indication

Respond with ONLY "YES" if you see clear evidence the like was applied.
Respond with "NO" if there's no evidence or the like button appears unpressed.
Respond with "ALREADY" if the content was already liked before."""

            response = self.gemini.generate(prompt)
            result = response.strip().upper()
            
            if "YES" in result:
                return "success"
            elif "ALREADY" in result:
                return "already_liked"
            else:
                return "failed"
                
        except Exception as e:
            self.log(f"Verification error: {e}")
            return "unknown"
    
    def _generate_report(self):
        """Generate accessible HTML report."""
        rows = ""
        for item in self.processed_links:
            action_label = f"View {item['type']} by {item.get('author', 'someone')} on LinkedIn"
            
            lines = item.get('text_lines', [item['text']])
            formatted_text = ""
            
            if lines:
                formatted_text += f"<div class='notif-header'><strong>{lines[0]}</strong></div>"
                if len(lines) > 1:
                    formatted_text += f"<div class='notif-content'>&ldquo;{lines[1]}&rdquo;</div>"
                if len(lines) > 2:
                    context_text = " ".join(lines[2:])
                    formatted_text += f"<div class='notif-context'>On: {context_text}</div>"
            else:
                formatted_text = item['text']

            like_status = item.get('like_status', 'unknown')
            status_badges = {
                'success': '<span class="status-badge status-success">✓ Liked</span>',
                'already_liked': '<span class="status-badge status-already">Already Liked</span>',
                'failed': '<span class="status-badge status-failed">✗ Failed</span>',
                'error': '<span class="status-badge status-error">⚠ Error</span>',
            }
            status_badge = status_badges.get(like_status, '<span class="status-badge status-unknown">? Unknown</span>')

            rows += f"""
            <tr>
                <th scope="row">{item['type']}</th>
                <td>{formatted_text}</td>
                <td>
                    <a href="{item['url']}" target="_blank" aria-label="{action_label}">
                        View on LinkedIn
                    </a>
                </td>
                <td>{status_badge}</td>
                <td>{item['time']}</td>
            </tr>
            """
        
        html_content = self._get_report_html(rows)
        
        with open(REVIEW_HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html_content)
        self.log(f"Report generated: {REVIEW_HTML_FILE}")
    
    def _get_report_html(self, rows):
        """Get the full HTML template for the report."""
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Engagement Review</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; line-height: 1.6; color: #333; }}
                h1 {{ color: #0a66c2; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; vertical-align: top; }}
                th {{ background-color: #f4f4f4; color: #333; min-width: 120px; }}
                .notif-header {{ margin-bottom: 8px; color: #191919; }}
                .notif-content {{ background: #f9f9f9; padding: 8px; border-left: 3px solid #0a66c2; margin-bottom: 8px; font-style: italic; }}
                .notif-context {{ font-size: 0.9em; color: #666; }}
                .status-badge {{ padding: 4px 10px; border-radius: 12px; font-size: 0.85em; font-weight: 600; display: inline-block; }}
                .status-success {{ background-color: #d4edda; color: #155724; }}
                .status-already {{ background-color: #e2e3e5; color: #383d41; }}
                .status-failed {{ background-color: #f8d7da; color: #721c24; }}
                .status-error {{ background-color: #fff3cd; color: #856404; }}
                .status-unknown {{ background-color: #d6d8db; color: #1b1e21; }}
                .sr-only {{ position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }}
                .btn-container {{ margin-top: 30px; text-align: center; }}
                .close-btn {{ background-color: #d11124; color: white; border: none; padding: 15px 30px; font-size: 18px; cursor: pointer; border-radius: 5px; }}
                .close-btn:hover {{ background-color: #a00c1b; }}
            </style>
        </head>
        <body>
            <main>
                <h1>Engagement Session Review</h1>
                <p>The following interactions were processed:</p>
                
                <table aria-label="Processed Notifications">
                    <thead>
                        <tr>
                            <th>Type</th>
                            <th>Notification Text</th>
                            <th>Link</th>
                            <th>Like Status</th>
                            <th>Time Processed</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                    </tbody>
                </table>
                
                <div class="btn-container">
                    <button id="shutdownBtn" class="close-btn">Done & Cleanup</button>
                </div>
            </main>
            
            <script>
                document.getElementById('shutdownBtn').addEventListener('click', function() {{
                    if (confirm('Are you sure? This will close the agent and delete this report.')) {{
                        this.disabled = true;
                        this.innerText = 'Shutting down...';
                        fetch('/shutdown', {{ method: 'POST' }})
                        .then(() => {{
                            document.body.innerHTML = "<h1>Session Closed. Bye!</h1>";
                            setTimeout(() => window.close(), 1000);
                        }})
                        .catch(() => {{
                            document.body.innerHTML = "<h1>Session Closed. Bye!</h1>";
                            setTimeout(() => window.close(), 1000);
                        }});
                    }}
                }});
            </script>
        </body>
        </html>
        """
    
    async def _start_review_server(self):
        """Start the review server and wait for shutdown."""
        port = self.get_config("engagement_agent.review_server_port", 8000)
        
        try:
            server = HTTPServer(('127.0.0.1', port), ReviewHandler)
        except OSError:
            port += 1
            server = HTTPServer(('127.0.0.1', port), ReviewHandler)
        
        url = f"http://127.0.0.1:{port}"
        self.log(f"Review server started at {url}")
        
        # Run server in background
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        # Open report in browser
        try:
            report_page = await self.context.new_page()
            await report_page.goto(url)
        except Exception as e:
            self.log(f"Warning: Could not open report: {e}")
            webbrowser.open(url)
        
        # Play ready sound
        self.play_ready_sound()
        
        # Wait for shutdown
        while not SHUTDOWN_EVENT.is_set():
            await asyncio.sleep(1)
        
        server.shutdown()


# Entry point for direct execution
async def main():
    agent = EngagementAgent()
    await agent.execute()


if __name__ == "__main__":
    print("DEBUG: Script started", flush=True)
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"DEBUG: Critical error: {e}", flush=True)
        import traceback
        traceback.print_exc()
