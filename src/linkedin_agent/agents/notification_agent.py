"""
LinkedIn Notification Engagement Agent
======================================
Monitors LinkedIn notifications for engagement (likes, comments, mentions, etc.)
and sends connection invites to non-connected users who have engaged.

Refactored: 2026-01-11 - Now uses BaseAgent for shared functionality

Author: AI Agent
Created: 2024-12-09
"""

import asyncio
import json
import os
import subprocess
import socket
import re
import random
from datetime import datetime

from dotenv import load_dotenv

from ..agents.base_agent import BaseAgent
from ..utils.anti_detection import (
    human_delay, human_scroll, human_mouse_move, 
    human_like_navigate, human_like_click, RateLimiter
)

# Load environment variables
load_dotenv()

# Configuration
NOTIFICATIONS_URL = "https://www.linkedin.com/notifications/"
DAILY_INVITE_LIMIT = 10


class WeeklyLimitReachedError(Exception):
    """Raised when LinkedIn's weekly invitation limit is detected."""
    pass


class NotificationAgent(BaseAgent):
    """
    Agent that monitors LinkedIn notifications and sends connection invites.
    
    Inherits from BaseAgent for:
    - Browser management
    - Logging
    - Configuration
    - History management
    """
    
    def get_agent_name(self) -> str:
        return "NotificationAgent"
    
    def __init__(self, config_path: str = "config.json"):
        super().__init__(config_path)
        
        # Statistics
        self.notifications_processed = 0
        self.invites_sent = 0
        self.already_connected = 0
        self.already_invited = 0
        
        # User profile URL for identifying user's own comments
        self.user_profile_url = None
        
        # Rate limiter for human-like pacing
        self.rate_limiter = RateLimiter(
            min_delay=5, 
            max_delay=15, 
            long_pause_every=3,
            long_pause_duration=(30, 60)
        )
    
    async def run(self):
        """Main notification agent logic."""
        self.log("=" * 60)
        self.log("LinkedIn Notification Engagement Agent Starting")
        self.log("=" * 60)
        
        # Navigate to notifications
        if not await self._navigate_to_notifications():
            self.log("Failed to navigate to notifications. Exiting.")
            return
        
        # Detect user's profile URL
        await self._detect_user_profile()
        
        # Process notifications
        await self._process_notifications()
        
        # Save metrics
        self._save_metrics()
        
        # Print summary
        self._print_summary()
    
    async def _navigate_to_notifications(self) -> bool:
        """Navigate to LinkedIn notifications page."""
        self.log(f"Navigating to notifications: {NOTIFICATIONS_URL}")
        await human_like_navigate(self.page, NOTIFICATIONS_URL)
        
        # Check login
        if not await self._check_login_required():
            return False
        
        # Close chat popups
        await self.close_chat_popups()
        
        # Wait for notifications
        try:
            await self.page.wait_for_selector(
                "div.nt-card, section.artdeco-card",
                timeout=10000
            )
            self.log("Notifications page loaded.")
            return True
        except:
            self.log("WARNING: Could not detect notification cards.")
            return True
    
    async def _check_login_required(self) -> bool:
        """Check if LinkedIn login is required."""
        await asyncio.sleep(2)
        current_url = self.page.url
        
        if "login" in current_url or "authwall" in current_url:
            self.log("LOGIN REQUIRED - Please log in to LinkedIn")
            self.play_ready_sound()
            self.show_notification("Login Required", "Please log in to LinkedIn")
            
            for _ in range(60):
                await asyncio.sleep(5)
                current_url = self.page.url
                if "login" not in current_url and "authwall" not in current_url:
                    self.log("Login detected. Continuing...")
                    return True
            
            self.log("ERROR: Login timeout.")
            return False
        
        return True
    
    async def _detect_user_profile(self):
        """Detect the logged-in user's profile URL."""
        try:
            # Try navigating to /in/me
            await self.page.goto("https://www.linkedin.com/in/me/", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            current_url = self.page.url
            if "/in/" in current_url and "/me" not in current_url:
                self.user_profile_url = current_url.split("?")[0].rstrip("/")
                self.log(f"Detected user profile: {self.user_profile_url}")
        except Exception as e:
            self.log(f"Error detecting user profile: {e}")
    
    async def _process_notifications(self):
        """Extract and process notifications."""
        # Navigate back to notifications
        await human_like_navigate(self.page, NOTIFICATIONS_URL)
        
        # Load history
        history = self.load_history("notification_history.json")
        if not history:
            history = {
                "processed_notifications": [],
                "invited_profiles": {},
                "already_connected": [],
                "skipped_profiles": [],
                "daily_invites": {}
            }
        
        # Scroll to load notifications
        await self._scroll_notifications()
        
        # Extract notifications
        notifications = await self._extract_notifications()
        
        # Process each notification
        max_invites = self.get_config("notification_agent.max_invites_per_run", 50)
        
        for notif in notifications:
            if self.invites_sent >= max_invites:
                self.log(f"Reached max invites limit ({max_invites}). Stopping.")
                break
            
            # Check daily limit
            today = datetime.now().strftime("%Y-%m-%d")
            daily_invites = history.get("daily_invites", {})
            todays_count = daily_invites.get(today, 0)
            
            if todays_count >= DAILY_INVITE_LIMIT:
                self.log(f"Daily invite limit reached ({DAILY_INVITE_LIMIT}). Stopping.")
                break
            
            # Process profiles in notification
            for profile in notif.get("profiles", []):
                if self.invites_sent >= max_invites:
                    break
                
                profile_url = profile.get("profile_url")
                name = profile.get("name", "Unknown")
                
                # Skip if already processed
                if profile_url in history.get("invited_profiles", {}):
                    self.already_invited += 1
                    continue
                if profile_url in history.get("already_connected", []):
                    self.already_connected += 1
                    continue
                if profile_url == self.user_profile_url:
                    continue
                
                # Check connection status and send invite
                status = await self._check_connection_status(profile_url)
                
                if status == "connected":
                    self.log(f"  {name} - Already connected")
                    history.setdefault("already_connected", []).append(profile_url)
                    self.already_connected += 1
                    
                elif status == "can_connect":
                    self.log(f"  {name} - Sending connection invite...")
                    await self._simulate_human_browsing()
                    
                    success = await self._send_connection_invite()
                    
                    if success:
                        history.setdefault("invited_profiles", {})[profile_url] = {
                            "name": name,
                            "invited_at": datetime.now().isoformat(),
                            "engagement_type": notif.get("engagement_type", "engaged")
                        }
                        self.invites_sent += 1
                        
                        # Increment daily count
                        history.setdefault("daily_invites", {})[today] = todays_count + 1
                        todays_count += 1
                        
                        self.log(f"  Progress: {self.invites_sent}/{max_invites} this run")
                        
                        # Rate limit
                        if self.invites_sent < max_invites:
                            await self.rate_limiter.wait(self.log)
                    else:
                        self.record_error()
                        history.setdefault("skipped_profiles", []).append(profile_url)
                
                # Save history after each profile
                self.save_history("notification_history.json", history)
                self.notifications_processed += 1
    
    async def _scroll_notifications(self):
        """Scroll to load more notifications."""
        self.log("Scrolling to load more notifications...")
        last_height = 0
        scroll_attempts = 0
        max_scroll = self.get_config("notification_agent.scroll_attempts", 15)
        
        while scroll_attempts < max_scroll:
            await human_scroll(self.page, random.randint(700, 1200))
            await human_delay(1.5, 3.0)
            
            current_height = await self.page.evaluate("document.body.scrollHeight")
            
            if current_height == last_height:
                break
            
            last_height = current_height
            scroll_attempts += 1
            
            if scroll_attempts % 5 == 0:
                await human_delay(3.0, 6.0)
        
        # Scroll back to top
        await self.page.evaluate("window.scrollTo(0, 0)")
        await human_delay(1.0, 2.0)
    
    async def _extract_notifications(self) -> list:
        """Extract engagement notifications from the page."""
        notifications = []
        
        cards = await self.page.query_selector_all("div.nt-card, article.nt-card")
        self.log(f"Found {len(cards)} notification cards")
        
        max_notifications = self.get_config("notification_agent.max_notifications_per_run", 100)
        
        for i, card in enumerate(cards[:max_notifications]):
            try:
                text = await card.inner_text()
                text_lower = text.lower()
                
                # Classify notification
                is_engagement = self._classify_notification(text_lower)
                
                if not is_engagement:
                    continue
                
                self.log(f"  [{i+1}] ENGAGEMENT: {text[:60].replace(chr(10), ' ')}...")
                
                # Extract profile links
                profiles = await self._extract_profiles_from_card(card)
                
                if profiles:
                    engagement_type = self._determine_engagement_type(text_lower)
                    notifications.append({
                        "text": text[:100],
                        "engagement_type": engagement_type,
                        "profiles": profiles
                    })
                    
            except Exception as e:
                self.log(f"  Error extracting notification {i+1}: {e}")
                continue
        
        self.log(f"Extracted {len(notifications)} engagement notifications")
        return notifications
    
    def _classify_notification(self, text_lower: str) -> bool:
        """Check if notification is an engagement notification."""
        engagement_keywords = [
            "liked your", "loves your", "loved your", "celebrated your",
            "supported your", "found your", "reacted to", "commented on",
            "mentioned you", "shared your", "reposted your", "replied to",
            "viewed your profile", "and others", "comment that mentioned you"
        ]
        return any(kw in text_lower for kw in engagement_keywords)
    
    def _determine_engagement_type(self, text_lower: str) -> str:
        """Determine the type of engagement."""
        if "comment that mentioned you" in text_lower:
            return "third_party_mention"
        elif "viewed your profile" in text_lower:
            return "viewed"
        elif "loved" in text_lower:
            return "loved"
        elif "liked" in text_lower:
            return "liked"
        elif "commented" in text_lower:
            return "commented"
        elif "mentioned" in text_lower:
            return "mentioned"
        elif "reacted" in text_lower:
            return "reacted"
        elif "shared" in text_lower or "reposted" in text_lower:
            return "shared"
        return "engaged"
    
    async def _extract_profiles_from_card(self, card) -> list:
        """Extract profile links from a notification card."""
        profiles = []
        links = await card.query_selector_all("a[href*='/in/']")
        
        for link in links:
            href = await link.get_attribute("href")
            name = await link.inner_text()
            name = name.strip() if name else ""
            
            # Skip noise
            noise_words = ["see all", "unread", "notification settings"]
            if any(nw in name.lower() for nw in noise_words):
                continue
            
            if href and "/in/" in href:
                if not href.startswith("http"):
                    href = "https://www.linkedin.com" + href
                href = href.split("?")[0]
                
                # Extract name from URL if needed
                if not name or len(name) < 2:
                    url_name = href.split("/in/")[-1].split("/")[0]
                    name = url_name.replace("-", " ").title()
                
                profiles.append({
                    "name": name,
                    "profile_url": href
                })
        
        # Deduplicate
        seen = set()
        unique = []
        for p in profiles:
            if p["profile_url"] not in seen:
                seen.add(p["profile_url"])
                unique.append(p)
        
        return unique
    
    async def _simulate_human_browsing(self):
        """Simulate random human browsing behavior."""
        try:
            action = random.choice(["scroll", "scroll", "hover", "read", "scroll_up"])
            
            if action == "scroll":
                await human_scroll(self.page, random.randint(150, 350))
                await human_delay(0.5, 1.5)
            elif action == "scroll_up":
                await self.page.evaluate(f"window.scrollBy(0, -{random.randint(50, 150)})")
                await human_delay(0.5, 1.0)
            elif action == "hover":
                elements = await self.page.query_selector_all("button, a, img")
                if elements:
                    elem = random.choice(elements[:10])
                    await human_mouse_move(self.page, elem)
                    await human_delay(0.3, 0.8)
            elif action == "read":
                await human_delay(1.5, 3.5)
            
            await human_mouse_move(self.page)
        except:
            pass
    
    async def _check_connection_status(self, profile_url: str) -> str:
        """Check connection status with a profile."""
        try:
            await human_like_navigate(self.page, profile_url)
            await asyncio.sleep(2)
            
            # Check for Connect button
            connect_selectors = [
                "button:has-text('Connect')",
                "button[aria-label*='Connect with']",
                "div.pvs-profile-actions button:has-text('Connect')"
            ]
            
            for selector in connect_selectors:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn and await btn.is_visible():
                        return "can_connect"
                except:
                    continue
            
            # Check if already connected
            message_btn = await self.page.query_selector("button:has-text('Message')")
            if message_btn and await message_btn.is_visible():
                return "connected"
            
            # Check for pending
            pending = await self.page.query_selector("button:has-text('Pending')")
            if pending:
                return "pending"
            
            # Check for Follow only
            follow = await self.page.query_selector("button:has-text('Follow')")
            if follow and await follow.is_visible():
                return "follow_only"
            
            return "unknown"
            
        except Exception as e:
            self.log(f"Error checking connection status: {e}")
            return "error"
    
    async def _send_connection_invite(self) -> bool:
        """Send a connection invite on the current profile page."""
        try:
            # Find Connect button
            connect_selectors = [
                "button:has-text('Connect')",
                "button[aria-label*='Connect with']",
                "div.pvs-profile-actions button:has-text('Connect')"
            ]
            
            connect_btn = None
            for selector in connect_selectors:
                try:
                    connect_btn = await self.page.query_selector(selector)
                    if connect_btn and await connect_btn.is_visible():
                        break
                    connect_btn = None
                except:
                    continue
            
            if not connect_btn:
                self.log("  Could not find Connect button")
                return False
            
            # Click Connect
            await human_like_click(self.page, connect_btn)
            await asyncio.sleep(2)
            
            # Handle modal - click Send without note
            send_selectors = [
                "button[aria-label='Send without a note']",
                "button:has-text('Send without a note')",
                "button:has-text('Send now')"
            ]
            
            for selector in send_selectors:
                try:
                    send_btn = await self.page.query_selector(selector)
                    if send_btn and await send_btn.is_visible():
                        await human_like_click(self.page, send_btn)
                        await asyncio.sleep(1)
                        self.log("  ✓ Invite sent!")
                        return True
                except:
                    continue
            
            # Check for weekly limit
            weekly_limit = await self.page.query_selector("text=weekly invitation limit")
            if weekly_limit:
                self.log("  ⚠ Weekly invitation limit reached!")
                raise WeeklyLimitReachedError()
            
            # Close any modal
            close_btn = await self.page.query_selector("button[aria-label='Dismiss']")
            if close_btn:
                await close_btn.click()
            
            return False
            
        except WeeklyLimitReachedError:
            raise
        except Exception as e:
            self.log(f"  Error sending invite: {e}")
            return False
    
    def _save_metrics(self):
        """Save run metrics for optimization."""
        metrics = {
            "notifications_processed": self.notifications_processed,
            "invites_sent": self.invites_sent,
            "errors": self.errors_encountered,
            "agent_type": "notification_agent"
        }
        self.optimizer.log_run(metrics)
    
    def _print_summary(self):
        """Print run summary."""
        self.log("\n" + "=" * 60)
        self.log("RUN SUMMARY")
        self.log("=" * 60)
        self.log(f"  Notifications processed: {self.notifications_processed}")
        self.log(f"  Connection invites sent: {self.invites_sent}")
        self.log(f"  Already connected: {self.already_connected}")
        self.log(f"  Already pending: {self.already_invited}")
        self.log(f"  Errors/Skipped: {self.errors_encountered}")
        self.log("=" * 60)


# Entry point for direct execution
async def main():
    agent = NotificationAgent()
    await agent.execute()


if __name__ == "__main__":
    asyncio.run(main())
