#!/usr/bin/env python3
"""Generate hash-enforced requirements locks from exact PyPI release metadata."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^;\s]+)$")


def release_hashes(name: str, version: str) -> list[str]:
    url = f"https://pypi.org/pypi/{quote(name, safe='')}/{quote(version, safe='')}/json"
    request = Request(url, headers={"User-Agent": "PhotoLUT-lock-hash-generator/1.0"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
            hashes = sorted({
                item["digests"]["sha256"]
                for item in payload.get("urls", [])
                if not item.get("yanked", False)
                and item.get("digests", {}).get("sha256")
            })
            if not hashes:
                raise ValueError(f"No non-yanked SHA-256 artifacts found for {name}=={version}")
            return hashes
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Unable to retrieve PyPI hashes for {name}=={version}: {last_error}")


def generate(source: Path, destination: Path) -> None:
    output = [
        "# Generated from PyPI JSON release digests; regenerate with scripts/generate_hashed_locks.py.",
        "--require-hashes",
        "",
    ]
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            output.append("")
            continue
        if line.startswith("#") or line.startswith("--"):
            output.append(raw)
            continue
        match = PIN.fullmatch(line)
        if not match:
            raise ValueError(f"Unsupported or unpinned requirement in {source}: {line}")
        name, version = match.groups()
        hashes = release_hashes(name, version)
        output.append(f"{name}=={version} \\")
        for index, digest in enumerate(hashes):
            suffix = " \\" if index < len(hashes) - 1 else ""
            output.append(f"    --hash=sha256:{digest}{suffix}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("locks", nargs="+", type=Path)
    args = parser.parse_args()
    for source in args.locks:
        destination = args.output_dir / source.name
        generate(source, destination)
        print(f"Generated {destination}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
