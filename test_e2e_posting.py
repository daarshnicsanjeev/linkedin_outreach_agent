import subprocess
import time
import requests
import json
import threading
import sys
import re

# Test Configuration
TEST_POST_URL = "https://www.linkedin.com/feed/update/urn:li:activity:7415797385081200640/"
TEST_COMMENT = "Great insight! (Automated E2E Test)"

def monitor_output(process):
    """Monitor and print the process output."""
    server_started = False
    
    for line in iter(process.stdout.readline, b''):
        line = line.decode('utf-8', errors='replace').strip()
        print(f"[AGENT] {line}")
        
        if "Review server started at" in line:
            server_started = True
    
    return server_started

def run_e2e_test():
    print("Starting E2E Posting Test...")
    
    # Start the agent
    process = subprocess.Popen(
        [sys.executable, "-u", "comment_agent.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=r"C:\Users\daars\.gemini\antigravity\scratch\linkedin_outreach_agent"
    )
    
    print("Waiting for Review Server to start...")
    
    # Wait for server to be ready
    server_url = None
    start_time = time.time()
    
    while time.time() - start_time < 120:  # Wait up to 2 minutes (scanning takes time)
        line = process.stdout.readline().decode('utf-8', errors='replace').strip()
        if not line:
            if process.poll() is not None:
                print("Agent exited prematurely.")
                return
            continue
            
        try:
            print(f"[AGENT] {line}")
        except:
            pass
        
        # Capture server URL
        match = re.search(r"Review server started at (http://[\d\.:]+)", line)
        if match:
            server_url = match.group(1)
            print(f"Server detected at: {server_url}")
            # DON'T break yet - wait for agent to be ready!
        
        # Wait for agent to reach wait loop BEFORE sending submit
        if server_url and "Waiting for user review" in line:
            print("Agent is now ready for submission.")
            break
            
    if not server_url:
        print("Timeout waiting for server to start.")
        process.terminate()
        return


    # Trigger posting via API
    print(f"Sending test comment to {server_url}/submit...")
    payload = {
        "approved": [
            {
                "author_name": "Test Author",
                "headline": "Test Headline",
                "post_url": TEST_POST_URL,
                "final_comment": TEST_COMMENT
            }
        ]
    }
    
    try:
        response = requests.post(f"{server_url}/submit", json=payload)
        print(f"Response: {response.status_code} - {response.text}")
        
        if response.status_code == 200:
            print("Submit successful! Agent should now be posting...")
        else:
            print(f"Submit failed: {response.text}")
            
    except Exception as e:
        print(f"Request failed: {e}")
    
    # Monitor for completion
    print("Monitoring for posting completion...")
    start_time = time.time()
    success = False
    
    while time.time() - start_time < 120:  # Wait 2 minutes for posting
        line = process.stdout.readline().decode('utf-8', errors='replace').strip()
        if not line:
            if process.poll() is not None:
                break
            continue
            
        try:
            print(f"[AGENT] {line}")
        except:
            pass
        
        if "Input cleared successfully!" in line or "Input cleared with Ctrl+Enter!" in line:
            print("SUCCESS: Input was cleared (Comment Posted)!")
            success = True
            
        if "Posting Complete!" in line:
            print("Agent finished posting cycle.")
            break
            
        if "CRITICAL ERROR" in line:
            print("Agent encountered a critical error.")
            break

    # Cleanup
    print("Cleaning up...")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        
    if success:
        print("\nE2E TEST PASSED: Comment posting verified.")
    else:
        print("\nE2E TEST FAILED: Did not see success confirmation.")

if __name__ == "__main__":
    run_e2e_test()
