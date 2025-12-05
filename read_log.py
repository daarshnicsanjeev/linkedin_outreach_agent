
import os

log_file = "agent_log.txt"
if os.path.exists(log_file):
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        print("--- Last 20 lines of agent_log.txt ---")
        for line in lines[-20:]:
            print(line.strip())
else:
    print(f"{log_file} not found.")

start_file = "debug_start.txt"
if os.path.exists(start_file):
    with open(start_file, "r") as f:
        print(f"\n--- {start_file} content ---")
        print(f.read())
else:
    print(f"\n{start_file} not found.")
