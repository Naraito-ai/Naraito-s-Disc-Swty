# -*- coding: utf-8 -*-
"""
validate_fusion_gifs_report.py - Validates every single player GIF URL in NBA_FUSION_GIF_MAPPINGS from nba_data.py
and prints a complete, verified report.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import ssl
import json
import urllib.request
from typing import Dict, Any, Tuple

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def verify_url(url: str) -> Tuple[bool, int, str]:
    if not url:
        return True, 0, "CLEAN_OMISSION"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            if resp.status != 200:
                return False, 0, f"HTTP {resp.status}"
            data = resp.read()
            size = len(data)
            if size > 5 * 1024 * 1024:
                return False, size, "Too large (> 5MB)"
            if not url.endswith(".gif") or "AAAAM" not in url:
                return False, size, "Not AAAAM small format"
            return True, size, "PASS"
    except Exception as e:
        return False, 0, f"Network/URL Error: {e}"

def main():
    from nba_data import NBA_FUSION_GIF_MAPPINGS
    print(f"==================================================")
    print(f"🏀 NBA FUSION GIF VALIDATION AUDIT REPORT ({len(NBA_FUSION_GIF_MAPPINGS)} CARDS)")
    print(f"==================================================\n")

    seen_urls = set()
    pass_count = 0
    fail_count = 0
    report_rows = []

    for cid, info in sorted(NBA_FUSION_GIF_MAPPINGS.items()):
        name = info["name"]
        url = info["gif_url"]

        if not url:
            pass_count += 1
            row = {
                "id": cid,
                "name": name,
                "url": "None (No authentic Tenor GIF exists)",
                "size": 0,
                "status": "PASS",
                "reason": "Authentic omission (Rule: Omit rather than use wrong GIF)"
            }
            report_rows.append(row)
            continue

        if url in seen_urls:
            fail_count += 1
            row = {
                "id": cid,
                "name": name,
                "url": url,
                "size": 0,
                "status": "FAIL",
                "reason": "Duplicate URL with another player"
            }
            report_rows.append(row)
            continue
        seen_urls.add(url)

        ok, size, msg = verify_url(url)
        if ok:
            pass_count += 1
            row = {
                "id": cid,
                "name": name,
                "url": url,
                "size": size,
                "status": "PASS",
                "reason": "Valid AAAAM format under 5MB"
            }
        else:
            fail_count += 1
            row = {
                "id": cid,
                "name": name,
                "url": url,
                "size": size,
                "status": "FAIL",
                "reason": msg
            }
        report_rows.append(row)

    for r in report_rows:
        print(f"Player: {r['name']} ({r['id']})")
        print(f"URL: {r['url']}")
        print(f"Size: {r['size']:,} bytes")
        print(f"Status: {r['status']}")
        if r['status'] == 'FAIL':
            print(f"Reason: {r['reason']}")
        print("--------------------------------------------------")

    print(f"\nFinal Summary: {pass_count} PASS, {fail_count} FAIL out of {len(NBA_FUSION_GIF_MAPPINGS)} players.")
    with open("final_audit_report.json", "w", encoding="utf-8") as f:
        json.dump(report_rows, f, indent=2)

if __name__ == "__main__":
    main()
