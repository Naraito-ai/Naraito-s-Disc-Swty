#!/usr/bin/env python3
"""
NBA Moments CLI Image Downloader & Collector
Fetches high-resolution real-life NBA match moment photos (dunk, celebration, scoring, pose)
using the SerpAPI Google Images search engine and saves them to ./assets/moments/{player_name}/
"""

import os
import sys
import io
import re
import argparse
import requests
from PIL import Image

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Default API key provided by user (can also be passed via environment variable SERPAPI_KEY)
DEFAULT_SERPAPI_KEY = "52d34e08122364a035094623d21280d66b189c1626e05a86f723ecccbfd20cf5"

def sanitize_folder_name(name: str) -> str:
    """Sanitizes player name for safe cross-platform folder naming."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def fetch_player_moments(
    player_name: str,
    moment_type: str = "celebration roar scream",
    output_dir: str = "./assets/moments",
    api_key: str = None,
    limit: int = 5,
    open_first: bool = False
) -> list:
    """Fetches Google Images for a player match moment via SerpAPI and saves up to `limit` images."""
    if not api_key:
        api_key = os.environ.get("SERPAPI_KEY", DEFAULT_SERPAPI_KEY)
    
    if not api_key:
        print("[-] Error: SERPAPI_KEY not found in environment variables or configuration.", file=sys.stderr)
        return []

    # Build intense, high-impact action query
    clean_moment = moment_type.strip()
    query = f"{player_name} {clean_moment} NBA match HD wallpaper"
    print(f"\n[+] Searching SerpAPI Google Images for: \"{query}\"...")

    params = {
        "engine": "google_images",
        "q": query,
        "tbm": "isch",
        "api_key": api_key,
        "num": 15
    }

    data = None
    for attempt in range(1, 4):
        try:
            response = requests.get("https://serpapi.com/search", params=params, timeout=25)
            if response.status_code == 429:
                print("[-] SerpAPI rate limit reached (HTTP 429). Please check your quota.", file=sys.stderr)
                return []
            response.raise_for_status()
            data = response.json()
            break
        except Exception as e:
            print(f"[-] Attempt {attempt}/3 failed: {e}", file=sys.stderr)
            if attempt == 3:
                return []

    if not data or "error" in data:
        err_msg = data.get("error") if data else "No data received"
        print(f"[-] SerpAPI Error: {err_msg}", file=sys.stderr)
        return []

    images_results = data.get("images_results", [])
    if not images_results:
        print(f"[-] No image results found for '{query}'.")
        return []

    folder_name = sanitize_folder_name(player_name)
    player_dir = os.path.join(output_dir, folder_name)
    os.makedirs(player_dir, exist_ok=True)

    saved_paths = []
    download_idx = 1

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for item in images_results:
        if download_idx > limit:
            break

        img_url = item.get("original") or item.get("thumbnail")
        if not img_url:
            continue

        try:
            img_resp = requests.get(img_url, headers=headers, timeout=8)
            if img_resp.status_code != 200:
                continue

            img_data = io.BytesIO(img_resp.content)
            img = Image.open(img_data)
            
            # Convert to RGB and save as JPG
            rgb_img = img.convert("RGB")
            out_file = os.path.join(player_dir, f"{download_idx}.jpg")
            rgb_img.save(out_file, "JPEG", quality=95)
            
            print(f"  [{download_idx}/{limit}] Saved: {out_file} ({rgb_img.width}x{rgb_img.height}px)")
            saved_paths.append(out_file)
            download_idx += 1

        except Exception as err:
            # Skip invalid, corrupted or blocked URLs
            continue

    if saved_paths:
        print(f"[✓] Successfully downloaded {len(saved_paths)} images to: {player_dir}")
        if open_first:
            try:
                print(f"[+] Opening first image: {saved_paths[0]}")
                Image.open(saved_paths[0]).show()
            except Exception as e:
                print(f"[-] Failed to open image: {e}")
    else:
        print(f"[-] No valid images could be saved for {player_name}.")

    return saved_paths


def main():
    parser = argparse.ArgumentParser(description="NBA Real-Life Match Moments Image Downloader")
    parser.add_argument("--player", "-p", type=str, help="NBA player name (e.g. 'LeBron James')")
    parser.add_argument("--moment", "-m", type=str, default="dunk", help="Moment type: dunk, celebration, scoring, pose (default: dunk)")
    parser.add_argument("--output", "-o", type=str, default="./assets/moments", help="Output directory path (default: ./assets/moments)")
    parser.add_argument("--limit", "-l", type=int, default=5, help="Number of images to download (default: 5)")
    parser.add_argument("--open", action="store_true", help="Open the first image after download")
    parser.add_argument("--all-players", action="store_true", help="Download top moment photos for all players in catalog")

    args = parser.parse_args()

    # If --all-players is passed or no specific player is provided, handle accordingly
    if args.all_players:
        # Import player list from bot if available
        try:
            import bot
            players = list({c["name"] for c in bot.NBA_2K_MOBILE_CARDS})
        except Exception:
            players = [
                "Michael Jordan", "LeBron James", "Stephen Curry", "Kobe Bryant",
                "Shaquille O'Neal", "Victor Wembanyama", "Luka Doncic", "Nikola Jokic",
                "Anthony Edwards", "Jayson Tatum", "Giannis Antetokounmpo", "Kevin Durant"
            ]
        
        print(f"[+] Downloading moments for {len(players)} players in catalog...")
        for p in players:
            fetch_player_moments(p, args.moment, args.output, limit=args.limit, open_first=False)
        return

    if not args.player:
        parser.print_help()
        print("\n[!] Please specify a player name with --player \"Player Name\" or use --all-players")
        sys.exit(1)

    fetch_player_moments(
        player_name=args.player,
        moment_type=args.moment,
        output_dir=args.output,
        limit=args.limit,
        open_first=args.open
    )


if __name__ == "__main__":
    main()
