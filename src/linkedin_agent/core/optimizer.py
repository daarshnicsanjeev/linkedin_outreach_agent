import json
import os
from datetime import datetime
from .config import ConfigManager

class AgentOptimizer:
    def __init__(self, history_path="agent_history.json", config_manager=None):
        self.history_path = history_path
        self.config_manager = config_manager or ConfigManager()

    def load_history(self):
        if not os.path.exists(self.history_path):
            return []
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []

    def save_history(self, history):
        try:
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            print(f"Error saving history: {e}")

    def log_run(self, metrics):
        history = self.load_history()
        run_entry = {
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics
        }
        history.append(run_entry)
        # Keep only last 50 runs to avoid huge file
        if len(history) > 50:
            history = history[-50:]
        self.save_history(history)
        return run_entry

    def log_change(self, msg):
        print(msg)
        try:
            with open("agent_log.txt", "a", encoding="utf-8") as f:
                f.write(f"[OPTIMIZER] {msg}\n")
        except:
            pass

    def optimize(self):
        history = self.load_history()
        if not history:
            return

        # Group runs by agent type
        runs_by_type = {
            "outreach_agent": [],
            "invite_withdrawal": [],
            "notification_agent": []
        }
        
        for run in history:
            metrics = run.get("metrics", {})
            agent_type = metrics.get("agent_type", "outreach_agent") # Default to outreach for old logs
            if agent_type in runs_by_type:
                runs_by_type[agent_type].append(run)
        
        # Optimize each agent type
        self.optimize_outreach(runs_by_type["outreach_agent"][-5:])
        self.optimize_invite_withdrawal(runs_by_type["invite_withdrawal"][-5:])
        self.optimize_notification(runs_by_type["notification_agent"][-5:])

    def optimize_outreach(self, recent_runs):
        if len(recent_runs) < 3:
            return

        # 1. Optimize Scroll Wait
        scroll_success_rates = [run["metrics"].get("scroll_success_rate", 1.0) for run in recent_runs]
        avg_scroll_success = sum(scroll_success_rates) / len(scroll_success_rates)
        current_scroll_wait = self.config_manager.get("timeouts.scroll_wait", 3000)
        
        if avg_scroll_success < 0.6:
            new_wait = min(current_scroll_wait + 1000, 10000)
            if new_wait > current_scroll_wait:
                self.log_change(f"[Outreach] Low scroll success ({avg_scroll_success:.2f}). Increasing scroll_wait: {current_scroll_wait} -> {new_wait}")
                self.config_manager.set("timeouts.scroll_wait", new_wait)
        elif avg_scroll_success > 0.9:
            new_wait = max(current_scroll_wait - 500, 2000)
            if new_wait < current_scroll_wait:
                self.log_change(f"[Outreach] High scroll success ({avg_scroll_success:.2f}). Decreasing scroll_wait: {current_scroll_wait} -> {new_wait}")
                self.config_manager.set("timeouts.scroll_wait", new_wait)

        # 2. Optimize Message Wait & Retries (Existing logic adapted)
        msg_failures = sum(1 for run in recent_runs if run["metrics"].get("message_verification_failed", False))
        current_msg_wait = self.config_manager.get("timeouts.message_send_wait", 3000)
        
        if msg_failures >= 1:
            new_wait = min(current_msg_wait + 1000, 10000)
            if new_wait > current_msg_wait:
                self.log_change(f"[Outreach] Message verification failures. Increasing message_send_wait: {current_msg_wait} -> {new_wait}")
                self.config_manager.set("timeouts.message_send_wait", new_wait)
        elif msg_failures == 0 and len(recent_runs) >= 5:
            new_wait = max(current_msg_wait - 500, 2000)
            if new_wait < current_msg_wait:
                self.log_change(f"[Outreach] Stable message sending. Decreasing message_send_wait: {current_msg_wait} -> {new_wait}")
                self.config_manager.set("timeouts.message_send_wait", new_wait)

        # 3. Optimize Chat Open
        chat_failures = sum(1 for run in recent_runs if run["metrics"].get("chat_open_failed", False))
        if chat_failures >= 2:
            cur_retries = self.config_manager.get("limits.chat_open_retries", 3)
            new_retries = min(cur_retries + 1, 6)
            if new_retries > cur_retries:
                self.log_change(f"[Outreach] Chat open failures. Increasing retries: {cur_retries} -> {new_retries}")
                self.config_manager.set("limits.chat_open_retries", new_retries)

        # 4. Optimize Identity Verification
        id_failures = sum(1 for run in recent_runs if run["metrics"].get("identity_verification_failed", False))
        cur_id_retries = self.config_manager.get("timeouts.identity_poll_retries", 15)
        
        if id_failures >= 2:
            new_retries = min(cur_id_retries + 5, 30)
            if new_retries > cur_id_retries:
                self.log_change(f"[Outreach] Identity failures. Increasing poll retries: {cur_id_retries} -> {new_retries}")
                self.config_manager.set("timeouts.identity_poll_retries", new_retries)
        
        # 5. Optimize File Upload Wait
        file_failures = sum(1 for run in recent_runs if run["metrics"].get("file_upload_failed", False))
        cur_upload_wait = self.config_manager.get("timeouts.file_upload_wait_ms", 5000)
        
        if file_failures >= 1:
            new_wait = min(cur_upload_wait + 2000, 15000)
            if new_wait > cur_upload_wait:
                self.log_change(f"[Outreach] File upload failures. Increasing wait: {cur_upload_wait} -> {new_wait}")
                self.config_manager.set("timeouts.file_upload_wait_ms", new_wait)

    def optimize_invite_withdrawal(self, recent_runs):
        if len(recent_runs) < 3:
            return
            
        # Optimize Dialog Timeout based on timeouts count
        timeouts = sum(run["metrics"].get("dialog_timeout_count", 0) for run in recent_runs)
        current_timeout = self.config_manager.get("invite_withdrawal.dialog_timeout_ms", 3000)
        
        if timeouts >= 2:
            new_timeout = min(current_timeout + 1000, 8000)
            if new_timeout > current_timeout:
                self.log_change(f"[Withdrawal] frequent dialog timeouts. Increasing dialog_timeout_ms: {current_timeout} -> {new_timeout}")
                self.config_manager.set("invite_withdrawal.dialog_timeout_ms", new_timeout)
        elif timeouts == 0 and len(recent_runs) >= 5:
            # Try to speed up if stable
            new_timeout = max(current_timeout - 500, 2000)
            if new_timeout < current_timeout:
                self.log_change(f"[Withdrawal] Stable dialogs. Decreasing dialog_timeout_ms: {current_timeout} -> {new_timeout}")
                self.config_manager.set("invite_withdrawal.dialog_timeout_ms", new_timeout)

    def optimize_notification(self, recent_runs):
        if len(recent_runs) < 3:
            return
            
        # Optimize Delay Between Invites based on errors
        errors = sum(run["metrics"].get("errors", 0) for run in recent_runs)
        current_delay = self.config_manager.get("notification_agent.delay_between_invites", 5)
        
        if errors >= 3:
            # High errors -> Slow down
            new_delay = min(current_delay + 2, 15)
            if new_delay > current_delay:
                self.log_change(f"[Notification] High errors ({errors}). Increasing delay_between_invites: {current_delay} -> {new_delay}")
                self.config_manager.set("notification_agent.delay_between_invites", new_delay)
        elif errors == 0 and len(recent_runs) >= 5:
            # No errors -> Speed up slightly
            new_delay = max(current_delay - 1, 3)
            if new_delay < current_delay:
                self.log_change(f"[Notification] Zero errors. Decreasing delay_between_invites: {current_delay} -> {new_delay}")
                self.config_manager.set("notification_agent.delay_between_invites", new_delay)

