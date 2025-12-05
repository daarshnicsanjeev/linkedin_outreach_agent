import json
import os

class ConfigManager:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_path):
            # Return defaults if file doesn't exist
            return {
                "timeouts": {
                    "page_load": 5000,
                    "scroll_wait": 3000,
                    "message_send_wait": 3000
                },
                "selectors": {
                    "connections_list": "div[data-view-name='connections-list']",
                    "show_more_btn": [
                        "button:has-text('Show more results')",
                        "button:has-text('Load more')",
                        "button:has-text('Show more')"
                    ]
                },
                "limits": {
                    "max_scrolls": 50,
                    "max_retries": 2
                }
            }
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key, default=None):
        # Support nested keys like "timeouts.page_load"
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, key, value):
        keys = key.split(".")
        target = self.config
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self.save_config()
