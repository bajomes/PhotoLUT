from playwright.sync_api import sync_playwright


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route(
            "**/api/ultrahdr/export",
            lambda route: route.fulfill(
                status=200,
                body=b"fake-ultrahdr-jpeg",
                content_type="image/jpeg",
                headers={"X-PhotoLUT-Gain-Map-Verified": "true"},
            ),
        )
        page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
        assert page.get_by_text("Ultra HDR photo export").is_visible()
        assert page.locator("#ultraHdrTiff").count() == 1
        assert page.locator("#ultraHdrQuality").input_value() == "95"
        assert page.locator("#ultraHdrBoost").input_value() == "4"
        page.locator("#ultraHdrTiff").set_input_files({
            "name": "browser-fixture.tiff",
            "mimeType": "image/tiff",
            "buffer": b"synthetic-tiff",
        })
        button = page.get_by_role("button", name="Export Ultra HDR JPEG")
        assert button.is_enabled()
        button.click()
        page.get_by_text("Export complete. Gain map verified; download the JPEG when ready.").wait_for()
        assert page.get_by_role("link", name="Download Ultra HDR JPEG").is_visible()
        browser.close()


if __name__ == "__main__":
    main()
