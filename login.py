import asyncio
import json
from playwright.async_api import async_playwright

# --- Configuration ---
LOGIN_URL = "https://x.com/login"
COOKIES_FILE_PATH = "./cookies.json"
LOGIN_TIMEOUT = 120000  # 2 minutes

async def automatic_login_and_save_cookies():
    """
    Launches a browser, waits for manual login, then automatically
    detects success, saves cookies, and closes.
    """
    async with async_playwright() as p:
        browser = None
        print("🚀 Launching browser for login...")
        try:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            print("   Navigating to the login page...")
            await page.goto(LOGIN_URL)

            print("\n   >>> Please log in to your X account in the browser window. <<<")
            print("   After you log in, just wait. The script will automatically close for you.")

            home_timeline_selector = 'a[data-testid="AppTabBar_Home_Link"]'
            
            print(f"\n   Waiting for successful login (up to {LOGIN_TIMEOUT / 60000} minutes)...")
            await page.wait_for_selector(home_timeline_selector, state='visible', timeout=LOGIN_TIMEOUT)
            
            print("\n✅ Login successful! Main timeline detected.")
            print("   Waiting 2 seconds to ensure all cookies are set...")
            await asyncio.sleep(2)

            print("   Saving session cookies...")
            cookies = await context.cookies()
            
            if not cookies:
                raise Exception("No cookies were captured despite successful login detection.")

            with open(COOKIES_FILE_PATH, 'w') as f:
                json.dump(cookies, f, indent=2)

            print(f"✅ Cookies saved successfully to {COOKIES_FILE_PATH}")
            print("   You can now start the main server.")

        except Exception as e:
            print(f"\n❌ ERROR: Login process failed or timed out.")
            print(f"   Please try running 'python login.py' again. Details: {e}")
        finally:
            if browser:
                print("   Closing browser.")
                await browser.close()

if __name__ == "__main__":
    asyncio.run(automatic_login_and_save_cookies())

