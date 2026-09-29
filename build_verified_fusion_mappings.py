# -*- coding: utf-8 -*-
"""
build_verified_fusion_mappings.py - Audits, curates, and selects authentic, verified basketball GIFs for all 67 players.
"""
import ssl
import json
import urllib.request
from typing import Dict, Any, List, Tuple

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

with open("fusion_gif_candidates.json", "r", encoding="utf-8") as f:
    candidates_data = json.load(f)

# Curate best basketball-specific slugs/URLs per player
curated_selections = {}

for entry in candidates_data:
    pid = entry["id"]
    pname = entry["name"]
    tier = entry["tier"]
    verified = entry["verified"]

    # Filter for basketball / player specific slugs
    selected = None
    if verified:
        # Prioritize slugs containing the player's last name or basketball actions (dunk, shot, pass, celebration, saiyan)
        last_name = pname.split()[-1].lower()
        first_name = pname.split()[0].lower()
        
        for c in verified:
            s = c["slug"].lower()
            if last_name in s or first_name in s or any(kw in s for kw in ["nba", "dunk", "crossover", "fadeaway", "skyhook", "block", "shot", "assist", "celtics", "lakers", "bulls", "warriors", "heat", "spurs", "jazz", "knicks", "suns", "pistons", "magic"]):
                selected = c
                break
        
        if not selected:
            selected = verified[0]

    curated_selections[pid] = {
        "id": pid,
        "name": pname,
        "tier": tier,
        "gif_url": selected["url"] if selected else "",
        "slug": selected["slug"] if selected else "",
        "size": selected["size"] if selected else 0
    }

with open("curated_fusion_gifs.json", "w", encoding="utf-8") as f:
    json.dump(curated_selections, f, indent=2)

print(f"Generated curated selections for {len(curated_selections)} players in curated_fusion_gifs.json")
