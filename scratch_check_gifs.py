# -*- coding: utf-8 -*-
"""
scratch_check_gifs.py - Search Tenor, validate AAAAM media URLs, check file sizes, and verify basketball relevance.
"""
import ssl
import json
import urllib.request
import urllib.parse
import re
import time
from typing import Dict, Any, List, Optional, Tuple

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def search_tenor_gifs(query: str, limit: int = 5) -> List[Dict[str, str]]:
    """Searches Tenor website for GIFs matching the query and returns direct AAAAM URLs."""
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', query).strip('-').lower()
    url = f"https://tenor.com/search/{slug}-gifs"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        # Find media URLs in HTML / Next.js data
        matches = re.findall(r'https://(?:media\d*\.tenor\.com(?:/m)?|c\.tenor\.com)/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)\.gif', html)
        results = []
        seen = set()
        for mid, slug_name in matches:
            if mid in seen:
                continue
            seen.add(mid)
            # Convert to standard AAAAM format
            clean_mid = mid
            if clean_mid.endswith(('AAAAC', 'AAAAd', 'AAAAP', 'AAAC', 'AAAd')):
                clean_mid = re.sub(r'AAAA[A-Z0-9]$|AAA[A-Z0-9]$', 'AAAAM', clean_mid)
            elif not clean_mid.endswith('AAAAM'):
                clean_mid = clean_mid + 'AAAAM' if not clean_mid.endswith('M') else clean_mid

            aaaam_url = f"https://media.tenor.com/{clean_mid}/{slug_name}.gif"
            results.append({"url": aaaam_url, "id": clean_mid, "slug": slug_name})
            if len(results) >= limit:
                break
        return results
    except Exception as e:
        print(f"Error searching Tenor for '{query}': {e}")
        return []

def verify_gif_url(url: str) -> Tuple[bool, int, str]:
    """Verifies that a GIF URL returns HTTP 200, valid image/gif content, and is under 5MB."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            if resp.status != 200:
                return False, 0, f"HTTP {resp.status}"
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
            size = len(data)
            if size > 5 * 1024 * 1024:
                return False, size, f"Too large ({size / (1024*1024):.2f}MB > 5MB)"
            if not (data.startswith(b'GIF87a') or data.startswith(b'GIF89a') or "image" in content_type.lower()):
                return False, size, "Invalid GIF format"
            return True, size, "OK"
    except Exception as e:
        return False, 0, str(e)


if __name__ == "__main__":
    test_q = "larry bird celtics"
    print(f"Searching for '{test_q}'...")
    res = search_tenor_gifs(test_q, limit=5)
    for r in res:
        ok, sz, msg = verify_gif_url(r["url"])
        print(f"  {r['url']} -> {sz} bytes (Valid: {ok}, {msg})")
