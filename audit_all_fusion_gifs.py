# -*- coding: utf-8 -*-
"""
audit_all_fusion_gifs.py - Comprehensive audit and replacement search for all 67 fusion GIFs
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

def search_tenor_candidates(search_terms: List[str], limit_per_term: int = 4) -> List[Dict[str, Any]]:
    """Searches Tenor for multiple query terms and returns unique verified candidates."""
    candidates = []
    seen_ids = set()

    for query in search_terms:
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', query).strip('-').lower()
        url = f"https://tenor.com/search/{slug}-gifs"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                html = resp.read().decode('utf-8', errors='ignore')

            matches = re.findall(r'https://(?:media\d*\.tenor\.com(?:/m)?|c\.tenor\.com)/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)\.gif', html)
            for mid, slug_name in matches:
                clean_mid = mid
                if clean_mid.endswith(('AAAAC', 'AAAAd', 'AAAAP', 'AAAC', 'AAAd')):
                    clean_mid = re.sub(r'AAAA[A-Z0-9]$|AAA[A-Z0-9]$', 'AAAAM', clean_mid)
                elif not clean_mid.endswith('AAAAM'):
                    clean_mid = clean_mid + 'AAAAM' if not clean_mid.endswith('M') else clean_mid

                if clean_mid in seen_ids:
                    continue
                seen_ids.add(clean_mid)

                aaaam_url = f"https://media.tenor.com/{clean_mid}/{slug_name}.gif"
                ok, size, msg = verify_gif_url(aaaam_url)
                if ok:
                    candidates.append({
                        "url": aaaam_url,
                        "slug": slug_name,
                        "size": size,
                        "term": query
                    })
                    if len(candidates) >= 6:
                        break
        except Exception as e:
            continue

    return candidates


PLAYERS_TO_AUDIT = [
    # Dark Matter (15)
    {"id": "dm-jordan-99", "name": "Michael Jordan", "tier": "Dark Matter (99)", "search": ["michael jordan dunk", "michael jordan bulls saiyan", "jordan shrug"]},
    {"id": "dm-kobe-99", "name": "Kobe Bryant", "tier": "Dark Matter (99)", "search": ["kobe bryant saiyan", "kobe dunk lakers", "kobe mamba celebration"]},
    {"id": "dm-lebron-99", "name": "LeBron James", "tier": "Dark Matter (99)", "search": ["lebron james dunk", "lebron silencer", "lebron cavs celebration"]},
    {"id": "dm-curry-99", "name": "Stephen Curry", "tier": "Dark Matter (99)", "search": ["stephen curry night night", "steph curry 3pt shimmy", "curry warriors celebration"]},
    {"id": "dm-shaq-99", "name": "Shaquille O'Neal", "tier": "Dark Matter (99)", "search": ["shaq dunk lakers", "shaquille oneal dunk", "shaq breaking backboard"]},
    {"id": "dm-kd-99", "name": "Kevin Durant", "tier": "Dark Matter (99)", "search": ["kevin durant dunk", "kevin durant warriors celebration", "kevin durant clutch"]},
    {"id": "dm-giannis-99", "name": "Giannis Antetokounmpo", "tier": "Dark Matter (99)", "search": ["giannis antetokounmpo dunk", "giannis bucks mean mug", "giannis celebration"]},
    {"id": "dm-magic-99", "name": "Magic Johnson", "tier": "Dark Matter (99)", "search": ["magic johnson no look pass", "magic johnson lakers celebration", "magic johnson showtime"]},
    {"id": "dm-bird-99", "name": "Larry Bird", "tier": "Dark Matter (99)", "search": ["larry bird larry legend", "larry bird 3pt contest", "larry bird celtics celebration"]},
    {"id": "dm-kareemabduljabbar-99", "name": "Kareem Abdul-Jabbar", "tier": "Dark Matter (99)", "search": ["kareem abdul jabbar skyhook", "kareem skyhook lakers", "kareem abdul jabbar basketball"]},
    {"id": "dm-wiltchamberlain-99", "name": "Wilt Chamberlain", "tier": "Dark Matter (99)", "search": ["wilt chamberlain dunk", "wilt chamberlain lakers", "wilt chamberlain 100"]},
    {"id": "dm-billrussell-99", "name": "Bill Russell", "tier": "Dark Matter (99)", "search": ["bill russell celtics block", "bill russell celtics champion", "bill russell nba"]},
    {"id": "dm-timduncan-99", "name": "Tim Duncan", "tier": "Dark Matter (99)", "search": ["tim duncan spurs dunk", "tim duncan block", "tim duncan spurs celebration"]},
    {"id": "dm-hakeemolajuwon-99", "name": "Hakeem Olajuwon", "tier": "Dark Matter (99)", "search": ["hakeem olajuwon dream shake", "hakeem olajuwon block", "hakeem rockets"]},
    {"id": "dm-wemby-99", "name": "Victor Wembanyama", "tier": "Dark Matter (99)", "search": ["victor wembanyama dunk", "wemby spurs dunk", "victor wembanyama block"]},

    # Galaxy Opal 98 (29)
    {"id": "go-luka-98", "name": "Luka Doncic", "tier": "Galaxy Opal (98)", "search": ["luka doncic step back", "luka doncic mavericks clutch", "luka doncic celebration"]},
    {"id": "go-jokic-98", "name": "Nikola Jokic", "tier": "Galaxy Opal (98)", "search": ["nikola jokic pass", "nikola jokic nuggets dunk", "nikola jokic celebration"]},
    {"id": "go-embiid-98", "name": "Joel Embiid", "tier": "Galaxy Opal (98)", "search": ["joel embiid dunk", "joel embiid 76ers airplane", "joel embiid celebration"]},
    {"id": "go-tatum-98", "name": "Jayson Tatum", "tier": "Galaxy Opal (98)", "search": ["jayson tatum dunk", "jayson tatum celtics clutch", "jayson tatum kissing ring"]},
    {"id": "go-tmac-98", "name": "Tracy McGrady", "tier": "Galaxy Opal (98)", "search": ["tracy mcgrady dunk", "tracy mcgrady 13 points in 35 seconds", "tmac rockets"]},
    {"id": "go-iverson-97", "name": "Allen Iverson", "tier": "Galaxy Opal (98/97)", "search": ["allen iverson crossover", "allen iverson step over tyronn lue", "allen iverson celebration"]},
    {"id": "go-dwyanewade-98", "name": "Dwyane Wade", "tier": "Galaxy Opal (98)", "search": ["dwyane wade dunk", "dwyane wade this is my house", "dwyane wade heat celebration"]},
    {"id": "go-kevingarnett-98", "name": "Kevin Garnett", "tier": "Galaxy Opal (98)", "search": ["kevin garnett anything is possible", "kevin garnett dunk", "kevin garnett celtics intense"]},
    {"id": "go-dirknowitzki-98", "name": "Dirk Nowitzki", "tier": "Galaxy Opal (98)", "search": ["dirk nowitzki fadeaway", "dirk nowitzki mavericks champion", "dirk nowitzki celebration"]},
    {"id": "go-charlesbarkley-98", "name": "Charles Barkley", "tier": "Galaxy Opal (98)", "search": ["charles barkley dunk", "charles barkley suns dunk", "charles barkley 76ers"]},
    {"id": "go-scottiepippen-98", "name": "Scottie Pippen", "tier": "Galaxy Opal (98)", "search": ["scottie pippen dunk ewing", "scottie pippen bulls dunk", "scottie pippen celebration"]},
    {"id": "go-davidrobinson-98", "name": "David Robinson", "tier": "Galaxy Opal (98)", "search": ["david robinson dunk", "david robinson spurs block", "david robinson admiral"]},
    {"id": "go-mosesmalone-98", "name": "Moses Malone", "tier": "Galaxy Opal (98)", "search": ["moses malone 76ers dunk", "moses malone basketball", "moses malone rebound"]},
    {"id": "go-juliuserving-98", "name": "Julius Erving", "tier": "Galaxy Opal (98)", "search": ["julius erving dunk", "dr j cradle dunk", "dr j behind the backboard"]},
    {"id": "go-johnstockton-98", "name": "John Stockton", "tier": "Galaxy Opal (98)", "search": ["john stockton assist", "john stockton jazz pass", "john stockton celebration"]},
    {"id": "go-karlmalone-98", "name": "Karl Malone", "tier": "Galaxy Opal (98)", "search": ["karl malone dunk", "karl malone jazz dunk", "karl malone mailman"]},
    {"id": "go-clydedrexler-98", "name": "Clyde Drexler", "tier": "Galaxy Opal (98)", "search": ["clyde drexler dunk", "clyde drexler glide", "clyde drexler blazers"]},
    {"id": "go-patrickewing-98", "name": "Patrick Ewing", "tier": "Galaxy Opal (98)", "search": ["patrick ewing dunk", "patrick ewing knicks dunk", "patrick ewing celebration"]},
    {"id": "go-oscarrobertson-98", "name": "Oscar Robertson", "tier": "Galaxy Opal (98)", "search": ["oscar robertson basketball", "oscar robertson bucks", "oscar robertson royals"]},
    {"id": "go-jerrywest-98", "name": "Jerry West", "tier": "Galaxy Opal (98)", "search": ["jerry west lakers shot", "jerry west lakers clutch", "jerry west basketball"]},
    {"id": "go-elginbaylor-98", "name": "Elgin Baylor", "tier": "Galaxy Opal (98)", "search": ["elgin baylor lakers", "elgin baylor dunk", "elgin baylor basketball"]},
    {"id": "go-waltfrazier-98", "name": "Walt Frazier", "tier": "Galaxy Opal (98)", "search": ["walt frazier knicks", "walt frazier basketball pass", "walt clyde frazier"]},
    {"id": "go-stevenash-98", "name": "Steve Nash", "tier": "Galaxy Opal (98)", "search": ["steve nash suns pass", "steve nash assist", "steve nash suns celebration"]},
    {"id": "go-jasonkidd-98", "name": "Jason Kidd", "tier": "Galaxy Opal (98)", "search": ["jason kidd nets pass", "jason kidd assist", "jason kidd mavericks pass"]},
    {"id": "go-isiahthomas-98", "name": "Isiah Thomas", "tier": "Galaxy Opal (98)", "search": ["isiah thomas pistons layup", "isiah thomas pistons celebration", "isiah thomas basketball"]},
    {"id": "go-dominiquewilkins-98", "name": "Dominique Wilkins", "tier": "Galaxy Opal (98)", "search": ["dominique wilkins windmill dunk", "dominique wilkins dunk", "dominique wilkins hawks"]},
    {"id": "go-damianlillard-98", "name": "Damian Lillard", "tier": "Galaxy Opal (98)", "search": ["damian lillard wave goodbye", "dame time celebration", "damian lillard 3pt"]},
    {"id": "go-kyrieirving-98", "name": "Kyrie Irving", "tier": "Galaxy Opal (98)", "search": ["kyrie irving handles", "kyrie irving layup", "kyrie irving 2016 finals shot"]},
    {"id": "go-paulgeorge-98", "name": "Paul George", "tier": "Galaxy Opal (98)", "search": ["paul george 360 windmill dunk", "paul george pacers dunk", "paul george clippers dunk"]},

    # Galaxy Opal 97 (23)
    {"id": "go-ad-97", "name": "Anthony Davis", "tier": "Galaxy Opal (97)", "search": ["anthony davis dunk", "anthony davis lakers block", "anthony davis kobe game winner"]},
    {"id": "go-kawhi-97", "name": "Kawhi Leonard", "tier": "Galaxy Opal (97)", "search": ["kawhi leonard the shot", "kawhi leonard dunk", "kawhi leonard raptors celebration"]},
    {"id": "go-butler-97", "name": "Jimmy Butler", "tier": "Galaxy Opal (97)", "search": ["jimmy butler heat celebration", "jimmy butler dunk", "jimmy butler clutch"]},
    {"id": "go-jamesharden-97", "name": "James Harden", "tier": "Galaxy Opal (97)", "search": ["james harden step back", "james harden rockets dunk", "james harden stir the pot"]},
    {"id": "go-russellwestbrook-97", "name": "Russell Westbrook", "tier": "Galaxy Opal (97)", "search": ["russell westbrook rock the baby", "russell westbrook ferocious dunk", "westbrook thunder dunk"]},
    {"id": "go-chrispaul-97", "name": "Chris Paul", "tier": "Galaxy Opal (97)", "search": ["chris paul clutch", "chris paul assist", "chris paul clippers celebration"]},
    {"id": "go-carmeloanthony-97", "name": "Carmelo Anthony", "tier": "Galaxy Opal (97)", "search": ["carmelo anthony three to the dome", "carmelo anthony knicks clutch", "melo dunk"]},
    {"id": "go-vincecarter-97", "name": "Vince Carter", "tier": "Galaxy Opal (97)", "search": ["vince carter dunk contest 360", "vince carter raptors dunk", "vince carter it's over"]},
    {"id": "go-rayallen-97", "name": "Ray Allen", "tier": "Galaxy Opal (97)", "search": ["ray allen game 6 3 pointer", "ray allen celtics 3pt", "ray allen shot"]},
    {"id": "go-reggiemiller-97", "name": "Reggie Miller", "tier": "Galaxy Opal (97)", "search": ["reggie miller 8 points 9 seconds", "reggie miller choke sign", "reggie miller pacers clutch"]},
    {"id": "go-paulpierce-97", "name": "Paul Pierce", "tier": "Galaxy Opal (97)", "search": ["paul pierce celtics clutch", "paul pierce the truth celebration", "paul pierce shot"]},
    {"id": "go-garypayton-97", "name": "Gary Payton", "tier": "Galaxy Opal (97)", "search": ["gary payton sonics alley oop", "gary payton trash talk sonics", "gary payton glove"]},
    {"id": "go-dwighthoward-97", "name": "Dwight Howard", "tier": "Galaxy Opal (97)", "search": ["dwight howard superman dunk", "dwight howard magic block", "dwight howard dunk contest"]},
    {"id": "go-alonzomourning-97", "name": "Alonzo Mourning", "tier": "Galaxy Opal (97)", "search": ["alonzo mourning block heat", "alonzo mourning dunk", "alonzo mourning heat celebration"]},
    {"id": "go-dikembemutombo-97", "name": "Dikembe Mutombo", "tier": "Galaxy Opal (97)", "search": ["dikembe mutombo finger wag", "dikembe mutombo block", "dikembe mutombo celebration"]},
    {"id": "go-granthill-97", "name": "Grant Hill", "tier": "Galaxy Opal (97)", "search": ["grant hill pistons dunk", "grant hill crossover", "grant hill dunk"]},
    {"id": "go-tonyparker-97", "name": "Tony Parker", "tier": "Galaxy Opal (97)", "search": ["tony parker spurs teardrop", "tony parker floater", "tony parker spurs celebration"]},
    {"id": "go-timhardaway-97", "name": "Tim Hardaway", "tier": "Galaxy Opal (97)", "search": ["tim hardaway killer crossover", "tim hardaway warriors crossover", "tim hardaway heat"]},
    {"id": "go-petemaravich-97", "name": "Pete Maravich", "tier": "Galaxy Opal (97)", "search": ["pete maravich behind the back pass", "pistol pete maravich pass", "pistol pete highlights"]},
    {"id": "go-willisreed-97", "name": "Willis Reed", "tier": "Galaxy Opal (97)", "search": ["willis reed knicks finals", "willis reed tunnel", "willis reed knicks"]},
    {"id": "go-bobcousy-97", "name": "Bob Cousy", "tier": "Galaxy Opal (97)", "search": ["bob cousy celtics pass", "bob cousy behind the back pass", "bob cousy basketball"]},
    {"id": "go-rickbarry-97", "name": "Rick Barry", "tier": "Galaxy Opal (97)", "search": ["rick barry warriors underhand", "rick barry free throw", "rick barry warriors"]},
    {"id": "go-donovanmitchell-97", "name": "Donovan Mitchell", "tier": "Galaxy Opal (97)", "search": ["donovan mitchell dunk", "donovan mitchell cavs clutch", "donovan mitchell jazz dunk"]}
]

def main():
    print(f"Auditing Tenor GIFs for {len(PLAYERS_TO_AUDIT)} players...")
    from nba_data import NBA_FUSION_GIF_MAPPINGS

    verified_mappings = {}

    for p in PLAYERS_TO_AUDIT:
        pid = p["id"]
        pname = p["name"]
        curr = NBA_FUSION_GIF_MAPPINGS.get(pid, {})
        curr_url = curr.get("gif_url", "")
        curr_ok, curr_size, curr_msg = verify_gif_url(curr_url) if curr_url else (False, 0, "No URL")

        print(f"\n[{pid}] {pname}: Current URL -> {curr_size} bytes (Valid: {curr_ok}, {curr_msg})")

        candidates = search_tenor_candidates(p["search"], limit_per_term=3)
        print(f"  Found {len(candidates)} candidate GIFs on Tenor:")
        for idx, c in enumerate(candidates[:4]):
            print(f"    {idx+1}. {c['url']} ({c['size']} bytes, slug: {c['slug']}, search: '{c['term']}')")

    print("\nAudit query complete.")

if __name__ == "__main__":
    main()
