import asyncio
from playwright.async_api import async_playwright

async def main():
    print("Starting Playwright...")
    async with async_playwright() as p:
        print("Playwright started.")
        try:
            print("Connecting to CDP...")
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            print("Connected!")
            await browser.close()
        except Exception as e:
            print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
