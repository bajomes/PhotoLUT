from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright


PIXEL = (
    "data:image/gif;base64,"
    "R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="
)


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
        page = browser.new_page(accept_downloads=True)

        def route_requests(route):
            nonlocal outputs
            request = route.request
            parsed = urlparse(request.url)

            if parsed.path == "/api/preview":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"before": PIXEL, "graded": PIXEL}),
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
            elif parsed.path == "/files/job123/all.zip":
                archive_format = parse_qs(parsed.query).get("format", [""])[0]
                requested_formats.append(archive_format)
                route.fulfill(
                    status=200,
                    content_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="photolut.zip"'},
                    body=b"PK\\x05\\x06" + b"\\x00" * 18,
                )
            else:
                route.continue_()

        page.route("**/*", route_requests)

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
        process_button.click()
        expect(page.locator(".result-card")).to_have_count(2, timeout=10_000)

        page.locator('.result-card[data-output-id="0"] .remove-result').click()
        expect(page.locator(".result-card")).to_have_count(1)
        expect(page.locator("#summary")).to_contain_text("1 photos available for export")

        for archive_format in ("jpeg", "tiff", "all"):
            page.locator("#dlZip").click()
            expect(page.locator("#downloadPicker")).to_be_visible()
            with page.expect_download():
                page.locator(f'[data-format="{archive_format}"]').click()

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
