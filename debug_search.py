
import os

log_file = r'c:\Users\daars\.gemini\antigravity\scratch\linkedin_outreach_agent\agent_log.txt'
output_file = r'c:\Users\daars\.gemini\antigravity\scratch\linkedin_outreach_agent\search_results.txt'

with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

results = []
for i, line in enumerate(lines, 1):
    if 'Lisa' in line or 'Parlagreco' in line:
        results.append(f'{i}: {line.strip()}')

with open(output_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))

print(f"Found {len(results)} matches.")
