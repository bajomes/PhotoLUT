#!/usr/bin/env python3
"""Report license metadata for every distribution pinned in a requirements lock."""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import re
import sys
from pathlib import Path


def parse_lock(path: Path) -> list[tuple[str, str]]:
    packages: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^;\s]+)", line)
        if not match:
            raise ValueError(f"Unsupported or unpinned lock entry in {path}: {line}")
        packages.append((match.group(1), match.group(2)))
    return packages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", default="requirements-dev.lock")
    args = parser.parse_args()
    lock = Path(args.lock)
    missing: list[str] = []
    rows: list[tuple[str, str, str, str]] = []
    for name, version in parse_lock(lock):
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            missing.append(f"{name}=={version}: not installed")
            continue
        actual = dist.version
        if actual != version:
            missing.append(f"{name}: lock={version}, installed={actual}")
        md = dist.metadata
        license_value = (md.get("License-Expression") or md.get("License") or "").strip()
        classifiers = "; ".join(
            value.removeprefix("License :: ")
            for value in md.get_all("Classifier", [])
            if value.startswith("License :: ")
        )
        rows.append((name, actual, license_value or "NOT DECLARED", classifiers or "NOT DECLARED"))
    print("# Dependency license metadata inventory")
    print()
    print(f"Source lock: `{lock.as_posix()}`")
    print()
    print("| Distribution | Version | License metadata | License classifiers |")
    print("|---|---:|---|---|")
    for name, version, license_value, classifiers in rows:
        license_cell = license_value.replace("|", "/")
        classifier_cell = classifiers.replace("|", "/")
        print(f"| {name} | {version} | {license_cell} | {classifier_cell} |")
    print()
    if missing:
        print("## Lock/install mismatches")
        for item in missing:
            print(f"- {item}")
        return 2
    undeclared = [row[0] for row in rows if row[2] == "NOT DECLARED" and row[3] == "NOT DECLARED"]
    print(f"Inventory count: {len(rows)} distributions.")
    print("Packages with no declared license metadata: " + (", ".join(undeclared) if undeclared else "none"))
    print("This report is metadata discovery only; legal compatibility and notice obligations require human review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
