# -*- coding: utf-8 -*-
"""
generate_final_fusion_mappings.py - Compiles, verifies, and formats the authoritative NBA_FUSION_GIF_MAPPINGS
"""
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

def verify_gif(url: str) -> Tuple[bool, int, str]:
    if not url:
        return False, 0, "No URL"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            if resp.status != 200:
                return False, 0, f"HTTP {resp.status}"
            data = resp.read()
            size = len(data)
            if size > 5 * 1024 * 1024:
                return False, size, "Too large (> 5MB)"
            return True, size, "PASS"
    except Exception as e:
        return False, 0, f"Error: {e}"

# Authoritative curated mappings with verified basketball hype/dunk/shot/moment GIFs
FINAL_MAPPINGS = {
    # ── Dark Matter ─────────────────────────────────────────────────────────────
    "dm-jordan-99": {
        "name": "Michael Jordan",
        "gif_url": "https://media.tenor.com/-5II3eZiaJcAAAAM/michael-jordan-basketball.gif",
        "flavor_text": "🐐 His Airness has transcended basketball itself"
    },
    "dm-kobe-99": {
        "name": "Kobe Bryant",
        "gif_url": "https://media.tenor.com/xUF6L_2N2ZAAAAAM/nba-saiyan.gif",
        "flavor_text": "🐍 The Black Mamba has ascended beyond all limits"
    },
    "dm-lebron-99": {
        "name": "LeBron James",
        "gif_url": "https://media.tenor.com/lquFMyMh8zYAAAAM/lebron-james-dunk.gif",
        "flavor_text": "👑 The King has entered God Mode"
    },
    "dm-curry-99": {
        "name": "Stephen Curry",
        "gif_url": "https://media.tenor.com/Oy2ncwqiZO8AAAAM/night-night-nighty-night.gif",
        "flavor_text": "🍳 Curry has cooked the entire universe from half court"
    },
    "dm-shaq-99": {
        "name": "Shaquille O'Neal",
        "gif_url": "https://media.tenor.com/kuyCaCZWKCwAAAAM/shaquille-oneal-basketball.gif",
        "flavor_text": "💥 Shaq Diesel has gone absolutely nuclear"
    },
    "dm-kd-99": {
        "name": "Kevin Durant",
        "gif_url": "https://media.tenor.com/7ruKh0zDurUAAAAM/dunk-kevin-durant-dunk.gif",
        "flavor_text": "🎯 The Slim Reaper cannot be stopped by anyone"
    },
    "dm-giannis-99": {
        "name": "Giannis Antetokounmpo",
        "gif_url": "https://media.tenor.com/KJeGdvrcQvMAAAAM/milwaukee-bucks-giannis-antetokounmpo.gif",
        "flavor_text": "⚡ The Greek Freak has become a full deity"
    },
    "dm-magic-99": {
        "name": "Magic Johnson",
        "gif_url": "https://media.tenor.com/zcX1Snd2CtsAAAAM/magic-johnson.gif",
        "flavor_text": "✨ Showtime has never looked this magical"
    },
    "dm-bird-99": {
        "name": "Larry Bird",
        "gif_url": "https://media.tenor.com/785iV9CCFTcAAAAM/larry-bird-robert-parish.gif",
        "flavor_text": "🧊 Larry Legend is ice cold and completely untouchable"
    },
    "dm-kareemabduljabbar-99": {
        "name": "Kareem Abdul-Jabbar",
        "gif_url": "https://media.tenor.com/JEnX7ebK0Z0AAAAM/kareem-kareem-skyhook.gif",
        "flavor_text": "🌀 The Skyhook is beyond all human comprehension"
    },
    "dm-wiltchamberlain-99": {
        "name": "Wilt Chamberlain",
        "gif_url": "https://media.tenor.com/jqrvfLdQhZYAAAAM/wilt-chamberlain-basketball.gif",
        "flavor_text": "👹 Wilt the Stilt has become a god among men"
    },
    "dm-billrussell-99": {
        "name": "Bill Russell",
        "gif_url": "https://media.tenor.com/-uKWiG9YwiYAAAAM/bill-russell.gif",
        "flavor_text": "🏆 The greatest winner in basketball history has ascended"
    },
    "dm-timduncan-99": {
        "name": "Tim Duncan",
        "gif_url": "https://media.tenor.com/69cPUdgnQxwAAAAM/tim-duncan.gif",
        "flavor_text": "🏆 The Big Fundamental has become fundamentally unstoppable"
    },
    "dm-hakeemolajuwon-99": {
        "name": "Hakeem Olajuwon",
        "gif_url": "https://media.tenor.com/u0aplK7iUvYAAAAM/hakeem-turn-around.gif",
        "flavor_text": "👻 The Dream Shake is now an unsolvable mystery"
    },
    "dm-wemby-99": {
        "name": "Victor Wembanyama",
        "gif_url": "https://media.tenor.com/XfmGUCYiEUEAAAAM/victor-wembanyama-wembanyama.gif",
        "flavor_text": "👽 Wemby has confirmed he is not from this planet"
    },

    # ── Galaxy Opal 98 OVR ──────────────────────────────────────────────────────
    "go-luka-98": {
        "name": "Luka Doncic",
        "gif_url": "https://media.tenor.com/C9ABcyLH9l4AAAAM/luka-doncic-stepback.gif",
        "flavor_text": "🌟 Luka Magic has gone completely beyond human limits"
    },
    "go-jokic-98": {
        "name": "Nikola Jokic",
        "gif_url": "https://media.tenor.com/MOufHecLk6IAAAAM/sports-sportsmanias.gif",
        "flavor_text": "♟️ The Joker has revealed his final unstoppable form"
    },
    "go-embiid-98": {
        "name": "Joel Embiid",
        "gif_url": "https://media.tenor.com/dZnUrWgomFAAAAAM/joel-embiid-slam.gif",
        "flavor_text": "🌍 The Process is now complete and totally unstoppable"
    },
    "go-tatum-98": {
        "name": "Jayson Tatum",
        "gif_url": "https://media.tenor.com/JegpKDR4F3gAAAAM/jayson-tatum-dunk.gif",
        "flavor_text": "🍀 Tatum has become the new face of Boston legend"
    },
    "go-tmac-98": {
        "name": "Tracy McGrady",
        "gif_url": "https://media.tenor.com/5GVprx8UYhAAAAAM/tracy-mcgrady-toronto-raptors.gif",
        "flavor_text": "⚡ T-Mac has unlocked unlimited scoring mode"
    },
    "go-iverson-97": {
        "name": "Allen Iverson",
        "gif_url": "https://media.tenor.com/1EWb9d-a80cAAAAM/iverson-crossover.gif",
        "flavor_text": "💨 The Answer moves faster than reality itself"
    },
    "go-alleniverson-97": {
        "name": "Allen Iverson",
        "gif_url": "https://media.tenor.com/1EWb9d-a80cAAAAM/iverson-crossover.gif",
        "flavor_text": "💨 The Answer moves faster than reality itself"
    },
    "go-dwyanewade-98": {
        "name": "Dwyane Wade",
        "gif_url": "https://media.tenor.com/wQqVEkxIPAkAAAAM/dwayne-wade-nba.gif",
        "flavor_text": "⚡ The Flash has reached absolute maximum velocity"
    },
    "go-kevingarnett-98": {
        "name": "Kevin Garnett",
        "gif_url": "https://media.tenor.com/1g9AnZZbvDMAAAAM/kevin-garnett.gif",
        "flavor_text": "🔥 KG's intensity has shattered every limit imaginable"
    },
    "go-dirknowitzki-98": {
        "name": "Dirk Nowitzki",
        "gif_url": "https://media.tenor.com/l0iTUt9dWAgAAAAM/dirk-nowitzki-dallas-mavericks.gif",
        "flavor_text": "🇩🇪 Nowitzki's fadeaway defies the laws of physics"
    },
    "go-charlesbarkley-98": {
        "name": "Charles Barkley",
        "gif_url": "https://media.tenor.com/BBAgR634QDwAAAAM/charles-barkley-sir-charles.gif",
        "flavor_text": "💪 Sir Charles has become an immovable force of nature"
    },
    "go-scottiepippen-98": {
        "name": "Scottie Pippen",
        "gif_url": "https://media.tenor.com/4zjloKDWg6sAAAAM/scottie-pippen.gif",
        "flavor_text": "🦸 Pip has stepped out of the shadow and into legend"
    },
    "go-davidrobinson-98": {
        "name": "David Robinson",
        "gif_url": "https://media.tenor.com/llHrhs7rvBoAAAAM/david-robinson-spurs.gif",
        "flavor_text": "⚓ The Admiral has commanded complete basketball domination"
    },
    "go-mosesmalone-98": {
        "name": "Moses Malone",
        "gif_url": "",  # Left empty per rule: no fake/wrong GIF
        "flavor_text": "💪 Moses has led his team to the promised land"
    },
    "go-juliuserving-98": {
        "name": "Julius Erving",
        "gif_url": "https://media.tenor.com/Nr762QJup18AAAAM/erving-sixers.gif",
        "flavor_text": "🩺 Dr J has prescribed a legendary dose of greatness"
    },
    "go-johnstockton-98": {
        "name": "John Stockton",
        "gif_url": "https://media.tenor.com/4SAdW1hPFXwAAAAM/jon-stockton-assist.gif",
        "flavor_text": "🎯 Stockton has become the puppet master of basketball"
    },
    "go-karlmalone-98": {
        "name": "Karl Malone",
        "gif_url": "https://media.tenor.com/LTIxrHUvj8kAAAAM/karl-malone-the-mail-man.gif",
        "flavor_text": "📬 The Mailman always delivers in legendary form"
    },
    "go-clydedrexler-98": {
        "name": "Clyde Drexler",
        "gif_url": "https://media.tenor.com/aTB1CJylK64AAAAM/clyde-drexler-nba.gif",
        "flavor_text": "🌊 Clyde the Glide has reached breathtaking new heights"
    },
    "go-patrickewing-98": {
        "name": "Patrick Ewing",
        "gif_url": "https://media.tenor.com/WVf7ugpBhoEAAAAM/patrick-ewing-33.gif",
        "flavor_text": "🏙️ Ewing has become the guardian of New York"
    },
    "go-oscarrobertson-98": {
        "name": "Oscar Robertson",
        "gif_url": "",  # Left empty per rule: no fake/wrong GIF
        "flavor_text": "📊 The Big O has redefined what is humanly possible"
    },
    "go-jerrywest-98": {
        "name": "Jerry West",
        "gif_url": "https://media.tenor.com/jPy4ArbPHUQAAAAM/jerry-west-lakers.gif",
        "flavor_text": "🏀 The Logo himself has come to life"
    },
    "go-elginbaylor-98": {
        "name": "Elgin Baylor",
        "gif_url": "",  # Left empty per rule: no fake/wrong GIF
        "flavor_text": "✈️ Elgin Baylor was flying before flying was even possible"
    },
    "go-waltfrazier-98": {
        "name": "Walt Frazier",
        "gif_url": "https://media.tenor.com/EU8UIOtlkKIAAAAM/walt-frazier.gif",
        "flavor_text": "😎 Clyde is too cool for this planet"
    },
    "go-stevenash-98": {
        "name": "Steve Nash",
        "gif_url": "https://media.tenor.com/75ewi4a2u5UAAAAM/steve-nash.gif",
        "flavor_text": "🎩 Nash turned basketball into an art form nobody else could paint"
    },
    "go-jasonkidd-98": {
        "name": "Jason Kidd",
        "gif_url": "https://media.tenor.com/QEvwiRiFDlAAAAAM/jason-kidd.gif",
        "flavor_text": "👁️ Kidd saw the game three plays ahead of everyone else"
    },
    "go-isiahthomas-98": {
        "name": "Isiah Thomas",
        "gif_url": "https://media.tenor.com/kvyhSwhFGI4AAAAM/detroit-pistons-isiah-thomas.gif",
        "flavor_text": "⚡ Zeke has proven size means absolutely nothing"
    },
    "go-dominiquewilkins-98": {
        "name": "Dominique Wilkins",
        "gif_url": "https://media.tenor.com/23AQEdGjo9kAAAAM/dominique-wilkins-windmill-dunk.gif",
        "flavor_text": "🦅 The Human Highlight Film has gone completely supernatural"
    },
    "go-damianlillard-98": {
        "name": "Damian Lillard",
        "gif_url": "https://media.tenor.com/B7vlYeVyouYAAAAM/dame-lillard.gif",
        "flavor_text": "⏰ Dame Time has become completely infinite"
    },
    "go-kyrieirving-98": {
        "name": "Kyrie Irving",
        "gif_url": "https://media.tenor.com/MltYmfAReOcAAAAM/kyrie-handles.gif",
        "flavor_text": "🌀 Uncle Drew's handles have completely broken the matrix"
    },
    "go-paulgeorge-98": {
        "name": "Paul George",
        "gif_url": "https://media.tenor.com/G8eP7Zgy_-YAAAAM/dunk-paul-george.gif",
        "flavor_text": "🌙 PG has elevated his game to another dimension entirely"
    },

    # ── Galaxy Opal 97 OVR ──────────────────────────────────────────────────────
    "go-ad-97": {
        "name": "Anthony Davis",
        "gif_url": "https://media.tenor.com/q7s8-zGWp-8AAAAM/lakers.gif",
        "flavor_text": "👁️ The Brow has unlocked complete basketball domination"
    },
    "go-kawhi-97": {
        "name": "Kawhi Leonard",
        "gif_url": "https://media.tenor.com/wOov1s3fCMEAAAAM/kawhi-kawhi-leonard.gif",
        "flavor_text": "🤖 The Klaw has fully activated terminator mode"
    },
    "go-butler-97": {
        "name": "Jimmy Butler",
        "gif_url": "https://media.tenor.com/LlA95VeBO4YAAAAM/miamiheat-jimmybutler.gif",
        "flavor_text": "🔥 Jimmy Buckets has grinded his way to immortality"
    },
    "go-jamesharden-97": {
        "name": "James Harden",
        "gif_url": "https://media.tenor.com/PzFNraX8AdkAAAAM/houston-rockets-stir.gif",
        "flavor_text": "🧔 The Beard's step back has become physically impossible to guard"
    },
    "go-russellwestbrook-97": {
        "name": "Russell Westbrook",
        "gif_url": "https://media.tenor.com/HliWh4j2SBsAAAAM/russel-westbrook-nba.gif",
        "flavor_text": "💢 Brodie runs on a different fuel than every other human being"
    },
    "go-chrispaul-97": {
        "name": "Chris Paul",
        "gif_url": "https://media.tenor.com/QqhVvvcJ-FgAAAAM/chris-paul-chrispaul.gif",
        "flavor_text": "🧠 The Point God controls the game from another dimension"
    },
    "go-carmeloanthony-97": {
        "name": "Carmelo Anthony",
        "gif_url": "https://media.tenor.com/4O4z-bR2qMMAAAAM/carmelo-anthony-melo.gif",
        "flavor_text": "🍊 Melo's midrange game is a form of poetry no one else can write"
    },
    "go-vincecarter-97": {
        "name": "Vince Carter",
        "gif_url": "https://media.tenor.com/8N_RlZgzqSoAAAAM/vince-carter-vince.gif",
        "flavor_text": "🦅 Vinsanity has taken flight into the stratosphere"
    },
    "go-rayallen-97": {
        "name": "Ray Allen",
        "gif_url": "https://media.tenor.com/-pDys2heFfQAAAAM/ray-allen.gif",
        "flavor_text": "🎯 The purest shooter to ever grace the hardwood"
    },
    "go-reggiemiller-97": {
        "name": "Reggie Miller",
        "gif_url": "https://media.tenor.com/p_99fxGEA4UAAAAM/reggie-miller-choke.gif",
        "flavor_text": "🤌 Reggie Miller lives for the moment everyone else fears"
    },
    "go-paulpierce-97": {
        "name": "Paul Pierce",
        "gif_url": "https://media.tenor.com/xVWgjAhAlZcAAAAM/paul-pierce-pierce.gif",
        "flavor_text": "💚 The Truth cannot be denied or stopped"
    },
    "go-garypayton-97": {
        "name": "Gary Payton",
        "gif_url": "https://media.tenor.com/NhVNJ-Nh2eUAAAAM/seattle-supersonics-gary-payton.gif",
        "flavor_text": "🧤 The Glove has locked down the entire universe"
    },
    "go-dwighthoward-97": {
        "name": "Dwight Howard",
        "gif_url": "https://media.tenor.com/UoIe4hF35J0AAAAM/dunk-contest.gif",
        "flavor_text": "🦸 Superman has taken complete ownership of the entire paint"
    },
    "go-alonzomourning-97": {
        "name": "Alonzo Mourning",
        "gif_url": "https://media.tenor.com/wF9FQunfa6YAAAAM/alonzo-mourning.gif",
        "flavor_text": "🛡️ Zo has rejected every shot in basketball history"
    },
    "go-dikembemutombo-97": {
        "name": "Dikembe Mutombo",
        "gif_url": "https://media.tenor.com/Q5knp6bJF7wAAAAM/no-no-no-sports.gif",
        "flavor_text": "☝️ Not in Dikembe's house. Not today. Not ever."
    },
    "go-granthill-97": {
        "name": "Grant Hill",
        "gif_url": "https://media.tenor.com/sfW2B6vJlHcAAAAM/grant-hill-dunk.gif",
        "flavor_text": "🌟 Grant Hill showed the world what a complete player looks like"
    },
    "go-tonyparker-97": {
        "name": "Tony Parker",
        "gif_url": "https://media.tenor.com/7mw-CscArwoAAAAM/tony-parker-spurs.gif",
        "flavor_text": "🇫🇷 The French Prince floated past every defender in history"
    },
    "go-timhardaway-97": {
        "name": "Tim Hardaway",
        "gif_url": "https://media.tenor.com/K-6KCIpOdocAAAAM/tim-hardaway-golden-state.gif",
        "flavor_text": "💫 The UTEP Two Step has crossed over into legend"
    },
    "go-petemaravich-97": {
        "name": "Pete Maravich",
        "gif_url": "https://media.tenor.com/9nw7rSUBdwIAAAAM/pete-maravich-pistol-pete.gif",
        "flavor_text": "🔫 Pistol Pete shoots from dimensions no one else can reach"
    },
    "go-willisreed-97": {
        "name": "Willis Reed",
        "gif_url": "",  # Left empty per rule: no fake/wrong GIF
        "flavor_text": "❤️ The heart of a champion cannot be measured"
    },
    "go-bobcousy-97": {
        "name": "Bob Cousy",
        "gif_url": "https://media.tenor.com/H0foamBzrn4AAAAM/bob-cousy-crossover.gif",
        "flavor_text": "🎩 The Cooz invented basketball magic before it had a name"
    },
    "go-rickbarry-97": {
        "name": "Rick Barry",
        "gif_url": "",  # Left empty per rule: no fake/wrong GIF
        "flavor_text": "🎯 Rick Barry did it his own way and it worked every single time"
    },
    "go-donovanmitchell-97": {
        "name": "Donovan Mitchell",
        "gif_url": "https://media.tenor.com/IXx9Sy0zangAAAAM/utah-jazz-donovan-mitchell.gif",
        "flavor_text": "🕷️ Spida Mitchell has spun a web no one can escape"
    }
}

def main():
    print(f"Auditing {len(FINAL_MAPPINGS)} final fusion mappings...")
    report_lines = []
    seen_urls = set()
    pass_count = 0
    fail_count = 0

    for cid, info in sorted(FINAL_MAPPINGS.items()):
        url = info["gif_url"]
        name = info["name"]

        if not url:
            report_lines.append(f"• **[{cid}] {name}**: `NO GIF` (Omitted per rule — no authentic GIF on Tenor) -> **PASS (Clean Omission)**")
            pass_count += 1
            continue

        if url in seen_urls:
            report_lines.append(f"• **[{cid}] {name}**: `{url}` -> **FAIL (Duplicate URL)**")
            fail_count += 1
            continue
        seen_urls.add(url)

        ok, size, msg = verify_gif(url)
        if ok:
            pass_count += 1
            report_lines.append(f"• **[{cid}] {name}**: `{url}` ({size:,} bytes) -> **PASS**")
        else:
            fail_count += 1
            report_lines.append(f"• **[{cid}] {name}**: `{url}` ({size:,} bytes) -> **FAIL ({msg})**")

    print(f"\nAudit complete: {pass_count} PASS, {fail_count} FAIL out of {len(FINAL_MAPPINGS)} players.")
    with open("fusion_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

if __name__ == "__main__":
    main()
