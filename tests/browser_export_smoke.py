from __future__ import annotations

import base64
import json
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


PIXEL = (
    "data:image/gif;base64,"
    "R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="
)

def _solid_pixel(color: str) -> str:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
        f'<rect width="1" height="1" fill="{color}"/></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


PREVIEW_BLACK = _solid_pixel("#000000")
PREVIEW_WHITE = _solid_pixel("#ffffff")


def _output(output_id: str, filename: str) -> dict:
    return {
        "id": output_id,
        "filename": filename,
        "metadata_preserved": True,
        "preview_before": PIXEL,
        "preview_after": PIXEL,
        "download_tiff": f"/files/job123/{filename}_lut.tiff",
        "download_jpeg": f"/files/job123/{filename}_lut.jpg",
    }


def main() -> None:
    outputs = [_output("0", "first.nef"), _output("1", "second.nef")]
    requested_formats: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()

        def route_requests(route):
            nonlocal outputs
            request = route.request
            parsed = urlparse(request.url)

            if parsed.path == "/api/preview":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"before": PREVIEW_BLACK, "graded": PREVIEW_WHITE}),
                )
            elif parsed.path == "/api/process":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"job_id": "job123"}),
                )
            elif parsed.path == "/api/jobs/job123":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({
                        "id": "job123",
                        "status": "done",
                        "progress": 100,
                        "current_file": None,
                        "total_files": 2,
                        "done_files": 2,
                        "message": "",
                        "outputs": outputs,
                    }),
                )
            elif parsed.path.startswith("/api/jobs/job123/outputs/"):
                output_id = parsed.path.rsplit("/", 1)[-1]
                outputs = [item for item in outputs if item["id"] != output_id]
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({
                        "removed": output_id,
                        "outputs": outputs,
                    }),
                )
            else:
                route.continue_()

        page.route("**/*", route_requests)
        page.add_init_script("""
            window.__photolutDownloads = [];
            const nativeAnchorClick = HTMLAnchorElement.prototype.click;
            HTMLAnchorElement.prototype.click = function () {
                if (this.href.includes("/files/job123/all.zip")) {
                    window.__photolutDownloads.push(this.href);
                    return;
                }
                return nativeAnchorClick.call(this);
            };
        """)

        page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
        page.locator("#rawInput").set_input_files([
            {"name": "first.nef", "mimeType": "image/x-nikon-nef", "buffer": b"raw-one"},
            {"name": "second.nef", "mimeType": "image/x-nikon-nef", "buffer": b"raw-two"},
        ])
        page.locator("#cubeInput").set_input_files({
            "name": "look.cube",
            "mimeType": "text/plain",
            "buffer": b"TITLE \"Identity\"\\nLUT_3D_SIZE 2\\n"
                      b"0 0 0\\n1 0 0\\n0 1 0\\n1 1 0\\n"
                      b"0 0 1\\n1 0 1\\n0 1 1\\n1 1 1\\n",
        })

        process_button = page.locator("#processBtn")
        expect(process_button).to_be_enabled(timeout=10_000)
        expect(page.locator("#previewWrap")).to_be_visible()
        page.wait_for_function("""
            const canvas = document.querySelector("#previewAfter");
            return canvas && canvas.width === 1 && canvas.height === 1;
        """)
        set_intensity = lambda value: page.locator("#intensity").evaluate(
            "(el, value) => { el.value = String(value); el.dispatchEvent(new Event('input', {bubbles:true})); }",
            value,
        )
        preview_pixel = lambda: page.locator("#previewAfter").evaluate(
            "canvas => Array.from(canvas.getContext('2d').getImageData(0, 0, 1, 1).data)"
        )
        set_intensity(0)
        assert preview_pixel() == [0, 0, 0, 255]
        set_intensity(50)
        assert preview_pixel() == [188, 188, 188, 255], (
            "50% black/white preview blend must be linear-light sRGB, not gamma-space opacity"
        )
        set_intensity(100)
        assert preview_pixel() == [255, 255, 255, 255]
        process_button.click()
        expect(page.locator(".result-card")).to_have_count(2, timeout=10_000)

        page.locator('.result-card[data-output-id="0"] .remove-result').click()
        expect(page.locator(".result-card")).to_have_count(1)
        expect(page.locator("#summary")).to_contain_text("1 photos available for export")

        for archive_format in ("jpeg", "tiff", "all"):
            page.locator("#dlZip").click()
            expect(page.locator("#downloadPicker")).to_be_visible()
            page.locator(f'[data-format="{archive_format}"]').click()
            expect(page.locator("#downloadPicker")).to_be_hidden()

        requested_formats = page.evaluate(
            "window.__photolutDownloads.map(url => new URL(url).searchParams.get('format'))"
        )
        assert requested_formats == ["jpeg", "tiff", "all"]

        page.locator('.result-card[data-output-id="1"] .remove-result').click()
        expect(page.locator(".result-card")).to_have_count(0)
        expect(page.locator("#dlZip")).to_be_hidden()
        expect(page.locator("#stageMessage")).to_have_text(
            "All export items have been removed."
        )

        browser.close()


if __name__ == "__main__":
    main()
