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

Refactored: 2026-01-11 - Now uses BaseAgent for shared functionality

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
from http.server import HTTPServer, BaseHTTPRequestHandler
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
FEED_URL = "https://www.linkedin.com/feed/"
REVIEW_HTML_FILE = "comment_review.html"
PENDING_COMMENTS_FILE = "pending_comments.json"
COMMENT_HISTORY_FILE = "comment_history.json"
SHUTDOWN_EVENT = threading.Event()
APPROVED_COMMENTS = []
POSTING_RESULTS = {}
POSTING_COMPLETE = False
AGENT_INSTANCE = None

# Legal profession indicators
LEGAL_KEYWORDS = [
    "attorney", "lawyer", "partner", "counsel", "esq", "jd", 
    "law firm", "legal", "litigator", "associate", "paralegal",
    "barrister", "solicitor", "advocate", "juris doctor",
    "of counsel", "managing partner", "founding partner"
]


def parse_relative_date(relative_time):
    """Convert LinkedIn relative time to actual date string."""
    now = datetime.now()
    relative_time = relative_time.lower().strip()
    
    try:
        if 'just now' in relative_time or 'now' in relative_time:
            result_date = now
        elif 'minute' in relative_time or 'm ago' in relative_time:
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
        elif 'month' in relative_time or 'mo' in relative_time:
            num = int(re.search(r'(\d+)', relative_time).group(1)) if re.search(r'(\d+)', relative_time) else 1
            result_date = now - timedelta(days=num*30)
        elif 'year' in relative_time or 'yr' in relative_time:
            num = int(re.search(r'(\d+)', relative_time).group(1)) if re.search(r'(\d+)', relative_time) else 1
            result_date = now - timedelta(days=num*365)
        else:
            return f"{relative_time} (today is {now.strftime('%B %d, %Y')})"
        
        return result_date.strftime('%B %d, %Y')
    except:
        return f"{relative_time} (today is {now.strftime('%B %d, %Y')})"


class ReviewHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for the review server."""
    
    def log_message(self, format, *args):
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
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            success_count = sum(1 for r in POSTING_RESULTS.values() if r.get("status") == "success")
            failed_count = sum(1 for r in POSTING_RESULTS.values() if r.get("status") == "failed")
            
            results_data = {
                "complete": POSTING_COMPLETE,
                "results": POSTING_RESULTS,
                "summary": {"success": success_count, "failed": failed_count, "total": len(POSTING_RESULTS)}
            }
            self.wfile.write(json.dumps(results_data).encode())
        elif self.path == "/results_page":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            results_file = "posting_results.html"
            if os.path.exists(results_file):
                with open(results_file, "r", encoding="utf-8") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            else:
                self.wfile.write(b"<h1>Results page not ready yet.</h1>")
        else:
            self.send_error(404)

    def do_POST(self):
        global APPROVED_COMMENTS, AGENT_INSTANCE
        
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length else ""
        
        if self.path == "/shutdown":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Shutting down...")
            SHUTDOWN_EVENT.set()
            
        elif self.path == "/submit":
            try:
                data = json.loads(body)
                APPROVED_COMMENTS = data.get("approved", [])
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "received", "count": len(APPROVED_COMMENTS)}).encode())
                
                SHUTDOWN_EVENT.set()
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                
        elif self.path == "/regenerate":
            try:
                data = json.loads(body)
                headline = data.get("headline", "")
                post_content = data.get("post_content", "")
                
                if AGENT_INSTANCE:
                    new_comment = AGENT_INSTANCE.generate_comment_sync(headline, post_content)
                else:
                    new_comment = "Error: Agent not available"
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"comment": new_comment}).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
        else:
            self.send_error(404)


class CommentAgent(BaseAgent):
    """
    Comment agent that scans LinkedIn feed for legal professional posts
    and generates AI-powered comments for review and posting.
    
    Inherits from BaseAgent for:
    - Browser management
    - Logging
    - Configuration
    - History management
    """
    
    def get_agent_name(self) -> str:
        return "CommentAgent"
    
    def __init__(self, config_path: str = "config.json"):
        super().__init__(config_path)
        
        global AGENT_INSTANCE
        AGENT_INSTANCE = self
        
        self.posts_to_comment = []
        self.user_name = None
        
        # Session metrics
        self.metrics = {
            "posts_scanned": 0,
            "legal_posts_found": 0,
            "comments_approved": 0,
            "comments_posted": 0,
            "errors": 0
        }
    
    async def run(self):
        """Main comment agent logic."""
        global SHUTDOWN_EVENT, APPROVED_COMMENTS, POSTING_COMPLETE, POSTING_RESULTS
        
        # Reset state
        POSTING_COMPLETE = False
        POSTING_RESULTS = {}
        SHUTDOWN_EVENT.clear()
        APPROVED_COMMENTS = []
        
        try:
            # Phase 1: Navigate to feed
            await self.navigate(FEED_URL)
            await asyncio.sleep(5)
            
            # Get user name for self-exclusion
            await self._identify_user_name()
            
            # Phase 2: Scan feed for legal posts
            await self._scan_feed_for_legal_posts()
            
            if not self.posts_to_comment:
                self.log("No posts from legal professionals found.")
                return
            
            # Phase 3: Generate review UI
            self._generate_review_html()
            
            # Phase 4: Start review server
            await self._start_review_server()
            
            # Phase 5: Post approved comments
            if APPROVED_COMMENTS:
                self.metrics["comments_approved"] = len(APPROVED_COMMENTS)
                await self._post_approved_comments()
                POSTING_COMPLETE = True
                
                # Wait for user to click Done
                SHUTDOWN_EVENT.clear()
                self.log("Waiting for user to click 'Done & Cleanup'...")
                
                while not SHUTDOWN_EVENT.is_set():
                    await asyncio.sleep(1)
        
        except Exception as e:
            self.log(f"CRITICAL ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup files
            for f in [REVIEW_HTML_FILE, PENDING_COMMENTS_FILE, "posting_results.html"]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except:
                        pass
    
    async def _identify_user_name(self):
        """Get current user's name for self-exclusion."""
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
    
    async def _scan_feed_for_legal_posts(self):
        """Scroll feed and collect posts from legal professionals."""
        self.log("Scanning feed for posts by legal professionals...")
        
        target_post_count = 10
        scroll_attempts = 0
        max_scroll_attempts = 20
        seen_posts = set()
        
        # Load comment history
        comment_history = self.load_history(COMMENT_HISTORY_FILE)
        if not comment_history:
            comment_history = {"posted_urls": [], "posts": []}
        
        while len(self.posts_to_comment) < target_post_count and scroll_attempts < max_scroll_attempts:
            # Get posts in view
            posts = await self.page.query_selector_all(
                "div.feed-shared-update-v2, div[data-urn^='urn:li:activity'], "
                "div[data-urn^='urn:li:share'], div[data-view-name='feed-full-update']"
            )
            self.log(f"Found {len(posts)} posts (Scroll {scroll_attempts})")
            
            for post in posts:
                try:
                    # Get post URN for dedup
                    post_urn = await post.get_attribute("data-urn")
                    
                    if not post_urn:
                        # Try extracting from innerHTML
                        try:
                            html_content = await post.inner_html()
                            urn_match = re.search(r'urn:li:(activity|share|ugcPost):\d+', html_content)
                            if urn_match:
                                post_urn = urn_match.group(0)
                        except:
                            pass
                    
                    if post_urn and post_urn in seen_posts:
                        continue
                    if post_urn:
                        seen_posts.add(post_urn)
                    
                    self.metrics["posts_scanned"] += 1
                    
                    # Extract post data
                    post_data = await self._extract_post_data(post)
                    if not post_data:
                        continue
                    
                    # Skip if already posted
                    if post_data["post_url"] in comment_history.get("posted_urls", []):
                        continue
                    
                    # Check if legal professional
                    if not self._is_legal_professional(post_data["headline"]):
                        continue
                    
                    self.metrics["legal_posts_found"] += 1
                    
                    # Generate comment
                    self.log(f"Generating comment for {post_data['author_name']}...")
                    comment = self.generate_comment_sync(
                        post_data["headline"], 
                        post_data["post_content"], 
                        post_data.get("post_date", "")
                    )
                    
                    self.posts_to_comment.append({
                        "id": post_urn or str(len(self.posts_to_comment)),
                        "author_name": post_data["author_name"],
                        "headline": post_data["headline"],
                        "post_content": post_data["post_content"],
                        "post_url": post_data["post_url"],
                        "profile_url": post_data.get("profile_url", ""),
                        "post_date": post_data.get("post_date", ""),
                        "generated_comment": comment,
                        "post_urn": post_urn
                    })
                    
                    if len(self.posts_to_comment) >= target_post_count:
                        break
                        
                except Exception as e:
                    self.log(f"Error processing post: {e}")
                    continue
            
            if len(self.posts_to_comment) < target_post_count:
                # Scroll to load more
                await human_scroll(self.page, random.randint(600, 1200))
                await human_delay(2.0, 4.0)
                scroll_attempts += 1
        
        self.log(f"Collected {len(self.posts_to_comment)} posts from legal professionals")
    
    async def _extract_post_data(self, post):
        """Extract author, headline, content from a post element."""
        try:
            author_name = "Unknown"
            headline = ""
            post_content = ""
            profile_url = ""
            post_url = ""
            post_date = ""
            
            # Try new structure first
            data_view_name = await post.get_attribute("data-view-name")
            is_new_structure = data_view_name == "feed-full-update"
            
            if is_new_structure:
                # Profile URL from actor image
                actor_img_link = await post.query_selector("a[data-view-name='feed-actor-image']")
                if actor_img_link:
                    profile_url = await actor_img_link.get_attribute("href")
                    if profile_url and profile_url.startswith("/"):
                        profile_url = "https://www.linkedin.com" + profile_url
                
                # Author name and headline from text link
                if profile_url:
                    clean_url = profile_url.split('?')[0]
                    all_links = await post.query_selector_all("a")
                    for link in all_links:
                        href = await link.get_attribute("href")
                        if href and clean_url in href:
                            view_name = await link.get_attribute("data-view-name")
                            if view_name != "feed-actor-image":
                                full_text = await link.inner_text()
                                parts = [p.strip() for p in full_text.split('\n') if p.strip()]
                                if parts:
                                    author_name = parts[0].split(" •")[0]
                                if len(parts) > 1:
                                    for p in parts[1:]:
                                        if not any(x in p for x in ["•", "1st", "2nd", "3rd", "Following"]):
                                            headline = p
                                            break
                                break
                
                # Content
                content_div = await post.query_selector("[data-view-name='feed-commentary']")
                if content_div:
                    post_content = await content_div.inner_text()
            else:
                # Legacy structure
                author_link = await post.query_selector("a.update-components-actor__container-link")
                if author_link:
                    profile_url = await author_link.get_attribute("href")
                
                name_el = await post.query_selector(".update-components-actor__name span[aria-hidden='true']")
                if name_el:
                    author_name = await name_el.inner_text()
                
                headline_el = await post.query_selector(".update-components-actor__description")
                if headline_el:
                    headline = await headline_el.inner_text()
                
                content_el = await post.query_selector(".feed-shared-update-v2__description, .update-components-text")
                if content_el:
                    post_content = await content_el.inner_text()
            
            # Get post URL
            time_link = await post.query_selector("a.app-aware-link[href*='/feed/update/']")
            if time_link:
                post_url = await time_link.get_attribute("href")
                if post_url and post_url.startswith("/"):
                    post_url = "https://www.linkedin.com" + post_url
            
            # Get post date
            time_el = await post.query_selector("time, span.update-components-actor__sub-description")
            if time_el:
                time_text = await time_el.inner_text()
                post_date = parse_relative_date(time_text)
            
            if not post_content or len(post_content) < 20:
                return None
            
            return {
                "author_name": author_name,
                "headline": headline,
                "post_content": post_content,
                "profile_url": profile_url,
                "post_url": post_url,
                "post_date": post_date
            }
            
        except Exception as e:
            self.log(f"Error extracting post data: {e}")
            return None
    
    def _is_legal_professional(self, headline: str) -> bool:
        """Use Gemini AI to check if headline indicates legal professional."""
        if not headline:
            return False
        
        try:
            prompt = f"""Analyze this LinkedIn headline and determine if this person has a legal background.
            
Headline: {headline}

Legal background includes: lawyers, attorneys, advocates, barristers, solicitors, legal counsel, 
partners at law firms, paralegals, legal associates, judges, in-house counsel, etc.

Respond with ONLY "YES" or "NO"."""

            response = self.gemini.generate(prompt)
            result = response.strip().upper()
            is_legal = result == "YES"
            
            if is_legal:
                self.log(f"  [YES] Legal professional: {headline[:60]}")
            
            return is_legal
        except Exception as e:
            self.log(f"Error checking legal background: {e}")
            return False
    
    def generate_comment_sync(self, headline: str, post_content: str, post_date: str = "") -> str:
        """Generate a professional comment using Gemini."""
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
- Keep it concise: 2-4 sentences max
- Sound natural and human, not generic
- NEVER use phrases like "Great post!", "Love this!", "So true!"
- Don't be overly effusive or sycophantic
- Match their professional tone
- Output plain text only, no HTML tags

Generate ONLY the comment text, nothing else."""

            response = self.gemini.generate(prompt)
            comment = response.strip()
            comment = re.sub(r'<[^>]+>', '', comment)
            
            return comment
        except Exception as e:
            self.log(f"Error generating comment: {e}")
            return "Thank you for sharing this insightful perspective."
    
    def _generate_review_html(self):
        """Generate LinkedIn-style accessible review HTML."""
        cards_html = ""
        
        for i, post in enumerate(self.posts_to_comment):
            author_name = post['author_name'].replace('<', '&lt;').replace('>', '&gt;')
            headline = post['headline'].replace('<', '&lt;').replace('>', '&gt;')
            post_content = post['post_content'].replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')[:500]
            comment = post['generated_comment'].replace('<', '&lt;').replace('>', '&gt;')
            post_id = post['id'].replace('"', '&quot;')
            
            cards_html += f"""
            <article class="post-card" data-post-id="{post_id}">
                <header class="post-header">
                    <div class="author-avatar"><span>{author_name[0].upper()}</span></div>
                    <div class="author-info">
                        <h2 class="author-name">{author_name}</h2>
                        <p class="author-headline">{headline}</p>
                    </div>
                </header>
                <div class="post-content"><p>{post_content}</p></div>
                <section class="comment-section">
                    <label for="comment-{i}">Your Comment:</label>
                    <textarea id="comment-{i}" class="comment-input" rows="4"
                        data-headline="{headline.replace('"', '&quot;')}"
                        data-post-content="{post_content[:300].replace('"', '&quot;')}"
                    >{comment}</textarea>
                </section>
                <div class="card-actions">
                    <button type="button" class="btn btn-regenerate" onclick="regenerateComment('{post_id}', {i})">
                        ↻ Regenerate
                    </button>
                    <label class="checkbox-label">
                        <input type="checkbox" class="approve-checkbox" data-index="{i}" checked>
                        <span>Approve</span>
                    </label>
                    <a href="{post['post_url']}" target="_blank" class="btn btn-view">View Post →</a>
                </div>
            </article>
            """
        
        html_content = self._get_review_html_template(cards_html)
        
        with open(REVIEW_HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html_content)
        self.log(f"Review HTML generated: {REVIEW_HTML_FILE}")
    
    def _get_review_html_template(self, cards_html: str) -> str:
        """Get the full HTML template for review page."""
        posts_json = json.dumps(self.posts_to_comment).replace("'", "\\'")
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Comment Review</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
               background: #f3f2ef; padding: 20px; max-width: 800px; margin: 0 auto; }}
        h1 {{ color: #0a66c2; margin-bottom: 20px; }}
        .post-card {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 16px; 
                     box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .post-header {{ display: flex; gap: 12px; margin-bottom: 16px; }}
        .author-avatar {{ width: 48px; height: 48px; border-radius: 50%; background: #0a66c2; 
                         display: flex; align-items: center; justify-content: center; 
                         color: white; font-weight: bold; font-size: 18px; }}
        .author-name {{ font-weight: 600; color: #000; }}
        .author-headline {{ color: #666; font-size: 14px; }}
        .post-content {{ background: #f9f9f9; padding: 12px; border-radius: 4px; margin-bottom: 16px; 
                        max-height: 150px; overflow: hidden; font-size: 14px; color: #333; }}
        .comment-section {{ margin-bottom: 16px; }}
        .comment-section label {{ font-weight: 600; display: block; margin-bottom: 8px; }}
        .comment-input {{ width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; 
                         font-family: inherit; resize: vertical; }}
        .card-actions {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
        .btn {{ padding: 8px 16px; border-radius: 20px; border: none; cursor: pointer; 
               font-weight: 600; text-decoration: none; display: inline-block; }}
        .btn-regenerate {{ background: #e0e0e0; color: #333; }}
        .btn-regenerate:hover {{ background: #d0d0d0; }}
        .btn-view {{ background: #0a66c2; color: white; }}
        .btn-view:hover {{ background: #004182; }}
        .checkbox-label {{ display: flex; align-items: center; gap: 6px; cursor: pointer; }}
        .approve-checkbox {{ width: 18px; height: 18px; }}
        .action-bar {{ position: fixed; bottom: 0; left: 0; right: 0; background: white; 
                      padding: 16px; box-shadow: 0 -2px 10px rgba(0,0,0,0.1); 
                      display: flex; justify-content: center; gap: 16px; }}
        .btn-submit {{ background: #057642; color: white; padding: 12px 32px; font-size: 16px; }}
        .btn-cancel {{ background: #cc1016; color: white; padding: 12px 32px; font-size: 16px; }}
        .content-wrapper {{ padding-bottom: 80px; }}
        .status-msg {{ text-align: center; padding: 20px; font-size: 18px; }}
    </style>
</head>
<body>
    <div class="content-wrapper">
        <h1>Comment Review</h1>
        <p>Review and edit the generated comments. Uncheck "Approve" to skip a post.</p>
        {cards_html}
    </div>
    
    <div class="action-bar">
        <button class="btn btn-cancel" onclick="cancelAll()">Cancel</button>
        <button class="btn btn-submit" onclick="submitApproved()">Post Approved ({len(self.posts_to_comment)})</button>
    </div>
    
    <script>
        const posts = {posts_json};
        
        async function regenerateComment(postId, index) {{
            const textarea = document.getElementById('comment-' + index);
            const card = document.querySelector('[data-post-id="' + postId + '"]');
            const btn = card.querySelector('.btn-regenerate');
            
            btn.disabled = true;
            btn.textContent = 'Generating...';
            
            try {{
                const resp = await fetch('/regenerate', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        post_id: postId,
                        headline: textarea.dataset.headline,
                        post_content: textarea.dataset.postContent
                    }})
                }});
                const data = await resp.json();
                textarea.value = data.comment;
            }} catch (e) {{
                console.error(e);
            }}
            
            btn.disabled = false;
            btn.textContent = '↻ Regenerate';
        }}
        
        async function submitApproved() {{
            const checkboxes = document.querySelectorAll('.approve-checkbox');
            const approved = [];
            
            checkboxes.forEach((cb, i) => {{
                if (cb.checked) {{
                    const textarea = document.getElementById('comment-' + i);
                    approved.push({{
                        index: i,
                        post_url: posts[i].post_url,
                        author_name: posts[i].author_name,
                        comment: textarea.value
                    }});
                }}
            }});
            
            document.querySelector('.action-bar').innerHTML = '<p class="status-msg">Posting ' + approved.length + ' comments...</p>';
            
            await fetch('/submit', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{ approved: approved }})
            }});
            
            // Poll for results
            pollResults();
        }}
        
        async function pollResults() {{
            try {{
                const resp = await fetch('/results');
                const data = await resp.json();
                
                if (data.complete) {{
                    document.querySelector('.action-bar').innerHTML = 
                        '<p class="status-msg">Done! ' + data.summary.success + ' posted, ' + 
                        data.summary.failed + ' failed</p>' +
                        '<button class="btn btn-cancel" onclick="shutdown()">Done & Cleanup</button>';
                }} else {{
                    setTimeout(pollResults, 1000);
                }}
            }} catch (e) {{
                setTimeout(pollResults, 1000);
            }}
        }}
        
        async function cancelAll() {{
            if (confirm('Cancel without posting any comments?')) {{
                await fetch('/shutdown', {{ method: 'POST' }});
                document.body.innerHTML = '<h1 style="text-align:center;margin-top:50px;">Cancelled. You can close this tab.</h1>';
            }}
        }}
        
        async function shutdown() {{
            await fetch('/shutdown', {{ method: 'POST' }});
            document.body.innerHTML = '<h1 style="text-align:center;margin-top:50px;">Done! You can close this tab.</h1>';
        }}
    </script>
</body>
</html>"""
    
    async def _start_review_server(self):
        """Start the review server and wait for user action."""
        port = 8080
        try:
            server = HTTPServer(('127.0.0.1', port), ReviewHandler)
        except OSError:
            port += 1
            server = HTTPServer(('127.0.0.1', port), ReviewHandler)
        
        url = f"http://127.0.0.1:{port}"
        self.log(f"Review server started at {url}")
        
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        # Open review page
        try:
            review_page = await self.context.new_page()
            await review_page.goto(url)
        except Exception as e:
            self.log(f"Warning: Could not open review page: {e}")
        
        # Play ready sound
        self.play_ready_sound()
        self.log("🔔 Ready for review")
        
        # Wait for user action
        while not SHUTDOWN_EVENT.is_set():
            await asyncio.sleep(1)
    
    async def _post_approved_comments(self):
        """Post all approved comments to LinkedIn."""
        global POSTING_RESULTS
        
        comment_history = self.load_history(COMMENT_HISTORY_FILE)
        if not comment_history:
            comment_history = {"posted_urls": [], "posts": []}
        
        for approved in APPROVED_COMMENTS:
            post_url = approved.get("post_url")
            author_name = approved.get("author_name")
            comment_text = approved.get("comment")
            
            try:
                self.log(f"Posting comment for {author_name}...")
                
                # Navigate to post
                await human_like_navigate(self.page, post_url)
                await asyncio.sleep(3)
                
                # Find comment input
                comment_input = await self._find_comment_input()
                if not comment_input:
                    POSTING_RESULTS[post_url] = {"status": "failed", "message": "Comment input not found"}
                    continue
                
                # Type comment
                await comment_input.click()
                await asyncio.sleep(0.5)
                await human_like_type(self.page, comment_input, comment_text)
                await asyncio.sleep(1)
                
                # Click submit
                submit_btn = await self.page.query_selector("button.comments-comment-box__submit-button")
                if submit_btn:
                    await human_like_click(self.page, submit_btn)
                    await asyncio.sleep(3)
                    
                    # Verify
                    success = await self._verify_comment_posted(comment_text)
                    
                    if success:
                        self.metrics["comments_posted"] += 1
                        POSTING_RESULTS[post_url] = {"status": "success", "message": "Posted successfully"}
                        
                        # Update history
                        if post_url not in comment_history.get("posted_urls", []):
                            comment_history.setdefault("posted_urls", []).append(post_url)
                        comment_history.setdefault("posts", []).append({
                            "url": post_url,
                            "author": author_name,
                            "comment": comment_text,
                            "success": True,
                            "timestamp": datetime.now().isoformat()
                        })
                        self.save_history(COMMENT_HISTORY_FILE, comment_history)
                    else:
                        POSTING_RESULTS[post_url] = {"status": "failed", "message": "Verification failed"}
                else:
                    POSTING_RESULTS[post_url] = {"status": "failed", "message": "Submit button not found"}
                    
            except Exception as e:
                self.log(f"Error posting comment: {e}")
                self.metrics["errors"] += 1
                POSTING_RESULTS[post_url] = {"status": "failed", "message": str(e)}
        
        # Play completion sound
        self.play_complete_sound()
    
    async def _find_comment_input(self):
        """Find the comment input field on the page."""
        selectors = [
            "div.comments-comment-box__form-container div.ql-editor",
            "div.comments-comment-texteditor div[contenteditable='true']",
            "div[data-placeholder='Add a comment…']",
            "div.ql-editor[data-placeholder]"
        ]
        
        for selector in selectors:
            try:
                el = await self.page.query_selector(selector)
                if el and await el.is_visible():
                    return el
            except:
                continue
        
        return None
    
    async def _verify_comment_posted(self, expected_comment: str) -> bool:
        """Verify the comment was posted using Gemini."""
        try:
            await asyncio.sleep(2)
            
            # Get recent comments
            comments = await self.page.query_selector_all(".comments-comment-item")
            
            for comment in comments[-5:]:  # Check last 5
                try:
                    text = await comment.inner_text()
                    if expected_comment[:50] in text:
                        return True
                except:
                    continue
            
            # Fallback: use Gemini
            page_text = await self.page.evaluate("document.body.innerText")
            
            prompt = f"""Check if this comment was successfully posted to LinkedIn.

EXPECTED COMMENT (first 100 chars):
{expected_comment[:100]}

PAGE CONTENT (last 5000 chars):
{page_text[-5000:]}

Respond with ONLY "YES" if the comment appears on the page, or "NO" if not."""

            response = self.gemini.generate(prompt)
            return "YES" in response.strip().upper()
            
        except Exception as e:
            self.log(f"Verification error: {e}")
            return False


# Entry point
async def main():
    agent = CommentAgent()
    await agent.execute()


if __name__ == "__main__":
    print("Starting LinkedIn Comment Agent...", flush=True)
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
