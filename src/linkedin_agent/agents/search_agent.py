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

Refactored: 2026-01-11 - Now uses BaseAgent for shared functionality

Author: AI Agent
Created: 2026-01-06
"""

import asyncio
import os
import json
import threading
import csv
import random
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

from dotenv import load_dotenv

from ..agents.base_agent import BaseAgent
from ..utils.anti_detection import (
    human_delay, human_scroll, human_mouse_move, 
    human_like_navigate
)

# Load environment variables
load_dotenv()

# Configuration
REVIEW_HTML_FILE = "search_review.html"
SEARCH_HISTORY_FILE = "search_history.json"
SEARCH_RESULTS_FILE = "search_results.json"
SHUTDOWN_EVENT = threading.Event()
INTERESTED_RESULTS = []
AGENT_INSTANCE = None


class BooleanSearchGenerator:
    """Generates Boolean search combinations for legal automation freelancing."""
    
    def __init__(self):
        self.legal_focus = [
            '"legal automation"', '"legal tech"', '"legaltech"',
            '"legal AI"', '"law firm automation"', '"legal operations"',
            '"contract automation"', '"document automation"'
        ]
        
        self.work_types = ['freelance', 'contract', 'consultant', 'contractor']
        self.hiring_indicators = ['hiring', 'seeking', 'looking for', 'need', 'opportunity']
    
    def generate_job_queries(self):
        """Generate Boolean queries for Jobs search - focused on AI automation."""
        return [
            '"legal AI" AND (freelance OR contract OR consultant)',
            '"legal automation" AND AI AND (freelance OR contract)',
            '"legal tech" AND AI AND (freelance OR consultant)',
            '"contract automation" AND AI AND (developer OR specialist)',
            '"document automation" AND AI AND legal',
            '"AI automation" AND legal AND (freelance OR contract)',
            '"CLM" AND AI AND (freelance OR consultant)',
            '"generative AI" AND legal AND (freelance OR contract)',
            '"AI agent" AND legal AND (freelance OR consultant)'
        ]
    
    def generate_post_queries(self):
        """Generate Boolean queries for Posts search with hiring indicators."""
        return [
            '"legal AI" AND (hiring OR "looking for" OR seeking)',
            '"AI automation" AND legal AND (freelance OR contract OR project)',
            '"legal automation" AND AI AND (hiring OR seeking OR help)',
            '"legal tech" AND AI AND (freelance OR consultant OR need)',
            '"generative AI" AND legal AND (hiring OR freelance)',
            '"AI agent" AND legal AND (developer OR hiring OR need)',
            '"law firm" AND AI AND automation AND (hiring OR seeking)'
        ]


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
                self.wfile.write(b"<h1>Error: Review file not found.</h1>")
        elif self.path == "/status":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "interested_count": len(INTERESTED_RESULTS),
                "shutdown": SHUTDOWN_EVENT.is_set()
            }).encode())
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
            SHUTDOWN_EVENT.set()
            
        elif self.path == "/mark_interested":
            try:
                data = json.loads(body)
                result_id = data.get("result_id")
                interested = data.get("interested", False)
                
                if interested and AGENT_INSTANCE:
                    if result_id not in [r.get("id") for r in INTERESTED_RESULTS]:
                        for r in AGENT_INSTANCE.all_results:
                            if r.get("id") == result_id:
                                INTERESTED_RESULTS.append(r)
                                break
                elif not interested:
                    INTERESTED_RESULTS = [r for r in INTERESTED_RESULTS if r.get("id") != result_id]
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "count": len(INTERESTED_RESULTS)}).encode())
            except:
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
            except:
                self.send_response(500)
                self.end_headers()
        else:
            self.send_error(404)


class SearchAgent(BaseAgent):
    """
    LinkedIn Boolean Search Agent for legal automation freelancing.
    
    Inherits from BaseAgent for:
    - Browser management
    - Logging
    - Configuration
    - History management
    """
    
    def get_agent_name(self) -> str:
        return "SearchAgent"
    
    def __init__(self, config_path: str = "config.json"):
        super().__init__(config_path)
        
        global AGENT_INSTANCE
        AGENT_INSTANCE = self
        
        self.search_generator = BooleanSearchGenerator()
        self.all_results = []
        self.job_results = []
        self.post_results = []
        self.seen_urls = set()
        
        # Session metrics
        self.run_metrics.update({
            "queries_executed": 0,
            "jobs_found": 0,
            "posts_found": 0,
            "duplicates_skipped": 0,
            "agent_type": "search_agent"
        })
    
    async def run(self):
        """Main search agent workflow."""
        global SHUTDOWN_EVENT, INTERESTED_RESULTS
        
        SHUTDOWN_EVENT.clear()
        INTERESTED_RESULTS = []
        
        try:
            # Load history
            history = self.load_history(SEARCH_HISTORY_FILE)
            if history:
                self.seen_urls = set(history.get("seen_urls", []))
                self.log(f"Loaded {len(self.seen_urls)} previously seen URLs")
            
            # Navigate to LinkedIn
            await self.navigate("https://www.linkedin.com/")
            await asyncio.sleep(3)
            
            # Run all searches
            await self._run_all_searches()
            
            if not self.all_results:
                self.log("No new results found.")
                return
            
            # Generate review UI
            self._generate_review_html()
            
            # Start review server
            await self._start_review_server()
            
            # Save history
            self._save_history()
            
            # Export if any interested
            if INTERESTED_RESULTS:
                self.export_to_csv()
            
        except Exception as e:
            self.log(f"CRITICAL ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            if os.path.exists(REVIEW_HTML_FILE):
                try:
                    os.remove(REVIEW_HTML_FILE)
                except:
                    pass
    
    async def _run_all_searches(self):
        """Execute all Boolean search combinations."""
        job_queries = self.search_generator.generate_job_queries()
        post_queries = self.search_generator.generate_post_queries()
        
        self.log(f"Running {len(job_queries)} job queries and {len(post_queries)} post queries...")
        
        # Search jobs
        for i, query in enumerate(job_queries):
            self.log(f"Job query {i+1}/{len(job_queries)}: {query[:50]}...")
            await self._search_jobs(query)
            await human_delay(3.0, 6.0)  # Anti-detection delay
        
        # Search posts
        for i, query in enumerate(post_queries):
            self.log(f"Post query {i+1}/{len(post_queries)}: {query[:50]}...")
            await self._search_posts(query)
            await human_delay(3.0, 6.0)
        
        self.log(f"Search complete: {len(self.job_results)} jobs, {len(self.post_results)} posts")
    
    async def _search_jobs(self, query: str):
        """Search LinkedIn Jobs with a Boolean query."""
        encoded_query = urllib.parse.quote(query)
        jobs_url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_query}&f_WT=2"
        
        try:
            await human_like_navigate(self.page, jobs_url)
            
            # Scroll to load results
            for _ in range(random.randint(2, 4)):
                await human_scroll(self.page)
                await human_delay(1.0, 2.5)
            
            # Extract job listings
            job_cards = await self.page.query_selector_all("div.job-card-container, li.jobs-search-results__list-item")
            
            for card in job_cards[:20]:
                try:
                    result = await self._extract_job_data(card, query)
                    if result and result["url"] not in self.seen_urls:
                        self.all_results.append(result)
                        self.job_results.append(result)
                        self.seen_urls.add(result["url"])
                        self.run_metrics["jobs_found"] += 1
                        self.log(f"  ✓ {result['title'][:50]} at {result['company'][:30] if result.get('company') else 'Unknown'}")
                except:
                    continue
            
            self.run_metrics["queries_executed"] += 1
            
        except Exception as e:
            self.log(f"  Error searching jobs: {e}")
    
    async def _extract_job_data(self, card, query: str) -> dict:
        """Extract job data from a job card element."""
        job_url = ""
        title = ""
        
        # Get URL and title
        url_selectors = [
            "a.job-card-container__link",
            "a.job-card-list__title",
            ".job-card-container a"
        ]
        
        for sel in url_selectors:
            link_el = await card.query_selector(sel)
            if link_el:
                href = await link_el.get_attribute("href")
                if href and href != "#":
                    job_url = href
                    title = await link_el.inner_text()
                    title = title.strip().split('\n')[0]
                    break
        
        # Fallback: construct from job ID
        if not job_url or job_url == "#":
            job_id = await card.get_attribute("data-job-id")
            if job_id:
                job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
        
        if job_url and job_url.startswith("/"):
            job_url = "https://www.linkedin.com" + job_url
        
        # Clean URL
        if job_url and "?" in job_url:
            job_url = job_url.split("?")[0]
        
        if not job_url or "linkedin.com" not in job_url:
            return None
        
        # Company
        company = ""
        company_el = await card.query_selector("span.job-card-container__primary-description, a.job-card-container__company-name")
        if company_el:
            company = (await company_el.inner_text()).strip()
        
        # Location
        location = ""
        location_el = await card.query_selector("li.job-card-container__metadata-item")
        if location_el:
            location = (await location_el.inner_text()).strip()
        
        return {
            "id": f"job_{len(self.all_results)}",
            "type": "job",
            "title": title,
            "company": company,
            "location": location,
            "url": job_url,
            "query": query,
            "found_at": datetime.now().isoformat()
        }
    
    async def _search_posts(self, query: str):
        """Search LinkedIn Posts with a Boolean query."""
        encoded_query = urllib.parse.quote(query)
        posts_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&sortBy=%22date_posted%22"
        
        try:
            await human_like_navigate(self.page, posts_url)
            
            for _ in range(random.randint(2, 4)):
                await human_scroll(self.page)
                await human_delay(1.0, 2.5)
            
            post_cards = await self.page.query_selector_all("div.feed-shared-update-v2, div[data-urn]")
            
            for card in post_cards[:15]:
                try:
                    result = await self._extract_post_data(card, query)
                    if result and result["url"] not in self.seen_urls:
                        # Check relevance with Gemini
                        if self._is_relevant_post(result.get("content", "")):
                            self.all_results.append(result)
                            self.post_results.append(result)
                            self.seen_urls.add(result["url"])
                            self.run_metrics["posts_found"] += 1
                            self.log(f"  ✓ Post by {result['author'][:30]}")
                except:
                    continue
            
            self.run_metrics["queries_executed"] += 1
            
        except Exception as e:
            self.log(f"  Error searching posts: {e}")
    
    async def _extract_post_data(self, card, query: str) -> dict:
        """Extract post data from a post card element."""
        post_urn = await card.get_attribute("data-urn")
        post_url = f"https://www.linkedin.com/feed/update/{post_urn}/" if post_urn else ""
        
        if not post_url:
            return None
        
        # Author
        author = "Unknown"
        author_el = await card.query_selector(".update-components-actor__name span, a.update-components-actor__meta-link")
        if author_el:
            author = (await author_el.inner_text()).strip().split('\n')[0]
        
        # Content
        content = ""
        content_el = await card.query_selector(".feed-shared-update-v2__description, .update-components-text")
        if content_el:
            content = (await content_el.inner_text())[:1000]
        
        return {
            "id": f"post_{len(self.all_results)}",
            "type": "post",
            "author": author,
            "content": content,
            "url": post_url,
            "query": query,
            "found_at": datetime.now().isoformat()
        }
    
    def _is_relevant_post(self, content: str) -> bool:
        """Check if post is relevant using Gemini."""
        if not content or len(content) < 20:
            return False
        
        try:
            prompt = f"""Is this LinkedIn post about hiring/seeking someone for legal AI automation work?

POST: {content[:1000]}

Answer YES if: hiring, seeking help, job opportunity, looking for freelancer/consultant
Answer NO if: just discussion, someone looking FOR a job, unrelated

Reply with only YES or NO."""

            response = self.gemini.generate(prompt)
            return "YES" in response.strip().upper()
        except:
            return True  # Include on error
    
    def _generate_review_html(self):
        """Generate accessible HTML review page."""
        results_html = ""
        
        for r in self.all_results:
            result_type = r.get("type", "unknown")
            title = r.get("title", r.get("author", "Unknown")).replace('<', '&lt;')
            subtitle = r.get("company", r.get("content", "")[:100]).replace('<', '&lt;')
            url = r.get("url", "")
            result_id = r.get("id", "")
            
            results_html += f"""
            <article class="result-card" data-id="{result_id}">
                <div class="result-type {result_type}">{result_type.upper()}</div>
                <h3>{title}</h3>
                <p class="subtitle">{subtitle}</p>
                <div class="actions">
                    <label><input type="checkbox" class="interested-cb" data-id="{result_id}"> Interested</label>
                    <a href="{url}" target="_blank" class="btn">View →</a>
                </div>
            </article>
            """
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Search Results Review</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f3f2ef; padding: 20px; max-width: 900px; margin: 0 auto; }}
        h1 {{ color: #0a66c2; }}
        .result-card {{ background: white; padding: 16px; margin: 12px 0; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .result-type {{ font-size: 12px; font-weight: bold; padding: 4px 8px; border-radius: 4px; display: inline-block; margin-bottom: 8px; }}
        .result-type.job {{ background: #0a66c2; color: white; }}
        .result-type.post {{ background: #057642; color: white; }}
        h3 {{ margin: 8px 0; }}
        .subtitle {{ color: #666; font-size: 14px; margin: 8px 0; }}
        .actions {{ display: flex; gap: 16px; align-items: center; margin-top: 12px; }}
        .btn {{ background: #0a66c2; color: white; padding: 8px 16px; border-radius: 20px; text-decoration: none; }}
        .action-bar {{ position: fixed; bottom: 0; left: 0; right: 0; background: white; padding: 16px; box-shadow: 0 -2px 10px rgba(0,0,0,0.1); text-align: center; }}
        .content-wrapper {{ padding-bottom: 80px; }}
        #interested-count {{ font-weight: bold; color: #057642; }}
    </style>
</head>
<body>
    <div class="content-wrapper">
        <h1>Search Results ({len(self.all_results)} found)</h1>
        <p>Jobs: {len(self.job_results)} | Posts: {len(self.post_results)}</p>
        {results_html}
    </div>
    <div class="action-bar">
        <span id="interested-count">0</span> selected | 
        <button onclick="exportCSV()" class="btn">Export CSV</button>
        <button onclick="shutdown()" class="btn" style="background:#cc1016">Done</button>
    </div>
    <script>
        document.querySelectorAll('.interested-cb').forEach(cb => {{
            cb.addEventListener('change', async (e) => {{
                const resp = await fetch('/mark_interested', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{result_id: e.target.dataset.id, interested: e.target.checked}})
                }});
                const data = await resp.json();
                document.getElementById('interested-count').textContent = data.count;
            }});
        }});
        async function exportCSV() {{
            const resp = await fetch('/export_csv', {{method: 'POST'}});
            const data = await resp.json();
            alert('Exported to: ' + data.path);
        }}
        async function shutdown() {{
            await fetch('/shutdown', {{method: 'POST'}});
            document.body.innerHTML = '<h1 style="text-align:center;margin-top:50px">Done! You can close this tab.</h1>';
        }}
    </script>
</body>
</html>"""
        
        with open(REVIEW_HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html)
    
    async def _start_review_server(self):
        """Start review server and wait for user action."""
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
        
        self.play_ready_sound()
        
        while not SHUTDOWN_EVENT.is_set():
            await asyncio.sleep(1)
    
    def _save_history(self):
        """Save search history."""
        self.save_history(SEARCH_HISTORY_FILE, {
            "seen_urls": list(self.seen_urls),
            "last_updated": datetime.now().isoformat()
        })
        
        self.save_history(SEARCH_RESULTS_FILE, {
            "timestamp": datetime.now().isoformat(),
            "metrics": self.run_metrics,
            "results": self.all_results
        })
    
    def export_to_csv(self) -> str:
        """Export interested results to CSV."""
        csv_path = f"legal_automation_opportunities_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Type", "Title/Author", "Company", "URL", "Query"])
                
                for r in INTERESTED_RESULTS:
                    writer.writerow([
                        r.get("type", ""),
                        r.get("title", r.get("author", "")),
                        r.get("company", ""),
                        r.get("url", ""),
                        r.get("query", "")
                    ])
            
            self.log(f"Exported {len(INTERESTED_RESULTS)} results to {csv_path}")
            return csv_path
        except Exception as e:
            self.log(f"Error exporting CSV: {e}")
            return ""


# Entry point
async def main():
    agent = SearchAgent()
    await agent.execute()


if __name__ == "__main__":
    print("Starting LinkedIn Search Agent...", flush=True)
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
