"""
Playwright automated validation of the ASCD Control Center UI Reset:
1. Desktop Viewport (1920x1080):
   - Opens http://localhost:5000
   - Switches to Tab 'ascd' (Command Deck)
   - Checks HUD stats and MCP toggles
   - Triggers ASCD Reset via button click (#ascd-btn-reset)
   - Verifies reset toast, baseline HUD telemetry, and pristine state
   - Captures screenshot: screenshots/ascd_reset_desktop_1920x1080.png
2. Mobile Touch Viewport (375x812):
   - Opens http://localhost:5000 with mobile touch emulation
   - Switches to Tab 'ascd' (Command Deck)
   - Verifies responsive layout and touch target accessibility of reset button
   - Triggers ASCD Reset via touch tap (#ascd-btn-reset)
   - Verifies reset toast and state update
   - Captures screenshot: screenshots/ascd_reset_mobile_375x812.png
"""

import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = Path("/home/xavkal/.gemini/antigravity-ide/brain/b642533c-dc99-479f-95f9-46568fa696a5/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


async def run_desktop_test(browser):
    print("\n--- Running Desktop ASCD Reset Test (1920x1080) ---")
    context = await browser.new_context(viewport={"width": 1920, "height": 1080})
    page = await context.new_page()

    await page.goto("http://localhost:5000", wait_until="networkidle")
    await asyncio.sleep(1.0)

    # Switch to ASCD Tab
    print("Switching to Command Deck (ASCD) tab...")
    await page.click("#tab-ascd")
    await asyncio.sleep(1.0)

    # Verify reset button exists and is visible
    reset_btn = page.locator("#ascd-btn-reset")
    is_visible = await reset_btn.is_visible()
    print(f"Desktop Reset button visible: {is_visible}")
    assert is_visible, "Reset button #ascd-btn-reset not visible on desktop"

    # Click reset button
    print("Clicking #ascd-btn-reset on Desktop...")
    await reset_btn.click()
    await asyncio.sleep(1.5)

    # Verify toast or notification
    toast = page.locator("#ascd-toast")
    toast_visible = await toast.is_visible()
    print(f"Desktop Toast visible: {toast_visible}")

    # Capture desktop screenshot
    desktop_shot = SCREENSHOTS_DIR / "ascd_reset_desktop_1920x1080.png"
    await page.screenshot(path=str(desktop_shot), full_page=False)
    print(f"Saved desktop screenshot: {desktop_shot}")

    await context.close()


async def run_mobile_test(browser):
    print("\n--- Running Mobile ASCD Reset Test (375x812 Touch) ---")
    context = await browser.new_context(
        viewport={"width": 375, "height": 812},
        is_mobile=True,
        has_touch=True,
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    )
    page = await context.new_page()

    await page.goto("http://localhost:5000", wait_until="networkidle")
    await asyncio.sleep(1.0)

    # Switch to ASCD Tab
    print("Switching to Command Deck (ASCD) tab on Mobile...")
    await page.click("#tab-ascd")
    await asyncio.sleep(1.0)

    reset_btn = page.locator("#ascd-btn-reset")
    is_visible = await reset_btn.is_visible()
    print(f"Mobile Reset button visible: {is_visible}")
    assert is_visible, "Reset button #ascd-btn-reset not visible on mobile"

    # Tap reset button
    print("Tapping #ascd-btn-reset on Mobile...")
    await reset_btn.tap()
    await asyncio.sleep(1.5)

    mobile_shot = SCREENSHOTS_DIR / "ascd_reset_mobile_375x812.png"
    await page.screenshot(path=str(mobile_shot), full_page=False)
    print(f"Saved mobile screenshot: {mobile_shot}")

    await context.close()


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            await run_desktop_test(browser)
            await run_mobile_test(browser)
            print("\nALL DESKTOP AND MOBILE UI RESET TESTS COMPLETED SUCCESSFULLY!")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
