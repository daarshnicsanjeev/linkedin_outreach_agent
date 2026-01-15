
import os

with open(r"c:\Users\daars\.gemini\antigravity\scratch\linkedin_outreach_agent\contend\debug_dom_structure.txt", "r", encoding="utf-8") as f:
    lines = f.readlines()

with open(r"c:\Users\daars\.gemini\antigravity\scratch\linkedin_outreach_agent\contend\search_results.txt", "w", encoding="utf-8") as out:
    for i, line in enumerate(lines):
        if "<img" in line.lower() or "img." in line.lower():
            out.write(f"{i+1}: {line.strip()}\n")
