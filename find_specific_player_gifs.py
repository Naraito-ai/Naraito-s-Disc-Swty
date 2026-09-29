# -*- coding: utf-8 -*-
"""
find_specific_player_gifs.py - Search Tenor for specific basketball players with targeted terms
"""
import ssl
import json
import re
import urllib.request
import urllib.parse
from typing import Dict, Any, List

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

TARGET_PLAYERS = [
    {"id": "dm-timduncan-99", "name": "Tim Duncan", "queries": ["tim-duncan-dunk-spurs", "tim-duncan-basketball-highlights", "tim-duncan-block-spurs", "tim-duncan-spurs"]},
    {"id": "go-davidrobinson-98", "name": "David Robinson", "queries": ["david-robinson-spurs-dunk", "david-robinson-admiral-spurs", "david-robinson-dunk"]},
    {"id": "go-mosesmalone-98", "name": "Moses Malone", "queries": ["moses-malone-sixers", "moses-malone-nba", "moses-malone-basketball", "moses-malone-76ers-dunk"]},
    {"id": "go-karlmalone-98", "name": "Karl Malone", "queries": ["karl-malone-dunk-jazz", "karl-malone-mailman-dunk", "karl-malone-jazz-highlights"]},
    {"id": "go-oscarrobertson-98", "name": "Oscar Robertson", "queries": ["oscar-robertson-bucks-highlights", "oscar-robertson-nba", "oscar-robertson-pass-basketball"]},
    {"id": "go-elginbaylor-98", "name": "Elgin Baylor", "queries": ["elgin-baylor-lakers-highlights", "elgin-baylor-nba", "elgin-baylor-basketball"]},
    {"id": "go-waltfrazier-98", "name": "Walt Frazier", "queries": ["walt-frazier-knicks-pass", "walt-clyde-frazier-knicks", "walt-frazier-highlights"]},
    {"id": "go-rickbarry-97", "name": "Rick Barry", "queries": ["rick-barry-underhand-freethrow", "rick-barry-warriors-highlights", "rick-barry-nba"]},
    {"id": "go-willisreed-97", "name": "Willis Reed", "queries": ["willis-reed-knicks-championship", "willis-reed-game-7", "willis-reed-highlights"]},
    {"id": "go-bobcousy-97", "name": "Bob Cousy", "queries": ["bob-cousy-celtics-crossover", "bob-cousy-pass-highlights", "bob-cousy-basketball"]},
    {"id": "go-reggiemiller-97", "name": "Reggie Miller", "queries": ["reggie-miller-choke-knicks", "reggie-miller-pacers-3pt", "reggie-miller-8-points"]},
    {"id": "go-tonyparker-97", "name": "Tony Parker", "queries": ["tony-parker-spurs-teardrop", "tony-parker-floater-spurs", "tony-parker-crossover-spurs"]},
    {"id": "go-alonzomourning-97", "name": "Alonzo Mourning", "queries": ["alonzo-mourning-block-heat", "alonzo-mourning-dunk-heat", "alonzo-mourning-heat-highlights"]},
    {"id": "go-paulgeorge-98", "name": "Paul George", "queries": ["paul-george-360-windmill-dunk", "paul-george-dunk-pacers", "paul-george-clippers-dunk"]},
    {"id": "go-jasonkidd-98", "name": "Jason Kidd", "queries": ["jason-kidd-nets-pass", "jason-kidd-fastbreak-assist", "jason-kidd-dallas-pass"]}
]

def search_tenor(query: str):
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', query).strip('-').lower()
    url = f"https://tenor.com/search/{slug}-gifs"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        matches = re.findall(r'https://(?:media\d*\.tenor\.com(?:/m)?|c\.tenor\.com)/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)\.gif', html)
        res = []
        seen = set()
        for mid, s in matches:
            clean_mid = mid
            if clean_mid.endswith(('AAAAC', 'AAAAd', 'AAAAP', 'AAAC', 'AAAd')):
                clean_mid = re.sub(r'AAAA[A-Z0-9]$|AAA[A-Z0-9]$', 'AAAAM', clean_mid)
            elif not clean_mid.endswith('AAAAM'):
                clean_mid = clean_mid + 'AAAAM' if not clean_mid.endswith('M') else clean_mid

            if clean_mid in seen: continue
            seen.add(clean_mid)
            res.append({"url": f"https://media.tenor.com/{clean_mid}/{s}.gif", "slug": s})
        return res
    except Exception as e:
        return []

def main():
    for p in TARGET_PLAYERS:
        print(f"\n====================\nSearching for {p['name']} ({p['id']})...")
        found = []
        for q in p["queries"]:
            r = search_tenor(q)
            for item in r:
                if item not in found:
                    found.append(item)
        print(f"Total results: {len(found)}")
        for idx, f in enumerate(found[:8]):
            print(f"  {idx+1}. {f['url']} (slug: {f['slug']})")

if __name__ == "__main__":
    main()
