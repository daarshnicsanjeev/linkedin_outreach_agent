"""
Shared Constants for LinkedIn Agents
=====================================
Centralized configuration values, selectors, and keywords.
"""

import os

# Base directories
PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(os.path.dirname(PACKAGE_DIR))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
DEBUG_DIR = os.path.join(PROJECT_ROOT, "debug")
USER_DATA_DIR = os.path.join(PROJECT_ROOT, "user_data")

# Chrome debugging
CHROME_DEBUG_PORT = 9222
CHROME_DEBUG_URL = f"http://localhost:{CHROME_DEBUG_PORT}"

# LinkedIn URLs
LINKEDIN_BASE_URL = "https://www.linkedin.com"
LINKEDIN_FEED_URL = f"{LINKEDIN_BASE_URL}/feed/"
LINKEDIN_CONNECTIONS_URL = f"{LINKEDIN_BASE_URL}/mynetwork/invite-connect/connections/"
LINKEDIN_NOTIFICATIONS_URL = f"{LINKEDIN_BASE_URL}/notifications/"
LINKEDIN_SEARCH_URL = f"{LINKEDIN_BASE_URL}/search/results/people/"

# Legal professional keywords for classification
KEYWORDS_PRACTICING = [
    "partner", "associate", "counsel", "attorney", "litigator", "lawyer",
    "principal", "barrister", "solicitor", "advocate", "legal counsel",
    "general counsel", "managing partner", "senior partner", "of counsel",
    "trial lawyer", "criminal defense", "personal injury", "corporate lawyer",
    "in-house counsel", "law firm", "law group", "legal services", "legal practice",
    "litigation", "j.d.", "jd", "esq", "llb", "llm", "juris doctor"
]

KEYWORDS_GENERAL = [
    "student", "recruiter", "legal ops", "paralegal", "intern", "assistant",
    "law student", "legal assistant", "legal secretary", "legal tech", "legaltech",
    "legal operations", "court clerk", "legal researcher", "legal analyst",
    "compliance", "legal advisor", "legal consultant", "legal professional"
]

# Default timeouts (ms)
DEFAULT_PAGE_LOAD_TIMEOUT = 30000
DEFAULT_ELEMENT_TIMEOUT = 10000
DEFAULT_NAVIGATION_TIMEOUT = 45000

# Rate limiting defaults
DEFAULT_MIN_DELAY = 1.5
DEFAULT_MAX_DELAY = 4.0
DEFAULT_ACTIONS_PER_SESSION = 50
