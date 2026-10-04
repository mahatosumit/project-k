"""Dependency vulnerability audit.

pip-audit cannot run in this environment because the bundled Python lacks the
``venv`` module, so this script performs the same check directly: for each pinned
package it asks the OSV database for known advisories affecting that exact
version.

Usage:  python scripts/audit_dependencies.py [requirements.txt]
Exit code is non-zero when any advisory is found, so CI can gate on it.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
PIN_RE = re.compile(r"^\s*([A-Za-z0-9._-]+)==([A-Za-z0-9._+!-]+)\s*$")


def parse_pins(path: Path) -> list[tuple[str, str]]:
    pins: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0]
        match = PIN_RE.match(line)
        if match:
            pins.append((match.group(1), match.group(2)))
    return pins


def query_osv(pins: list[tuple[str, str]]) -> dict:
    body = json.dumps(
        {"queries": [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v} for n, v in pins]}
    ).encode()
    request = urllib.request.Request(
        OSV_BATCH, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https host
        return json.loads(response.read().decode())


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "requirements.txt")
    pins = parse_pins(target)
    if not pins:
        print(f"no pinned requirements found in {target}")
        return 1

    print(f"auditing {len(pins)} pinned packages against the OSV database\n")
    try:
        results = query_osv(pins)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"could not reach OSV ({type(exc).__name__}); rerun when the network is available")
        return 2

    found = 0
    for (name, version), result in zip(pins, results.get("results", []), strict=False):
        vulns = result.get("vulns") or []
        if not vulns:
            continue
        found += len(vulns)
        for vuln in vulns:
            severity = ""
            for entry in vuln.get("severity") or []:
                severity = entry.get("score", "")
                break
            print(f"  {name}=={version}: {vuln.get('id')} {severity}")
            summary = (vuln.get("summary") or "").strip()
            if summary:
                print(f"      {summary[:160]}")

    if found:
        print(f"\nFAIL: {found} advisories affect the pinned set. Resolve before release.")
        return 1
    print("PASS: no known advisories affect the pinned dependency set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
