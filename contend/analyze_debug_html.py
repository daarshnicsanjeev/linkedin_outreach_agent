import os
import re

html_path = 'contend/debug_alt_text_missing.html'

if not os.path.exists(html_path):
    print(f"File not found: {html_path}")
    exit(1)

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()


output_path = 'contend/analysis_output.txt'
with open(output_path, 'w', encoding='utf-8') as out_f:
    out_f.write(f"Read {len(content)} bytes\n")

    # regex for buttons with aria-label or text
    buttons = re.findall(r'<button[^>]*>', content)
    out_f.write(f"Found {len(buttons)} buttons\n")

    out_f.write("\n--- Potential ALT buttons ---\n")
    count = 0
    for btn in buttons:
        lower_btn = btn.lower()
        if 'alt' in lower_btn or 'text' in lower_btn or 'description' in lower_btn:
            out_f.write(btn + "\n")
            count += 1
            if count > 20: 
                out_f.write("... and more\n")
                break

    out_f.write("\n--- Elements with 'Alt' in aria-label ---\n")
    aria_elements = re.findall(r'<[^>]+aria-label="[^"]*alt[^"]*"[^>]*>', content, re.IGNORECASE)
    for el in aria_elements:
        out_f.write(el + "\n")

    out_f.write("\n--- Search for 'Alternative' ---\n")
    alt_elements = re.findall(r'<[^>]+>[^<]*Alternative[^<]*</[^>]+>', content, re.IGNORECASE)
    for el in alt_elements:
        out_f.write(el + "\n")

    out_f.write("\n--- Navigation Buttons ---\n")
    nav_full = re.findall(r'<button[^>]+aria-label="[^"]*(?:Next|Done|Save)[^"]*"[^>]*>', content, re.IGNORECASE)
    for btn in nav_full:
        out_f.write(btn[:200] + "\n")


