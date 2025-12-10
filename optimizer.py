import json
import os
from datetime import datetime
from config_manager import ConfigManager

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

        # Advanced Optimization Logic
        recent_runs = history[-5:] # Look at last 5 runs
        if len(recent_runs) < 3:
            # Need at least 3 runs to make decisions
            return

        # 1. Optimize Scroll Wait (Bidirectional)
        scroll_success_rates = [run["metrics"].get("scroll_success_rate", 1.0) for run in recent_runs]
        avg_scroll_success = sum(scroll_success_rates) / len(scroll_success_rates)
        
        current_scroll_wait = self.config_manager.get("timeouts.scroll_wait", 3000)
        
        if avg_scroll_success < 0.6:
            # Low success rate -> Increase wait
            new_wait = min(current_scroll_wait + 1000, 10000) # Cap at 10s
            if new_wait > current_scroll_wait:
                self.log_change(f"Low scroll success ({avg_scroll_success:.2f}). Increasing scroll_wait: {current_scroll_wait} -> {new_wait}")
                self.config_manager.set("timeouts.scroll_wait", new_wait)
        elif avg_scroll_success > 0.9:
            # High success rate -> Try to decrease wait (Speed up)
            new_wait = max(current_scroll_wait - 500, 2000) # Min 2s
            if new_wait < current_scroll_wait:
                self.log_change(f"High scroll success ({avg_scroll_success:.2f}). Decreasing scroll_wait: {current_scroll_wait} -> {new_wait}")
                self.config_manager.set("timeouts.scroll_wait", new_wait)

        # 2. Optimize Message Wait (Bidirectional)
        msg_failures = 0
        for run in recent_runs:
            if run["metrics"].get("message_verification_failed", False):
                msg_failures += 1
        
        current_msg_wait = self.config_manager.get("timeouts.message_send_wait", 3000)
        
        if msg_failures >= 1:
            # Failures detected -> Increase wait
            new_wait = min(current_msg_wait + 1000, 10000)
            if new_wait > current_msg_wait:
                self.log_change(f"Message verification failures detected. Increasing message_send_wait: {current_msg_wait} -> {new_wait}")
                self.config_manager.set("timeouts.message_send_wait", new_wait)
        elif msg_failures == 0 and len(recent_runs) >= 5:
            # No failures in last 5 runs -> Try to decrease wait
            new_wait = max(current_msg_wait - 500, 2000) # Min 2s
            if new_wait < current_msg_wait:
                self.log_change(f"Stable message sending. Decreasing message_send_wait: {current_msg_wait} -> {new_wait}")
                self.config_manager.set("timeouts.message_send_wait", new_wait)

        # 3. Optimize Retries based on Errors
        error_runs = 0
        for run in recent_runs:
            if run["metrics"].get("errors"):
                error_runs += 1
        
        current_retries = self.config_manager.get("limits.max_retries", 2)
        if error_runs >= 2:
            # Frequent errors -> Increase retries
            new_retries = min(current_retries + 1, 5)
            if new_retries > current_retries:
                self.log_change(f"Frequent errors detected. Increasing max_retries: {current_retries} -> {new_retries}")
                self.config_manager.set("limits.max_retries", new_retries)
        
        # 4. Optimize Chat Open Retries based on chat open failures
        chat_open_failures = 0
        for run in recent_runs:
            if run["metrics"].get("chat_open_failed", False):
                chat_open_failures += 1
        
        current_chat_retries = self.config_manager.get("limits.chat_open_retries", 3)
        current_chat_delay = self.config_manager.get("limits.chat_open_delay_ms", 2000)
        
        if chat_open_failures >= 2:
            # Frequent chat open failures -> Increase retries and delay
            new_retries = min(current_chat_retries + 1, 6)
            new_delay = min(current_chat_delay + 1000, 5000)  # Cap at 5s
            
            if new_retries > current_chat_retries:
                self.log_change(f"Chat open failures detected. Increasing chat_open_retries: {current_chat_retries} -> {new_retries}")
                self.config_manager.set("limits.chat_open_retries", new_retries)
            if new_delay > current_chat_delay:
                self.log_change(f"Chat open failures detected. Increasing chat_open_delay_ms: {current_chat_delay} -> {new_delay}")
                self.config_manager.set("limits.chat_open_delay_ms", new_delay)
        elif chat_open_failures == 0 and len(recent_runs) >= 5:
            # No chat failures in last 5 runs -> Try to optimize (speed up)
            new_delay = max(current_chat_delay - 500, 1500)  # Min 1.5s
            if new_delay < current_chat_delay:
                self.log_change(f"Stable chat opening. Decreasing chat_open_delay_ms: {current_chat_delay} -> {new_delay}")
                self.config_manager.set("limits.chat_open_delay_ms", new_delay)
        
        # 5. Optimize Identity Verification based on failures
        identity_failures = 0
        for run in recent_runs:
            if run["metrics"].get("identity_verification_failed", False):
                identity_failures += 1
        
        current_id_retries = self.config_manager.get("timeouts.identity_poll_retries", 15)
        current_id_delay = self.config_manager.get("timeouts.identity_poll_delay_ms", 300)
        
        if identity_failures >= 2:
            # Increase polling retries and delay
            new_retries = min(current_id_retries + 5, 30)
            new_delay = min(current_id_delay + 100, 1000)
            
            if new_retries > current_id_retries:
                self.log_change(f"Identity verification failures. Increasing identity_poll_retries: {current_id_retries} -> {new_retries}")
                self.config_manager.set("timeouts.identity_poll_retries", new_retries)
            if new_delay > current_id_delay:
                self.log_change(f"Identity verification failures. Increasing identity_poll_delay_ms: {current_id_delay} -> {new_delay}")
                self.config_manager.set("timeouts.identity_poll_delay_ms", new_delay)
        elif identity_failures == 0 and len(recent_runs) >= 5:
            # Stable - speed up polling
            new_delay = max(current_id_delay - 50, 200)
            if new_delay < current_id_delay:
                self.log_change(f"Stable identity verification. Decreasing identity_poll_delay_ms: {current_id_delay} -> {new_delay}")
                self.config_manager.set("timeouts.identity_poll_delay_ms", new_delay)
        
        # 6. Optimize File Upload Wait based on failures
        file_failures = 0
        for run in recent_runs:
            if run["metrics"].get("file_upload_failed", False):
                file_failures += 1
        
        current_upload_wait = self.config_manager.get("timeouts.file_upload_wait_ms", 5000)
        
        if file_failures >= 1:
            # File upload is critical - increase wait
            new_wait = min(current_upload_wait + 2000, 15000)
            if new_wait > current_upload_wait:
                self.log_change(f"File upload failures. Increasing file_upload_wait_ms: {current_upload_wait} -> {new_wait}")
                self.config_manager.set("timeouts.file_upload_wait_ms", new_wait)
        elif file_failures == 0 and len(recent_runs) >= 5:
            # Stable - try to speed up
            new_wait = max(current_upload_wait - 500, 3000)
            if new_wait < current_upload_wait:
                self.log_change(f"Stable file uploads. Decreasing file_upload_wait_ms: {current_upload_wait} -> {new_wait}")
                self.config_manager.set("timeouts.file_upload_wait_ms", new_wait)
        
        # 7. Optimize UI Response Time
        # If message verification failures occur, increase UI wait time
        if msg_failures >= 1:
            current_ui_wait = self.config_manager.get("timeouts.ui_response_wait_ms", 1000)
            new_ui_wait = min(current_ui_wait + 500, 3000)
            if new_ui_wait > current_ui_wait:
                self.log_change(f"Increasing ui_response_wait_ms for stability: {current_ui_wait} -> {new_ui_wait}")
                self.config_manager.set("timeouts.ui_response_wait_ms", new_ui_wait)
        
        print("Optimization complete.")
