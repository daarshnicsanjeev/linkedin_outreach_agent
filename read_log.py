import os

log_file = "agent_log.txt"
if os.path.exists(log_file):
    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        print(f"Total lines: {len(lines)}")
        print("--- Last 60 lines of agent_log.txt ---")
        for line in lines[-60:]:
            print(line.rstrip())
else:
    print(f"{log_file} not found.")
