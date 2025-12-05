import difflib
from datetime import datetime, timedelta

# --- Mock Agent Methods ---
def parse_connection_date(text):
    text = text.lower()
    today = datetime.now()
    try:
        if "hour" in text or "minute" in text or "moment" in text or "day" in text:
            return today
        if "week" in text:
            parts = text.split()
            for p in parts:
                if p.isdigit():
                    weeks = int(p)
                    return today - timedelta(weeks=weeks)
        if "month" in text:
            parts = text.split()
            for p in parts:
                if p.isdigit():
                    months = int(p)
                    return today - timedelta(days=months*30)
        if "year" in text:
            parts = text.split()
            for p in parts:
                if p.isdigit():
                    years = int(p)
                    return today - timedelta(days=years*365)
        return today
    except:
        return today

def classify_role(headline, practicing_keywords, general_keywords):
    headline = headline.lower()
    if any(k in headline for k in practicing_keywords):
        return "PRACTICING"
    if any(k in headline for k in general_keywords):
        return "GENERAL"
    return "SKIP"

def verify_identity(expected, found):
    ratio = difflib.SequenceMatcher(None, expected.lower(), found.lower()).ratio()
    return ratio

# --- TESTS ---

print("--- Testing Date Parsing ---")
d1 = parse_connection_date("Connected 2 weeks ago")
assert (datetime.now() - d1).days >= 14, "2 weeks failed"
print(f"2 weeks ago: {d1.date()} (OK)")

d2 = parse_connection_date("Connected 4 months ago")
assert (datetime.now() - d2).days >= 120, "4 months failed"
print(f"4 months ago: {d2.date()} (OK)")

print("\n--- Testing Role Classification ---")
p_keywords = ["partner", "associate", "counsel", "attorney"]
g_keywords = ["student", "recruiter"]

assert classify_role("Senior Associate Attorney", p_keywords, g_keywords) == "PRACTICING"
assert classify_role("Law Student at Harvard", p_keywords, g_keywords) == "GENERAL"
assert classify_role("Software Engineer", p_keywords, g_keywords) == "SKIP"
print("Role Classification OK")

print("\n--- Testing Fuzzy Matching ---")
# Case 1: Exact match
assert verify_identity("Sanjeev Chaodhari", "Sanjeev Chaodhari") == 1.0
# Case 2: Minor difference (e.g. middle initial)
ratio = verify_identity("Sanjeev Chaodhari", "Sanjeev K. Chaodhari")
print(f"Match 'Sanjeev Chaodhari' vs 'Sanjeev K. Chaodhari': {ratio:.2f}")
assert ratio > 0.85

# Case 3: Totally different
ratio = verify_identity("Sanjeev Chaodhari", "John Doe")
print(f"Match 'Sanjeev Chaodhari' vs 'John Doe': {ratio:.2f}")
assert ratio < 0.5

print("\nALL TESTS PASSED")
