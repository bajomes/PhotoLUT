from __future__ import annotations

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    inspect_payload = {
        "filename": "sample.mp4",
        "codec": "hevc",
        "codec_profile": "Main 10",
        "width": 3840,
        "height": 2160,
        "pixel_format": "yuv420p10le",
        "bit_depth": 10,
        "frame_rate": "30/1",
        "duration_seconds": 12.0,
        "container": "mov,mp4",
        "color_transfer": "arib-std-b67",
        "color_primaries": "bt2020",
        "color_matrix": "bt2020nc",
        "color_range": "tv",
        "is_hdr": True,
        "hdr_format": "HLG",
        "hdr_metadata_complete": True,
        "hlg_metadata_complete": True,
        "dolby_vision_detected": False,
        "dolby_vision_profile": None,
        "is_4k30_or_higher": True,
        "warnings": [],
    }
    process_requests: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.add_init_script("""
            window.__photolutVideoDownloads = [];
            const nativeAnchorClick = HTMLAnchorElement.prototype.click;
            HTMLAnchorElement.prototype.click = function () {
                if (this.download && this.download.endsWith('.mp4')) {
                    window.__photolutVideoDownloads.push(this.download);
                    return;
                }
                return nativeAnchorClick.call(this);
            };
        """)

        def route_inspection(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=__import__("json").dumps(inspect_payload),
            )

        def route_processing(route):
            process_requests.append(route.request.post_data or "")
            route.fulfill(
                status=200,
                body=b"mock-video-output",
                content_type="video/mp4",
                headers={"X-PhotoLUT-Processing-Device": "NVIDIA GPU"},
            )

        page.route("**/api/video/inspect", route_inspection)
        page.route("**/api/video/process", route_processing)
        page.goto("http://127.0.0.1:8000/", wait_until="networkidle")

        page.locator("#videoInspectInput").set_input_files({
            "name": "sample.mp4",
            "mimeType": "video/mp4",
            "buffer": b"mock-video-input",
        })
        page.get_by_role("button", name="Inspect video metadata").click()
        expect(page.locator("#videoInspectResult")).to_be_visible()
        expect(page.locator("#processVideoBtn")).to_be_enabled()

        page.locator("#videoLutInput").set_input_files({
            "name": "creative.cube",
            "mimeType": "text/plain",
            "buffer": b'TITLE "Identity"\nLUT_3D_SIZE 2\n'
                      b"0 0 0\n1 0 0\n0 1 0\n1 1 0\n"
                      b"0 0 1\n1 0 1\n0 1 1\n1 1 1\n",
        })

        for profile, status_text, expected_name in (
            ("hlg", "HDR HLG/BT.2020 export complete", "sample_photolut_hdr_hlg_10bit.mp4"),
            ("rec709", "SDR BT.709 export complete", "sample_photolut_sdr_rec709_10bit.mp4"),
        ):
            page.locator("#videoLutProfile").select_option(profile)
            page.get_by_role("button", name="Apply LUT & export 10-bit video").click()
            expect(page.locator("#videoProcessStatus")).to_contain_text(status_text)
            expect(page.locator("#videoProcessStatus")).to_contain_text("NVIDIA GPU")
            expect(page.locator("#videoPreviewPanel")).to_be_visible()
            expect(page.locator("#videoBeforePreview")).to_be_visible()
            expect(page.locator("#processedVideoPreview")).to_be_visible()
            expect(page.locator("#videoCompareSeek")).to_be_visible()
            expect(page.locator("#videoComparePlay")).to_be_visible()

            assert f'name="lut_profile"\r\n\r\n{profile}' in process_requests[-1]
            page.locator("#downloadProcessedVideo").click()
            names = page.evaluate("window.__photolutVideoDownloads")
            assert names[-1] == expected_name

        assert len(process_requests) == 2
        browser.close()


if __name__ == "__main__":
    main()
