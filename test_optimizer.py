import json
import os
from optimizer import AgentOptimizer
from config_manager import ConfigManager

# Setup
history_file = "test_history.json"
config_file = "test_config.json"

# Create initial config
initial_config = {
    "timeouts": {
        "page_load": 5000,
        "scroll_wait": 5000, # Start high
        "message_send_wait": 5000 # Start high
    },
    "limits": {
        "max_retries": 2
    }
}
with open(config_file, "w") as f:
    json.dump(initial_config, f)

# Create mock history (Success case)
mock_history = []
for _ in range(5):
    mock_history.append({
        "timestamp": "2025-01-01T12:00:00",
        "metrics": {
            "scroll_success_rate": 1.0, # Perfect scroll
            "message_verification_failed": False, # Perfect messaging
            "errors": []
        }
    })

with open(history_file, "w") as f:
    json.dump(mock_history, f)

# Run Optimizer
cm = ConfigManager(config_path=config_file)
opt = AgentOptimizer(history_path=history_file, config_manager=cm)

print("--- Initial Config ---")
print(cm.config)

opt.optimize()

print("\n--- Optimized Config (Should be lower) ---")
cm = ConfigManager(config_path=config_file) # Reload
print(cm.config)

# Verify
assert cm.get("timeouts.scroll_wait") < 5000, "Scroll wait should have decreased"
assert cm.get("timeouts.message_send_wait") < 5000, "Message wait should have decreased"

print("\nSUCCESS: Optimizer correctly decreased wait times based on success history.")

# Cleanup
os.remove(history_file)
os.remove(config_file)
