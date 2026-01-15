"""
Test Script for LinkedIn Post Creation
======================================
This script isolates the LinkedIn posting functionality from the main agent.
It bypasses the slow Opal AI generation by using dummy content and images.
Focus: Debugging the 'Add Alt Text' flow.
"""

import asyncio
import os
import sys
from PIL import Image

# Add parent directory to path to allow imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# Import the specific agent class (adjust import based on actual file structure)
# Assuming post_creation_agent.py is in the same directory (contend/)
from post_creation_agent import PostCreationAgent

def create_dummy_image(path):
    """Create a simple red square image for testing."""
    img = Image.new('RGB', (800, 800), color='red')
    img.save(path)
    print(f"Created dummy image at: {path}")
    return path

async def test_posting_flow():
    agent = PostCreationAgent()
    
    # 1. Setup
    print("\n--- STARTING TEST ---")
    await agent.start()
    
    # Create test assets
    test_image_path = os.path.join(current_dir, "test_image.jpg")
    create_dummy_image(test_image_path)
    test_content = "This is a test post to verify the automated posting agent. #Test #Automation"
    test_alt_text = "A solid red square used for testing automated image verification."
    
    try:
        # 2. LinkedIn Navigation
        print("\n--- NAVIGATING TO LINKEDIN ---")
        if not await agent.navigate_to_linkedin():
            print("Failed navigation")
            return

        # 3. Start Post
        print("\n--- STARTING POST ---")
        if not await agent.click_start_post():
            print("Failed to click start post")
            return

        # 4. Paste Content
        print("\n--- PASTING CONTENT ---")
        if not await agent.paste_content(test_content):
            print("Failed to paste content")
            # Continue anyway, image matters more

        # 5. Attach Image
        print("\n--- ATTACHING IMAGE ---")
        if not await agent.attach_image(test_image_path):
            print("Failed to attach image")
            return
            
        # 6. Add Alt Text (CRITICAL TEST)
        print("\n--- TESTING ALT TEXT ---")
        success = await agent.add_alt_text(test_alt_text)
        
        if success:
            print("\n>>> SUCCESS: Alt text added correctly! <<<")
        else:
            print("\n>>> FAILURE: Could not add alt text. <<<")
            
        print("\nTest complete. Leaving browser open for manual inspection for 30 seconds...")
        await asyncio.sleep(30)
        
    except Exception as e:
        print(f"Test crashed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await agent.stop()
        # Clean up
        if os.path.exists(test_image_path):
            try:
                os.remove(test_image_path)
            except:
                pass

if __name__ == "__main__":
    asyncio.run(test_posting_flow())
