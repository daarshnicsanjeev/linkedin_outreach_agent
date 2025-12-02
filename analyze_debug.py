
import os

def search_file(filename, search_term):
    with open("analysis_result.txt", "a", encoding="utf-8") as out:
        out.write(f"Searching {filename} for '{search_term}'...\n")
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
                index = content.find(search_term)
                if index != -1:
                    out.write(f"Found '{search_term}' at index {index}\n")
                    start = max(0, index - 500)
                    end = min(len(content), index + 500)
                    out.write(f"Context:\n{content[start:end]}\n")
                else:
                    out.write(f"'{search_term}' NOT FOUND.\n")
        except Exception as e:
            out.write(f"Error reading {filename}: {e}\n")

if os.path.exists("analysis_result.txt"):
    os.remove("analysis_result.txt")

search_file("debug_page_initial.html", 'scaffold-finite-scroll')
search_file("debug_page_initial.html", 'connections-list')
search_file("debug_page_initial.html", 'overflow')
