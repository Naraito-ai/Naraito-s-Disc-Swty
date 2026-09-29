# -*- coding: utf-8 -*-
"""
audit_all_fusion_gifs_fast.py - Fast concurrent async audit and search for all 67 fusion GIFs
"""
import ssl
import json
import re
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional, Tuple

PLAYERS = [
    # Dark Matter (15)
    {"id": "dm-jordan-99", "name": "Michael Jordan", "tier": "Dark Matter (99)", "search": ["michael-jordan-dunk", "michael-jordan-bulls", "jordan-shrug"]},
    {"id": "dm-kobe-99", "name": "Kobe Bryant", "tier": "Dark Matter (99)", "search": ["kobe-bryant-saiyan", "kobe-dunk-lakers", "kobe-bryant-mamba"]},
    {"id": "dm-lebron-99", "name": "LeBron James", "tier": "Dark Matter (99)", "search": ["lebron-james-dunk", "lebron-silencer", "lebron-james-cavs"]},
    {"id": "dm-curry-99", "name": "Stephen Curry", "tier": "Dark Matter (99)", "search": ["stephen-curry-night-night", "steph-curry-shimmy", "steph-curry-3pt"]},
    {"id": "dm-shaq-99", "name": "Shaquille O'Neal", "tier": "Dark Matter (99)", "search": ["shaq-dunk-lakers", "shaquille-oneal-dunk", "shaq-breaking-backboard"]},
    {"id": "dm-kd-99", "name": "Kevin Durant", "tier": "Dark Matter (99)", "search": ["kevin-durant-dunk", "kevin-durant-warriors", "kevin-durant-clutch"]},
    {"id": "dm-giannis-99", "name": "Giannis Antetokounmpo", "tier": "Dark Matter (99)", "search": ["giannis-antetokounmpo-dunk", "giannis-bucks-mean-mug", "giannis-celebration"]},
    {"id": "dm-magic-99", "name": "Magic Johnson", "tier": "Dark Matter (99)", "search": ["magic-johnson-no-look-pass", "magic-johnson-lakers", "magic-johnson-showtime"]},
    {"id": "dm-bird-99", "name": "Larry Bird", "tier": "Dark Matter (99)", "search": ["larry-bird-larry-legend", "larry-bird-3pt", "larry-bird-celtics"]},
    {"id": "dm-kareemabduljabbar-99", "name": "Kareem Abdul-Jabbar", "tier": "Dark Matter (99)", "search": ["kareem-abdul-jabbar-skyhook", "kareem-skyhook", "kareem-abdul-jabbar-lakers"]},
    {"id": "dm-wiltchamberlain-99", "name": "Wilt Chamberlain", "tier": "Dark Matter (99)", "search": ["wilt-chamberlain-dunk", "wilt-chamberlain-lakers", "wilt-chamberlain-100"]},
    {"id": "dm-billrussell-99", "name": "Bill Russell", "tier": "Dark Matter (99)", "search": ["bill-russell-celtics-block", "bill-russell-celtics", "bill-russell-nba"]},
    {"id": "dm-timduncan-99", "name": "Tim Duncan", "tier": "Dark Matter (99)", "search": ["tim-duncan-spurs-dunk", "tim-duncan-block", "tim-duncan-spurs"]},
    {"id": "dm-hakeemolajuwon-99", "name": "Hakeem Olajuwon", "tier": "Dark Matter (99)", "search": ["hakeem-olajuwon-dream-shake", "hakeem-olajuwon-block", "hakeem-rockets"]},
    {"id": "dm-wemby-99", "name": "Victor Wembanyama", "tier": "Dark Matter (99)", "search": ["victor-wembanyama-dunk", "wemby-spurs-dunk", "victor-wembanyama-block"]},

    # Galaxy Opal 98 (29)
    {"id": "go-luka-98", "name": "Luka Doncic", "tier": "Galaxy Opal (98)", "search": ["luka-doncic-step-back", "luka-doncic-mavericks", "luka-doncic-clutch"]},
    {"id": "go-jokic-98", "name": "Nikola Jokic", "tier": "Galaxy Opal (98)", "search": ["nikola-jokic-pass", "nikola-jokic-nuggets", "nikola-jokic-dunk"]},
    {"id": "go-embiid-98", "name": "Joel Embiid", "tier": "Galaxy Opal (98)", "search": ["joel-embiid-dunk", "joel-embiid-76ers", "joel-embiid-celebration"]},
    {"id": "go-tatum-98", "name": "Jayson Tatum", "tier": "Galaxy Opal (98)", "search": ["jayson-tatum-dunk", "jayson-tatum-celtics", "jayson-tatum-ring"]},
    {"id": "go-tmac-98", "name": "Tracy McGrady", "tier": "Galaxy Opal (98)", "search": ["tracy-mcgrady-dunk", "tracy-mcgrady-13-points", "tmac-rockets"]},
    {"id": "go-iverson-97", "name": "Allen Iverson", "tier": "Galaxy Opal (98/97)", "search": ["allen-iverson-crossover", "allen-iverson-step-over", "allen-iverson-76ers"]},
    {"id": "go-dwyanewade-98", "name": "Dwyane Wade", "tier": "Galaxy Opal (98)", "search": ["dwyane-wade-dunk", "dwyane-wade-this-is-my-house", "dwyane-wade-heat"]},
    {"id": "go-kevingarnett-98", "name": "Kevin Garnett", "tier": "Galaxy Opal (98)", "search": ["kevin-garnett-dunk", "kevin-garnett-celtics", "kevin-garnett-intensity"]},
    {"id": "go-dirknowitzki-98", "name": "Dirk Nowitzki", "tier": "Galaxy Opal (98)", "search": ["dirk-nowitzki-fadeaway", "dirk-nowitzki-mavericks", "dirk-nowitzki-shot"]},
    {"id": "go-charlesbarkley-98", "name": "Charles Barkley", "tier": "Galaxy Opal (98)", "search": ["charles-barkley-dunk", "charles-barkley-suns", "charles-barkley-76ers"]},
    {"id": "go-scottiepippen-98", "name": "Scottie Pippen", "tier": "Galaxy Opal (98)", "search": ["scottie-pippen-dunk", "scottie-pippen-bulls", "scottie-pippen-defense"]},
    {"id": "go-davidrobinson-98", "name": "David Robinson", "tier": "Galaxy Opal (98)", "search": ["david-robinson-dunk", "david-robinson-spurs", "david-robinson-admiral"]},
    {"id": "go-mosesmalone-98", "name": "Moses Malone", "tier": "Galaxy Opal (98)", "search": ["moses-malone-76ers", "moses-malone-dunk", "moses-malone-rockets"]},
    {"id": "go-juliuserving-98", "name": "Julius Erving", "tier": "Galaxy Opal (98)", "search": ["julius-erving-dunk", "dr-j-dunk", "dr-j-cradle-dunk"]},
    {"id": "go-johnstockton-98", "name": "John Stockton", "tier": "Galaxy Opal (98)", "search": ["john-stockton-assist", "john-stockton-jazz", "john-stockton-pass"]},
    {"id": "go-karlmalone-98", "name": "Karl Malone", "tier": "Galaxy Opal (98)", "search": ["karl-malone-dunk", "karl-malone-jazz", "karl-malone-mailman"]},
    {"id": "go-clydedrexler-98", "name": "Clyde Drexler", "tier": "Galaxy Opal (98)", "search": ["clyde-drexler-dunk", "clyde-drexler-glide", "clyde-drexler-blazers"]},
    {"id": "go-patrickewing-98", "name": "Patrick Ewing", "tier": "Galaxy Opal (98)", "search": ["patrick-ewing-dunk", "patrick-ewing-knicks", "patrick-ewing-block"]},
    {"id": "go-oscarrobertson-98", "name": "Oscar Robertson", "tier": "Galaxy Opal (98)", "search": ["oscar-robertson-bucks", "oscar-robertson-royals", "oscar-robertson-basketball"]},
    {"id": "go-jerrywest-98", "name": "Jerry West", "tier": "Galaxy Opal (98)", "search": ["jerry-west-lakers", "jerry-west-shot", "jerry-west-clutch"]},
    {"id": "go-elginbaylor-98", "name": "Elgin Baylor", "tier": "Galaxy Opal (98)", "search": ["elgin-baylor-lakers", "elgin-baylor-dunk", "elgin-baylor-highlights"]},
    {"id": "go-waltfrazier-98", "name": "Walt Frazier", "tier": "Galaxy Opal (98)", "search": ["walt-frazier-knicks", "walt-clyde-frazier", "walt-frazier-basketball"]},
    {"id": "go-stevenash-98", "name": "Steve Nash", "tier": "Galaxy Opal (98)", "search": ["steve-nash-suns-pass", "steve-nash-assist", "steve-nash-suns"]},
    {"id": "go-jasonkidd-98", "name": "Jason Kidd", "tier": "Galaxy Opal (98)", "search": ["jason-kidd-nets-pass", "jason-kidd-assist", "jason-kidd-pass"]},
    {"id": "go-isiahthomas-98", "name": "Isiah Thomas", "tier": "Galaxy Opal (98)", "search": ["isiah-thomas-pistons", "isiah-thomas-dribble", "isiah-thomas-layup"]},
    {"id": "go-dominiquewilkins-98", "name": "Dominique Wilkins", "tier": "Galaxy Opal (98)", "search": ["dominique-wilkins-windmill-dunk", "dominique-wilkins-dunk", "dominique-wilkins-hawks"]},
    {"id": "go-damianlillard-98", "name": "Damian Lillard", "tier": "Galaxy Opal (98)", "search": ["damian-lillard-wave", "dame-time", "damian-lillard-3pt"]},
    {"id": "go-kyrieirving-98", "name": "Kyrie Irving", "tier": "Galaxy Opal (98)", "search": ["kyrie-irving-handles", "kyrie-irving-layup", "kyrie-irving-clutch"]},
    {"id": "go-paulgeorge-98", "name": "Paul George", "tier": "Galaxy Opal (98)", "search": ["paul-george-360-dunk", "paul-george-dunk", "paul-george-pacers"]},

    # Galaxy Opal 97 (23)
    {"id": "go-ad-97", "name": "Anthony Davis", "tier": "Galaxy Opal (97)", "search": ["anthony-davis-dunk", "anthony-davis-lakers", "anthony-davis-block"]},
    {"id": "go-kawhi-97", "name": "Kawhi Leonard", "tier": "Galaxy Opal (97)", "search": ["kawhi-leonard-the-shot", "kawhi-leonard-dunk", "kawhi-leonard-raptors"]},
    {"id": "go-butler-97", "name": "Jimmy Butler", "tier": "Galaxy Opal (97)", "search": ["jimmy-butler-heat", "jimmy-butler-dunk", "jimmy-butler-clutch"]},
    {"id": "go-jamesharden-97", "name": "James Harden", "tier": "Galaxy Opal (97)", "search": ["james-harden-step-back", "james-harden-rockets", "james-harden-stir"]},
    {"id": "go-russellwestbrook-97", "name": "Russell Westbrook", "tier": "Galaxy Opal (97)", "search": ["russell-westbrook-rock-the-baby", "russell-westbrook-dunk", "westbrook-thunder"]},
    {"id": "go-chrispaul-97", "name": "Chris Paul", "tier": "Galaxy Opal (97)", "search": ["chris-paul-clippers", "chris-paul-assist", "chris-paul-clutch"]},
    {"id": "go-carmeloanthony-97", "name": "Carmelo Anthony", "tier": "Galaxy Opal (97)", "search": ["carmelo-anthony-three-to-the-dome", "carmelo-anthony-knicks", "carmelo-anthony-melo"]},
    {"id": "go-vincecarter-97", "name": "Vince Carter", "tier": "Galaxy Opal (97)", "search": ["vince-carter-dunk-contest", "vince-carter-raptors-dunk", "vince-carter-windmill"]},
    {"id": "go-rayallen-97", "name": "Ray Allen", "tier": "Galaxy Opal (97)", "search": ["ray-allen-game-6-3-pointer", "ray-allen-celtics-3pt", "ray-allen-heats-shot"]},
    {"id": "go-reggiemiller-97", "name": "Reggie Miller", "tier": "Galaxy Opal (97)", "search": ["reggie-miller-8-points-9-seconds", "reggie-miller-choke", "reggie-miller-pacers"]},
    {"id": "go-paulpierce-97", "name": "Paul Pierce", "tier": "Galaxy Opal (97)", "search": ["paul-pierce-celtics-clutch", "paul-pierce-the-truth", "paul-pierce-celtics"]},
    {"id": "go-garypayton-97", "name": "Gary Payton", "tier": "Galaxy Opal (97)", "search": ["gary-payton-sonics", "gary-payton-glove", "gary-payton-alley-oop"]},
    {"id": "go-dwighthoward-97", "name": "Dwight Howard", "tier": "Galaxy Opal (97)", "search": ["dwight-howard-superman-dunk", "dwight-howard-magic-block", "dwight-howard-dunk"]},
    {"id": "go-alonzomourning-97", "name": "Alonzo Mourning", "tier": "Galaxy Opal (97)", "search": ["alonzo-mourning-block", "alonzo-mourning-heat", "alonzo-mourning-dunk"]},
    {"id": "go-dikembemutombo-97", "name": "Dikembe Mutombo", "tier": "Galaxy Opal (97)", "search": ["dikembe-mutombo-finger-wag", "dikembe-mutombo-block", "dikembe-mutombo-nuggets"]},
    {"id": "go-granthill-97", "name": "Grant Hill", "tier": "Galaxy Opal (97)", "search": ["grant-hill-pistons-dunk", "grant-hill-crossover", "grant-hill-dunk"]},
    {"id": "go-tonyparker-97", "name": "Tony Parker", "tier": "Galaxy Opal (97)", "search": ["tony-parker-spurs-teardrop", "tony-parker-floater", "tony-parker-spurs"]},
    {"id": "go-timhardaway-97", "name": "Tim Hardaway", "tier": "Galaxy Opal (97)", "search": ["tim-hardaway-killer-crossover", "tim-hardaway-warriors", "tim-hardaway-heat"]},
    {"id": "go-petemaravich-97", "name": "Pete Maravich", "tier": "Galaxy Opal (97)", "search": ["pete-maravich-behind-the-back-pass", "pistol-pete-maravich", "pete-maravich-pass"]},
    {"id": "go-willisreed-97", "name": "Willis Reed", "tier": "Galaxy Opal (97)", "search": ["willis-reed-knicks", "willis-reed-tunnel", "willis-reed-finals"]},
    {"id": "go-bobcousy-97", "name": "Bob Cousy", "tier": "Galaxy Opal (97)", "search": ["bob-cousy-celtics-pass", "bob-cousy-behind-the-back", "bob-cousy-pass"]},
    {"id": "go-rickbarry-97", "name": "Rick Barry", "tier": "Galaxy Opal (97)", "search": ["rick-barry-warriors", "rick-barry-underhand", "rick-barry-free-throw"]},
    {"id": "go-donovanmitchell-97", "name": "Donovan Mitchell", "tier": "Galaxy Opal (97)", "search": ["donovan-mitchell-dunk", "donovan-mitchell-cavs", "donovan-mitchell-jazz"]}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

sem = asyncio.Semaphore(10)

async def check_url(session: aiohttp.ClientSession, url: str) -> Tuple[bool, int, str]:
    if not url:
        return False, 0, "Empty URL"
    try:
        async with sem:
            async with session.get(url, headers=HEADERS, timeout=6) as resp:
                if resp.status != 200:
                    return False, 0, f"HTTP {resp.status}"
                data = await resp.read()
                size = len(data)
                if size > 5 * 1024 * 1024:
                    return False, size, f"Too large ({size / (1024*1024):.2f}MB)"
                return True, size, "OK"
    except Exception as e:
        return False, 0, str(e)

async def search_player_gifs(session: aiohttp.ClientSession, player: Dict[str, Any]) -> Dict[str, Any]:
    candidates = []
    seen_ids = set()

    for term in player["search"]:
        url = f"https://tenor.com/search/{term}-gifs"
        try:
            async with sem:
                async with session.get(url, headers=HEADERS, timeout=6) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        matches = re.findall(r'https://(?:media\d*\.tenor\.com(?:/m)?|c\.tenor\.com)/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)\.gif', html)
                        for mid, slug in matches:
                            clean_mid = mid
                            if clean_mid.endswith(('AAAAC', 'AAAAd', 'AAAAP', 'AAAC', 'AAAd')):
                                clean_mid = re.sub(r'AAAA[A-Z0-9]$|AAA[A-Z0-9]$', 'AAAAM', clean_mid)
                            elif not clean_mid.endswith('AAAAM'):
                                clean_mid = clean_mid + 'AAAAM' if not clean_mid.endswith('M') else clean_mid

                            if clean_mid in seen_ids:
                                continue
                            seen_ids.add(clean_mid)
                            aaaam_url = f"https://media.tenor.com/{clean_mid}/{slug}.gif"
                            candidates.append({"url": aaaam_url, "slug": slug, "term": term})
        except Exception:
            continue

    # Verify candidates
    verified = []
    for c in candidates[:8]:
        ok, sz, msg = await check_url(session, c["url"])
        if ok:
            verified.append({
                "url": c["url"],
                "slug": c["slug"],
                "size": sz,
                "term": c["term"]
            })
            if len(verified) >= 3:
                break

    return {
        "id": player["id"],
        "name": player["name"],
        "tier": player["tier"],
        "verified": verified
    }

async def main():
    print(f"Auditing Tenor GIFs for {len(PLAYERS)} players concurrently...")
    connector = aiohttp.TCPConnector(ssl=False, limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [search_player_gifs(session, p) for p in PLAYERS]
        results = await asyncio.gather(*tasks)

        with open("fusion_gif_candidates.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        print(f"✅ Finished! Gathered candidates for {len(results)} players in fusion_gif_candidates.json")
        for r in results:
            print(f"[{r['id']}] {r['name']}: {len(r['verified'])} verified candidate(s)")
            if r['verified']:
                top = r['verified'][0]
                print(f"   -> Top: {top['url']} ({top['size']} bytes, slug: {top['slug']})")

if __name__ == "__main__":
    asyncio.run(main())
