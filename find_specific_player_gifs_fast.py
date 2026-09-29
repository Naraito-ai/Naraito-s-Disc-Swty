# -*- coding: utf-8 -*-
"""
find_specific_player_gifs_fast.py - Async search for targeted player GIFs on Tenor
"""
import ssl
import json
import re
import asyncio
import aiohttp
from typing import Dict, Any, List

TARGET_PLAYERS = [
    {"id": "dm-timduncan-99", "name": "Tim Duncan", "queries": ["tim-duncan-dunk-spurs", "tim-duncan-basketball", "tim-duncan-block-spurs", "tim-duncan-spurs"]},
    {"id": "go-davidrobinson-98", "name": "David Robinson", "queries": ["david-robinson-spurs-dunk", "david-robinson-admiral-spurs", "david-robinson-dunk", "david-robinson-spurs"]},
    {"id": "go-mosesmalone-98", "name": "Moses Malone", "queries": ["moses-malone-sixers", "moses-malone-nba", "moses-malone-76ers-dunk", "moses-malone-basketball"]},
    {"id": "go-karlmalone-98", "name": "Karl Malone", "queries": ["karl-malone-dunk-jazz", "karl-malone-mailman-dunk", "karl-malone-jazz", "karl-malone-slam"]},
    {"id": "go-oscarrobertson-98", "name": "Oscar Robertson", "queries": ["oscar-robertson-bucks", "oscar-robertson-nba", "oscar-robertson-basketball", "oscar-robertson-royals"]},
    {"id": "go-elginbaylor-98", "name": "Elgin Baylor", "queries": ["elgin-baylor-lakers", "elgin-baylor-nba", "elgin-baylor-basketball", "elgin-baylor-highlights"]},
    {"id": "go-waltfrazier-98", "name": "Walt Frazier", "queries": ["walt-frazier-knicks-pass", "walt-clyde-frazier", "walt-frazier-basketball", "walt-frazier-knicks"]},
    {"id": "go-rickbarry-97", "name": "Rick Barry", "queries": ["rick-barry-underhand-freethrow", "rick-barry-warriors", "rick-barry-nba", "rick-barry-basketball"]},
    {"id": "go-willisreed-97", "name": "Willis Reed", "queries": ["willis-reed-knicks-championship", "willis-reed-game-7", "willis-reed-knicks", "willis-reed-tunnel"]},
    {"id": "go-bobcousy-97", "name": "Bob Cousy", "queries": ["bob-cousy-celtics-crossover", "bob-cousy-pass", "bob-cousy-basketball", "bob-cousy-celtics"]},
    {"id": "go-reggiemiller-97", "name": "Reggie Miller", "queries": ["reggie-miller-choke-knicks", "reggie-miller-pacers-3pt", "reggie-miller-8-points", "reggie-miller-pacers"]},
    {"id": "go-tonyparker-97", "name": "Tony Parker", "queries": ["tony-parker-spurs-teardrop", "tony-parker-floater-spurs", "tony-parker-crossover-spurs", "tony-parker-spurs"]},
    {"id": "go-alonzomourning-97", "name": "Alonzo Mourning", "queries": ["alonzo-mourning-block-heat", "alonzo-mourning-dunk-heat", "alonzo-mourning-heat", "alonzo-mourning-dunk"]},
    {"id": "go-paulgeorge-98", "name": "Paul George", "queries": ["paul-george-360-windmill-dunk", "paul-george-dunk-pacers", "paul-george-clippers-dunk", "paul-george-dunk"]},
    {"id": "go-jasonkidd-98", "name": "Jason Kidd", "queries": ["jason-kidd-nets-pass", "jason-kidd-fastbreak-assist", "jason-kidd-dallas-pass", "jason-kidd-nets"]}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

sem = asyncio.Semaphore(15)

async def check_url(session: aiohttp.ClientSession, url: str):
    try:
        async with sem:
            async with session.get(url, headers=HEADERS, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    return True, len(data)
    except Exception:
        pass
    return False, 0

async def search_query(session: aiohttp.ClientSession, query: str):
    url = f"https://tenor.com/search/{query}-gifs"
    try:
        async with sem:
            async with session.get(url, headers=HEADERS, timeout=5) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    matches = re.findall(r'https://(?:media\d*\.tenor\.com(?:/m)?|c\.tenor\.com)/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)\.gif', html)
                    res = []
                    for mid, s in matches:
                        clean_mid = mid
                        if clean_mid.endswith(('AAAAC', 'AAAAd', 'AAAAP', 'AAAC', 'AAAd')):
                            clean_mid = re.sub(r'AAAA[A-Z0-9]$|AAA[A-Z0-9]$', 'AAAAM', clean_mid)
                        elif not clean_mid.endswith('AAAAM'):
                            clean_mid = clean_mid + 'AAAAM' if not clean_mid.endswith('M') else clean_mid
                        res.append({"url": f"https://media.tenor.com/{clean_mid}/{s}.gif", "slug": s})
                    return res
    except Exception:
        pass
    return []

async def process_player(session: aiohttp.ClientSession, player: Dict[str, Any]):
    found = []
    seen = set()
    for q in player["queries"]:
        items = await search_query(session, q)
        for it in items:
            if it["url"] not in seen:
                seen.add(it["url"])
                found.append(it)

    verified = []
    for item in found[:10]:
        ok, sz = await check_url(session, item["url"])
        if ok and sz < 5 * 1024 * 1024:
            verified.append({
                "url": item["url"],
                "slug": item["slug"],
                "size": sz
            })

    return {
        "id": player["id"],
        "name": player["name"],
        "verified": verified
    }

async def main():
    connector = aiohttp.TCPConnector(ssl=False, limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [process_player(session, p) for p in TARGET_PLAYERS]
        results = await asyncio.gather(*tasks)

        out = {}
        for r in results:
            out[r["id"]] = r

        with open("targeted_player_gifs.json", "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)

        print(f"Targeted search finished for {len(results)} players.")

if __name__ == "__main__":
    asyncio.run(main())
