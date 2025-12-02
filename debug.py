import asyncio
from playwright.async_api import async_playwright

async def main():
    print("Import successful")
    async with async_playwright() as p:
        print("Playwright initialized")
        try:
            browser = await p.chromium.launch(headless=True)
            print("Browser launched")
            await browser.close()
        except Exception as e:
            print(f"Browser launch failed: {e}")

if __name__ == "__main__":
    with open("debug_log.txt", "w") as f:
        f.write("Starting script\n")
    try:
        asyncio.run(main())
        with open("debug_log.txt", "a") as f:
            f.write("Finished script\n")
    except Exception as e:
        with open("debug_log.txt", "a") as f:
            f.write(f"Script failed: {e}\n")
