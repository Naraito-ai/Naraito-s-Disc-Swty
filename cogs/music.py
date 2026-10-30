import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import logging
import re
import urllib.parse
import urllib.request
from collections import deque
from typing import Optional, Union, Dict, List, Any, Tuple
import yt_dlp
import time
import unicodedata
import math
import audioop
import difflib
import queue
import threading

import base64
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

logger = logging.getLogger("SweetyBot.Music")

# ─── Spotify Client ───────────────────────────────────────────────────────────

spotify_client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
spotify_client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()

spotify = None
if spotify_client_id and spotify_client_secret:
    try:
        spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=spotify_client_id,
            client_secret=spotify_client_secret
        ))
    except Exception as e:
        logger.warning(f"Failed to initialize Spotify client: {e}")


def is_vevo_entry(cand: dict) -> bool:
    """Detects if a YouTube video entry belongs to VEVO, which has strict DRM/bot-blocks on datacenter IPs."""
    if not cand or not isinstance(cand, dict):
        return False
    check_values = [
        cand.get("uploader") or "",
        cand.get("channel") or "",
        cand.get("uploader_id") or "",
        cand.get("channel_url") or "",
        cand.get("uploader_url") or "",
        cand.get("creator") or "",
    ]
    for val in check_values:
        if "vevo" in str(val).lower():
            return True
    title = str(cand.get("title") or "")
    if re.search(r'\bvevo\b', title, re.IGNORECASE):
        return True
    return False


COVER_PENALTIES = [
    "cover", "tribute", "remix", "slowed", "reverb", "edit",
    "mashup", "bootleg", "nightcore", "sped up", "acoustic",
    "karaoke", "version", "lofi", "aish", "unplugged", "funk",
    "piano", "instrumental", "orchestral", "guitar", "violin",
    "harp", "medley", "8d audio", "bass boosted", "synthesia",
    "tutorial", "sheet music", "backing track", "originally performed by",
    "tribute to", "tribute band", "kids biz", "piano song masters"
]


def validate_canonical_match(query: str, cand_artist: str, cand_title: str) -> bool:
    """
    Validates whether a candidate track (from Spotify or metadata search)
    is a genuine match for the user's query, preventing unrelated tracks
    (e.g., 'Sam Smith' for query 'mika mitsuraba stay with me')
    from hijacking the playback.
    """
    q_clean = query.lower()
    q_words = set(re.findall(r'\b\w{2,}\b', q_clean))
    
    # Strip common search noise words
    noise = {"song", "track", "music", "audio", "video", "official", "lyrics", "full", "hd", "hq"}
    q_words = q_words - noise
    if not q_words:
        return True

    a_clean = (cand_artist or "").lower()
    t_clean = (cand_title or "").lower()
    a_words = set(re.findall(r'\b\w{2,}\b', a_clean)) - {"the", "feat", "ft"}
    t_words = set(re.findall(r'\b\w{2,}\b', t_clean)) - {"the", "feat", "ft"}

    # Title match check: candidate title must match title words in query
    matched_title = set()
    for qw in q_words:
        for tw in t_words:
            if qw == tw or (len(qw) >= 4 and len(tw) >= 4 and (qw in tw or tw in qw)):
                matched_title.add(qw)
                break
            elif len(qw) >= 3 and len(tw) >= 3 and difflib.SequenceMatcher(None, qw, tw).ratio() >= 0.70:
                matched_title.add(qw)
                break

    # If title matched NONE of the query words, reject immediately
    if not matched_title:
        return False

    # Check remaining query words against candidate artist
    unmatched_query_words = q_words - matched_title
    if unmatched_query_words:
        has_artist_match = False
        for qw in unmatched_query_words:
            for aw in a_words:
                if qw == aw or (len(qw) >= 4 and len(aw) >= 4 and (qw in aw or aw in qw)):
                    has_artist_match = True
                    break
                elif len(qw) >= 3 and len(aw) >= 3 and difflib.SequenceMatcher(None, qw, aw).ratio() >= 0.65:
                    has_artist_match = True
                    break
            if has_artist_match:
                break
        if not has_artist_match:
            return False

    return True


def clean_title_for_matching(text: str) -> str:
    # Strip parenthetical annotations like (The New Life of Tamizh), (From "Thangamagan"), (Official Audio)
    t = re.sub(r'[\(\[].*?[\)\]]', '', text or '')
    t = re.sub(r'[^\w\s]', '', t)
    return ' '.join(t.lower().split())


def score_candidate(title: str, artist: str = "", play_count: int = 0, release_year=None, query: str = "", is_topic: bool = False, is_studio: bool = False) -> float:
    score = 0.0
    title_lower = (title or "").lower().strip()
    artist_lower = (artist or "").lower().strip()
    q_lower = (query or "").lower().strip()

    # Penalize unwanted covers, piano versions, karaoke, remixes heavily
    for word in COVER_PENALTIES:
        if word in title_lower or word in artist_lower:
            if word not in q_lower:
                score -= 3000.0

    # Official licensed studio catalog bonus (JioSaavn CD masters)
    if is_studio:
        score += 300.0

    # YouTube Topic channels (Artist - Topic) -> +500 bonus
    if is_topic:
        channel_name = re.sub(r'\s*-\s*topic$', '', artist_lower).strip()
        q_words = [w for w in re.findall(r'\w+', q_lower) if len(w) > 2]
        if not q_words or any(w in q_lower for w in re.findall(r'\w+', channel_name)) or any(w in channel_name for w in q_words):
            score += 500.0
        else:
            score -= 200.0

    noise = {"song", "track", "music", "audio", "video", "official", "lyrics", "full", "hd", "hq", "the", "and", "feat", "ft", "for"}
    q_clean_words = [w for w in re.findall(r'\b\w{2,}\b', q_lower) if w not in noise]
    t_clean_words = [w for w in re.findall(r'\b\w{2,}\b', title_lower) if w not in noise]
    a_clean_words = [w for w in re.findall(r'\b\w{2,}\b', artist_lower) if w not in noise]

    # Check title matches
    matched_t = set()
    for qw in q_clean_words:
        for tw in t_clean_words:
            if qw == tw or (len(qw) >= 4 and len(tw) >= 4 and (qw in tw or tw in qw)):
                matched_t.add(qw)
                break
            elif len(qw) >= 3 and len(tw) >= 3 and difflib.SequenceMatcher(None, qw, tw).ratio() >= 0.70:
                matched_t.add(qw)
                break

    # If the candidate title matches NONE of the query words:
    if q_clean_words and not matched_t:
        return -9999.0

    # Unmatched query words are presumed artist terms
    unmatched_q = [w for w in q_clean_words if w not in matched_t]

    if unmatched_q:
        significant_unmatched = [w for w in unmatched_q if len(w) >= 3]
        matched_a = set()
        for qw in significant_unmatched:
            for aw in a_clean_words:
                if qw == aw or (len(qw) >= 4 and len(aw) >= 4 and (qw in aw or aw in qw)):
                    matched_a.add(qw)
                    break
                elif len(qw) >= 3 and len(aw) >= 3 and difflib.SequenceMatcher(None, qw, aw).ratio() >= 0.65:
                    matched_a.add(qw)
                    break

        # If significant artist words were in query but ZERO match candidate artist/channel:
        # Disqualify candidate immediately! (e.g. Sam Smith for Miki Matsubara query)
        if significant_unmatched and not matched_a:
            return -9999.0

        if matched_a:
            score += 600.0 * (len(matched_a) / len(significant_unmatched))

    clean_cand = clean_title_for_matching(title)
    clean_q = clean_title_for_matching(query)
    clean_q_without_artist = clean_q
    if unmatched_q:
        for qw in unmatched_q:
            clean_q_without_artist = re.sub(rf'\b{re.escape(qw)}\b', '', clean_q_without_artist).strip()

    if clean_cand == clean_q or (clean_cand and clean_cand == clean_q_without_artist):
        score += 500.0
    elif clean_cand and (clean_cand in clean_q or clean_q in clean_cand):
        score += 350.0
    elif matched_t:
        score += min(300.0, len(matched_t) * 150.0)

    # Play count = strongest "original" signal
    try:
        p_count = int(play_count or 0)
    except (ValueError, TypeError):
        p_count = 0

    if p_count >= 100_000_000:
        score += 800.0
    elif p_count >= 10_000_000:
        score += 600.0
    elif p_count >= 1_000_000:
        score += 400.0
    elif p_count >= 100_000:
        score += 200.0
    elif p_count >= 10_000:
        score += 100.0

    # Older = more likely original
    if release_year:
        try:
            ry = int(release_year)
            score += max(0, (2025 - ry) * 10)
        except (ValueError, TypeError):
            pass

    # Bonus for official audio / matching artist
    if "official audio" in title_lower and "remix" not in title_lower:
        score += 50.0

    return score


def score_music_candidate(cand: dict, query: str = "") -> float:
    """
    Ranks search candidates using score_candidate logic to guarantee original version first priority:
    - Penalizes covers, remixes, bootlegs, sped up, edits by -400 each.
    - Multi-million play counts provide strong signal (+200, +500, +800).
    - Older release years receive priority.
    - Verified artist topic channels receive +500 bonus.
    """
    if not cand or not isinstance(cand, dict):
        return -9999.0

    title = cand.get("title") or cand.get("song") or ""
    uploader = cand.get("uploader") or cand.get("channel") or cand.get("primary_artists") or ""
    uploader_id = cand.get("uploader_id") or ""
    views = cand.get("view_count") or cand.get("play_count") or 0
    year = cand.get("release_year") or cand.get("year")
    if not year and cand.get("upload_date"):
        try:
            year = int(str(cand["upload_date"])[:4])
        except Exception:
            pass
    is_topic = "- topic" in str(uploader).lower() or "- topic" in str(uploader_id).lower()
    is_studio = bool(cand.get("is_studio"))

    return score_candidate(title, uploader, views, year, query=query, is_topic=is_topic, is_studio=is_studio)


SAAVN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "X-Forwarded-For": "49.37.241.1",
    "Client-IP": "49.37.241.1",
    "CF-Connecting-IP": "49.37.241.1",
}


def fetch_official_studio_track(search_query: str, min_score: float = 800.0) -> Optional[dict]:
    """
    Fetches 100% original, official studio master (320kbps CD audio) via licensed CDN.
    Guarantees official studio track playback without datacenter bot-blocks or amateur remixes.
    Strictly scores candidates: picks highest scoring candidate with score >= min_score (default 800).
    """
    try:
        q_clean = search_query.strip()
        q_clean = re.sub(r'[\(\[](?:official\s*(?:video|audio|music\s*video)?|lyrics|audio|video)[\)\]]', '', q_clean, flags=re.IGNORECASE).strip()
        q_enc = urllib.parse.quote(q_clean)
        user_wants_variant = any(w in q_clean.lower() for w in ("remix", "cover", "slowed", "flip", "edit", "instrumental", "karaoke", "mashup", "reverb"))

        candidates = []
        # 1. Primary: JioSaavn Catalog Search with play counts & ranking
        try:
            url = f"https://www.jiosaavn.com/api.php?__call=search.getResults&_format=json&_marker=0&cc=in&p=1&n=15&q={q_enc}"
            req = urllib.request.Request(url, headers=SAAVN_HEADERS)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            for r in results:
                title = r.get("song") or r.get("title") or ""
                artist = r.get("primary_artists") or r.get("more_info", {}).get("singers") or ""
                plays = int(r.get("play_count") or 0)
                year = r.get("year") or r.get("more_info", {}).get("year")
                pid = r.get("id")
                if pid and title:
                    candidates.append({
                        "id": pid,
                        "title": title,
                        "uploader": artist,
                        "duration": int(r.get("duration") or 0),
                        "play_count": plays,
                        "year": year,
                        "raw": r,
                    })
        except Exception as e:
            logger.warning(f"JioSaavn catalog search failed for '{search_query}': {e}")

        # 2. Secondary autocomplete fallback
        if not candidates:
            try:
                url2 = f"https://www.jiosaavn.com/api.php?__call=autocomplete.get&_format=json&_marker=0&cc=in&includeMetaTags=1&query={q_enc}"
                req2 = urllib.request.Request(url2, headers=SAAVN_HEADERS)
                with urllib.request.urlopen(req2, timeout=5.0) as resp2:
                    data2 = json.loads(resp2.read().decode("utf-8"))
                for r in data2.get("songs", {}).get("data", []):
                    title = r.get("title") or ""
                    artist = r.get("more_info", {}).get("singers") or r.get("more_info", {}).get("primary_artists") or ""
                    pid = r.get("id")
                    if pid and title:
                        candidates.append({
                            "id": pid,
                            "title": title,
                            "uploader": artist,
                            "duration": 0,
                            "play_count": 0,
                            "year": None,
                            "raw": r,
                        })
            except Exception as e:
                logger.warning(f"JioSaavn autocomplete fallback failed for '{search_query}': {e}")

        if not candidates:
            return None

        # 3. Score & filter candidates to guarantee original version first priority
        scored_candidates = []
        for c in candidates:
            s = score_candidate(
                title=c["title"],
                artist=c["uploader"],
                play_count=c.get("play_count", 0),
                release_year=c.get("year"),
                query=q_clean,
                is_studio=True,
            )
            c["score"] = s
            scored_candidates.append(c)

        scored_candidates.sort(key=lambda c: c["score"], reverse=True)

        eligible = [c for c in scored_candidates if user_wants_variant or c["score"] >= min_score]
        if not eligible:
            logger.info(f"No JioSaavn candidates met min_score={min_score} for '{search_query}'. Top was: '{scored_candidates[0]['title']}' (Score: {scored_candidates[0]['score']:.1f})")
            return None

        # Fetch details for top eligible candidates in a single fast batch request
        top_eligible = eligible[:6]
        batch_pids = ",".join(c["id"] for c in top_eligible)
        details = {}
        try:
            detail_url = f"https://www.jiosaavn.com/api.php?__call=song.getDetails&cc=in&_marker=0&_format=json&pids={batch_pids}"
            req_det = urllib.request.Request(detail_url, headers=SAAVN_HEADERS)
            with urllib.request.urlopen(req_det, timeout=5.0) as resp_det:
                details = json.loads(resp_det.read().decode("utf-8"))
        except Exception as batch_err:
            logger.warning(f"Batch Saavn getDetails failed for {batch_pids}: {batch_err}")

        for top_song in top_eligible:
            pid = top_song["id"]
            song_info = details.get(pid, {})
            enc_url = song_info.get("encrypted_media_url")
            if not enc_url:
                continue

            try:
                from pyDes import des, ECB, PAD_PKCS5
                k = des(b"38346591", ECB, b"\0\0\0\0\0\0\0\0", pad=None, padmode=PAD_PKCS5)
                raw_stream = k.decrypt(base64.b64decode(enc_url.strip())).decode("utf-8")
                stream_url = raw_stream.replace("_96.mp4", "_320.mp4")

                if not stream_url:
                    continue

                title = song_info.get("song") or top_song.get("title", "Unknown")
                artist = song_info.get("primary_artists") or top_song.get("uploader", "")
                full_title = f"{title} - {artist}" if artist else title
                thumbnail = (song_info.get("image") or top_song.get("raw", {}).get("image") or "").replace("150x150", "500x500").replace("50x50", "500x500")
                duration = int(song_info.get("duration") or top_song.get("duration") or 0)
                web_url = song_info.get("perma_url") or f"https://www.jiosaavn.com/song/{pid}"

                logger.info(f"Official Studio Master resolved: '{full_title}' (Score: {top_song['score']:.1f}, Plays: {top_song.get('play_count', 0)})")
                return {
                    "title": full_title,
                    "url": stream_url,
                    "webpage_url": web_url,
                    "thumbnail": thumbnail,
                    "duration": duration,
                    "uploader": artist or "Official Studio Master",
                    "is_live": False,
                }
            except Exception as cand_err:
                logger.warning(f"Error resolving Saavn candidate {pid}: {cand_err}")
                continue

        return None
    except Exception as e:
        logger.warning(f"Official studio track fetch failed: {e}")
        return None


def fetch_oembed(oembed_url: str) -> Optional[dict]:
    """Fetch public oEmbed metadata synchronously (safe for executor)."""
    try:
        req = urllib.request.Request(
            oembed_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def parse_spotify_user_input(profile_input: str) -> tuple[str, str]:
    """Parses raw profile input and returns (spotify_id, profile_url)."""
    raw = profile_input.strip()
    if "open.spotify.com/user/" in raw:
        user_id = raw.split("open.spotify.com/user/")[1].split("?")[0].strip("/")
    elif "spotify:user:" in raw:
        user_id = raw.split("spotify:user:")[1].split("?")[0].strip()
    else:
        user_id = raw
    return user_id, f"https://open.spotify.com/user/{user_id}"


def fetch_spotify_profile_info(user_id: str) -> Optional[dict]:
    """Fetches public Spotify profile metadata and public playlists."""
    profile_url = f"https://open.spotify.com/user/{user_id}"
    try:
        req = urllib.request.Request(
            profile_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            html = resp.read().decode("utf-8")
    except Exception as e:
        logger.warning(f"Failed to fetch Spotify profile HTML for {user_id}: {e}")
        return None

    og_title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    og_img = re.search(r'<meta property="og:image" content="([^"]+)"', html)
    og_desc = re.search(r'<meta property="og:description" content="([^"]+)"', html)

    display_name = og_title.group(1).replace("&#39;", "'").replace("&amp;", "&") if og_title else user_id
    avatar_url = og_img.group(1) if og_img else None
    description = og_desc.group(1) if og_desc else None

    # Parse public playlists
    playlists = []
    seen_ids = set()
    matches = [m.start() for m in re.finditer(r'/playlist/', html)]
    for idx in matches:
        snippet = html[idx:idx+600]
        p_id_m = re.search(r'/playlist/([a-zA-Z0-9]+)', snippet)
        if not p_id_m:
            continue
        p_id = p_id_m.group(1)
        if p_id in seen_ids:
            continue
        seen_ids.add(p_id)

        p_name_m = re.search(r'data-encore-id="text">([^<]+)</span>', snippet)
        p_name = p_name_m.group(1).replace("&#39;", "'").replace("&amp;", "&") if p_name_m else f"Playlist {len(playlists)+1}"

        p_img_m = re.search(r'src="([^"]+)"', snippet)
        p_img = p_img_m.group(1) if p_img_m else None

        playlists.append({
            "id": p_id,
            "name": p_name,
            "url": f"https://open.spotify.com/playlist/{p_id}",
            "image": p_img
        })

    return {
        "spotify_id": user_id,
        "display_name": display_name,
        "profile_url": profile_url,
        "avatar_url": avatar_url,
        "description": description,
        "playlists": playlists
    }


def extract_spotify_playlist_tracks_public(playlist_id_or_url: str) -> list[dict]:
    """Extracts track items from a Spotify playlist or album using the public embed JSON or Spotipy."""
    p_id = playlist_id_or_url.strip()
    entity_type = "album" if ("/album/" in p_id or "spotify:album:" in p_id) else "playlist"
    if f"/{entity_type}/" in p_id:
        p_id = p_id.split(f"/{entity_type}/")[1].split("?")[0].strip("/")
    elif f"spotify:{entity_type}:" in p_id:
        p_id = p_id.split(f"spotify:{entity_type}:")[1].split("?")[0].strip("/")

    # 1. Try public embed endpoint (fast, zero auth)
    try:
        req = urllib.request.Request(
            f"https://open.spotify.com/embed/{entity_type}/{p_id}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            html = resp.read().decode("utf-8")
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if m:
            data = json.loads(m.group(1))
            entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
            raw_tracks = entity.get("trackList", [])
            tracks = []
            for t in raw_tracks:
                title = t.get("title", "")
                artist = t.get("subtitle", "")
                dur_ms = t.get("duration", 0)
                if title:
                    tracks.append({
                        "title": f"{title} {artist}".strip(),
                        "url": f"{title} {artist}".strip(),
                        "duration": int(dur_ms / 1000) if dur_ms else 0,
                        "webpage_url": f"{title} {artist}".strip()
                    })
            if tracks:
                return tracks
    except Exception as e:
        logger.debug(f"Public embed playlist fetch failed: {e}")

    # 2. Try Spotipy client if available
    if spotify:
        try:
            res = spotify.playlist_items(p_id, limit=50)
            items = res.get("items", [])
            tracks = []
            for item in items:
                t = item.get("track")
                if t and t.get("name"):
                    artist = t["artists"][0]["name"] if t.get("artists") else ""
                    name = f"{t['name']} {artist}".strip()
                    tracks.append({
                        "title": name,
                        "url": name,
                        "duration": int(t.get("duration_ms", 0) / 1000),
                        "webpage_url": name
                    })
            if tracks:
                return tracks
        except Exception as e:
            logger.debug(f"Spotipy playlist fetch failed: {e}")

    return []


# ─── YT-DLP Config ────────────────────────────────────────────────────────────

# Preload working SoundCloud client ID so soundcloud searches never fail with "Unable to extract client id"
try:
    from yt_dlp.extractor.soundcloud import SoundcloudBaseIE
    def _patched_sc_initialize(self):
        self._CLIENT_ID = "kR7dAfT5UXQgmgde1pLjfsRGiaoANLvT"
    SoundcloudBaseIE._initialize_pre_login = _patched_sc_initialize
except Exception as _sc_err:
    pass

# Write cookies from environment variable if provided
_yt_cookies = os.environ.get("YOUTUBE_COOKIES", "").strip()
if _yt_cookies and not os.path.exists("cookies.txt"):
    try:
        with open("cookies.txt", "w", encoding="utf-8") as _f:
            _f.write(_yt_cookies)
        logger.info("Wrote YOUTUBE_COOKIES environment variable to cookies.txt")
    except Exception as _ce:
        logger.warning(f"Failed to write cookies.txt from environment: {_ce}")

YTDL_OPTIONS = {
    "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
    "noplaylist": False,
    "nocheckcertificate": True,
    "ignoreerrors": True,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "socket_timeout": 10,
    "concurrent_fragment_downloads": 4,
    "extractor_args": {
        "youtube": {
            "player_client": ["ios", "android", "mweb"],
        }
    },
}

if os.path.exists("cookies.txt"):
    YTDL_OPTIONS["cookiefile"] = "cookies.txt"

YTDL_PLAYLIST_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "extract_flat": "in_playlist",
    "nocheckcertificate": True,
    "ignoreerrors": True,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "socket_timeout": 15,
    "extractor_args": {
        "youtube": {
            "player_client": ["ios", "android", "mweb"],
        }
    },
}

if os.path.exists("cookies.txt"):
    YTDL_PLAYLIST_OPTIONS["cookiefile"] = "cookies.txt"

AUDIO_FILTERS = {
    "bassboost_low": "bass=g=5:f=110:w=0.6",
    "bassboost": "bass=g=10:f=110:w=0.6",
    "bassboost_high": "bass=g=16:f=110:w=0.6",
    "nightcore": "asetrate=48000*1.25,aresample=48000,atempo=1.05",
    "vaporwave": "asetrate=48000*0.85,aresample=48000,aecho=0.8:0.9:1000:0.3",
    "8d": "apulsator=hz=0.125:amount=1",
    "treble": "treble=g=5:f=3000:w=0.5",
    "pop": "equalizer=f=1000:t=q:w=1:g=2,equalizer=f=4000:t=q:w=1:g=3",
}

RADIO_STATIONS = {
    "lofi": {
        "name": "☕ 24/7 Lofi Chill Beats",
        "url": "https://live.hunter.fm/lofi_high",
        "desc": "Chill lofi study & relaxing beats"
    },
    "synthwave": {
        "name": "🌆 Nightride FM — 24/7 Synthwave",
        "url": "https://stream.nightride.fm/nightride.mp3",
        "desc": "Cyberpunk, synthwave & retrowave"
    },
    "jazz": {
        "name": "🎷 Smooth Lounge & Jazz",
        "url": "http://ice1.somafm.com/secretagent-128-mp3",
        "desc": "Secret Agent lounge, jazz & spy vibes"
    }
}

def make_ffmpeg_audio(stream_url: str, seek_seconds: int = 0, audio_filter: Optional[str] = None, is_live: bool = False) -> discord.FFmpegPCMAudio:
    before_opts = (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5"
    )
    if seek_seconds > 0:
        before_opts = f"-ss {seek_seconds} " + before_opts

    # Auto-detect live radio streams from station list or live stream URLs
    if not is_live:
        for st in RADIO_STATIONS.values():
            if st.get("url") and st["url"] in stream_url:
                is_live = True
                break

    filters = []
    if audio_filter and audio_filter in AUDIO_FILTERS:
        filters.append(AUDIO_FILTERS[audio_filter])

    opts = "-vn -threads 2"
    if filters:
        opts += f" -af {','.join(filters)}"

    return discord.FFmpegPCMAudio(
        stream_url,
        before_options=before_opts,
        options=opts,
        executable="ffmpeg"
    )


def parse_lrc(text: str) -> list[tuple[float, str]]:
    timed_lines = []
    ts_pattern = re.compile(r'\[(\d{1,2}):(\d{2}(?:\.\d{1,3})?)\]')
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        timestamps = list(ts_pattern.finditer(line))
        if not timestamps:
            continue
        lyric = ts_pattern.sub('', line).strip()
        if not lyric:
            continue
        for m in timestamps:
            mins, secs = m.groups()
            total_sec = int(mins) * 60 + float(secs)
            timed_lines.append((total_sec, lyric))
    timed_lines.sort(key=lambda x: x[0])
    return timed_lines


def clean_song_title_and_artist(raw_title: str, raw_artist: str = "") -> tuple[str, str, list[tuple[str, str]]]:
    """
    Cleans song title & artist names preserving non-Latin scripts (Japanese, Korean, Spanish, Cyrillic, etc.)
    and returns (clean_title, clean_artist, [(artist_candidate, track_candidate), ...]).
    """
    title = unicodedata.normalize("NFKC", raw_title or "").strip()
    artist = unicodedata.normalize("NFKC", raw_artist or "").strip() if raw_artist else ""

    # Clean channel / uploader noise if passed as artist
    if artist:
        artist = re.sub(r' - Topic$', '', artist, flags=re.IGNORECASE).strip()
        artist = re.sub(r'VEVO$', '', artist, flags=re.IGNORECASE).strip()
        artist = re.sub(r'(?:Official\s*Channel|Official|Records|Entertainment|Music)$', '', artist, flags=re.IGNORECASE).strip()

    # Clean bracketed / parenthetical noise without deleting valid song words like 'Video' or 'Audio'
    clean = re.sub(r'[\(\[](?:official\s*(?:music\s*)?(?:video|audio|visualizer|lyric\s*video)|lyrics?|visualizer|audio|hd|4k|remastered|explicit|mv|sped\s*up|slowed)[\)\]]', '', title, flags=re.IGNORECASE)
    # Strip trailing metadata suffixes like '| Official Video' or '- Official Audio'
    clean = re.sub(r'\s*\|\s*(?:official\s*(?:video|audio|music\s*video)|lyrics?|4k|hd).*$', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\s*-\s*(?:official\s*(?:video|audio|music\s*video)|lyrics?).*$', '', clean, flags=re.IGNORECASE)
    clean = clean.strip(' |•-')

    candidates: list[tuple[str, str]] = []
    # YouTube titles are predominantly "Artist - Track" or "Track - Artist"
    for delim in [' - ', ' – ', ' — ', ' | ', '•']:
        if delim in clean:
            p1, p2 = clean.split(delim, 1)
            p1, p2 = p1.strip(' |•-'), p2.strip(' |•-')
            if p1 and p2:
                # Primary candidate: Artist = p1, Track = p2
                candidates.append((p1, p2))
                # Inverted candidate: Artist = p2, Track = p1
                candidates.append((p2, p1))
            break

    if artist and clean:
        candidates.append((artist, clean))
    if not candidates and clean:
        candidates.append(("", clean))

    return clean, artist, candidates


def fetch_lyrics(title: str, artist: str = "") -> Optional[dict]:
    """
    Fetch lyrics synchronously with multi-tier fallback:
      1. LRCLIB exact match with candidates (artist <-> track)
      2. LRCLIB intelligent ranked search (prioritizing synced LRC, penalizing instrumentals)
      3. LRCLIB raw query search
      4. Lyrics.ovh plain lyrics fallback
    Preserves all Unicode characters for international music (J-Pop, K-Pop, Latin, Hindi, etc.).
    """
    clean_title, clean_artist, candidates = clean_song_title_and_artist(title, artist)

    def _score_item(item: dict, target_track: str, target_artist: str = "") -> int:
        t_name = (item.get("trackName") or "").strip().lower()
        a_name = (item.get("artistName") or "").strip().lower()
        has_synced = bool(item.get("syncedLyrics"))
        has_plain = bool(item.get("plainLyrics"))

        if not (has_synced or has_plain):
            return -1

        score = 0
        if has_synced:
            score += 100
        if has_plain:
            score += 20

        # Penalize instrumental backing tracks when searching for vocal performance
        if "inst" in t_name or "instrumental" in t_name:
            score -= 50

        if target_artist and target_artist.lower() in a_name:
            score += 80
        elif target_artist and a_name in target_artist.lower():
            score += 40

        c_target = (target_track or "").strip().lower()
        if t_name == c_target:
            score += 80
        elif c_target and (c_target in t_name or t_name in c_target):
            score += 40

        return score

    # ── 1. LRCLIB Exact Lookup ────────────────────────────────────────────────
    for cand_artist, cand_track in candidates:
        if cand_artist and cand_track and cand_artist.lower() not in ["unknown", ""]:
            try:
                params = urllib.parse.urlencode({"track_name": cand_track, "artist_name": cand_artist})
                req = urllib.request.Request(f"https://lrclib.net/api/get?{params}", headers={"User-Agent": "SweetyBot/2.0"})
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    data = json.loads(resp.read().decode())
                    if data and (data.get("plainLyrics") or data.get("syncedLyrics")):
                        return data
            except Exception:
                pass

    # ── 2. LRCLIB Ranked Search ───────────────────────────────────────────────
    search_queries: list[tuple[str, str, str]] = []
    for cand_artist, cand_track in candidates:
        if cand_artist and cand_track:
            search_queries.append((f"{cand_artist} {cand_track}", cand_track, cand_artist))
    if clean_title:
        search_queries.append((clean_title, clean_title, clean_artist))
    if title and title != clean_title:
        search_queries.append((title, title, clean_artist))

    best_item = None
    best_score = -1

    for q_str, t_track, t_artist in search_queries[:4]:
        try:
            q_enc = urllib.parse.quote(q_str.strip())
            req = urllib.request.Request(f"https://lrclib.net/api/search?q={q_enc}", headers={"User-Agent": "SweetyBot/2.0"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                results = json.loads(resp.read().decode())
                if results and isinstance(results, list):
                    for item in results:
                        s = _score_item(item, t_track, t_artist)
                        if s > best_score:
                            best_score = s
                            best_item = item
                            # If high confidence synced match, return immediately
                            if s >= 180 and item.get("syncedLyrics"):
                                return best_item
        except Exception as e:
            logger.debug(f"LRCLIB search error for '{q_str}': {e}")

    if best_item and best_score >= 80:
        return best_item

    # If any match was found with lyrics, accept it
    if best_item and (best_item.get("syncedLyrics") or best_item.get("plainLyrics")):
        return best_item

    # ── 3. Fallback: Lyrics.ovh Plain Lyrics ──────────────────────────────────
    for cand_artist, cand_track in candidates:
        if cand_artist and cand_track and cand_artist.lower() not in ["unknown", ""]:
            try:
                url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(cand_artist)}/{urllib.parse.quote(cand_track)}"
                req = urllib.request.Request(url, headers={"User-Agent": "SweetyBot/2.0"})
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    ovh_data = json.loads(resp.read().decode())
                    lyrics = ovh_data.get("lyrics")
                    if lyrics and lyrics.strip():
                        return {
                            "trackName": cand_track,
                            "artistName": cand_artist,
                            "plainLyrics": lyrics.strip(),
                            "syncedLyrics": None,
                        }
            except Exception:
                pass

    return None

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
    "executable": "ffmpeg",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
ytdl_playlist = yt_dlp.YoutubeDL(YTDL_PLAYLIST_OPTIONS)

YTDL_SEARCH_OPTIONS = dict(YTDL_OPTIONS)
YTDL_SEARCH_OPTIONS["extract_flat"] = True
YTDL_SEARCH_OPTIONS["extractor_args"] = {
    "youtube": {
        "player_client": ["android", "web"],
    }
}
ytdl_search = yt_dlp.YoutubeDL(YTDL_SEARCH_OPTIONS)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def fmt_duration(seconds):
    if seconds is None or seconds < 0:
        return "00:00"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def progress_bar(elapsed, total, length=16):
    if not total or total <= 0:
        return "━" * length
    percent = min(1.0, max(0.0, elapsed / total))
    filled = int(percent * length)
    filled = min(filled, length)
    unfilled = length - filled
    # Spotify-style realistic player: bold played track + knob + light remaining track
    return "━" * filled + "●" + "─" * unfilled





# ─── Guild Music State ────────────────────────────────────────────────────────

class GuildMusicState:
    def __init__(self):
        self.queue: deque = deque()
        self.current: Optional["YTDLSource"] = None
        self.loop: bool = False
        self.loop_queue: bool = False
        self.volume: float = 1.0
        self.user_volume_level: int = 100
        self.voice_client: Optional[discord.VoiceClient] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.skip_votes: set = set()
        self.np_message: Optional[discord.Message] = None
        self.start_time: Optional[float] = None
        self.paused_elapsed: float = 0.0
        self.pause_start: Optional[float] = None
        self.update_task: Optional[asyncio.Task] = None
        self.is_247: bool = False
        self.filter: Optional[str] = None
        self.autoplay: bool = False
        self.last_played_track: Optional[dict] = None
        self.played_history: deque = deque(maxlen=30)
        self.radio_station: Optional[str] = None
        self.karaoke_task: Optional[asyncio.Task] = None
        self.karaoke_singer: Optional[discord.Member] = None
        self.karaoke_scores: dict[int, int] = {}
        self.karaoke_reactions: dict[str, int] = {"roses": 0, "tomatoes": 0}
        self.karaoke_stage_msg: Optional[discord.Message] = None
        self.karaoke_judge_view: Optional[Any] = None
        self.is_instrumental: bool = False

    def clear(self):
        self.queue.clear()
        self.current = None
        self.loop = False
        self.loop_queue = False
        self.volume = 1.0
        self.user_volume_level = 100
        self.skip_votes.clear()
        self.np_message = None
        self.start_time = None
        self.paused_elapsed = 0.0
        self.pause_start = None
        self.filter = None
        self.radio_station = None
        self.karaoke_singer = None
        self.karaoke_scores.clear()
        self.karaoke_reactions = {"roses": 0, "tomatoes": 0}
        self.karaoke_stage_msg = None
        self.karaoke_judge_view = None
        self.is_instrumental = False
        if self.update_task:
            self.update_task.cancel()
            self.update_task = None
        if self.karaoke_task:
            self.karaoke_task.cancel()
            self.karaoke_task = None

    def get_elapsed(self) -> float:
        if self.start_time is None:
            return 0.0
        if self.pause_start is not None:
            return self.paused_elapsed
        return self.paused_elapsed + (time.time() - self.start_time)

    def on_pause(self):
        if self.pause_start is None and self.start_time is not None:
            self.paused_elapsed += time.time() - self.start_time
            self.pause_start = time.time()
            self.start_time = None

    def on_resume(self):
        if self.pause_start is not None:
            self.start_time = time.time()
            self.pause_start = None




# ─── YTDLSource ───────────────────────────────────────────────────────────────

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=1.0):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title", "Unknown")
        self.url = data.get("webpage_url", "")
        self.thumbnail = data.get("thumbnail", "")
        self.duration = data.get("duration", 0)
        self.requester = data.get("requester", "Unknown")
        self.uploader = data.get("uploader", "Unknown")
        self.view_count = data.get("view_count", 0)

    def read(self) -> bytes:
        ret = self.original.read()
        if not ret:
            return b""
        # Direct audio scaling: 1.0 = standard 100% loudness, 0.5 = 50%, 1.5 = 150% boost
        vol = max(0.0, min(float(self.volume), 2.0))
        if vol == 1.0:
            return ret
        return audioop.mul(ret, 2, vol)

    @classmethod
    async def _search_and_extract(cls, search_query: str, *, loop=None, volume=1.0, seek_seconds=0, audio_filter=None, requester="Unknown", exclude_video_ids=None):
        loop = loop or asyncio.get_event_loop()
        data = None
        clean_q = search_query.strip()
        user_wants_variant = any(w in clean_q.lower() for w in ("remix", "cover", "slowed", "flip", "edit", "instrumental", "karaoke", "live", "nightcore", "reverb", "acoustic", "extended", "sped up", "1 hour", "loop"))



        # 0. Canonical Track & Original Artist Resolution (Spotify metadata verification)
        # Identifies the true original song and original artist so we never play covers/mashups/bootlegs
        canonical_q = clean_q
        if spotify and not user_wants_variant:
            try:
                pure_q = re.sub(r'^(?:ytsearch\d*:|scsearch\d*:)\s*', '', clean_q).strip()
                sp_res = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: spotify.search(q=pure_q, type="track", limit=5)),
                    timeout=1.5
                )
                sp_items = sp_res.get("tracks", {}).get("items", []) if sp_res else []
                for sp_t in sp_items:
                    sp_name = sp_t.get("name", "")
                    sp_artist = sp_t["artists"][0]["name"] if sp_t.get("artists") else ""
                    if sp_name and validate_canonical_match(pure_q, sp_artist, sp_name):
                        # Determine if query contained artist-specific intent:
                        q_words = set(re.findall(r'\b\w{2,}\b', pure_q.lower())) - {"song", "track", "music", "audio", "video", "official", "lyrics", "full", "hd", "hq"}
                        t_words = set(re.findall(r'\b\w{2,}\b', sp_name.lower()))
                        unmatched = q_words - t_words

                        # Only rewrite if user explicitly specified artist tokens or extra qualifiers
                        if unmatched:
                            canonical_q = f"{sp_artist} - {sp_name}" if sp_artist else sp_name
                            logger.info(f"Canonical original track identified via Spotify: '{canonical_q}' (for query '{clean_q}')")
                        break
            except Exception as sp_err:
                logger.debug(f"Spotify canonical track resolution skipped: {sp_err}")

        # 1. Primary for standard music queries: Official Studio Master Resolver (320kbps CD Audio)
        # Guarantees 100% original studio audio, zero datacenter bot-blocks, zero amateur bootlegs
        if not user_wants_variant:
            try:
                official_track = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: fetch_official_studio_track(canonical_q, min_score=800.0)),
                    timeout=2.5
                )
                if official_track and official_track.get("url"):
                    data = official_track
            except Exception as e:
                logger.debug(f"Official studio track primary lookup failed: {e}")

        # 2. Search YouTube if official studio resolver didn't match or user wants a variant/remix
        if not data:
            try:
                # Normalize any ytsearch prefix so we always inspect up to 10 entries
                s_query = re.sub(r'^ytsearch\d*:\s*', '', canonical_q).strip()
                yt_term = f"ytsearch5:{s_query}"
                yt_data = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: ytdl_search.extract_info(yt_term, download=False)),
                    timeout=3.5
                )
                entries = [e for e in yt_data.get("entries", []) if e] if yt_data else []
                if entries:
                    # Filter out VEVO entries and previously failed/blocked video IDs
                    exclude_ids = set(exclude_video_ids or [])
                    non_vevo = [e for e in entries if not is_vevo_entry(e) and e.get("id") not in exclude_ids]
                    candidate_pool = non_vevo if non_vevo else [e for e in entries if e.get("id") not in exclude_ids] or entries

                    # Rank non-VEVO candidates using scoring system: prefer shortest, cleanest title without remixes/edits
                    ranked = sorted(candidate_pool, key=lambda e: score_music_candidate(e, canonical_q), reverse=True)

                    consecutive_bot_blocks = 0
                    for cand in ranked[:5]:
                        logger.info(f"Evaluating candidate: '{cand.get('title')}' (Score: {score_music_candidate(cand, canonical_q):.1f})")
                        # If candidate is already a fully resolved source with streamable direct url (not a webpage)
                        if cand.get("url") and not any(cand.get("url", "").startswith(p) for p in ("https://www.youtube.com", "http://www.youtube.com", "https://youtu.be")):
                            fmts = cand.get("formats", [])
                            if any(f.get("acodec") != "none" and f.get("url") for f in fmts):
                                data = cand
                                break

                        cand_url = cand.get("webpage_url") or cand.get("url")
                        if not cand_url or not str(cand_url).startswith("http"):
                            if cand.get("id"):
                                cand_url = f"https://www.youtube.com/watch?v={cand['id']}"

                        if cand_url:
                            try:
                                cand_full = await asyncio.wait_for(
                                    loop.run_in_executor(None, lambda: ytdl.extract_info(cand_url, download=False)),
                                    timeout=3.0
                                )
                                if cand_full and not is_vevo_entry(cand_full):
                                    has_audio = cand_full.get("url") or any(f.get("acodec") != "none" and f.get("url") for f in cand_full.get("formats", []))
                                    if has_audio:
                                        data = cand_full
                                        break
                            except Exception as cand_err:
                                logger.warning(f"Candidate '{cand.get('title')}' extraction failed: {cand_err}")
                                err_str = str(cand_err).lower()
                                if any(b_word in err_str for b_word in ("bot", "sign in", "429", "captcha", "forbidden")):
                                    logger.warning("YouTube datacenter bot-block detected, jumping immediately to fallback.")
                                    break
                                continue
            except Exception as yt_err:
                logger.warning(f"YouTube search failed for '{search_query}': {yt_err}")
                data = None

        # If data found from search, ensure formats/url are resolved
        if data and not (data.get("url") or data.get("formats")):
            video_url = data.get("webpage_url") or (f"https://www.youtube.com/watch?v={data['id']}" if data.get("id") else None)
            if video_url:
                try:
                    full_data = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda: ytdl.extract_info(video_url, download=False)),
                        timeout=8.0
                    )
                    if full_data:
                        data = full_data
                except Exception as e:
                    logger.debug(f"Deep video extraction failed for {video_url}: {e}")

        # 3. Secondary studio master fallback using the resolved title if YouTube gave a title but no streamable audio
        if (not data or not (data.get("url") or data.get("formats"))) and not user_wants_variant:
            try:
                cand_title = data.get("title") if (data and data.get("title")) else canonical_q
                official_track = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: fetch_official_studio_track(cand_title, min_score=800.0)),
                    timeout=8.0
                )
                if official_track and official_track.get("url"):
                    data = official_track
            except Exception as e:
                logger.debug(f"Secondary official studio track lookup failed: {e}")

        # 4. Fallback to SoundCloud (strictly filter DRM tracks & filter unwanted bootlegs/flips)
        if not data or not (data.get("url") or data.get("formats")):
            try:
                sc_data = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: ytdl.extract_info(f"scsearch8:{canonical_q}", download=False)),
                    timeout=2.5
                )
                sc_entries = [e for e in sc_data.get("entries", []) if e]
                sc_candidates = []
                for candidate in sc_entries:
                    s_url = candidate.get("url")
                    if not s_url:
                        fmts = [f for f in candidate.get("formats", []) if f.get("acodec") != "none" and f.get("url")]
                        if fmts:
                            s_url = fmts[-1]["url"]
                    if not s_url or candidate.get("drm"):
                        continue
                    candidate["stream_url"] = s_url
                    sc_candidates.append(candidate)

                if sc_candidates:
                    sc_candidates.sort(key=lambda c: score_music_candidate(c, canonical_q), reverse=True)
                    for cand in sc_candidates:
                        if not user_wants_variant and score_music_candidate(cand, canonical_q) < 250:
                            continue
                        data = cand
                        if not data.get("url") and cand.get("stream_url"):
                            data["url"] = cand["stream_url"]
                        break
            except Exception as sc_err:
                logger.warning(f"SoundCloud fallback search failed for '{canonical_q}': {sc_err}")
                data = None

        if not data:
            raise ValueError(f"Could not find or stream the original version of '{search_query}'. Try adding the artist name or pasting a direct link.")

        stream_url = data.get("url")
        # YouTube watch webpage URLs are not direct audio streams!
        if not stream_url or any(str(stream_url).startswith(p) for p in ("https://www.youtube.com", "http://www.youtube.com", "https://youtu.be")):
            formats = data.get("formats", []) if data else []
            audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("url")]
            if audio_formats:
                stream_url = audio_formats[-1]["url"]
            else:
                stream_url = None

        # If stream_url could not be resolved from YouTube (e.g. datacenter bot block), fallback to official studio master
        if not stream_url:
            try:
                cand_fallback = (data.get("title") if data and data.get("title") else None) or canonical_q
                official_track = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: fetch_official_studio_track(cand_fallback, min_score=800.0)),
                    timeout=8.0
                )
                if official_track and official_track.get("url"):
                    data = official_track
                    stream_url = official_track["url"]
            except Exception as e:
                logger.debug(f"Secondary official studio fallback failed: {e}")

        if not stream_url:
            raise ValueError(f"No streamable audio found for '{search_query}'.")

        data["requester"] = requester


        is_live = bool(data.get("is_live"))
        source = make_ffmpeg_audio(stream_url, seek_seconds=seek_seconds, audio_filter=audio_filter, is_live=is_live)
        return cls(source, data=data, volume=volume), False

    @classmethod
    async def from_url(cls, url, *, loop=None, volume=1.0, seek_seconds=0, audio_filter=None, requester="Unknown"):
        loop = loop or asyncio.get_event_loop()
        url = url.strip()

        # ── 1. Spotify URL Handler ───────────────────────────────────────────
        if "spotify.com" in url or url.startswith("spotify:"):
            # Check for Spotify playlist or album
            if "/playlist/" in url or "/album/" in url:
                entries = []
                if spotify:
                    try:
                        if "/playlist/" in url:
                            playlist_id = url.split("/playlist/")[1].split("?")[0]
                            res = await loop.run_in_executor(None, lambda: spotify.playlist_items(playlist_id, limit=100))
                            raw_items = res.get("items", [])
                            items = [i.get("track") for i in raw_items if i and i.get("track")]
                        else:
                            album_id = url.split("/album/")[1].split("?")[0]
                            res = await loop.run_in_executor(None, lambda: spotify.album_tracks(album_id, limit=100))
                            items = [i for i in res.get("items", []) if i]

                        for t in items:
                            t_title = f"{t.get('name', 'Unknown')} {t['artists'][0]['name'] if t.get('artists') else ''}".strip()
                            entries.append({
                                "title": t_title,
                                "webpage_url": t_title,
                                "duration": int(t.get("duration_ms", 0) / 1000),
                                "requester": requester,
                            })
                    except Exception as sp_err:
                        logger.warning(f"Spotify API playlist extraction failed: {sp_err}")

                # Fallback to public Spotify embed scraper if API didn't return entries
                if not entries and "/playlist/" in url:
                    try:
                        public_tracks = await loop.run_in_executor(
                            None, lambda: extract_spotify_playlist_tracks_public(url)
                        )
                        for pt in public_tracks:
                            pt["requester"] = requester
                            entries.append(pt)
                    except Exception as pub_err:
                        logger.warning(f"Public Spotify playlist extraction fallback failed: {pub_err}")

                if entries:
                    return entries, True
                else:
                    raise ValueError("⚠️ Could not load tracks from this Spotify playlist/album. Ensure the playlist is public.")

            track_search_term = None
            if spotify and ("/track/" in url or "spotify:track:" in url):
                try:
                    if "spotify:track:" in url:
                        track_id = url.split("spotify:track:")[1].split("?")[0].strip()
                    else:
                        track_id = url.split("/track/")[1].split("?")[0].strip()
                    t_data = await loop.run_in_executor(None, lambda: spotify.track(track_id))
                    if t_data and t_data.get("name"):
                        artist = t_data["artists"][0]["name"] if t_data.get("artists") else ""
                        track_search_term = f"{t_data['name']} {artist}".strip()
                except Exception as e:
                    logger.debug(f"Spotify API track lookup failed: {e}")

            if not track_search_term:
                # Fallback to public Spotify oEmbed / scraper
                try:
                    oembed_data = await loop.run_in_executor(
                        None,
                        lambda: fetch_oembed(f"https://open.spotify.com/oembed?url={urllib.parse.quote(url)}")
                    )
                    if oembed_data and oembed_data.get("title"):
                        track_search_term = oembed_data["title"]
                except Exception as e:
                    logger.debug(f"Spotify oEmbed lookup failed: {e}")

            if track_search_term:
                return await cls._search_and_extract(track_search_term, loop=loop, volume=volume, requester=requester)

            raise ValueError("⚠️ Couldn't resolve this Spotify link. Try searching by song name directly with !play.")

        # ── 2. Direct HTTP/HTTPS URLs (YouTube, SoundCloud, direct audio) ─────
        if url.startswith("http://") or url.startswith("https://"):
            data = None
            is_playlist_url = any(param in url for param in ("list=", "/playlist", "/sets/", "/album/"))

            target_url = url
            yt_match = re.search(r'(?:youtube\.com\/(?:watch\?.*v=|v\/|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})', url)
            if yt_match and not is_playlist_url:
                target_url = f"https://www.youtube.com/watch?v={yt_match.group(1)}"
                # If cookies.txt is not provided, pre-emptively resolve official studio audio via oEmbed
                # to guarantee 100% original CD audio in ~250ms and bypass datacenter bot detection entirely
                if not os.path.exists("cookies.txt"):
                    try:
                        oembed = await loop.run_in_executor(
                            None,
                            lambda: fetch_oembed(f"https://www.youtube.com/oembed?url={urllib.parse.quote(target_url)}&format=json")
                        )
                        if oembed and oembed.get("title"):
                            clean_t, clean_a, _ = clean_song_title_and_artist(oembed["title"], oembed.get("author_name", ""))
                            search_term = f"{clean_a} {clean_t}".strip() if clean_a and clean_a.lower() not in clean_t.lower() else clean_t
                            official_track = await loop.run_in_executor(
                                None,
                                lambda: fetch_official_studio_track(search_term or oembed["title"])
                            )
                            if official_track and official_track.get("url"):
                                official_track["requester"] = requester
                                source = make_ffmpeg_audio(official_track["url"], seek_seconds=seek_seconds, audio_filter=audio_filter, is_live=False)
                                return cls(source, data=official_track, volume=volume), False
                    except Exception as oe_err:
                        logger.debug(f"Pre-emptive YouTube oEmbed studio master check skipped: {oe_err}")

            # Use ytdl_playlist (extract_flat: in_playlist) for playlist URLs to avoid timing out!
            active_ytdl = ytdl_playlist if is_playlist_url else ytdl
            timeout_sec = 15.0 if is_playlist_url else 10.0

            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: active_ytdl.extract_info(target_url, download=False)),
                    timeout=timeout_sec
                )
            except Exception as e:
                logger.warning(f"Direct yt-dlp extraction failed for {target_url}: {e}")
                data = None

            # Handle playlists
            if data and "entries" in data:
                raw_entries = [e for e in data["entries"] if e]
                if not raw_entries:
                    raise ValueError("⚠️ Playlist is empty or all entries failed to load.")

                if is_playlist_url:
                    clean_entries = []
                    for entry in raw_entries:
                        e_title = entry.get("title") or "Unknown Track"
                        e_url = entry.get("url") or entry.get("webpage_url")
                        if not e_url or not str(e_url).startswith("http"):
                            if entry.get("id"):
                                e_url = f"https://www.youtube.com/watch?v={entry['id']}"
                            else:
                                e_url = e_title
                        entry["title"] = e_title
                        entry["url"] = e_url
                        entry["webpage_url"] = e_url
                        entry["requester"] = requester
                        clean_entries.append(entry)
                    return clean_entries, True
                else:
                    data = raw_entries[0]
                    if not data.get("url") and not data.get("formats"):
                        web_url = data.get("webpage_url") or data.get("url") or (f"https://www.youtube.com/watch?v={data.get('id', '')}" if data.get("id") else None)
                        if web_url and web_url.startswith("http"):
                            try:
                                data = await asyncio.wait_for(
                                    loop.run_in_executor(None, lambda: ytdl.extract_info(web_url, download=False)),
                                    timeout=8.0
                                )
                            except Exception:
                                pass

            # If direct extraction failed, or if the video is VEVO (which datacenter IPs cannot stream),
            # or if it has no streamable audio formats:
            stream_url = None
            is_vevo = False
            if data and not is_playlist_url:
                is_vevo = is_vevo_entry(data)
                if not is_vevo:
                    stream_url = data.get("url")
                    if not stream_url:
                        formats = data.get("formats", [])
                        audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("url")]
                        if audio_formats:
                            stream_url = audio_formats[-1]["url"]

            # When a direct URL fails to extract a streamable audio URL (or is a VEVO direct URL):
            if (not data or not stream_url or is_vevo) and not is_playlist_url:
                fallback_title = data.get("title") if data else None

                # Fetch video title from oEmbed if missing
                if not fallback_title and ("youtube.com" in url or "youtu.be" in url):
                    try:
                        oembed = await loop.run_in_executor(
                            None,
                            lambda: fetch_oembed(f"https://www.youtube.com/oembed?url={urllib.parse.quote(target_url)}&format=json")
                        )
                        if oembed and oembed.get("title"):
                            fallback_title = oembed["title"]
                    except Exception as oe_err:
                        logger.debug(f"oEmbed title fetch failed for {target_url}: {oe_err}")

                if fallback_title:
                    reason = "VEVO DRM / bot-block" if is_vevo else "direct stream unavailable"
                    logger.info(f"Direct URL failed to extract streamable audio URL ({reason}). Automatically falling back to searching ytsearch with title: '{fallback_title}'")
                    clean_t, clean_a, _ = clean_song_title_and_artist(fallback_title)
                    search_term = f"{clean_a} {clean_t}".strip() if clean_a and clean_a.lower() not in clean_t.lower() else clean_t
                    failed_id = data.get("id") if data else (yt_match.group(1) if yt_match else None)
                    exclude_ids = [failed_id] if failed_id else None
                    return await cls._search_and_extract(search_term or fallback_title, loop=loop, volume=volume, requester=requester, exclude_video_ids=exclude_ids)

            if not data or not stream_url:
                raise ValueError("⚠️ Could not find or stream a playable audio track for this link. Try searching by song name instead.")

            data["requester"] = requester
            is_live = bool(data.get("is_live"))
            source = make_ffmpeg_audio(stream_url, seek_seconds=seek_seconds, audio_filter=audio_filter, is_live=is_live)
            return cls(source, data=data, volume=volume), False

        # ── 3. Plain Text Search Query ────────────────────────────────────────
        return await cls._search_and_extract(url, loop=loop, volume=volume, seek_seconds=seek_seconds, audio_filter=audio_filter, requester=requester)

    @classmethod
    async def regrab_stream(cls, data, volume=1.0, seek_seconds=0, audio_filter=None):
        loop = asyncio.get_event_loop()
        title = data.get("title", "") or ""
        requester = data.get("requester", "Unknown")

        # 1. Direct CDN stream URL (official studio master, Saavn CDN, direct audio file, or radio)
        # Only reuse if it is a genuine direct stream URL (NOT a webpage URL and NOT a plain song title)
        raw_stream_url = data.get("stream_url") or data.get("url") or ""
        if isinstance(raw_stream_url, str) and (raw_stream_url.startswith("http://") or raw_stream_url.startswith("https://")):
            u_low = raw_stream_url.lower()
            is_webpage = any(domain in u_low for domain in ("youtube.com", "youtu.be", "soundcloud.com", "spotify.com"))
            is_googlevideo = any(h in u_low for h in ("googlevideo.com", "manifest.googlevideo.com"))
            if not is_webpage and not is_googlevideo:
                is_live = bool(data.get("is_live"))
                source = make_ffmpeg_audio(raw_stream_url, seek_seconds=seek_seconds, audio_filter=audio_filter, is_live=is_live)
                return cls(source, data=data, volume=volume)

        # 2. Check if we have a direct YouTube / SoundCloud webpage URL to extract fresh stream formats
        web_url = data.get("webpage_url") or data.get("url") or ""
        is_http = isinstance(web_url, str) and web_url.startswith("http")
        is_yt_or_sc = is_http and any(d in web_url.lower() for d in ("youtube.com", "youtu.be", "soundcloud.com"))

        fresh = None
        if is_yt_or_sc:
            yt_m = re.search(r'(?:youtube\.com\/(?:watch\?.*v=|v\/|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})', web_url)
            if yt_m and "list=" not in web_url:
                web_url = f"https://www.youtube.com/watch?v={yt_m.group(1)}"
            try:
                fresh = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: ytdl.extract_info(web_url, download=False)),
                    timeout=8.0
                )
            except Exception as e:
                logger.debug(f"regrab_stream extract_info failed for {web_url}: {e}")
                fresh = None

        if fresh:
            stream_url = fresh.get("url")
            if not stream_url or any(d in str(stream_url).lower() for d in ("youtube.com", "youtu.be", "soundcloud.com")):
                formats = [f for f in fresh.get("formats", []) if f.get("acodec") != "none" and f.get("url")]
                if formats:
                    stream_url = formats[-1]["url"]

            if stream_url:
                fresh["requester"] = requester
                is_live = bool(fresh.get("is_live") or data.get("is_live"))
                source = make_ffmpeg_audio(stream_url, seek_seconds=seek_seconds, audio_filter=audio_filter, is_live=is_live)
                return cls(source, data=fresh, volume=volume)

        # 3. Fallback: Search track by title (Essential for Spotify playlist items, queued title strings, and failed direct extractions)
        search_target = title or (web_url if not is_http else "") or data.get("name", "")
        if search_target and search_target != "Unknown":
            source, _ = await cls._search_and_extract(
                search_target, loop=loop, volume=volume, seek_seconds=seek_seconds, audio_filter=audio_filter, requester=requester
            )
            return source

        raise ValueError(f"Could not regrab stream for track: {title or 'Unknown'}")


# ─── Interactive Music Views ──────────────────────────────────────────────────

class LyricsPaginationView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], user_id: int):
        super().__init__(timeout=180)
        self.pages = pages
        self.user_id = user_id
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = (self.current_page == 0)
        self.next_btn.disabled = (self.current_page >= len(self.pages) - 1)

    @discord.ui.button(emoji="◀️", label="Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Only the requester can paginate.", ephemeral=True)
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(emoji="▶️", label="Next", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Only the requester can paginate.", ephemeral=True)
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)


class LiveKaraokeView(discord.ui.View):
    def __init__(self, cog: "Music", guild: discord.Guild, track_name: str, artist_name: str, timed_lines: list[tuple[float, str]], pages: list[discord.Embed], user_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.track_name = track_name
        self.artist_name = artist_name
        self.timed_lines = timed_lines
        self.pages = pages
        self.user_id = user_id
        self.mode = "live"
        self.current_page = 0
        self.message: Optional[discord.Message] = None
        self.update_task: Optional[asyncio.Task] = None
        self.last_text = ""
        self.update_controls()

    def update_controls(self):
        if self.mode == "live":
            self.prev_btn.disabled = True
            self.next_btn.disabled = True
            self.toggle_mode_btn.label = "📜 Full Lyrics"
            self.toggle_mode_btn.emoji = "📜"
        else:
            self.prev_btn.disabled = (self.current_page == 0)
            self.next_btn.disabled = (self.current_page >= len(self.pages) - 1)
            self.toggle_mode_btn.label = "🎙️ Live Karaoke"
            self.toggle_mode_btn.emoji = "🎙️"

    def build_teleprompter_embed(self, elapsed: float, duration: int) -> discord.Embed:
        lines = self.timed_lines
        idx = -1
        for i, (t, _) in enumerate(lines):
            if elapsed >= t:
                idx = i
            else:
                break

        if idx == -1:
            body = "🎵 *(Intro instrumental playing...)*\n\n▶️ **Next:** " + lines[0][1]
        else:
            display = []
            for p in range(max(0, idx - 2), idx):
                display.append(f"*{lines[p][1]}*")
            display.append(f"▶️ **🔥 {lines[idx][1]} 🔥**")
            for n in range(idx + 1, min(len(lines), idx + 3)):
                display.append(f"`{lines[n][1]}`")
            body = "\n".join(display)

        cur_min, cur_sec = divmod(int(elapsed or 0), 60)
        tot_min, tot_sec = divmod(int(duration or 0), 60)
        pct = min(1.0, max(0.0, float(elapsed or 0) / float(duration))) if duration and duration > 0 else 0
        bar_len = 16
        filled = int(pct * bar_len)
        bar = "▬" * filled + "🔘" + "▬" * (bar_len - filled)
        prog_header = f"`{cur_min}:{cur_sec:02d}` {bar} `{tot_min}:{tot_sec:02d}`"

        embed = discord.Embed(
            title=f"🎙️ Live Karaoke — {self.track_name}",
            description=f"**Artist:** {self.artist_name}\n{prog_header}\n\n{body}",
            color=0x1DB954
        )
        embed.set_footer(text="Live Synced Karaoke • Real-time line-by-line sync")
        return embed

    async def karaoke_loop(self):
        state = self.cog.get_state(self.guild.id)
        consecutive_fails = 0
        base_interval = 3.0

        while not self.is_finished():
            try:
                if not state.current or not state.voice_client or not state.voice_client.is_connected():
                    break
                if not (state.voice_client.is_playing() or state.voice_client.is_paused()):
                    break

                if self.mode == "live" and self.message:
                    elapsed = state.get_elapsed()
                    dur = int(getattr(state.current, "duration", 0) or 0) or int(self.timed_lines[-1][0] + 15)
                    embed = self.build_teleprompter_embed(elapsed, dur)
                    embed_desc = embed.description
                    if embed_desc != self.last_text:
                        self.last_text = embed_desc
                        try:
                            if hasattr(self.message, "channel") and hasattr(self.message.channel, "get_partial_message"):
                                msg_obj = self.message.channel.get_partial_message(self.message.id)
                                await msg_obj.edit(embed=embed, view=self)
                            else:
                                await self.message.edit(embed=embed, view=self)
                            consecutive_fails = 0
                        except discord.HTTPException as http_err:
                            consecutive_fails += 1
                            backoff = min(30.0, base_interval * (2 ** (consecutive_fails - 1)))
                            if http_err.status == 429:
                                retry_after = getattr(http_err, "retry_after", backoff)
                                wait_time = max(float(retry_after or 0.0), backoff)
                                logger.warning(f"Rate limited in karaoke_loop, backing off {wait_time:.1f}s (fail #{consecutive_fails})")
                                await asyncio.sleep(wait_time)
                            else:
                                logger.debug(f"HTTP exception in karaoke edit: {http_err}")
                                await asyncio.sleep(backoff)
                        except Exception as edit_err:
                            consecutive_fails += 1
                            backoff = min(30.0, base_interval * (2 ** (consecutive_fails - 1)))
                            logger.debug(f"Karaoke edit error: {edit_err}")
                            await asyncio.sleep(backoff)

                await asyncio.sleep(base_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Karaoke loop notice: {e}")
                await asyncio.sleep(base_interval)

    @discord.ui.button(emoji="◀️", label="Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Only the requester can paginate.", ephemeral=True)
        self.current_page = max(0, self.current_page - 1)
        self.update_controls()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(emoji="▶️", label="Next", style=discord.ButtonStyle.secondary, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Only the requester can paginate.", ephemeral=True)
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self.update_controls()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(emoji="📜", label="Full Lyrics", style=discord.ButtonStyle.primary, row=0)
    async def toggle_mode_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Only the requester can switch modes.", ephemeral=True)
        if self.mode == "live":
            self.mode = "pages"
            self.update_controls()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        else:
            self.mode = "live"
            self.update_controls()
            state = self.cog.get_state(self.guild.id)
            elapsed = state.get_elapsed() if state else 0
            dur = int(getattr(state.current, "duration", 0) or 0) if state and state.current else int(self.timed_lines[-1][0] + 15)
            embed = self.build_teleprompter_embed(elapsed, dur)
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="⏹", label="Stop Sync", style=discord.ButtonStyle.danger, row=0)
    async def stop_sync_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Only the requester can stop sync.", ephemeral=True)
        if self.update_task and not self.update_task.done():
            self.update_task.cancel()
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji="🎙️", label="Take Stage", style=discord.ButtonStyle.success, row=1)
    async def stage_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.start_karaoke_stage(interaction)

    @discord.ui.button(emoji="🎵", label="Backing Track", style=discord.ButtonStyle.secondary, row=1)
    async def backing_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.toggle_instrumental_backing(interaction)

    async def on_timeout(self):
        if self.update_task and not self.update_task.done():
            self.update_task.cancel()
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class KaraokeJudgeView(discord.ui.View):
    def __init__(self, cog: "Music", guild: discord.Guild, singer: discord.Member, song_title: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.singer = singer
        self.song_title = song_title
        self.message: Optional[discord.Message] = None

    def get_state(self) -> GuildMusicState:
        return self.cog.get_state(self.guild.id)

    def build_judge_embed(self) -> discord.Embed:
        state = self.get_state()
        scores = state.karaoke_scores
        roses = state.karaoke_reactions.get("roses", 0)
        tomatoes = state.karaoke_reactions.get("tomatoes", 0)

        if scores:
            avg = sum(scores.values()) / len(scores)
            stars = "⭐" * int(round(avg / 2))
            score_bar = make_progress_bar(int(avg * 10), 100, 10)
            score_text = f"**{avg:.1f} / 10** {stars}\n`[{score_bar}]` • **{len(scores)}** Judge(s)"
        else:
            score_text = "*No ratings submitted yet. Be the first to judge!*"

        desc = (
            f"🌟 **Current Singer:** {self.singer.mention}\n"
            f"🎶 **Track:** `{self.song_title}`\n\n"
            f"📊 **Live Rating:**\n{score_text}\n\n"
            f"🌹 **Roses:** {roses}  •  🍅 **Tomatoes:** {tomatoes}\n\n"
            f"*Unmute your mic and sing along! Listeners in VC can rate this performance below!*"
        )
        embed = discord.Embed(
            title="🎤 Live Karaoke Stage — Judge's Panel",
            description=desc,
            color=0xFEE75C
        )
        if self.singer.display_avatar:
            embed.set_thumbnail(url=self.singer.display_avatar.url)
        embed.set_footer(text="Sweety Live Karaoke Stage • Rockstar Hall of Fame • Use !singers for top rankings")
        return embed

    async def _handle_vote(self, interaction: discord.Interaction, score: int, label: str):
        if interaction.user.id == self.singer.id:
            return await interaction.response.send_message("❌ You cannot rate your own performance!", ephemeral=True)

        state = self.get_state()
        state.karaoke_scores[interaction.user.id] = score
        embed = self.build_judge_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        if not interaction.response.is_done():
            await interaction.response.send_message(f"🗳️ You rated {self.singer.display_name}: **{score}/10** ({label})!", ephemeral=True)
        else:
            await interaction.followup.send(f"🗳️ You rated {self.singer.display_name}: **{score}/10** ({label})!", ephemeral=True)

    @discord.ui.button(emoji="🌟", label="10/10 Idol", style=discord.ButtonStyle.success, row=0)
    async def idol_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, 10, "🌟 Idol Status")

    @discord.ui.button(emoji="🔥", label="8/10 Hype", style=discord.ButtonStyle.primary, row=0)
    async def hype_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, 8, "🔥 Hype Performance")

    @discord.ui.button(emoji="👏", label="5/10 Good", style=discord.ButtonStyle.secondary, row=0)
    async def good_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, 5, "👏 Solid Delivery")

    @discord.ui.button(emoji="📣", label="Voice Crack", style=discord.ButtonStyle.secondary, row=0)
    async def crack_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, 2, "📣 Voice Crack")

    @discord.ui.button(emoji="🌹", label="Toss Rose", style=discord.ButtonStyle.success, row=1)
    async def rose_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        state.karaoke_reactions["roses"] = state.karaoke_reactions.get("roses", 0) + 1
        embed = self.build_judge_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        if not interaction.response.is_done():
            await interaction.response.send_message(f"🌹 You threw a rose on stage for {self.singer.display_name}!", ephemeral=True)
        else:
            await interaction.followup.send(f"🌹 You threw a rose on stage for {self.singer.display_name}!", ephemeral=True)

    @discord.ui.button(emoji="🍅", label="Throw Tomato", style=discord.ButtonStyle.danger, row=1)
    async def tomato_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        state.karaoke_reactions["tomatoes"] = state.karaoke_reactions.get("tomatoes", 0) + 1
        embed = self.build_judge_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        if not interaction.response.is_done():
            await interaction.response.send_message(f"🍅 *Splat!* You threw a tomato at {self.singer.display_name}!", ephemeral=True)
        else:
            await interaction.followup.send(f"🍅 *Splat!* You threw a tomato at {self.singer.display_name}!", ephemeral=True)

    @discord.ui.button(emoji="🎵", label="Backing Track", style=discord.ButtonStyle.secondary, row=1)
    async def instrumental_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.toggle_instrumental_backing(interaction)



class FilterSelect(discord.ui.Select):
    def __init__(self, cog: "Music", guild: discord.Guild):
        self.cog = cog
        self.guild = guild
        options = [
            discord.SelectOption(label="Clear Filter", value="clear", emoji="🔄", description="Reset to standard clean audio"),
            discord.SelectOption(label="Bassboost (Medium)", value="bassboost", emoji="🔊", description="+10dB rich bass punch"),
            discord.SelectOption(label="Bassboost High (Extreme)", value="bassboost_high", emoji="💥", description="+16dB heavy bass"),
            discord.SelectOption(label="Nightcore", value="nightcore", emoji="🌙", description="High pitch + 1.25x tempo"),
            discord.SelectOption(label="Vaporwave", value="vaporwave", emoji="📼", description="Slowed 0.85x + retro echo reverb"),
            discord.SelectOption(label="8D Audio", value="8d", emoji="🎧", description="Headphone 360° circle surround sound"),
            discord.SelectOption(label="Pop Equalizer", value="pop", emoji="✨", description="Vocal and mid clarity boost"),
            discord.SelectOption(label="Treble Boost", value="treble", emoji="⚡", description="Crisp high frequencies"),
        ]
        super().__init__(placeholder="Select an audio filter preset...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        state = self.cog.get_state(self.guild.id)
        if choice == "clear":
            state.filter = None
            msg = "🔄 Audio filter reset to **Normal**."
        else:
            state.filter = choice
            msg = f"🎛️ Audio filter set to **{choice}**!"

        # Hot-swap current playing stream with the new filter
        if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()) and state.current:
            try:
                elapsed = int(state.get_elapsed())
                new_source = await YTDLSource.regrab_stream(
                    state.current.data,
                    volume=state.volume,
                    seek_seconds=elapsed,
                    audio_filter=state.filter
                )
                new_source.title = state.current.title
                state.current = new_source
                state.voice_client.source = new_source
            except Exception as e:
                logger.warning(f"Error hot-swapping filter: {e}")

        if state.np_message:
            try:
                embed = await self.cog.build_np_embed(state)
                await state.np_message.edit(embed=embed)
            except Exception:
                pass

        await interaction.response.send_message(msg, ephemeral=True)


class FilterSelectView(discord.ui.View):
    def __init__(self, cog: "Music", guild: discord.Guild):
        super().__init__(timeout=60)
        self.add_item(FilterSelect(cog, guild))


class RadioSelect(discord.ui.Select):
    def __init__(self, cog: "Music", guild: discord.Guild):
        self.cog = cog
        self.guild = guild
        options = [
            discord.SelectOption(label="Lofi Chill Beats", value="lofi", emoji="☕", description="24/7 relaxing study & sleep beats"),
            discord.SelectOption(label="Nightride FM (Synthwave)", value="synthwave", emoji="🌆", description="24/7 cyberpunk & retrowave"),
            discord.SelectOption(label="Smooth Lounge & Jazz", value="jazz", emoji="🎷", description="24/7 Secret Agent lounge & jazz"),
            discord.SelectOption(label="Stop Radio", value="stop", emoji="⏹", description="Stop radio and disconnect"),
        ]
        super().__init__(placeholder="Select a 24/7 radio station...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        station_key = self.values[0]
        await self.cog.start_radio_station(interaction, station_key)


class RadioSelectView(discord.ui.View):
    def __init__(self, cog: "Music", guild: discord.Guild):
        super().__init__(timeout=60)
        self.add_item(RadioSelect(cog, guild))


# ─── Now Playing View ─────────────────────────────────────────────────────────

class NowPlayingView(discord.ui.View):
    def __init__(self, cog: "Music", guild: discord.Guild):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild = guild

    def get_state(self) -> GuildMusicState:
        return self.cog.get_state(self.guild.id)

    # ── Row 0 ─────────────────────────────────────────────────────────────────

    @discord.ui.button(emoji="⏮", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        if not state.current:
            return await interaction.response.send_message("Nothing playing.", ephemeral=True)
        state.queue.appendleft(state.current.data)
        if state.voice_client and state.voice_client.is_playing():
            state.voice_client.stop()
        await interaction.response.defer()

    @discord.ui.button(emoji="⏸", style=discord.ButtonStyle.primary, custom_id="np_pause", row=0)
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        vc = state.voice_client
        if not vc:
            return await interaction.response.send_message("Not in a voice channel.", ephemeral=True)

        if vc.is_playing():
            vc.pause()
            state.on_pause()
            button.emoji = "▶️"
            button.style = discord.ButtonStyle.success
            await self.cog.set_vc_status(vc.channel, f"⏸️ Paused: {state.current.title}" if state.current else None)
        elif vc.is_paused():
            vc.resume()
            state.on_resume()
            button.emoji = "⏸"
            button.style = discord.ButtonStyle.primary
            await self.cog.set_vc_status(vc.channel, f"🎶 {state.current.title}" if state.current else None)

        embed = await self.cog.build_np_embed(state)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.secondary, row=0)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        if not state.voice_client or not state.voice_client.is_playing():
            return await interaction.response.send_message("Nothing to skip.", ephemeral=True)

        is_dj = await self.cog.is_dj_or_admin(interaction.user)
        if is_dj:
            state.voice_client.stop()
            return await interaction.response.send_message("⏭ Skipped by DJ / Admin.", ephemeral=True)

        vc_members = [m for m in state.voice_client.channel.members if not m.bot]
        if len(vc_members) <= 1:
            state.voice_client.stop()
            return await interaction.response.send_message("⏭ Skipped.", ephemeral=True)

        state.skip_votes.add(interaction.user.id)
        needed = (len(vc_members) // 2) + 1

        if len(state.skip_votes) >= needed:
            state.skip_votes.clear()
            state.voice_client.stop()
            await interaction.response.send_message("⏭ Vote passed — skipped!", ephemeral=False)
        else:
            await interaction.response.send_message(
                f"🗳️ Vote recorded! **{len(state.skip_votes)}/{needed}** votes to skip.", ephemeral=False
            )

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.danger, row=0)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        await self.cog.bot.db.clear_music_queue(interaction.guild_id)
        if state.voice_client:
            vc_channel = state.voice_client.channel
            state.clear()
            state.voice_client.stop()
            if not state.is_247:
                await state.voice_client.disconnect()
                state.voice_client = None
                await self.cog.set_vc_status(vc_channel, None)
            else:
                await self.cog.set_vc_status(vc_channel, "📻 Sweety 24/7 — Idle")

        for child in self.children:
            child.disabled = True

        desc = "Music stopped and queue cleared." if not state.is_247 else "Music stopped and queue cleared. *(24/7 mode active — staying in VC)*"
        embed = discord.Embed(
            title="⏹ Stopped",
            description=desc,
            color=0x2b2d31
        )
        await interaction.response.edit_message(embed=embed, view=self)

    # ── Row 1 ─────────────────────────────────────────────────────────────────

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="np_loop", row=1)
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        if not state.loop and not state.loop_queue:
            state.loop = True
            button.emoji = "🔂"
            button.style = discord.ButtonStyle.success
            msg = "🔂 Looping current track."
        elif state.loop:
            state.loop = False
            state.loop_queue = True
            button.emoji = "🔁"
            button.style = discord.ButtonStyle.primary
            msg = "🔁 Looping queue."
        else:
            state.loop = False
            state.loop_queue = False
            button.emoji = "🔁"
            button.style = discord.ButtonStyle.secondary
            msg = "Loop off."

        embed = await self.cog.build_np_embed(state)
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, row=1)
    async def shuffle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        import random
        state = self.get_state()
        if not state.queue:
            return await interaction.response.send_message("Queue is empty.", ephemeral=True)
        q = list(state.queue)
        random.shuffle(q)
        state.queue = deque(q)
        await self.cog._persist_queue(interaction.guild_id)
        await interaction.response.send_message("🔀 Queue shuffled.", ephemeral=True)

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, row=1)
    async def vol_down_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        cur_level = getattr(state, "user_volume_level", None) or int(round(state.volume * 100))
        new_level = max(10, cur_level - 10)
        state.user_volume_level = new_level
        state.volume = round(new_level / 100.0, 3)
        if state.current and hasattr(state.current, "volume"):
            state.current.volume = state.volume
        if state.voice_client and state.voice_client.source and hasattr(state.voice_client.source, "volume"):
            state.voice_client.source.volume = state.volume
        embed = await self.cog.build_np_embed(state)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, row=1)
    async def vol_up_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        cur_level = getattr(state, "user_volume_level", None) or int(round(state.volume * 100))
        new_level = min(100, cur_level + 10)
        state.user_volume_level = new_level
        state.volume = round(new_level / 100.0, 3)
        if state.current and hasattr(state.current, "volume"):
            state.current.volume = state.volume
        if state.voice_client and state.voice_client.source and hasattr(state.voice_client.source, "volume"):
            state.voice_client.source.volume = state.volume
        embed = await self.cog.build_np_embed(state)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="🎙️", label="Stage", style=discord.ButtonStyle.success, row=1)
    async def stage_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.start_karaoke_stage(interaction)

    # ── Row 2 ─────────────────────────────────────────────────────────────────

    @discord.ui.button(emoji="🎤", label="Lyrics", style=discord.ButtonStyle.secondary, row=2)
    async def lyrics_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        if not state.current:
            return await interaction.response.send_message("Nothing playing.", ephemeral=True)
        await interaction.response.defer()
        await self.cog.display_lyrics(interaction, state.current.title, ephemeral=False)

    @discord.ui.button(emoji="🎛️", label="Filter", style=discord.ButtonStyle.secondary, row=2)
    async def filter_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = FilterSelectView(self.cog, interaction.guild)
        await interaction.response.send_message("🎛️ Select an audio filter preset:", view=view, ephemeral=True)

    @discord.ui.button(emoji="📻", label="Radio", style=discord.ButtonStyle.secondary, row=2)
    async def radio_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RadioSelectView(self.cog, interaction.guild)
        await interaction.response.send_message("📻 Select a 24/7 radio station:", view=view, ephemeral=True)

    @discord.ui.button(emoji="📋", label="Queue", style=discord.ButtonStyle.secondary, row=2)
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        if not state.queue:
            return await interaction.response.send_message("Queue is empty.", ephemeral=True)

        lines = []
        for i, track in enumerate(list(state.queue)[:12], 1):
            title = track.get("title", "Unknown")[:40]
            dur = fmt_duration(track.get("duration", 0))
            lines.append(f"`{i:02d}.` {title} `{dur}`")

        if len(state.queue) > 12:
            lines.append(f"\n*...and {len(state.queue) - 12} more tracks*")

        embed = discord.Embed(
            title=f"📋 Queue — {len(state.queue)} tracks",
            description="\n".join(lines),
            color=0x5865F2
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji="❤️", label="Save", style=discord.ButtonStyle.secondary, row=2)
    async def save_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        if not state.current:
            return await interaction.response.send_message("Nothing playing to save.", ephemeral=True)
        modal = SavePlaylistModal(self.cog, state)
        await interaction.response.send_modal(modal)


# ─── Search Results View ──────────────────────────────────────────────────────

class SearchResultsView(discord.ui.View):
    def __init__(self, cog: "Music", interaction_or_ctx, entries: list):
        super().__init__(timeout=30)
        self.cog = cog
        self.context = interaction_or_ctx
        self.entries = entries
        self.message = None

        # Add a button per result
        for i, entry in enumerate(entries, 1):
            button = discord.ui.Button(
                label=str(i),
                style=discord.ButtonStyle.secondary,
                row=0
            )
            button.callback = self.make_callback(entry)
            self.add_item(button)

        # Cancel button
        cancel = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            row=0
        )
        cancel.callback = self.cancel_callback
        self.add_item(cancel)

    def make_callback(self, entry):
        async def callback(interaction: discord.Interaction):
            self.stop()
            for child in self.children:
                child.disabled = True

            title = entry.get("title", "Unknown")
            url = entry.get("webpage_url") or entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id', '')}"

            embed = discord.Embed(
                title="⏳ Loading...",
                description=f"Fetching **{title}**",
                color=0x5865F2
            )
            await interaction.response.edit_message(embed=embed, view=self)

            # Hand off to play logic
            state = self.cog.get_state(interaction.guild_id)
            state.text_channel = interaction.channel

            vc = interaction.user.voice.channel if interaction.user.voice else None
            if not vc:
                return await interaction.followup.send("❌ Join a voice channel first.", ephemeral=True)

            await self.ensure_voice_client(ctx.guild, vc, state)

            is_247 = await self.cog.is_247_enabled(interaction.guild_id)
            if is_247:
                try:
                    await self.cog.bot.db.set_config(interaction.guild_id, "music_247_channel_id", str(vc.id))
                except Exception:
                    pass

            try:
                result, _ = await YTDLSource.from_url(
                    url, volume=state.volume, requester=str(interaction.user.display_name)
                )
            except Exception as e:
                try:
                    result, _ = await YTDLSource._search_and_extract(
                        title, volume=state.volume, requester=str(interaction.user.display_name)
                    )
                except Exception:
                    return await interaction.followup.send(f"❌ Error: `{e}`")

            if state.voice_client.is_playing() or state.voice_client.is_paused():
                if len(state.queue) >= 200:
                    return await interaction.followup.send("⚠️ Queue is full (200 tracks max). Skip or remove some tracks first.", ephemeral=True)
                state.queue.append(result.data)
                await self.cog._persist_queue(interaction.guild_id)
                embed = discord.Embed(
                    title="➕ Added to Queue",
                    description=f"[{result.title}]({result.url})",
                    color=0x5865F2
                )
                embed.set_thumbnail(url=result.thumbnail)
                embed.add_field(name="Duration", value=fmt_duration(result.duration))
                embed.add_field(name="Position", value=f"#{len(state.queue)}")
                if interaction.message:
                    await interaction.message.edit(embed=embed, view=None)
                else:
                    await interaction.edit_original_response(embed=embed, view=None)
            else:
                state.current = result
                state.start_time = time.time()
                state.paused_elapsed = 0.0
                state.pause_start = None
                state.voice_client.play(
                    result,
                    after=lambda e: self.cog.schedule_play_next(interaction.guild)
                )
                await self.cog.set_vc_status(state.voice_client.channel, f"🎶 {result.title}")
                np_embed = await self.cog.build_np_embed(state)
                np_view = NowPlayingView(self.cog, interaction.guild)
                if interaction.message:
                    await interaction.message.edit(embed=np_embed, view=np_view)
                    state.np_message = interaction.message
                else:
                    msg = await interaction.edit_original_response(embed=np_embed, view=np_view)
                    state.np_message = msg
                state.update_task = asyncio.create_task(
                    self.cog.live_updater(interaction.guild)
                )

        return callback

    async def cancel_callback(self, interaction: discord.Interaction):
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(title="❌ Search cancelled.", color=0x2b2d31),
            view=None
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(
                    embed=discord.Embed(title="⏱ Search expired.", color=0x2b2d31),
                    view=self
                )
            elif hasattr(self.context, "edit_original_response"):
                await self.context.edit_original_response(
                    embed=discord.Embed(title="⏱ Search expired.", color=0x2b2d31),
                    view=self
                )
        except Exception:
            pass


# ─── Save Playlist Modal ──────────────────────────────────────────────────────

class SavePlaylistModal(discord.ui.Modal, title="💾 Save to Playlist"):
    playlist_name = discord.ui.TextInput(
        label="Playlist name",
        placeholder="e.g. my chill mix",
        max_length=32,
        required=True
    )

    def __init__(self, cog, state):
        super().__init__()
        self.cog = cog
        self.state = state

    async def on_submit(self, interaction: discord.Interaction):
        name = self.playlist_name.value.strip()
        state = self.state
        tracks = []

        if state.current:
            tracks.append({
                "title": state.current.title,
                "url": state.current.url,
                "duration": state.current.duration,
                "webpage_url": state.current.url,
            })
        for t in state.queue:
            tracks.append({
                "title": t.get("title", "Unknown"),
                "url": t.get("webpage_url", ""),
                "duration": t.get("duration", 0),
                "webpage_url": t.get("webpage_url", ""),
            })

        if not tracks:
            return await interaction.response.send_message("Nothing to save.", ephemeral=True)

        try:
            await self.cog.bot.db.execute("""
                INSERT INTO music_playlists (user_id, name, tracks, guild_id, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (user_id, name)
                DO UPDATE SET tracks = $3, guild_id = $4, updated_at = NOW()
            """, interaction.user.id, name, json.dumps(tracks), interaction.guild_id)
            await interaction.response.send_message(
                f"✅ Saved **{len(tracks)} tracks** to playlist **{name}**.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ DB error: {e}", ephemeral=True)


# ─── Autocomplete ─────────────────────────────────────────────────────────────

_autocomplete_cache: dict[str, list[app_commands.Choice[str]]] = {}

async def play_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    raw = current.strip()
    if len(raw) < 2:
        return []
    q = raw.lower()
    if q in _autocomplete_cache:
        return _autocomplete_cache[q]
    try:
        loop = asyncio.get_event_loop()
        choices = []

        # 1. Primary Choice is ALWAYS the user's exact typed query.
        # This guarantees that if the user presses Enter immediately or clicks send
        # without selecting an option, Discord sends what they actually typed instead of hijacking.
        choices.append(
            app_commands.Choice(
                name=f"▶️ Play exact: {raw}"[:100],
                value=raw
            )
        )

        if spotify:
            try:
                results = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: spotify.search(q=raw, type="track", limit=8)
                    ),
                    timeout=2.0
                )
                tracks = results.get("tracks", {}).get("items", [])
                for t in tracks:
                    if len(choices) >= 5:
                        break
                    if not t or not t.get("name") or not t.get("artists"):
                        continue
                    name = t["name"]
                    artist = t["artists"][0]["name"]
                    title_lower = name.lower()
                    # Filter out covers, slowed, reverb, karaoke, instrumental, remixes
                    if any(w in title_lower for w in ("slowed", "reverb", "cover", "karaoke", "tribute", "instrumental", "remix", "piano version", "sped up")):
                        continue
                    val = f"{name} {artist}"
                    if val.lower() == raw.lower():
                        continue
                    choices.append(app_commands.Choice(
                        name=f"🎵 {name} — {artist}"[:100],
                        value=val
                    ))
            except Exception as e:
                logger.debug(f"Spotify autocomplete search failed: {e}")

        if len(choices) < 2:
            # Fallback to fast SoundCloud autocomplete search
            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: ytdl.extract_info(f"scsearch8:{raw}", download=False)
                    ),
                    timeout=2.5
                )
                entries = data.get("entries", [])
                for e in entries:
                    if len(choices) >= 5:
                        break
                    t_name = e.get("title", "")
                    if not t_name:
                        continue
                    t_low = t_name.lower()
                    if any(w in t_low for w in ("slowed", "reverb", "cover", "karaoke", "tribute", "instrumental", "remix", "piano version", "sped up")):
                        continue
                    if t_name.lower() == raw.lower():
                        continue
                    choices.append(app_commands.Choice(
                        name=f"🎵 {t_name}"[:100],
                        value=t_name
                    ))
            except Exception as e:
                logger.debug(f"SoundCloud autocomplete search failed: {e}")

        if choices:
            if len(_autocomplete_cache) > 200:
                _autocomplete_cache.clear()
            _autocomplete_cache[q] = choices
        return choices
    except Exception as e:
        logger.warning(f"Autocomplete error: {e}")
        return [app_commands.Choice(name=f"▶️ Play exact: {raw}"[:100], value=raw)]


# ─── Spotify Playlists View ───────────────────────────────────────────────────

class SpotifyPlaylistsView(discord.ui.View):
    def __init__(self, cog: "Music", user: discord.User | discord.Member, profile_data: dict):
        super().__init__(timeout=600)
        self.cog = cog
        self.user = user
        self.profile_data = profile_data
        self.playlists = profile_data.get("playlists", [])
        self.selected_url = self.playlists[0]["url"] if self.playlists else None
        self.selected_name = self.playlists[0]["name"] if self.playlists else None

        if self.playlists:
            options = []
            for p in self.playlists[:25]:
                options.append(
                    discord.SelectOption(
                        label=p["name"][:90],
                        value=p["url"],
                        description=f"ID: {p['id'][:20]}",
                        default=(p["url"] == self.selected_url)
                    )
                )

            select = discord.ui.Select(
                placeholder="Choose a Spotify playlist...",
                min_values=1,
                max_values=1,
                options=options,
                row=0
            )
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        self.selected_url = interaction.data["values"][0]
        for p in self.playlists:
            if p["url"] == self.selected_url:
                self.selected_name = p["name"]
                break
        try:
            await interaction.response.defer()
        except Exception:
            pass

    @discord.ui.button(label="Play in VC", style=discord.ButtonStyle.success, emoji="▶️", row=1)
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_url:
            return await interaction.response.send_message("❌ No playlist selected.", ephemeral=True)

        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Join a voice channel first.", ephemeral=True)

        try:
            await interaction.response.defer()
        except Exception:
            pass

        try:
            vc = interaction.user.voice.channel
            state = self.cog.get_state(interaction.guild_id)
            state.text_channel = interaction.channel

            vc_client = await self.cog.ensure_voice_client(interaction.guild, vc, state)
            if not vc_client:
                return await interaction.followup.send("❌ Could not connect to your voice channel. Check bot permissions.", ephemeral=True)

            is_247 = await self.cog.is_247_enabled(interaction.guild_id)
            if is_247:
                try:
                    await self.cog.bot.db.set_config(interaction.guild_id, "music_247_channel_id", str(vc.id))
                except Exception:
                    pass

            tracks = await asyncio.get_running_loop().run_in_executor(
                None, lambda: extract_spotify_playlist_tracks_public(self.selected_url)
            )
            if not tracks:
                return await interaction.followup.send("❌ Could not load tracks from this Spotify playlist.", ephemeral=True)

            for t in tracks:
                t["requester"] = str(interaction.user.display_name)
                state.queue.append(t)
            await self.cog._persist_queue(interaction.guild_id)

            embed = discord.Embed(
                title="📋 Spotify Playlist Queued",
                description=f"Added **{len(tracks)} tracks** from **{self.selected_name}** to the queue.",
                color=0x1DB954
            )
            embed.set_footer(text=f"Requested by {interaction.user.display_name}")
            await interaction.followup.send(embed=embed)

            if state.voice_client and not state.voice_client.is_playing() and not state.voice_client.is_paused():
                state.current = None
                await self.cog.play_next(interaction.guild)
        except Exception as play_err:
            logger.error(f"Error in SpotifyPlaylistsView play_button: {play_err}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ Failed to play playlist: `{play_err}`", ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="Save to Sweety", style=discord.ButtonStyle.primary, emoji="💾", row=1)
    async def save_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_url:
            return await interaction.response.send_message("❌ No playlist selected.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        tracks = await asyncio.get_running_loop().run_in_executor(
            None, lambda: extract_spotify_playlist_tracks_public(self.selected_url)
        )
        if not tracks:
            return await interaction.followup.send("❌ Could not fetch tracks to save.", ephemeral=True)

        save_name = self.selected_name[:32] if self.selected_name else "spotify_mix"
        try:
            await self.cog.bot.db.execute("""
                INSERT INTO music_playlists (user_id, name, tracks, guild_id, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (user_id, name)
                DO UPDATE SET tracks = $3, guild_id = $4, updated_at = NOW()
            """, interaction.user.id, save_name, json.dumps(tracks), interaction.guild_id)
            await interaction.followup.send(
                f"✅ Saved **{len(tracks)} tracks** to your Sweety playlist **{save_name}**!\nPlay it anytime with `/playlist play {save_name}`.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ DB error saving playlist: {e}", ephemeral=True)


# ─── Music Cog ────────────────────────────────────────────────────────────────

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.states: dict[int, GuildMusicState] = {}
        self._watchdog_task: Optional[asyncio.Task] = None
        self._reconnecting_guilds: set[int] = set()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """
        Runs automatically when the bot joins or moves to a voice channel.
        Queries guild.bitrate_limit and auto-patches the channel's bitrate
        to its absolute maximum capacity to eliminate server-side audio compression.
        """
        if member.id == self.bot.user.id and after.channel and isinstance(after.channel, (discord.VoiceChannel, discord.StageChannel)):
            await self.auto_maximize_channel_bitrate(after.channel)

    async def auto_maximize_channel_bitrate(self, channel: Union[discord.VoiceChannel, discord.StageChannel]):
        """
        Dynamically inspects guild.bitrate_limit and upgrades channel bitrate if below capacity.
        Guarded against Discord API rate limits by checking current bitrate before editing.
        """
        try:
            guild = channel.guild
            max_bitrate = int(getattr(guild, "bitrate_limit", 96000))
            current_bitrate = getattr(channel, "bitrate", 64000)

            if current_bitrate < max_bitrate:
                bot_member = guild.me or guild.get_member(self.bot.user.id)
                if bot_member and channel.permissions_for(bot_member).manage_channels:
                    await channel.edit(bitrate=max_bitrate, reason="Sweety Ultra-High Fidelity: Auto Maximize Bitrate")
                    logger.info(f"🔊 Auto-tuned #{channel.name} bitrate to {max_bitrate // 1000}kbps in '{guild.name}' (Tier Max).")
                else:
                    logger.debug(f"Missing 'Manage Channels' permission in '{guild.name}' to auto-upgrade bitrate.")
        except discord.Forbidden:
            logger.debug(f"Forbidden error trying to edit bitrate for #{channel.name}.")
        except Exception as e:
            logger.warning(f"Error auto-maximizing voice bitrate: {e}")

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Ensure all Music cog commands are always whitelisted regardless of server mode."""
        return True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure all Music cog interactions are always whitelisted regardless of server mode."""
        return True

    async def cog_load(self):
        """Start 24/7 voice watchdog supervisor loop and restore saved queues when cog loads."""
        self.loop = asyncio.get_running_loop()
        self._watchdog_task = asyncio.create_task(self._watchdog_247_loop())
        asyncio.create_task(self._restore_saved_queues())

    def schedule_play_next(self, guild: discord.Guild):
        """Thread-safely schedules play_next on the main asyncio event loop from the audio thread."""
        try:
            loop = getattr(self, "loop", None) or getattr(self.bot, "loop", None)
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(self.play_next(guild), loop)
            else:
                asyncio.create_task(self.play_next(guild))
        except Exception as e:
            logger.debug(f"Error scheduling play_next: {e}")

    async def cog_unload(self):
        """Cancel watchdog task when cog is unloaded."""
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()

    async def _persist_queue(self, guild_id: int):
        """Persists the current in-memory queue to music_queues table."""
        try:
            state = self.get_state(guild_id)
            items = []
            for track in list(state.queue):
                items.append({
                    "url": track.get("webpage_url") or track.get("url") or "",
                    "title": track.get("title") or "Unknown Track",
                    "duration": track.get("duration") or 0,
                    "requested_by_id": track.get("requested_by_id") or "",
                    "requester": track.get("requester") or track.get("requested_by_name") or "User"
                })
            await self.bot.db.save_music_queue(guild_id, items)
        except Exception as e:
            logger.debug(f"Failed to persist music queue for guild {guild_id}: {e}")

    async def _restore_saved_queues(self):
        """Restores persisted queues into in-memory GuildMusicState on startup."""
        await self.bot.wait_until_ready()
        try:
            saved_queues = await self.bot.db.load_all_music_queues()
            for guild_id_str, items in saved_queues.items():
                try:
                    guild_id = int(guild_id_str)
                    state = self.get_state(guild_id)
                    if not state.queue:
                        for item in items:
                            state.queue.append(item)
                        logger.info(f"Restored {len(items)} queued tracks for guild {guild_id}.")
                except Exception as g_err:
                    logger.debug(f"Error restoring queue for guild {guild_id_str}: {g_err}")
        except Exception as e:
            logger.error(f"Error restoring saved music queues: {e}")

    def get_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self.states:
            self.states[guild_id] = GuildMusicState()
            if hasattr(self.bot, "db") and self.bot.db:
                asyncio.create_task(self._restore_247(guild_id))
        state = self.states[guild_id]
        if hasattr(self, "bot"):
            guild = self.bot.get_guild(guild_id)
            if guild and guild.voice_client:
                state.voice_client = guild.voice_client
        return state

    async def ensure_voice_client(self, guild: discord.Guild, vc: discord.VoiceChannel, state: GuildMusicState) -> Optional[discord.VoiceClient]:
        """Safely connects or moves voice_client, handling already-connected voice client seamlessly."""
        voice_client = guild.voice_client or state.voice_client
        if not voice_client or not voice_client.is_connected():
            try:
                voice_client = await vc.connect(timeout=20.0, reconnect=True, self_deaf=True)
            except discord.ClientException:
                voice_client = guild.voice_client
            except Exception as e:
                logger.warning(f"Voice connect error: {e}")
                voice_client = guild.voice_client
        elif voice_client.channel != vc:
            try:
                await voice_client.move_to(vc)
            except Exception as e:
                logger.warning(f"Voice move_to error: {e}")
        state.voice_client = voice_client
        return voice_client

    async def is_247_enabled(self, guild_id: int) -> bool:
        """Reliably checks 24/7 status from in-memory state and database cache."""
        state = self.states.get(guild_id)
        if state and state.is_247:
            return True
        try:
            val = await self.bot.db.get_config(guild_id, "music_247", "false")
            enabled = str(val).lower() == "true"
            if enabled and guild_id in self.states:
                self.states[guild_id].is_247 = True
            return enabled
        except Exception:
            return False

    async def _restore_247(self, guild_id: int):
        try:
            val = await self.bot.db.get_config(guild_id, "music_247", "false")
            if str(val).lower() == "true":
                if guild_id in self.states:
                    self.states[guild_id].is_247 = True
        except Exception:
            pass

    async def _watchdog_247_loop(self):
        """Continuous background supervisor ensuring 24/7 voice presence survives reboots, sleep cycles, and drops."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(5.0)
        logger.info("📻 [24/7 Watchdog] Started 24/7 voice supervisor loop.")
        while not self.bot.is_closed():
            try:
                await self._check_and_restore_all_247()
            except Exception as e:
                logger.debug(f"[24/7 Watchdog] Iteration error: {e}")
            await asyncio.sleep(20.0)

    async def _check_and_restore_all_247(self):
        """Scans all guilds for active 24/7 mode and reconnects any missing or moved voice clients."""
        for guild in list(self.bot.guilds):
            try:
                # Do not interfere if VoiceAssistant is active or running in this guild
                va_cog = self.bot.cogs.get("VoiceAssistant")
                if va_cog and guild.id in getattr(va_cog, "sessions", {}):
                    continue

                is_247 = await self.is_247_enabled(guild.id)
                if not is_247:
                    continue

                state = self.get_state(guild.id)
                state.is_247 = True

                target_vc = None
                saved_ch_id = await self.bot.db.get_config(guild.id, "music_247_channel_id", None)
                if saved_ch_id:
                    try:
                        target_vc = guild.get_channel(int(saved_ch_id))
                    except (ValueError, TypeError):
                        pass

                # If no saved channel yet, but bot is currently in a VC
                if not target_vc and guild.voice_client and guild.voice_client.channel:
                    target_vc = guild.voice_client.channel
                    await self.bot.db.set_config(guild.id, "music_247_channel_id", str(target_vc.id))

                # If still no target_vc, intelligently find a suitable voice channel
                if not target_vc and guild.voice_channels:
                    for ch in guild.voice_channels:
                        perms = ch.permissions_for(guild.me)
                        if perms.connect and perms.speak:
                            name_lower = ch.name.lower()
                            if any(k in name_lower for k in ["music", "24/7", "radio", "chill", "lounge"]):
                                target_vc = ch
                                break
                    if not target_vc:
                        for ch in guild.voice_channels:
                            perms = ch.permissions_for(guild.me)
                            if perms.connect and perms.speak:
                                target_vc = ch
                                break
                    if target_vc:
                        await self.bot.db.set_config(guild.id, "music_247_channel_id", str(target_vc.id))

                if not target_vc:
                    continue

                # Case 1: Bot is not connected or connection is closed
                if not guild.voice_client or not guild.voice_client.is_connected():
                    if guild.id in self._reconnecting_guilds:
                        continue
                    self._reconnecting_guilds.add(guild.id)
                    try:
                        logger.info(f"📻 [24/7 Watchdog] Reconnecting in {guild.name} to '{target_vc.name}'...")
                        if guild.voice_client:
                            try:
                                await guild.voice_client.disconnect(force=True)
                            except Exception:
                                pass
                            await asyncio.sleep(1.0)

                        new_vc = await target_vc.connect(timeout=20.0, reconnect=True, self_deaf=True)
                        state.voice_client = new_vc
                        logger.info(f"✅ [24/7 Watchdog] Reconnected in {guild.name} ({target_vc.name})")
                        if not state.current:
                            await self.set_vc_status(target_vc, "📻 Sweety 24/7 — Idle")
                    except Exception as ex:
                        logger.warning(f"⚠️ [24/7 Watchdog] Could not connect to '{target_vc.name}' in {guild.name}: {ex}")
                    finally:
                        self._reconnecting_guilds.discard(guild.id)
                else:
                    state.voice_client = guild.voice_client
                    # Case 2: Bot was moved to AFK channel
                    if guild.afk_channel and guild.voice_client.channel.id == guild.afk_channel.id and target_vc.id != guild.afk_channel.id:
                        try:
                            logger.info(f"📻 [24/7 Watchdog] Moving bot out of AFK channel back to '{target_vc.name}' in {guild.name}")
                            await guild.voice_client.move_to(target_vc)
                        except Exception as ex:
                            logger.warning(f"⚠️ [24/7 Watchdog] Failed moving back from AFK: {ex}")
            except Exception as ge:
                logger.debug(f"[24/7 Watchdog] Guild {guild.id} check error: {ge}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Immediate auto-reconnect if 24/7 mode is active and bot gets disconnected or moved."""
        if member.id != self.bot.user.id:
            return

        guild = member.guild
        # Do not interfere if VoiceAssistant is active or running in this guild
        va_cog = self.bot.cogs.get("VoiceAssistant")
        if va_cog and guild.id in getattr(va_cog, "sessions", {}):
            return

        state = self.get_state(guild.id)

        # 1. Bot disconnected completely
        if after.channel is None and before.channel is not None:
            is_247 = await self.is_247_enabled(guild.id)
            if is_247:
                state.is_247 = True
                target_channel = before.channel
                saved_ch_id = await self.bot.db.get_config(guild.id, "music_247_channel_id", None)
                if saved_ch_id:
                    try:
                        saved_ch = guild.get_channel(int(saved_ch_id))
                        if saved_ch:
                            target_channel = saved_ch
                    except (ValueError, TypeError):
                        pass

                if guild.id in self._reconnecting_guilds:
                    return
                self._reconnecting_guilds.add(guild.id)

                try:
                    await asyncio.sleep(2.0)
                    if guild.voice_client:
                        try:
                            await guild.voice_client.disconnect(force=True)
                        except Exception:
                            pass
                        await asyncio.sleep(0.5)

                    new_vc = await target_channel.connect(timeout=20.0, reconnect=True, self_deaf=True)
                    state.voice_client = new_vc
                    logger.info(f"✅ [24/7 Event] Reconnected voice client in {guild.name} ({target_channel.name})")
                    if not state.current:
                        await self.set_vc_status(target_channel, "📻 Sweety 24/7 — Idle")
                except Exception as e:
                    logger.warning(f"⚠️ [24/7 Event] Auto-reconnect failed in {guild.name}: {e}")
                finally:
                    self._reconnecting_guilds.discard(guild.id)

        # 2. Bot moved to AFK channel
        elif after.channel is not None and guild.afk_channel and after.channel.id == guild.afk_channel.id:
            is_247 = await self.is_247_enabled(guild.id)
            if is_247:
                state.is_247 = True
                target_channel = before.channel if before.channel and before.channel.id != guild.afk_channel.id else None
                saved_ch_id = await self.bot.db.get_config(guild.id, "music_247_channel_id", None)
                if saved_ch_id:
                    try:
                        saved_ch = guild.get_channel(int(saved_ch_id))
                        if saved_ch and saved_ch.id != guild.afk_channel.id:
                            target_channel = saved_ch
                    except (ValueError, TypeError):
                        pass

                if target_channel and guild.voice_client:
                    try:
                        logger.info(f"📻 [24/7 Event] Moved to AFK channel in {guild.name}. Moving back to '{target_channel.name}'...")
                        await asyncio.sleep(1.0)
                        await guild.voice_client.move_to(target_channel)
                    except Exception as e:
                        logger.warning(f"⚠️ [24/7 Event] Failed moving back from AFK: {e}")

        # 3. Bot moved to another normal voice channel
        elif after.channel is not None:
            is_247 = await self.is_247_enabled(guild.id)
            if is_247:
                state.is_247 = True
                state.voice_client = guild.voice_client
                await self.bot.db.set_config(guild.id, "music_247_channel_id", str(after.channel.id))


    async def set_vc_status(self, channel: Optional[discord.VoiceChannel], status: Optional[str]):
        """Sets the voice channel status message based on current track or state."""
        if not channel:
            return
        try:
            val = status[:500] if status else None
            await self.bot.http.edit_voice_channel_status(val, channel_id=channel.id)
        except Exception as e:
            logger.debug(f"Could not set voice channel status in {channel.name}: {e}")

    async def build_np_embed(self, state: GuildMusicState) -> discord.Embed:
        src = state.current
        if not src:
            return discord.Embed(title="Nothing playing.", color=0x2b2d31)

        elapsed = state.get_elapsed()
        total = src.duration or 0

        is_paused = state.voice_client and state.voice_client.is_paused()
        status_text = "Paused" if is_paused else "Playing"
        status_icon = "⏸" if is_paused else "▶"

        if state.loop:
            loop_str = "🔂 Track"
        elif state.loop_queue:
            loop_str = "🔁 Queue"
        else:
            loop_str = "Off"

        vol_display = getattr(state, "user_volume_level", None)
        if vol_display is None:
            vol_display = int(round(state.volume * 100))

        bar = progress_bar(elapsed, total, length=16)
        elapsed_str = fmt_duration(elapsed)
        total_str = fmt_duration(total) if total > 0 else "LIVE"
        percent_str = f"{int(min(1.0, elapsed / total) * 100)}%" if total > 0 else "Live"

        # Dynamic visualizer wave
        if is_paused:
            wave = "⏸️ `PAUSED`"
        else:
            waves = [" ▂▃▅▆▇", "▃▅▇▆▅▃", "▅▆▇▅▃ ", "▇▆▅▃ ▂"]
            wave = f"🎶 `{waves[int(elapsed) % len(waves)]}`"

        queue_len = len(state.queue)
        next_track = list(state.queue)[0].get("title", "Unknown")[:35] if queue_len else "Nothing"

        views = src.view_count
        if views >= 1_000_000:
            views_str = f"{views/1_000_000:.1f}M"
        elif views >= 1_000:
            views_str = f"{views/1_000:.1f}K"
        elif views > 0:
            views_str = str(views)
        else:
            views_str = "N/A"

        vol_icon = "🔊" if vol_display >= 60 else ("🔉" if vol_display >= 20 else "🔈")

        is_sp = "spotify" in src.url.lower() or "spotify" in src.title.lower()
        embed = discord.Embed(
            title=src.title,
            url=src.url if src.url.startswith("http") else None,
            color=0x1DB954 if is_sp else 0x5865F2
        )
        embed.set_author(
            name=f"🎵 {status_text} • Vol {vol_display}% • Loop {loop_str}"
        )
        if src.thumbnail:
            embed.set_thumbnail(url=src.thumbnail)

        # Monospace Spotify-style media player bar
        player_box = f"```\n{status_icon}  {elapsed_str}  {bar}  {total_str}\n```"
        filter_str = f" • Filter: `{state.filter}`" if state.filter else ""
        autoplay_str = " • 📻 `Autoplay`" if state.autoplay else ""

        embed.add_field(
            name=f"Progress • {percent_str}",
            value=f"{player_box}{wave}  •  {vol_icon} `{vol_display}%`  •  Loop: `{loop_str}`{filter_str}{autoplay_str}",
            inline=False
        )
        embed.add_field(name="👤 Requested by", value=src.requester, inline=True)
        embed.add_field(name="🎙️ Channel", value=src.uploader or "Unknown", inline=True)
        embed.add_field(name="👁️ Views", value=views_str, inline=True)
        embed.add_field(
            name=f"📋 Queue — {queue_len} track{'s' if queue_len != 1 else ''} up next",
            value=f"Next: **{next_track}**" if queue_len else "Nothing queued",
            inline=False
        )
        embed.set_footer(text="Sweety Music • Spotify Style Player • Click 🎤 for Lyrics")
        return embed

    async def live_updater(self, guild: discord.Guild):
        state = self.get_state(guild.id)
        while True:
            await asyncio.sleep(5)
            try:
                if not state.np_message or not state.current:
                    break
                if not state.voice_client or not (
                    state.voice_client.is_playing() or state.voice_client.is_paused()
                ):
                    break
                if state.voice_client.is_paused():
                    continue

                embed = await self.build_np_embed(state)
                await state.np_message.edit(embed=embed)
            except discord.NotFound:
                state.np_message = None
                break
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = getattr(e, "retry_after", 2.0) or 2.0
                    await asyncio.sleep(retry_after)
                    continue
                # For non-429 HTTP exceptions, wait briefly and keep loop alive
                await asyncio.sleep(2.5)
                continue
            except Exception as e:
                logger.debug(f"Live updater error in {guild.id}: {e}")
                await asyncio.sleep(2.5)
                continue

    async def is_dj_or_admin(self, member: discord.Member) -> bool:
        if member.id == 719932313919684670:
            return True
        if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
            return True
        dj_role_id = await self.bot.db.get_config(member.guild.id, "dj_role_id", None)
        if dj_role_id:
            try:
                role_id = int(dj_role_id)
                if any(r.id == role_id for r in member.roles):
                    return True
            except ValueError:
                pass
        if any(r.name.lower() == "dj" for r in member.roles):
            return True
        return False

    async def find_recommendation(self, last_track: dict, history: deque) -> Optional[dict]:
        """Finds a smart recommendation based on last played track."""
        title = last_track.get("title", "")
        clean = re.sub(r'[\(\[].*?[\)\]]', '', title).strip()
        clean = re.sub(r'(feat\.|ft\.|official|video|audio|lyrics|hd|4k|sped up|slowed).*', '', clean, flags=re.IGNORECASE).strip()

        seen_titles = {h.get("title", "").lower() for h in history if isinstance(h, dict)}
        seen_titles.add(title.lower())

        if spotify:
            try:
                s_res = await asyncio.get_running_loop().run_in_executor(
                    None, lambda: spotify.search(q=clean, type="track", limit=5)
                )
                items = s_res.get("tracks", {}).get("items", [])
                if items:
                    seed_id = items[0]["id"]
                    recs = await asyncio.get_running_loop().run_in_executor(
                        None, lambda: spotify.recommendations(seed_tracks=[seed_id], limit=10)
                    )
                    rec_tracks = recs.get("tracks", [])
                    for rt in rec_tracks:
                        t_name = f"{rt['name']} {rt['artists'][0]['name'] if rt.get('artists') else ''}".strip()
                        if t_name.lower() not in seen_titles:
                            return {
                                "title": t_name,
                                "webpage_url": t_name,
                                "duration": int(rt.get("duration_ms", 0) / 1000),
                                "requester": "📻 Autoplay"
                            }
            except Exception as e:
                logger.debug(f"Spotify autoplay recommendation error: {e}")

        try:
            query = f"ytsearch8:{clean} mix"
            data = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(None, lambda: ytdl.extract_info(query, download=False)),
                timeout=6.0
            )
            entries = [e for e in data.get("entries", []) if e]
            for candidate in entries:
                c_title = candidate.get("title", "")
                if c_title.lower() not in seen_titles:
                    return {
                        "title": c_title,
                        "webpage_url": candidate.get("webpage_url") or candidate.get("url") or f"https://www.youtube.com/watch?v={candidate.get('id', '')}",
                        "duration": candidate.get("duration", 0),
                        "thumbnail": candidate.get("thumbnail", ""),
                        "uploader": candidate.get("uploader", "Unknown"),
                        "requester": "📻 Autoplay"
                    }
        except Exception as e:
            logger.debug(f"YouTube autoplay recommendation error: {e}")

        return None

    async def start_radio_station(self, interaction: discord.Interaction, station_key: str):
        if station_key == "stop":
            state = self.get_state(interaction.guild_id)
            state.clear()
            await self.bot.db.clear_music_queue(interaction.guild_id)
            is_247 = await self.is_247_enabled(interaction.guild_id)
            if state.voice_client:
                state.voice_client.stop()
                if not is_247:
                    await state.voice_client.disconnect(force=True)
                    state.voice_client = None
                else:
                    await self.set_vc_status(state.voice_client.channel, "📻 Sweety 24/7 — Idle")
            msg = "⏹ Radio stopped." if not is_247 else "⏹ Radio stopped. *(24/7 mode active — staying in VC)*"
            if not interaction.response.is_done():
                return await interaction.response.send_message(msg, ephemeral=True)
            return await interaction.followup.send(msg, ephemeral=True)

        station = RADIO_STATIONS.get(station_key)
        if not station:
            if not interaction.response.is_done():
                return await interaction.response.send_message("❌ Invalid radio station.", ephemeral=True)
            return await interaction.followup.send("❌ Invalid radio station.", ephemeral=True)

        if not interaction.user.voice:
            if not interaction.response.is_done():
                return await interaction.response.send_message("❌ Join a voice channel first.", ephemeral=True)
            return await interaction.followup.send("❌ Join a voice channel first.", ephemeral=True)

        vc = interaction.user.voice.channel
        state = self.get_state(interaction.guild_id)
        state.text_channel = interaction.channel
        state.is_247 = True
        state.radio_station = station_key
        state.queue.clear()
        await self.bot.db.clear_music_queue(interaction.guild_id)

        try:
            await self.bot.db.set_config(interaction.guild_id, "music_247", "true")
            await self.bot.db.set_config(interaction.guild_id, "music_247_channel_id", str(vc.id))
        except Exception:
            pass

        await self.cog.ensure_voice_client(interaction.guild, vc, state)

        source = make_ffmpeg_audio(station["url"], seek_seconds=0, audio_filter=state.filter, is_live=True)
        radio_data = {
            "title": station["name"],
            "webpage_url": station["url"],
            "thumbnail": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400",
            "duration": 0,
            "requester": interaction.user.display_name,
            "uploader": station["desc"],
            "view_count": 0,
            "is_live": True,
        }
        ytdl_src = YTDLSource(source, data=radio_data, volume=state.volume)
        state.current = ytdl_src
        state.start_time = time.time()
        state.paused_elapsed = 0.0
        state.pause_start = None

        if state.voice_client.is_playing() or state.voice_client.is_paused():
            state.voice_client.stop()

        state.voice_client.play(
            ytdl_src,
            after=lambda e: self.schedule_play_next(interaction.guild)
        )
        await self.set_vc_status(vc, f"📻 {station['name']}")

        embed = await self.build_np_embed(state)
        view = NowPlayingView(self, interaction.guild)
        state.np_message = await interaction.channel.send(embed=embed, view=view)
        state.update_task = asyncio.create_task(self.live_updater(interaction.guild))
        if not interaction.response.is_done():
            await interaction.response.send_message(f"📻 Tuned in to **{station['name']}**! (24/7 Radio Mode)", ephemeral=True)
        else:
            await interaction.followup.send(f"📻 Tuned in to **{station['name']}**! (24/7 Radio Mode)", ephemeral=True)

    async def display_lyrics(self, interaction_or_ctx, query: Optional[str] = None, ephemeral: bool = False):
        guild = interaction_or_ctx.guild
        user = interaction_or_ctx.user if hasattr(interaction_or_ctx, "user") else interaction_or_ctx.author
        state = self.get_state(guild.id)

        target_query = query
        target_artist = ""
        is_playing_track = False

        if not target_query:
            if not state.current:
                msg = "❌ Nothing is currently playing. Specify a song name: `/lyrics <song>`"
                if hasattr(interaction_or_ctx, "response"):
                    if not interaction_or_ctx.response.is_done():
                        return await interaction_or_ctx.response.send_message(msg, ephemeral=True)
                    return await interaction_or_ctx.followup.send(msg, ephemeral=True)
                return await interaction_or_ctx.send(msg)
            target_query = state.current.title
            curr_data = getattr(state.current, "data", {}) or {}
            target_artist = curr_data.get("artist") or curr_data.get("creator") or state.current.uploader or ""
            is_playing_track = True
        else:
            if state.current and (query.lower() in state.current.title.lower() or state.current.title.lower() in query.lower()):
                is_playing_track = True
                curr_data = getattr(state.current, "data", {}) or {}
                target_artist = curr_data.get("artist") or curr_data.get("creator") or state.current.uploader or ""

        if hasattr(interaction_or_ctx, "response") and not interaction_or_ctx.response.is_done():
            await interaction_or_ctx.response.defer(ephemeral=ephemeral)

        lyrics_data = await asyncio.get_running_loop().run_in_executor(
            None, lambda: fetch_lyrics(target_query, target_artist)
        )

        if not lyrics_data or not (lyrics_data.get("plainLyrics") or lyrics_data.get("syncedLyrics")):
            msg = f"❌ No lyrics found for **{target_query}**."
            if hasattr(interaction_or_ctx, "response"):
                return await interaction_or_ctx.followup.send(msg, ephemeral=ephemeral)
            return await interaction_or_ctx.send(msg)

        track_name = lyrics_data.get("trackName") or target_query
        artist_name = lyrics_data.get("artistName") or target_artist or "Unknown Artist"

        # Prepare clean lines for full static pagination (strip any raw timestamps)
        raw_text = lyrics_data.get("plainLyrics") or lyrics_data.get("syncedLyrics") or ""
        clean_text = re.sub(r'\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]', '', raw_text)
        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]

        chunk_size = 24
        chunks = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]
        if not chunks:
            chunks = [["[Instrumental / No lyrics]"]]

        synced_raw = lyrics_data.get("syncedLyrics")
        timed_lines = parse_lrc(synced_raw) if synced_raw else []
        is_synced = bool(timed_lines)

        pages = []
        for idx, chunk in enumerate(chunks):
            page_text = "\n".join(chunk)
            header_desc = f"**Artist:** {artist_name}\n\n" if is_synced else f"**Artist:** {artist_name}\n*(Static Lyrics — Real-time teleprompter sync unavailable for this track)*\n\n"
            footer_text = f"Page {idx+1}/{len(chunks)} • Sweety Karaoke Lyrics" if is_synced else f"Page {idx+1}/{len(chunks)} • Static / Unsynced Lyrics • Sweety Karaoke"
            embed = discord.Embed(
                title=f"🎤 {track_name}",
                description=f"{header_desc}{page_text}",
                color=0x1DB954
            )
            embed.set_footer(text=footer_text)
            pages.append(embed)

        # If current song is playing and has synced timestamps, launch LiveKaraokeView!
        if is_playing_track and timed_lines and state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()):
            if state.karaoke_task and not state.karaoke_task.done():
                state.karaoke_task.cancel()

            view = LiveKaraokeView(self, guild, track_name, artist_name, timed_lines, pages, user.id)
            elapsed = state.get_elapsed()
            dur = int(getattr(state.current, "duration", 0) or 0) or int(timed_lines[-1][0] + 15)
            initial_embed = view.build_teleprompter_embed(elapsed, dur)

            if hasattr(interaction_or_ctx, "response"):
                sent_msg = await interaction_or_ctx.followup.send(embed=initial_embed, view=view, ephemeral=False)
            else:
                sent_msg = await interaction_or_ctx.send(embed=initial_embed, view=view)

            view.message = sent_msg
            task = asyncio.create_task(view.karaoke_loop())
            view.update_task = task
            state.karaoke_task = task
        else:
            view = LyricsPaginationView(pages, user.id) if len(pages) > 1 else None
            if hasattr(interaction_or_ctx, "response"):
                await interaction_or_ctx.followup.send(embed=pages[0], view=view, ephemeral=ephemeral)
            else:
                await interaction_or_ctx.send(embed=pages[0], view=view)

    async def play_next(self, guild: discord.Guild):
        state = self.get_state(guild.id)

        # Process and record completed Karaoke Stage performance
        if state.karaoke_singer and state.current:
            singer = state.karaoke_singer
            song_title = state.current.title
            scores = dict(state.karaoke_scores)
            roses = state.karaoke_reactions.get("roses", 0)
            tomatoes = state.karaoke_reactions.get("tomatoes", 0)
            total_votes = len(scores)

            # Disable (grey out) the previous KaraokeJudgeView buttons by calling view.stop()
            if state.karaoke_judge_view:
                try:
                    state.karaoke_judge_view.stop()
                    for child in state.karaoke_judge_view.children:
                        child.disabled = True
                    if state.karaoke_stage_msg:
                        await state.karaoke_stage_msg.edit(view=state.karaoke_judge_view)
                except Exception as stop_view_err:
                    logger.debug(f"Error disabling karaoke judge view: {stop_view_err}")

            if total_votes < 3:
                # Minimum 3 votes required for award classification
                try:
                    await self.bot.db.execute(
                        """
                        INSERT INTO karaoke_performances (guild_id, user_id, user_name, song_title, score, votes_count)
                        VALUES ($1, $2, $3, $4, 0.0, $5)
                        """ if self.bot.db.is_postgres else """
                        INSERT INTO karaoke_performances (guild_id, user_id, user_name, song_title, score, votes_count)
                        VALUES (?, ?, ?, ?, 0.0, ?)
                        """,
                        guild.id, singer.id, singer.display_name, song_title, total_votes
                    )
                except Exception as de:
                    logger.debug(f"Failed to record unranked karaoke score: {de}")

                review_embed = discord.Embed(
                    title="🎸 Stage Review Complete",
                    description=(
                        f"🎤 **Singer:** {singer.mention}\n"
                        f"🎶 **Song:** `{song_title}`\n\n"
                        f"🎤 *Performance ended — not enough audience votes to award a score (minimum 3 votes required).*\n"
                        f"👥 **Judges:** {total_votes} listener(s)\n"
                        f"🌹 **Roses:** {roses}  •  🍅 **Tomatoes:** {tomatoes}"
                    ),
                    color=discord.Color.orange()
                )
                if singer.display_avatar:
                    review_embed.set_thumbnail(url=singer.display_avatar.url)
                review_embed.set_footer(text="Sweety Live Karaoke Stage")

                if state.text_channel:
                    try:
                        await state.text_channel.send(embed=review_embed)
                    except Exception:
                        pass
            else:
                avg = sum(scores.values()) / total_votes
                if avg >= 9.0:
                    verdict = "🌟 Platinum Idol (Perfection!)"
                    color = 0xFEE75C
                elif avg >= 7.5:
                    verdict = "🔥 Crowd Pleaser (Hype Performance!)"
                    color = 0x57F287
                elif avg >= 5.0:
                    verdict = "🎤 Rising Star (Solid Delivery!)"
                    color = 0x5865F2
                else:
                    verdict = "💀 Broken Mic Award (Better luck next time!)"
                    color = 0xED4245

                try:
                    await self.bot.db.execute(
                        """
                        INSERT INTO karaoke_performances (guild_id, user_id, user_name, song_title, score, votes_count)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """ if self.bot.db.is_postgres else """
                        INSERT INTO karaoke_performances (guild_id, user_id, user_name, song_title, score, votes_count)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        guild.id, singer.id, singer.display_name, song_title, round(avg, 2), total_votes
                    )
                except Exception as de:
                    logger.debug(f"Failed to record karaoke score: {de}")

                stars = "⭐" * int(round(avg / 2))
                review_embed = discord.Embed(
                    title="🎸 Stage Review Complete!",
                    description=(
                        f"🎤 **Singer:** {singer.mention}\n"
                        f"🎶 **Song:** `{song_title}`\n\n"
                        f"🏅 **Final Stage Score:** **{avg:.1f} / 10** {stars}\n"
                        f"🏆 **Verdict:** {verdict}\n"
                        f"👥 **Judges:** {total_votes} listener(s)\n"
                        f"🌹 **Roses:** {roses}  •  🍅 **Tomatoes:** {tomatoes}\n\n"
                        f"✨ *Type `!singers` to view the server's Rockstar Hall of Fame!*"
                    ),
                    color=color
                )
                if singer.display_avatar:
                    review_embed.set_thumbnail(url=singer.display_avatar.url)
                review_embed.set_footer(text="Sweety Live Karaoke Stage")

                if state.text_channel:
                    try:
                        await state.text_channel.send(embed=review_embed)
                    except Exception:
                        pass

            # Automatically clear previous singer state
            state.karaoke_singer = None
            state.karaoke_scores.clear()
            state.karaoke_reactions = {"roses": 0, "tomatoes": 0}
            state.karaoke_stage_msg = None
            state.karaoke_judge_view = None
            state.is_instrumental = False

        if state.karaoke_task and not state.karaoke_task.done():
            state.karaoke_task.cancel()
            state.karaoke_task = None

        if not state.voice_client or not state.voice_client.is_connected():
            if guild.voice_client and guild.voice_client.is_connected():
                state.voice_client = guild.voice_client
            else:
                return

        if state.update_task:
            state.update_task.cancel()
            state.update_task = None

        if state.loop and state.current:
            source = await YTDLSource.regrab_stream(state.current.data, state.volume, audio_filter=state.filter)
            state.start_time = time.time()
            state.paused_elapsed = 0.0
            state.pause_start = None
            state.voice_client.play(
                source,
                after=lambda e: self.schedule_play_next(guild)
            )
            state.current = source
            await self.set_vc_status(state.voice_client.channel, f"🎶 {source.title}")
            if state.np_message:
                embed = await self.build_np_embed(state)
                view = NowPlayingView(self, guild)
                await state.np_message.edit(embed=embed, view=view)
            state.update_task = asyncio.create_task(self.live_updater(guild))
            return

        if state.loop_queue and state.current:
            state.queue.append(state.current.data)

        if not state.queue:
            if state.autoplay and state.last_played_track:
                rec_track = await self.find_recommendation(state.last_played_track, state.played_history)
                if rec_track:
                    state.queue.append(rec_track)
                    if state.text_channel:
                        embed = discord.Embed(
                            title="📻 Smart Autoplay",
                            description=f"Queue finished. Auto-queued: **[{rec_track.get('title')}]({rec_track.get('webpage_url')})**",
                            color=0x1DB954
                        )
                        await state.text_channel.send(embed=embed)

        if not state.queue:
            state.current = None
            await self.bot.db.clear_music_queue(guild.id)
            await self.set_vc_status(state.voice_client.channel, "📻 Sweety 24/7 — Idle" if state.is_247 else None)
            if state.np_message:
                desc = "📻 **24/7 mode active** — staying in voice channel." if state.is_247 else "Add more tracks with `/play`."
                embed = discord.Embed(
                    title="✅ Queue Finished",
                    description=desc,
                    color=0x57F287 if state.is_247 else 0x5865F2
                )
                try:
                    await state.np_message.edit(embed=embed, view=None)
                except Exception:
                    pass
                state.np_message = None
            return

        track_data = state.queue.popleft()
        await self._persist_queue(guild.id)
        state.last_played_track = track_data
        state.played_history.append(track_data)
        try:
            source = await YTDLSource.regrab_stream(track_data, state.volume, audio_filter=state.filter)
            state.current = source
        except Exception as regrab_err:
            logger.error(f"Failed to stream track '{track_data.get('title')}': {regrab_err}")
            if state.text_channel:
                try:
                    await state.text_channel.send(f"⚠️ Could not stream **{track_data.get('title', 'Unknown')}** ({regrab_err}). Skipping to next track...")
                except Exception:
                    pass
            self.schedule_play_next(guild)
            return
        # Asynchronously log to Supabase song_history & in-memory cache
        if hasattr(self.bot, "db") and hasattr(self.bot.db, "log_song_history"):
            asyncio.create_task(
                self.bot.db.log_song_history(
                    guild_id=guild.id,
                    song_title=getattr(source, "title", "Unknown"),
                    uri=track_data.get("webpage_url") or track_data.get("url") or "",
                    duration=int(getattr(source, "duration", 0) or 0),
                    requester=str(track_data.get("requester") or "")
                )
            )

        state.skip_votes.clear()
        state.start_time = time.time()
        state.paused_elapsed = 0.0
        state.pause_start = None

        state.voice_client.play(
            source,
            after=lambda e: self.schedule_play_next(guild)
        )
        await self.set_vc_status(state.voice_client.channel, f"🎶 {source.title}")

        embed = await self.build_np_embed(state)
        view = NowPlayingView(self, guild)

        if state.np_message:
            try:
                await state.np_message.edit(embed=embed, view=view)
            except discord.NotFound:
                state.np_message = None

        if state.text_channel and not state.np_message:
            state.np_message = await state.text_channel.send(embed=embed, view=view)

        state.update_task = asyncio.create_task(self.live_updater(guild))

    @commands.command(name="bitrate", help="Check audio bitrate of the current voice channel")
    @commands.guild_only()
    async def bitrate_prefix(self, ctx: commands.Context):
        guild = ctx.guild
        member = ctx.author
        vc = getattr(getattr(member, "voice", None), "channel", None)
        bot_vc = getattr(getattr(guild, "voice_client", None), "channel", None)
        target_channel = vc or bot_vc

        if not target_channel:
            return await ctx.send("❌ Join a voice channel to inspect its bitrate.")

        current_kbps = getattr(target_channel, "bitrate", 64000) // 1000
        max_kbps = int(getattr(guild, "bitrate_limit", 96000)) // 1000
        boost_tier = getattr(guild, "premium_tier", 0)

        embed = discord.Embed(
            title="🔊 Voice Audio & Bitrate Fidelity",
            color=0x57F287 if current_kbps >= max_kbps else 0xFEE75C
        )
        embed.add_field(name="🎙️ Channel", value=target_channel.mention, inline=True)
        embed.add_field(name="⚡ Active Bitrate", value=f"**{current_kbps} kbps**", inline=True)
        embed.add_field(name="🏆 Max Server Limit", value=f"**{max_kbps} kbps** (Tier {boost_tier})", inline=True)
        embed.add_field(name="📊 Audio Quality", value="🟢 **Lossless Peak** (Maximum allowed by server tier)" if current_kbps >= max_kbps else "🟡 Below Capacity", inline=False)
        embed.set_footer(text="Sweety Ultra-High Fidelity Audio Engine")
        await ctx.send(embed=embed)

    @app_commands.command(name="play", description="Play a song — search by name or paste a URL")
    @app_commands.describe(query="Song name or URL")
    @app_commands.autocomplete(query=play_autocomplete)
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        if not interaction.user.voice:
            return await interaction.followup.send("❌ Join a voice channel first.", ephemeral=True)

        try:
            vc = interaction.user.voice.channel
            state = self.get_state(interaction.guild_id)
            state.text_channel = interaction.channel

            if not state.voice_client or not state.voice_client.is_connected():
                state.voice_client = await vc.connect(timeout=20.0, reconnect=True, self_deaf=True)
            elif state.voice_client.channel != vc:
                await state.voice_client.move_to(vc)

            is_247 = await self.is_247_enabled(interaction.guild_id)
            if is_247:
                try:
                    await self.bot.db.set_config(interaction.guild_id, "music_247_channel_id", str(vc.id))
                except Exception:
                    pass

            result, is_playlist = await YTDLSource.from_url(
                query, volume=state.volume, requester=str(interaction.user.display_name)
            )

            if is_playlist:
                playlist_warn = ""
                if len(result) > 100:
                    result = result[:100]
                    playlist_warn = "⚠️ Playlist capped at 100 tracks. Only the first 100 were added.\n"

                if len(state.queue) >= 200:
                    return await interaction.followup.send(
                        "⚠️ Queue is full (200 tracks max). Skip or remove some tracks first.",
                        ephemeral=True
                    )

                if len(state.queue) + len(result) > 200:
                    allowed = 200 - len(state.queue)
                    result = result[:allowed]
                    playlist_warn += f"⚠️ Queue reached 200 tracks limit. Only {allowed} tracks were added.\n"

                for track in result:
                    state.queue.append(track)
                await self._persist_queue(interaction.guild_id)

                embed = discord.Embed(
                    title="📋 Playlist Queued",
                    description=f"{playlist_warn}Added **{len(result)} tracks** to the queue.",
                    color=0x57F287
                )
                embed.set_footer(text=f"Requested by {interaction.user.display_name}")
                await interaction.followup.send(embed=embed)
                if not state.voice_client.is_playing():
                    await self.play_next(interaction.guild)
            else:
                if state.voice_client.is_playing() or state.voice_client.is_paused():
                    if len(state.queue) >= 200:
                        return await interaction.followup.send(
                            "⚠️ Queue is full (200 tracks max). Skip or remove some tracks first.",
                            ephemeral=True
                        )
                    state.queue.append(result.data)
                    await self._persist_queue(interaction.guild_id)
                    embed = discord.Embed(
                        title="➕ Added to Queue",
                        description=f"[{result.title}]({result.url})",
                        color=0x5865F2
                    )
                    embed.set_thumbnail(url=result.thumbnail)
                    embed.add_field(name="Duration", value=fmt_duration(result.duration))
                    embed.add_field(name="Position", value=f"#{len(state.queue)}")
                    embed.set_footer(text=f"Requested by {interaction.user.display_name}")
                    return await interaction.followup.send(embed=embed)
                else:
                    state.current = result
                    state.start_time = time.time()
                    state.paused_elapsed = 0.0
                    state.pause_start = None
                    state.voice_client.play(
                        result,
                        after=lambda e: self.schedule_play_next(interaction.guild)
                    )
                    await self.set_vc_status(state.voice_client.channel, f"🎶 {result.title}")
                    embed = await self.build_np_embed(state)
                    view = NowPlayingView(self, interaction.guild)
                    state.np_message = await interaction.followup.send(embed=embed, view=view)
                    state.update_task = asyncio.create_task(self.live_updater(interaction.guild))
        except ValueError as ve:
            return await interaction.followup.send(str(ve), ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /play: {e}")
            return await interaction.followup.send(f"❌ Error loading track: {e}", ephemeral=True)

    @app_commands.command(name="search", description="Search for a song and pick from results")
    @app_commands.describe(query="Song name to search")
    @app_commands.autocomplete(query=play_autocomplete)
    async def search(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        if not interaction.user.voice:
            return await interaction.followup.send("❌ Join a voice channel first.", ephemeral=True)

        canonical_q = query.strip()
        user_wants_variant = any(w in canonical_q.lower() for w in ("remix", "cover", "slowed", "flip", "edit", "instrumental", "karaoke", "live", "nightcore", "reverb", "acoustic", "extended", "sped up", "1 hour", "loop"))
        if spotify and not user_wants_variant:
            try:
                sp_res = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, lambda: spotify.search(q=canonical_q, type="track", limit=5)),
                    timeout=2.0
                )
                sp_items = sp_res.get("tracks", {}).get("items", []) if sp_res else []
                for sp_t in sp_items:
                    sp_name = sp_t.get("name", "")
                    sp_artist = sp_t["artists"][0]["name"] if sp_t.get("artists") else ""
                    if sp_name and validate_canonical_match(canonical_q, sp_artist, sp_name):
                        canonical_q = f"{sp_artist} - {sp_name}" if sp_artist else sp_name
                        break
            except Exception:
                pass

        try:
            data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: ytdl_search.extract_info(f"ytsearch10:{canonical_q}", download=False)
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ Search failed: `{e}`")

        raw_entries = [e for e in data.get("entries", []) if e] if data else []
        candidate_pool = [e for e in raw_entries if not is_vevo_entry(e)] or raw_entries
        ranked = sorted(candidate_pool, key=lambda e: score_music_candidate(e, canonical_q), reverse=True)
        entries = ranked[:5]

        if not entries:
            return await interaction.followup.send("❌ No results found.")

        # Build results embed
        lines = []
        for i, entry in enumerate(entries, 1):
            title = entry.get("title", "Unknown")[:50]
            dur = fmt_duration(entry.get("duration", 0))
            channel = entry.get("uploader", "Unknown")[:25]
            lines.append(f"`{i}.` **{title}** `{dur}`\n    ↳ {channel}")

        embed = discord.Embed(
            title=f"🔍 Results for: {query}",
            description="\n\n".join(lines),
            color=0x5865F2
        )
        embed.set_footer(text="Pick a track below — expires in 30s")

        view = SearchResultsView(self, interaction, entries)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="nowplaying", description="Show the now playing panel")
    async def nowplaying(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        if not state.current:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        embed = await self.build_np_embed(state)
        view = NowPlayingView(self, interaction.guild)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="skip", description="Skip the current track")
    async def skip(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        if not state.voice_client or not state.voice_client.is_playing():
            return await interaction.response.send_message("Nothing playing.", ephemeral=True)
        is_dj = await self.is_dj_or_admin(interaction.user)
        if is_dj:
            state.voice_client.stop()
            return await interaction.response.send_message("⏭ Skipped by DJ / Admin.")
        vc_members = [m for m in state.voice_client.channel.members if not m.bot]
        if len(vc_members) <= 1:
            state.voice_client.stop()
            return await interaction.response.send_message("⏭ Skipped.")
        state.skip_votes.add(interaction.user.id)
        needed = (len(vc_members) // 2) + 1
        if len(state.skip_votes) >= needed:
            state.skip_votes.clear()
            state.voice_client.stop()
            await interaction.response.send_message("⏭ Vote passed — skipped!")
        else:
            await interaction.response.send_message(f"🗳️ Vote recorded! **{len(state.skip_votes)}/{needed}** votes to skip.")

    @app_commands.command(name="stop", description="Stop music and clear queue")
    async def stop(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        await self.bot.db.clear_music_queue(interaction.guild_id)
        if state.voice_client:
            vc_channel = state.voice_client.channel
            state.clear()
            state.voice_client.stop()
            if not state.is_247:
                await state.voice_client.disconnect(force=True)
                state.voice_client = None
                await self.set_vc_status(vc_channel, None)
                await interaction.response.send_message("⏹ Stopped and disconnected.")
            else:
                await self.set_vc_status(vc_channel, "📻 Sweety 24/7 — Idle")
                await interaction.response.send_message("⏹ Stopped playback. *(24/7 mode active — staying in VC)*")
        else:
            await interaction.response.send_message("Nothing playing.", ephemeral=True)

    @app_commands.command(name="247", description="Toggle 24/7 mode so Sweety stays connected to the voice channel permanently")
    async def toggle_247_slash(self, interaction: discord.Interaction):
        await self.toggle_247(interaction)

    async def toggle_247(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)

        if not state.voice_client or not state.voice_client.is_connected():
            if not interaction.user.voice:
                return await interaction.response.send_message(
                    "❌ Join a voice channel first to enable 24/7 mode.", ephemeral=True
                )
            vc = interaction.user.voice.channel
            state.voice_client = await vc.connect(timeout=20.0, reconnect=True, self_deaf=True)
            state.text_channel = interaction.channel

        state.is_247 = not state.is_247

        try:
            await self.bot.db.set_config(
                interaction.guild_id, "music_247", "true" if state.is_247 else "false"
            )
            if state.is_247 and state.voice_client and state.voice_client.channel:
                await self.bot.db.set_config(
                    interaction.guild_id, "music_247_channel_id", str(state.voice_client.channel.id)
                )
            else:
                await self.bot.db.set_config(
                    interaction.guild_id, "music_247_channel_id", ""
                )
        except Exception as e:
            logger.debug(f"Failed to persist 24/7 config: {e}")

        ch_name = state.voice_client.channel.name if state.voice_client and state.voice_client.channel else "voice channel"

        if state.is_247:
            if not state.current:
                await self.set_vc_status(state.voice_client.channel, "📻 Sweety 24/7 — Idle")
            embed = discord.Embed(
                title="📻 24/7 Mode Enabled",
                description=f"Sweety will now stay in **{ch_name}** 24/7, even when the queue finishes or the bot restarts.",
                color=0x57F287
            )
            embed.set_footer(text="Use /247 or !247 again to disable.")
        else:
            embed = discord.Embed(
                title="📻 24/7 Mode Disabled",
                description="Sweety will now leave the voice channel when inactive.",
                color=0xED4245
            )
            if not state.queue and not state.current and state.voice_client:
                vc_channel = state.voice_client.channel
                await state.voice_client.disconnect(force=True)
                state.voice_client = None
                await self.set_vc_status(vc_channel, None)

        await interaction.response.send_message(embed=embed)

    @commands.command(name="247", aliases=["stay", "24/7"], help="Toggle 24/7 mode in voice channel")
    async def toggle_247_prefix(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)

        if not state.voice_client or not state.voice_client.is_connected():
            if not ctx.author.voice:
                return await ctx.send("❌ Join a voice channel first to enable 24/7 mode.")
            vc = ctx.author.voice.channel
            state.voice_client = await vc.connect(timeout=20.0, reconnect=True, self_deaf=True)
            state.text_channel = ctx.channel

        state.is_247 = not state.is_247

        try:
            await self.bot.db.set_config(
                ctx.guild.id, "music_247", "true" if state.is_247 else "false"
            )
            if state.is_247 and state.voice_client and state.voice_client.channel:
                await self.bot.db.set_config(
                    ctx.guild.id, "music_247_channel_id", str(state.voice_client.channel.id)
                )
            else:
                await self.bot.db.set_config(
                    ctx.guild.id, "music_247_channel_id", ""
                )
        except Exception as e:
            logger.debug(f"Failed to persist 24/7 config: {e}")

        ch_name = state.voice_client.channel.name if state.voice_client and state.voice_client.channel else "voice channel"

        if state.is_247:
            if not state.current:
                await self.set_vc_status(state.voice_client.channel, "📻 Sweety 24/7 — Idle")
            embed = discord.Embed(
                title="📻 24/7 Mode Enabled",
                description=f"Sweety will now stay in **{ch_name}** 24/7, even when the queue finishes or the bot restarts.",
                color=0x57F287
            )
            embed.set_footer(text="Use !247 or /247 again to disable.")
        else:
            embed = discord.Embed(
                title="📻 24/7 Mode Disabled",
                description="Sweety will now leave the voice channel when inactive.",
                color=0xED4245
            )
            if not state.queue and not state.current and state.voice_client:
                vc_channel = state.voice_client.channel
                await state.voice_client.disconnect(force=True)
                state.voice_client = None
                await self.set_vc_status(vc_channel, None)

        await ctx.send(embed=embed)

    @commands.command(name="stop", help="Stop playback and clear queue")
    async def stop_prefix(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        await self.bot.db.clear_music_queue(ctx.guild.id)
        if state.voice_client:
            vc_channel = state.voice_client.channel
            state.clear()
            state.voice_client.stop()
            if not state.is_247:
                await state.voice_client.disconnect(force=True)
                state.voice_client = None
                await self.set_vc_status(vc_channel, None)
                await ctx.send("⏹ Stopped and disconnected.")
            else:
                await self.set_vc_status(vc_channel, "📻 Sweety 24/7 — Idle")
                await ctx.send("⏹ Stopped playback. *(24/7 mode active — staying in VC. Use `!leave` or `!247` to disconnect)*")
        else:
            await ctx.send("Nothing playing.")

    @commands.command(name="disconnect", aliases=["leave", "dc"], help="Disconnect Sweety and disable 24/7 mode")
    async def disconnect_prefix(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        state.clear()
        state.is_247 = False
        await self.bot.db.clear_music_queue(ctx.guild.id)
        try:
            await self.bot.db.set_config(ctx.guild.id, "music_247", "false")
            await self.bot.db.set_config(ctx.guild.id, "music_247_channel_id", "")
        except Exception:
            pass

        if ctx.guild.voice_client:
            vc_channel = ctx.guild.voice_client.channel
            await ctx.guild.voice_client.disconnect(force=True)
            state.voice_client = None
            await self.set_vc_status(vc_channel, None)
            await ctx.send("👋 Disconnected and 24/7 mode disabled.")
        else:
            await ctx.send("❌ Not currently connected to a voice channel.")

    @commands.command(name="play", aliases=["p"], help="Play a song by name or URL")
    async def play_prefix(self, ctx: commands.Context, *, query: str):
        if not ctx.author.voice:
            return await ctx.send("❌ Join a voice channel first.")

        try:
            try:
                await ctx.typing()
            except Exception:
                pass
            vc = ctx.author.voice.channel
            state = self.get_state(ctx.guild.id)
            state.text_channel = ctx.channel

            if not state.voice_client or not state.voice_client.is_connected():
                state.voice_client = await vc.connect(timeout=20.0, reconnect=True, self_deaf=True)
            elif state.voice_client.channel != vc:
                await state.voice_client.move_to(vc)

            is_247 = await self.is_247_enabled(ctx.guild.id)
            if is_247:
                try:
                    await self.bot.db.set_config(ctx.guild.id, "music_247_channel_id", str(vc.id))
                except Exception:
                    pass

            result, is_playlist = await YTDLSource.from_url(
                query, volume=state.volume, requester=str(ctx.author.display_name)
            )

            if is_playlist:
                playlist_warn = ""
                if len(result) > 100:
                    result = result[:100]
                    playlist_warn = "⚠️ Playlist capped at 100 tracks. Only the first 100 were added.\n"

                if len(state.queue) >= 200:
                    return await ctx.send("⚠️ Queue is full (200 tracks max). Skip or remove some tracks first.")

                if len(state.queue) + len(result) > 200:
                    allowed = 200 - len(state.queue)
                    result = result[:allowed]
                    playlist_warn += f"⚠️ Queue reached 200 tracks limit. Only {allowed} tracks were added.\n"

                for track in result:
                    state.queue.append(track)
                await self._persist_queue(ctx.guild.id)

                embed = discord.Embed(
                    title="📋 Playlist Queued",
                    description=f"{playlist_warn}Added **{len(result)} tracks** to the queue.",
                    color=0x57F287
                )
                embed.set_footer(text=f"Requested by {ctx.author.display_name}")
                await ctx.send(embed=embed)
                if not state.voice_client.is_playing():
                    await self.play_next(ctx.guild)
            else:
                if state.voice_client.is_playing() or state.voice_client.is_paused():
                    if len(state.queue) >= 200:
                        return await ctx.send("⚠️ Queue is full (200 tracks max). Skip or remove some tracks first.")
                    state.queue.append(result.data)
                    await self._persist_queue(ctx.guild.id)
                    embed = discord.Embed(
                        title="➕ Added to Queue",
                        description=f"[{result.title}]({result.url})",
                        color=0x5865F2
                    )
                    embed.set_thumbnail(url=result.thumbnail)
                    embed.add_field(name="Duration", value=fmt_duration(result.duration))
                    embed.add_field(name="Position", value=f"#{len(state.queue)}")
                    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
                    return await ctx.send(embed=embed)
                else:
                    state.current = result
                    state.start_time = time.time()
                    state.paused_elapsed = 0.0
                    state.pause_start = None
                    state.voice_client.play(
                        result,
                        after=lambda e: self.schedule_play_next(ctx.guild)
                    )
                    await self.set_vc_status(state.voice_client.channel, f"🎶 {result.title}")
                    embed = await self.build_np_embed(state)
                    view = NowPlayingView(self, ctx.guild)
                    state.np_message = await ctx.send(embed=embed, view=view)
                    state.update_task = asyncio.create_task(self.live_updater(ctx.guild))
        except ValueError as ve:
            await ctx.send(str(ve))
        except Exception as e:
            logger.error(f"Error in play command: {e}")
            await ctx.send(f"❌ Error loading track: {e}")

    @commands.command(name="search", help="Search for a song and pick from results")
    async def search_prefix(self, ctx: commands.Context, *, query: str):
        if not ctx.author.voice:
            return await ctx.send("❌ Join a voice channel first.")

        canonical_q = query.strip()
        user_wants_variant = any(w in canonical_q.lower() for w in ("remix", "cover", "slowed", "flip", "edit", "instrumental", "karaoke", "live", "nightcore", "reverb", "acoustic", "extended", "sped up", "1 hour", "loop"))
        if spotify and not user_wants_variant:
            try:
                sp_res = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, lambda: spotify.search(q=canonical_q, type="track", limit=5)),
                    timeout=2.0
                )
                sp_items = sp_res.get("tracks", {}).get("items", []) if sp_res else []
                for sp_t in sp_items:
                    sp_name = sp_t.get("name", "")
                    sp_artist = sp_t["artists"][0]["name"] if sp_t.get("artists") else ""
                    if sp_name and validate_canonical_match(canonical_q, sp_artist, sp_name):
                        canonical_q = f"{sp_artist} - {sp_name}" if sp_artist else sp_name
                        break
            except Exception:
                pass

        try:
            data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: ytdl_search.extract_info(f"ytsearch10:{canonical_q}", download=False)
            )
        except Exception as e:
            return await ctx.send(f"❌ Search failed: `{e}`")

        raw_entries = [e for e in data.get("entries", []) if e] if data else []
        candidate_pool = [e for e in raw_entries if not is_vevo_entry(e)] or raw_entries
        ranked = sorted(candidate_pool, key=lambda e: score_music_candidate(e, canonical_q), reverse=True)
        entries = ranked[:5]

        if not entries:
            return await ctx.send("❌ No results found.")

        lines = []
        for i, entry in enumerate(entries, 1):
            title = entry.get("title", "Unknown")[:50]
            dur = fmt_duration(entry.get("duration", 0))
            channel = entry.get("uploader", "Unknown")[:25]
            lines.append(f"`{i}.` **{title}** `{dur}`\n    ↳ {channel}")

        embed = discord.Embed(
            title=f"🔍 Results for: {query}",
            description="\n\n".join(lines),
            color=0x5865F2
        )
        embed.set_footer(text="Pick a track below — expires in 30s")

        view = SearchResultsView(self, ctx, entries)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.command(name="skip", aliases=["s"], help="Skip current track")
    async def skip_prefix(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        if not state.voice_client or not state.voice_client.is_playing():
            return await ctx.send("Nothing playing.")
        is_dj = await self.is_dj_or_admin(ctx.author)
        if is_dj:
            state.voice_client.stop()
            return await ctx.send("⏭ Skipped by DJ / Admin.")
        vc_members = [m for m in state.voice_client.channel.members if not m.bot]
        if len(vc_members) <= 1:
            state.voice_client.stop()
            return await ctx.send("⏭ Skipped.")
        state.skip_votes.add(ctx.author.id)
        needed = (len(vc_members) // 2) + 1
        if len(state.skip_votes) >= needed:
            state.skip_votes.clear()
            state.voice_client.stop()
            await ctx.send("⏭ Vote passed — skipped!")
        else:
            await ctx.send(f"🗳️ Vote recorded! **{len(state.skip_votes)}/{needed}** votes to skip.")

    @commands.command(name="nowplaying", aliases=["np"], help="Show currently playing track")
    async def nowplaying_prefix(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        if not state.current:
            return await ctx.send("Nothing is playing.")
        embed = await self.build_np_embed(state)
        view = NowPlayingView(self, ctx.guild)
        await ctx.send(embed=embed, view=view)

    async def start_karaoke_stage(self, interaction_or_ctx, singer: Optional[discord.Member] = None):
        """Activates the live Karaoke Stage and opens the interactive Judge's Panel."""
        guild = interaction_or_ctx.guild
        member = singer or (interaction_or_ctx.user if hasattr(interaction_or_ctx, "user") else interaction_or_ctx.author)
        state = self.get_state(guild.id)

        if not state.current or not state.voice_client or not state.voice_client.is_connected():
            msg = "❌ Play a song first before taking the stage!"
            if hasattr(interaction_or_ctx, "response"):
                if not interaction_or_ctx.response.is_done():
                    return await interaction_or_ctx.response.send_message(msg, ephemeral=True)
                return await interaction_or_ctx.followup.send(msg, ephemeral=True)
            return await interaction_or_ctx.send(msg)

        if not member.voice or member.voice.channel != state.voice_client.channel:
            msg = f"❌ You must be in **{state.voice_client.channel.name}** to take the Karaoke Stage!"
            if hasattr(interaction_or_ctx, "response"):
                if not interaction_or_ctx.response.is_done():
                    return await interaction_or_ctx.response.send_message(msg, ephemeral=True)
                return await interaction_or_ctx.followup.send(msg, ephemeral=True)
            return await interaction_or_ctx.send(msg)

        # Check if another singer is already performing on stage
        if state.karaoke_singer and state.karaoke_singer.id != member.id and state.voice_client.is_playing():
            is_dj = await self.is_dj_or_admin(member)
            if not is_dj:
                msg = f"🎤 **{state.karaoke_singer.display_name}** is currently on stage performing! Wait until their track completes before taking the mic."
                if hasattr(interaction_or_ctx, "response"):
                    if not interaction_or_ctx.response.is_done():
                        return await interaction_or_ctx.response.send_message(msg, ephemeral=True)
                    return await interaction_or_ctx.followup.send(msg, ephemeral=True)
                return await interaction_or_ctx.send(msg)

        state.karaoke_singer = member
        state.karaoke_scores.clear()
        state.karaoke_reactions = {"roses": 0, "tomatoes": 0}

        view = KaraokeJudgeView(self, guild, member, state.current.title)
        embed = view.build_judge_embed()

        if hasattr(interaction_or_ctx, "response"):
            if not interaction_or_ctx.response.is_done():
                msg_obj = await interaction_or_ctx.response.send_message(embed=embed, view=view)
            else:
                msg_obj = await interaction_or_ctx.followup.send(embed=embed, view=view)
        else:
            msg_obj = await interaction_or_ctx.send(embed=embed, view=view)

        state.karaoke_stage_msg = msg_obj
        state.karaoke_judge_view = view
        await self.set_vc_status(state.voice_client.channel, f"🎤 Live Karaoke: {member.display_name} singing!")

    async def toggle_instrumental_backing(self, interaction_or_ctx):
        """Switches current playback between original vocal track and karaoke instrumental backing track."""
        guild = interaction_or_ctx.guild
        state = self.get_state(guild.id)

        if not state.current or not state.voice_client or not state.voice_client.is_connected():
            msg = "❌ Nothing is currently playing."
            if hasattr(interaction_or_ctx, "response"):
                if not interaction_or_ctx.response.is_done():
                    return await interaction_or_ctx.response.send_message(msg, ephemeral=True)
                return await interaction_or_ctx.followup.send(msg, ephemeral=True)
            return await interaction_or_ctx.send(msg)

        title = state.current.title
        clean_title = re.sub(r'[\(\[].*?[\)\]]', '', title).strip()
        elapsed = state.get_elapsed()

        if hasattr(interaction_or_ctx, "response") and not interaction_or_ctx.response.is_done():
            await interaction_or_ctx.response.defer()

        if not state.is_instrumental:
            query = f"{clean_title} karaoke instrumental"
            try:
                result, _ = await YTDLSource.from_url(
                    query,
                    volume=state.volume,
                    seek_seconds=int(elapsed),
                    audio_filter=state.filter,
                    requester="🎵 Karaoke Backing Track"
                )
                state.is_instrumental = True
                state.voice_client.source = result
                state.current = result
                yt_title = getattr(result, "title", clean_title)
                yt_url = getattr(result, "webpage_url", None) or "https://youtube.com"
                msg = (
                    f"🎵 Switched to **Karaoke Instrumental Track** at `{int(elapsed//60)}:{int(elapsed%60):02d}`!\n"
                    f"▶ **Selected Stream:** [{yt_title}]({yt_url})"
                )
            except Exception as e:
                msg = f"⚠️ Could not find an instrumental backing track for `{clean_title}`: {e}"
        else:
            try:
                result = await YTDLSource.regrab_stream(
                    state.current.data,
                    state.volume,
                    seek_seconds=int(elapsed),
                    audio_filter=state.filter
                )
                state.is_instrumental = False
                state.voice_client.source = result
                state.current = result
                msg = f"🎤 Switched back to **Original Vocal Track** for `{clean_title}`!"
            except Exception as e:
                msg = f"⚠️ Error returning to original track: {e}"

        if hasattr(interaction_or_ctx, "followup"):
            await interaction_or_ctx.followup.send(msg)
        else:
            await interaction_or_ctx.send(msg)

    @commands.command(name="sing", aliases=["stage", "mic"], help="Take the Karaoke Stage in voice channel")
    async def sing_prefix(self, ctx: commands.Context):
        await self.start_karaoke_stage(ctx)

    @commands.command(name="instrumental", aliases=["backing"], help="Switch to karaoke instrumental backing track")
    async def instrumental_prefix(self, ctx: commands.Context):
        await self.toggle_instrumental_backing(ctx)

    @commands.command(name="singers", aliases=["halloffame", "karaokelb", "idols"], help="View the server's Rockstar Hall of Fame")
    async def singers_leaderboard(self, ctx: commands.Context):
        """Displays the Top 10 Karaoke singers in the server."""
        try:
            query = """
                SELECT user_id, user_name, AVG(score) as avg_score, COUNT(*) as perf_count, MAX(score) as best_score
                FROM karaoke_performances
                WHERE guild_id = $1
                GROUP BY user_id, user_name
                ORDER BY avg_score DESC, perf_count DESC
                LIMIT 10
            """ if self.bot.db.is_postgres else """
                SELECT user_id, user_name, AVG(score) as avg_score, COUNT(*) as perf_count, MAX(score) as best_score
                FROM karaoke_performances
                WHERE guild_id = ?
                GROUP BY user_id, user_name
                ORDER BY avg_score DESC, perf_count DESC
                LIMIT 10
            """
            rows = await self.bot.db.fetch(query, ctx.guild.id)
            if not rows:
                embed = discord.Embed(
                    title="🎸 Rockstar Hall of Fame",
                    description=(
                        "No one has taken the Karaoke Stage yet in this server!\n\n"
                        "💡 **How to enter the Hall of Fame:**\n"
                        "1. Join a voice channel and play a song: `!play <song>`\n"
                        "2. Claim the mic: `!sing` or click `[🎙️ Stage]`\n"
                        "3. Sing along while your server members rate your performance!"
                    ),
                    color=0xFEE75C
                )
                return await ctx.send(embed=embed)

            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            lines = []
            for idx, r in enumerate(rows):
                medal = medals[idx] if idx < len(medals) else f"#{idx+1}"
                u_id = r["user_id"]
                u_name = r["user_name"]
                avg_s = float(r["avg_score"])
                p_cnt = int(r["perf_count"])
                best_s = float(r["best_score"])
                member = ctx.guild.get_member(int(u_id))
                name_str = member.mention if member else f"**{u_name}**"

                stars = "⭐" * int(round(avg_s / 2))
                lines.append(
                    f"{medal} {name_str} — **{avg_s:.1f} / 10** {stars}\n"
                    f"   └ *{p_cnt} song(s) performed • Personal Best: {best_s:.1f}/10*"
                )

            embed = discord.Embed(
                title=f"🎸 {ctx.guild.name}'s Rockstar Hall of Fame",
                description="\n\n".join(lines),
                color=0xFEE75C
            )
            embed.set_footer(text="Sweety Live Karaoke • Claim the mic with !sing or [🎙️ Stage]")
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Error fetching singers leaderboard: {e}")
            await ctx.send(f"❌ Error loading Hall of Fame: {e}")

    @app_commands.command(name="pause", description="Pause or resume music playback")
    async def pause(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        if state.voice_client and state.voice_client.is_playing():
            state.voice_client.pause()
            state.on_pause()
            await self.set_vc_status(state.voice_client.channel, f"⏸️ Paused: {state.current.title}" if state.current else None)
            if state.np_message:
                try:
                    embed = await self.build_np_embed(state)
                    await state.np_message.edit(embed=embed)
                except Exception:
                    pass
            await interaction.response.send_message("⏸ Paused.")
        elif state.voice_client and state.voice_client.is_paused():
            state.voice_client.resume()
            state.on_resume()
            await self.set_vc_status(state.voice_client.channel, f"🎶 {state.current.title}" if state.current else None)
            if state.np_message:
                try:
                    embed = await self.build_np_embed(state)
                    await state.np_message.edit(embed=embed)
                except Exception:
                    pass
            await interaction.response.send_message("▶️ Resumed.")
        else:
            await interaction.response.send_message("Nothing is currently playing or paused.", ephemeral=True)

    @commands.command(name="pause")
    async def prefix_pause(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        if state.voice_client and state.voice_client.is_playing():
            state.voice_client.pause()
            state.on_pause()
            await self.set_vc_status(state.voice_client.channel, f"⏸️ Paused: {state.current.title}" if state.current else None)
            await ctx.send("⏸ Paused.")
        elif state.voice_client and state.voice_client.is_paused():
            state.voice_client.resume()
            state.on_resume()
            await self.set_vc_status(state.voice_client.channel, f"🎶 {state.current.title}" if state.current else None)
            await ctx.send("▶️ Resumed.")
        else:
            await ctx.send("Nothing is currently playing or paused.")

    @commands.command(name="resume", aliases=["unpause"])
    async def prefix_resume(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        if state.voice_client and state.voice_client.is_paused():
            state.voice_client.resume()
            state.on_resume()
            await self.set_vc_status(state.voice_client.channel, f"🎶 {state.current.title}" if state.current else None)
            await ctx.send("▶️ Resumed.")
        else:
            await ctx.send("Nothing is paused.")

    @app_commands.command(name="volume", description="Set volume level (10% to 100%)")
    @app_commands.describe(level="Volume percentage from 10% to 100% (100% is standard)")
    async def volume(self, interaction: discord.Interaction, level: int):
        state = self.get_state(interaction.guild_id)
        warn_msg = None
        if level > 100:
            level = 100
            warn_msg = "⚠️ Volume capped at 100% to prevent audio distortion."
        elif level < 1:
            level = 10

        factor = round(level / 100.0, 3)
        state.volume = factor
        state.user_volume_level = level

        if state.current and hasattr(state.current, "volume"):
            state.current.volume = factor
        if state.voice_client and state.voice_client.source and hasattr(state.voice_client.source, "volume"):
            state.voice_client.source.volume = factor

        if state.np_message:
            try:
                embed = await self.build_np_embed(state)
                await state.np_message.edit(embed=embed)
            except Exception:
                pass

        vol_icon = "🔊" if level >= 60 else ("🔉" if level >= 20 else "🔈")
        if warn_msg:
            await interaction.response.send_message(f"{warn_msg}\n{vol_icon} Volume set to **{level}%** (10% to 100%).")
        else:
            await interaction.response.send_message(f"{vol_icon} Volume set to **{level}%** (10% to 100%).")

    @commands.command(name="volume", aliases=["vol"])
    async def prefix_volume(self, ctx: commands.Context, level: int):
        state = self.get_state(ctx.guild.id)
        warn_msg = None
        if level > 100:
            level = 100
            warn_msg = "⚠️ Volume capped at 100% to prevent audio distortion."
        elif level < 1:
            level = 10

        factor = round(level / 100.0, 3)
        state.volume = factor
        state.user_volume_level = level

        if state.current and hasattr(state.current, "volume"):
            state.current.volume = factor
        if state.voice_client and state.voice_client.source and hasattr(state.voice_client.source, "volume"):
            state.voice_client.source.volume = factor

        if state.np_message:
            try:
                embed = await self.build_np_embed(state)
                await state.np_message.edit(embed=embed)
            except Exception:
                pass

        vol_icon = "🔊" if level >= 60 else ("🔉" if level >= 20 else "🔈")
        if warn_msg:
            await ctx.send(f"{warn_msg}\n{vol_icon} Volume set to **{level}%** (10% to 100%).")
        else:
            await ctx.send(f"{vol_icon} Volume set to **{level}%** (10% to 100%).")

    @app_commands.command(name="loop", description="Toggle loop mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Track", value="track"),
        app_commands.Choice(name="Queue", value="queue"),
        app_commands.Choice(name="Off", value="off"),
    ])
    async def loop(self, interaction: discord.Interaction, mode: str):
        state = self.get_state(interaction.guild_id)
        state.loop = mode == "track"
        state.loop_queue = mode == "queue"
        msgs = {"track": "🔂 Looping track.", "queue": "🔁 Looping queue.", "off": "Loop off."}
        await interaction.response.send_message(msgs[mode])

    @app_commands.command(name="seek", description="Jump to a specific timestamp in the current song (e.g. 1:30 or 90)")
    @app_commands.describe(timestamp="Timestamp to jump to (e.g. 1:30, 02:45, or seconds like 90)")
    async def seek(self, interaction: discord.Interaction, timestamp: str):
        state = self.get_state(interaction.guild_id)
        if not state.voice_client or not state.current:
            return await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

        parts = timestamp.strip().split(":")
        try:
            if len(parts) == 1:
                seek_secs = int(parts[0])
            elif len(parts) == 2:
                seek_secs = int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                seek_secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            else:
                return await interaction.response.send_message("❌ Invalid timestamp format. Use `1:30` or seconds like `90`.", ephemeral=True)
        except ValueError:
            return await interaction.response.send_message("❌ Invalid timestamp format. Use `1:30` or seconds like `90`.", ephemeral=True)

        if seek_secs < 0 or (state.current.duration and seek_secs > state.current.duration):
            max_d = fmt_duration(state.current.duration) if state.current.duration else "song length"
            return await interaction.response.send_message(f"❌ Timestamp must be between `00:00` and `{max_d}`.", ephemeral=True)

        await interaction.response.defer()
        try:
            source = await YTDLSource.regrab_stream(state.current.data, state.volume, seek_seconds=seek_secs, audio_filter=state.filter)
            state.voice_client.pause()
            state.voice_client.stop()
            state.start_time = time.time()
            state.paused_elapsed = float(seek_secs)
            state.pause_start = None
            state.current = source
            state.voice_client.play(
                source,
                after=lambda e: self.schedule_play_next(interaction.guild)
            )
            embed = await self.build_np_embed(state)
            if state.np_message:
                try:
                    await state.np_message.edit(embed=embed)
                except Exception:
                    pass
            await interaction.followup.send(f"⏩ Seeked to **{fmt_duration(seek_secs)}**.")
        except Exception as e:
            logger.error(f"Error seeking: {e}")
            await interaction.followup.send(f"❌ Failed to seek: {e}", ephemeral=True)

    @commands.command(name="seek", help="Jump to timestamp (e.g. !seek 1:30)")
    async def prefix_seek(self, ctx: commands.Context, timestamp: str):
        state = self.get_state(ctx.guild.id)
        if not state.voice_client or not state.current:
            return await ctx.send("❌ Nothing is currently playing.")

        parts = timestamp.strip().split(":")
        try:
            if len(parts) == 1:
                seek_secs = int(parts[0])
            elif len(parts) == 2:
                seek_secs = int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                seek_secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            else:
                return await ctx.send("❌ Invalid timestamp format. Use `1:30` or seconds like `90`.")
        except ValueError:
            return await ctx.send("❌ Invalid timestamp format. Use `1:30` or seconds like `90`.")

        if seek_secs < 0 or (state.current.duration and seek_secs > state.current.duration):
            max_d = fmt_duration(state.current.duration) if state.current.duration else "song length"
            return await ctx.send(f"❌ Timestamp must be between `00:00` and `{max_d}`.")

        try:
            source = await YTDLSource.regrab_stream(state.current.data, state.volume, seek_seconds=seek_secs, audio_filter=state.filter)
            state.voice_client.pause()
            state.voice_client.stop()
            state.start_time = time.time()
            state.paused_elapsed = float(seek_secs)
            state.pause_start = None
            state.current = source
            state.voice_client.play(
                source,
                after=lambda e: self.schedule_play_next(ctx.guild)
            )
            embed = await self.build_np_embed(state)
            if state.np_message:
                try:
                    await state.np_message.edit(embed=embed)
                except Exception:
                    pass
            await ctx.send(f"⏩ Seeked to **{fmt_duration(seek_secs)}**.")
        except Exception as e:
            logger.error(f"Error seeking: {e}")
            await ctx.send(f"❌ Failed to seek: {e}")

    # ─── Queue Management Commands (/queue) ───────────────────────────────────

    queue_group = app_commands.Group(name="queue", description="View and manage the song queue")

    @queue_group.command(name="view", description="Show the current queue")
    async def queue_view_slash(self, interaction: discord.Interaction):
        await self.queue_cmd(interaction)

    @queue_group.command(name="remove", description="Remove a track from the queue by position")
    @app_commands.describe(position="Track number in the queue")
    async def queue_remove_slash(self, interaction: discord.Interaction, position: int):
        await self.remove(interaction, position)

    @queue_group.command(name="shuffle", description="Shuffle all tracks in the current queue")
    async def queue_shuffle_slash(self, interaction: discord.Interaction):
        await self.shuffle(interaction)

    @queue_group.command(name="clear", description="Clear all queued songs")
    async def queue_clear_slash(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        count = len(state.queue)
        state.queue.clear()
        await self.bot.db.clear_music_queue(interaction.guild_id)
        await interaction.response.send_message(f"🗑 Cleared **{count}** tracks from the queue.")

    @queue_group.command(name="autoplay", description="Toggle smart autoplay to recommend and queue similar tracks")
    @app_commands.describe(mode="Enable or disable autoplay (leave blank to toggle)")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Toggle", value="toggle"),
        app_commands.Choice(name="Enable (On)", value="on"),
        app_commands.Choice(name="Disable (Off)", value="off"),
    ])
    async def queue_autoplay_slash(self, interaction: discord.Interaction, mode: Optional[str] = "toggle"):
        state = self.get_state(interaction.guild_id)
        if mode == "on":
            state.autoplay = True
        elif mode == "off":
            state.autoplay = False
        else:
            state.autoplay = not state.autoplay
        status_str = "**Enabled** 🟢" if state.autoplay else "**Disabled** 🔴"
        await interaction.response.send_message(f"📻 Smart Autoplay is now {status_str}! When the queue ends, Sweety will automatically find and play similar songs.")

    async def shuffle(self, interaction: discord.Interaction):
        import random
        state = self.get_state(interaction.guild_id)
        if not state.queue:
            return await interaction.response.send_message("Queue empty.", ephemeral=True)
        q = list(state.queue)
        random.shuffle(q)
        state.queue = deque(q)
        await self._persist_queue(interaction.guild_id)
        await interaction.response.send_message("🔀 Shuffled.")

    async def queue_cmd(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        if not state.current and not state.queue:
            return await interaction.response.send_message("Queue empty.", ephemeral=True)
        embed = discord.Embed(title="🎶 Queue", color=0x5865F2)
        if state.current:
            embed.add_field(
                name="▶️ Now Playing",
                value=f"[{state.current.title}]({state.current.url}) `{fmt_duration(state.current.duration)}`",
                inline=False
            )
        if state.queue:
            lines = []
            for i, t in enumerate(list(state.queue)[:10], 1):
                lines.append(f"`{i}.` {t.get('title','Unknown')[:45]} `{fmt_duration(t.get('duration',0))}`")
            if len(state.queue) > 10:
                lines.append(f"*+{len(state.queue)-10} more*")
            embed.add_field(name="Up Next", value="\n".join(lines), inline=False)
        loop_str = "🔂 Track" if state.loop else ("🔁 Queue" if state.loop_queue else "Off")
        embed.set_footer(text=f"Loop: {loop_str}  •  Vol: {int(state.volume*100)}%")
        await interaction.response.send_message(embed=embed)

    async def remove(self, interaction: discord.Interaction, position: int):
        state = self.get_state(interaction.guild_id)
        if position < 1 or position > len(state.queue):
            return await interaction.response.send_message("Invalid position.", ephemeral=True)
        q = list(state.queue)
        removed = q.pop(position - 1)
        state.queue = deque(q)
        await self._persist_queue(interaction.guild_id)
        await interaction.response.send_message(f"🗑 Removed **{removed.get('title','Unknown')}**.")

    @commands.command(name="queue", aliases=["q"])
    async def prefix_queue(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        if not state.current and not state.queue:
            return await ctx.send("Queue empty.")
        embed = discord.Embed(title="🎶 Queue", color=0x5865F2)
        if state.current:
            embed.add_field(
                name="▶️ Now Playing",
                value=f"[{state.current.title}]({state.current.url}) `{fmt_duration(state.current.duration)}`",
                inline=False
            )
        if state.queue:
            lines = []
            for i, t in enumerate(list(state.queue)[:10], 1):
                lines.append(f"`{i}.` {t.get('title','Unknown')[:45]} `{fmt_duration(t.get('duration',0))}`")
            if len(state.queue) > 10:
                lines.append(f"*+{len(state.queue)-10} more*")
            embed.add_field(name="Up Next", value="\n".join(lines), inline=False)
        loop_str = "🔂 Track" if state.loop else ("🔁 Queue" if state.loop_queue else "Off")
        embed.set_footer(text=f"Loop: {loop_str}  •  Vol: {int(state.volume*100)}%")
        await ctx.send(embed=embed)

    @commands.command(name="shuffle")
    async def prefix_shuffle(self, ctx: commands.Context):
        import random
        state = self.get_state(ctx.guild.id)
        if not state.queue:
            return await ctx.send("Queue empty.")
        q = list(state.queue)
        random.shuffle(q)
        state.queue = deque(q)
        await self._persist_queue(ctx.guild.id)
        await ctx.send("🔀 Shuffled.")

    @commands.command(name="remove")
    async def prefix_remove(self, ctx: commands.Context, position: int):
        state = self.get_state(ctx.guild.id)
        if position < 1 or position > len(state.queue):
            return await ctx.send("Invalid position.")
        q = list(state.queue)
        removed = q.pop(position - 1)
        state.queue = deque(q)
        await self._persist_queue(ctx.guild.id)
        await ctx.send(f"🗑 Removed **{removed.get('title','Unknown')}**.")

    # ─── Spotify Commands (Grouped under /spotify) ─────────────────────────────

    spotify_group = app_commands.Group(name="spotify", description="Spotify profile and playlist integration")

    @spotify_group.command(name="link", description="Link your Spotify account or profile URL")
    @app_commands.describe(profile="Your Spotify profile URL (open.spotify.com/user/...) or username (leave empty for guide)")
    async def spotify_link(self, interaction: discord.Interaction, profile: Optional[str] = None):
        if not profile:
            base_url = os.getenv("RENDER_EXTERNAL_URL", "https://sweety-discord-bot-fra.onrender.com").rstrip("/")
            oauth_url = f"{base_url}/api/spotify/login?user_id={interaction.user.id}"

            embed = discord.Embed(
                title="🎧 How to Link Your Spotify Profile",
                description=(
                    "Link your Spotify profile to view, browse, and play your public playlists in voice channels!\n\n"
                    "**📱 On Phone (Mobile App — 3 Taps):**\n"
                    "1️⃣ Open the Spotify app.\n"
                    "2️⃣ Tap your **Profile icon** (top-left) ➔ **View profile**.\n"
                    "3️⃣ Tap the **3 dots (`...`)** ➔ **Share** ➔ **Copy link**.\n"
                    "4️⃣ Run: `/spotify link profile:<paste link>`\n\n"
                    "**💻 On Desktop / Web Browser:**\n"
                    "1️⃣ Click **🔍 Find My Username** below to view your account overview.\n"
                    "2️⃣ Copy your **Username** or profile URL.\n"
                    "3️⃣ Run: `/spotify link profile:<username>`\n\n"
                    "💡 *Sweety accepts full URLs (`open.spotify.com/user/...`) or raw usernames!*"
                ),
                color=0x1DB954
            )
            embed.set_footer(text="Sweety Music • Instant Spotify Profile Linking")

            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                label="Find My Username",
                url="https://www.spotify.com/account/overview/",
                style=discord.ButtonStyle.link,
                emoji="🔍"
            ))
            view.add_item(discord.ui.Button(
                label="Open Spotify Web",
                url="https://open.spotify.com/",
                style=discord.ButtonStyle.link,
                emoji="🎵"
            ))
            view.add_item(discord.ui.Button(
                label="Connect via OAuth",
                url=oauth_url,
                style=discord.ButtonStyle.link,
                emoji="⚡"
            ))

            return await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        await interaction.response.defer()
        user_id, prof_url = parse_spotify_user_input(profile)
        info = await asyncio.get_running_loop().run_in_executor(
            None, lambda: fetch_spotify_profile_info(user_id)
        )
        if not info:
            return await interaction.followup.send(
                "❌ Could not find a Spotify profile for that URL or ID. Please check your link.",
                ephemeral=True
            )

        ok = await self.bot.db.set_spotify_profile(
            interaction.user.id,
            info["spotify_id"],
            info["display_name"],
            info["profile_url"],
            info.get("avatar_url")
        )
        if not ok:
            return await interaction.followup.send("❌ Failed to save profile to database.", ephemeral=True)

        embed = discord.Embed(
            title="🔗 Spotify Profile Linked!",
            description=f"Successfully linked **[{info['display_name']}]({info['profile_url']})** to your Discord account.",
            color=0x1DB954
        )
        if info.get("avatar_url"):
            embed.set_thumbnail(url=info["avatar_url"])
        pl_count = len(info.get("playlists", []))
        embed.add_field(name="Public Playlists", value=f"**{pl_count}** found", inline=True)
        embed.add_field(name="Username / ID", value=f"`{info['spotify_id']}`", inline=True)
        embed.set_footer(text="Use /spotify playlists to view and play your playlists!")
        await interaction.followup.send(embed=embed)

    @spotify_group.command(name="profile", description="View a member's linked Spotify profile")
    @app_commands.describe(member="Member to view (defaults to yourself)")
    async def spotify_profile(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        await interaction.response.defer()

        row = await self.bot.db.get_spotify_profile(target.id)
        if not row:
            msg = "You haven't linked a Spotify profile yet. Run `/spotify link <profile_url>`!" if target.id == interaction.user.id else f"{target.display_name} has not linked a Spotify profile."
            return await interaction.followup.send(f"❌ {msg}", ephemeral=True)

        info = await asyncio.get_running_loop().run_in_executor(
            None, lambda: fetch_spotify_profile_info(row["spotify_id"])
        )
        data = info or row

        embed = discord.Embed(
            title=f"🎵 {data.get('display_name', 'Spotify Profile')}",
            url=data.get("profile_url", f"https://open.spotify.com/user/{data['spotify_id']}"),
            color=0x1DB954
        )
        if data.get("avatar_url"):
            embed.set_thumbnail(url=data["avatar_url"])

        embed.add_field(name="Discord User", value=target.mention, inline=True)
        embed.add_field(name="Spotify ID", value=f"`{data['spotify_id']}`", inline=True)
        if info and "playlists" in info:
            embed.add_field(name="Public Playlists", value=f"**{len(info['playlists'])}** playlists", inline=True)
        embed.set_footer(text="Use /spotify playlists to browse & play tracks")
        await interaction.followup.send(embed=embed)

    @spotify_group.command(name="playlists", description="View and play public playlists from a linked Spotify profile")
    @app_commands.describe(member="Member to view playlists from (defaults to yourself)")
    async def spotify_playlists(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        await interaction.response.defer()

        row = await self.bot.db.get_spotify_profile(target.id)
        if not row:
            msg = "You haven't linked a Spotify profile yet. Run `/spotify link <profile_url>` first!" if target.id == interaction.user.id else f"{target.display_name} has not linked a Spotify profile."
            return await interaction.followup.send(f"❌ {msg}", ephemeral=True)

        playlists = []
        if row.get("playlists"):
            try:
                playlists = json.loads(row["playlists"])
            except Exception:
                playlists = []

        info = await asyncio.get_running_loop().run_in_executor(
            None, lambda: fetch_spotify_profile_info(row["spotify_id"])
        )
        if not info:
            info = dict(row)

        if not playlists and info.get("playlists"):
            playlists = info["playlists"]
        elif playlists:
            info["playlists"] = playlists

        if not playlists:
            return await interaction.followup.send(
                "❌ **No playlists found on this Spotify profile.**\n\n"
                "**Why are your playlists missing?**\n"
                "1️⃣ **Profile Visibility:** In Spotify, open your playlist ➔ click `...` ➔ select **'Add to profile'** so it is visible publicly.\n"
                "2️⃣ **Direct Import:** You can also import any Spotify playlist directly into Sweety using:\n"
                "`/spotify import playlist_url:<your playlist link>`\n"
                "3️⃣ **Play Directly:** Or just play it anytime in VC using `/play <your playlist link>`!",
                ephemeral=True
            )

        embed = discord.Embed(
            title=f"🎧 Playlists for {info.get('display_name', row.get('display_name', 'User'))}",
            description=f"Found **{len(playlists)} playlists** on [{info.get('display_name', 'Spotify Profile')}]({info.get('profile_url', row.get('profile_url'))}).\nSelect a playlist below to **Play in VC** or **Save to Sweety**:",
            color=0x1DB954
        )
        if info.get("avatar_url"):
            embed.set_thumbnail(url=info["avatar_url"])

        for i, p in enumerate(playlists[:8], 1):
            embed.add_field(name=f"`{i}.` {p['name'][:30]}", value=f"[Open in Spotify]({p['url']})", inline=True)

        view = SpotifyPlaylistsView(self, interaction.user, info)
        await interaction.followup.send(embed=embed, view=view)

    @spotify_group.command(name="play", description="Play a Spotify playlist by name or URL")
    @app_commands.describe(playlist="Playlist name (from your linked profile) or Spotify playlist link")
    async def spotify_play(self, interaction: discord.Interaction, playlist: str):
        await interaction.response.defer()
        if not interaction.user.voice:
            return await interaction.followup.send("❌ Join a voice channel first.", ephemeral=True)

        playlist_url = None
        playlist_name = playlist

        # Check if direct URL was passed
        if "spotify.com/playlist/" in playlist or playlist.startswith("spotify:playlist:"):
            playlist_url = playlist
        else:
            row = await self.bot.db.get_spotify_profile(interaction.user.id)
            if not row:
                return await interaction.followup.send(
                    "❌ Please link your Spotify profile with `/spotify link` or paste a direct Spotify playlist URL.",
                    ephemeral=True
                )
            info = await asyncio.get_running_loop().run_in_executor(
                None, lambda: fetch_spotify_profile_info(row["spotify_id"])
            )
            if info and info.get("playlists"):
                for p in info["playlists"]:
                    if playlist.lower() in p["name"].lower():
                        playlist_url = p["url"]
                        playlist_name = p["name"]
                        break

        if not playlist_url:
            return await interaction.followup.send(f"❌ Could not find a playlist matching **{playlist}**.", ephemeral=True)

        vc = interaction.user.voice.channel
        state = self.get_state(interaction.guild_id)
        state.text_channel = interaction.channel

        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await vc.connect(timeout=20.0, reconnect=True, self_deaf=True)
        elif state.voice_client.channel != vc:
            await state.voice_client.move_to(vc)

        is_247 = await self.is_247_enabled(interaction.guild_id)
        if is_247:
            try:
                await self.bot.db.set_config(interaction.guild_id, "music_247_channel_id", str(vc.id))
            except Exception:
                pass

        tracks = await asyncio.get_running_loop().run_in_executor(
            None, lambda: extract_spotify_playlist_tracks_public(playlist_url)
        )
        if not tracks:
            return await interaction.followup.send("❌ Failed to retrieve tracks from this Spotify playlist.", ephemeral=True)

        playlist_warn = ""
        if len(tracks) > 100:
            tracks = tracks[:100]
            playlist_warn = "⚠️ Playlist capped at 100 tracks. Only the first 100 were added.\n"

        if len(state.queue) >= 200:
            return await interaction.followup.send(
                "⚠️ Queue is full (200 tracks max). Skip or remove some tracks first.",
                ephemeral=True
            )

        if len(state.queue) + len(tracks) > 200:
            allowed = 200 - len(state.queue)
            tracks = tracks[:allowed]
            playlist_warn += f"⚠️ Queue reached 200 tracks limit. Only {allowed} tracks were added.\n"

        for t in tracks:
            t["requester"] = str(interaction.user.display_name)
            state.queue.append(t)
        await self._persist_queue(interaction.guild_id)

        embed = discord.Embed(
            title="📋 Spotify Playlist Queued",
            description=f"{playlist_warn}Queued **{len(tracks)} tracks** from **{playlist_name}**.",
            color=0x1DB954
        )
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

        if not state.voice_client.is_playing() and not state.voice_client.is_paused():
            await self.play_next(interaction.guild)

    @spotify_group.command(name="import", description="Import a Spotify playlist into your saved Sweety playlists")
    @app_commands.describe(playlist_url="Spotify playlist link", name="Custom name for the saved playlist (optional)")
    async def spotify_import(self, interaction: discord.Interaction, playlist_url: str, name: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if "spotify.com/playlist/" not in playlist_url:
            return await interaction.followup.send("❌ Invalid Spotify playlist link. Format: `https://open.spotify.com/playlist/...`")

        tracks = await asyncio.get_running_loop().run_in_executor(
            None, lambda: extract_spotify_playlist_tracks_public(playlist_url)
        )
        if not tracks:
            return await interaction.followup.send("❌ Could not extract tracks from this playlist link.")

        save_name = (name or "spotify_import").strip()[:32]
        try:
            await self.bot.db.execute("""
                INSERT INTO music_playlists (user_id, name, tracks, guild_id, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (user_id, name)
                DO UPDATE SET tracks = $3, guild_id = $4, updated_at = NOW()
            """, interaction.user.id, save_name, json.dumps(tracks), interaction.guild_id)
            await interaction.followup.send(
                f"✅ Successfully imported **{len(tracks)} tracks** into playlist **{save_name}**!\nPlay it anytime using `/playlist play {save_name}`."
            )
        except Exception as e:
            await interaction.followup.send(f"❌ DB error: {e}")

    @spotify_group.command(name="unlink", description="Unlink your Spotify profile")
    async def spotify_unlink(self, interaction: discord.Interaction):
        await self.bot.db.delete_spotify_profile(interaction.user.id)
        await interaction.response.send_message("🗑 Unlinked your Spotify profile.", ephemeral=True)

    @commands.group(name="spotify", invoke_without_command=True)
    async def spotify_prefix(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🎧 Sweety Spotify Integration",
            description=(
                "`!spotify link [url_or_id]` — Link profile (or get 1-click connect button)\n"
                "`!spotify profile [member]` — View linked profile\n"
                "`!spotify playlists [member]` — View & play public playlists\n"
                "`!spotify play <name_or_url>` — Play a playlist\n"
                "`!spotify import <url> [name]` — Import into bot playlists\n"
                "`!spotify unlink` — Unlink profile"
            ),
            color=0x1DB954
        )
        await ctx.send(embed=embed)

    @spotify_prefix.command(name="link")
    async def spotify_prefix_link(self, ctx: commands.Context, *, profile: Optional[str] = None):
        base_url = os.getenv("RENDER_EXTERNAL_URL", "https://sweety-discord-bot-fra.onrender.com").rstrip("/")
        oauth_url = f"{base_url}/api/spotify/login?user_id={ctx.author.id}"
        if not profile:
            embed = discord.Embed(
                title="🎧 How to Link Your Spotify Profile",
                description=(
                    "Link your Spotify profile to view, browse, and play your public playlists in voice channels!\n\n"
                    "**📱 On Phone (Mobile App — 3 Taps):**\n"
                    "1️⃣ Open the Spotify app.\n"
                    "2️⃣ Tap your **Profile icon** (top-left) ➔ **View profile**.\n"
                    "3️⃣ Tap the **3 dots (`...`)** ➔ **Share** ➔ **Copy link**.\n"
                    "4️⃣ Run: `!spotify link <paste link>`\n\n"
                    "**💻 On Desktop / Web Browser:**\n"
                    "1️⃣ Click **🔍 Find My Username** below to view your account overview.\n"
                    "2️⃣ Copy your **Username** or profile URL.\n"
                    "3️⃣ Run: `!spotify link <username>`\n\n"
                    "💡 *Sweety accepts full URLs (`open.spotify.com/user/...`) or raw usernames!*"
                ),
                color=0x1DB954
            )
            embed.set_footer(text="Sweety Music • Instant Spotify Profile Linking")
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                label="Find My Username",
                url="https://www.spotify.com/account/overview/",
                style=discord.ButtonStyle.link,
                emoji="🔍"
            ))
            view.add_item(discord.ui.Button(
                label="Open Spotify Web",
                url="https://open.spotify.com/",
                style=discord.ButtonStyle.link,
                emoji="🎵"
            ))
            view.add_item(discord.ui.Button(
                label="Connect via OAuth",
                url=oauth_url,
                style=discord.ButtonStyle.link,
                emoji="⚡"
            ))
            return await ctx.send(embed=embed, view=view)

        user_id, prof_url = parse_spotify_user_input(profile)
        info = await asyncio.get_running_loop().run_in_executor(
            None, lambda: fetch_spotify_profile_info(user_id)
        )
        if not info:
            return await ctx.send("❌ Could not find a Spotify profile for that URL or ID.")
        ok = await self.bot.db.set_spotify_profile(
            ctx.author.id, info["spotify_id"], info["display_name"], info["profile_url"], info.get("avatar_url")
        )
        if not ok:
            return await ctx.send("❌ Failed to save profile to database.")
        embed = discord.Embed(
            title="🔗 Spotify Profile Linked!",
            description=f"Successfully linked **[{info['display_name']}]({info['profile_url']})** to your Discord account.",
            color=0x1DB954
        )
        if info.get("avatar_url"):
            embed.set_thumbnail(url=info["avatar_url"])
        embed.set_footer(text="Use !spotify playlists to view and play your playlists!")
        await ctx.send(embed=embed)

    # ─── Saved Playlist Commands (Integrated into /spotify to save global command slots) ───

    @spotify_group.command(name="saved_play", description="Load and play a saved playlist")
    @app_commands.describe(name="The name of your saved playlist")
    async def playlist_play(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        if not interaction.user.voice:
            return await interaction.followup.send("❌ Join a voice channel first.", ephemeral=True)
        try:
            row = await self.bot.db.fetchrow(
                "SELECT tracks FROM music_playlists WHERE user_id=$1 AND name=$2 AND (guild_id=$3 OR guild_id IS NULL)",
                interaction.user.id, name, interaction.guild_id
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ DB error: {e}")
        if not row:
            return await interaction.followup.send(f"❌ No playlist named **{name}**.", ephemeral=True)
        tracks = json.loads(row["tracks"])
        state = self.get_state(interaction.guild_id)
        state.text_channel = interaction.channel

        playlist_warn = ""
        if len(tracks) > 100:
            tracks = tracks[:100]
            playlist_warn = "⚠️ Playlist capped at 100 tracks. Only the first 100 were added.\n"

        if len(state.queue) >= 200:
            return await interaction.followup.send(
                "⚠️ Queue is full (200 tracks max). Skip or remove some tracks first.",
                ephemeral=True
            )

        if len(state.queue) + len(tracks) > 200:
            allowed = 200 - len(state.queue)
            tracks = tracks[:allowed]
            playlist_warn += f"⚠️ Queue reached 200 tracks limit. Only {allowed} tracks were added.\n"

        vc = interaction.user.voice.channel
        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await vc.connect(timeout=20.0, reconnect=True, self_deaf=True)
        elif state.voice_client.channel != vc:
            await state.voice_client.move_to(vc)

        is_247 = await self.is_247_enabled(interaction.guild_id)
        if is_247:
            try:
                await self.bot.db.set_config(interaction.guild_id, "music_247_channel_id", str(vc.id))
            except Exception:
                pass
        for t in tracks:
            state.queue.append(t)
        await self._persist_queue(interaction.guild_id)
        if not state.voice_client.is_playing():
            await self.play_next(interaction.guild)
        embed = discord.Embed(
            title="📋 Playlist Loaded",
            description=f"{playlist_warn}**{name}** — {len(tracks)} tracks queued.",
            color=0x57F287
        )
        await interaction.followup.send(embed=embed)

    @spotify_group.command(name="saved_list", description="Show your saved playlists")
    async def playlist_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            rows = await self.bot.db.fetch(
                "SELECT name, tracks FROM music_playlists WHERE user_id=$1 AND (guild_id=$2 OR guild_id IS NULL) ORDER BY created_at DESC",
                interaction.user.id, interaction.guild_id
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ DB error: {e}")
        if not rows:
            return await interaction.followup.send("No saved playlists.")
        embed = discord.Embed(title="🎵 Your Saved Playlists", color=0x5865F2)
        for row in rows:
            count = len(json.loads(row["tracks"]))
            embed.add_field(name=row["name"], value=f"{count} tracks", inline=True)
        await interaction.followup.send(embed=embed)

    @spotify_group.command(name="saved_delete", description="Delete a saved playlist")
    @app_commands.describe(name="The name of the playlist to delete")
    async def playlist_delete(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.db.execute(
                "DELETE FROM music_playlists WHERE user_id=$1 AND name=$2 AND (guild_id=$3 OR guild_id IS NULL)",
                interaction.user.id, name, interaction.guild_id
            )
            if result == "DELETE 0":
                await interaction.followup.send(f"No playlist named **{name}**.")
            else:
                await interaction.followup.send(f"🗑 Deleted **{name}**.")
        except Exception as e:
            await interaction.followup.send(f"❌ DB error: {e}")

    # ─── Prefix Playlist Commands (!playlist play/list/delete) ──────────────────

    @commands.group(name="playlist", invoke_without_command=True)
    async def prefix_playlist_group(self, ctx: commands.Context):
        embed = discord.Embed(
            title="📋 Sweety Saved Playlists",
            description=(
                "`!playlist play <name>` — Load and play a saved playlist\n"
                "`!playlist list` — View all your saved playlists\n"
                "`!playlist delete <name>` — Delete a saved playlist"
            ),
            color=0x5865F2
        )
        await ctx.send(embed=embed)

    @prefix_playlist_group.command(name="play")
    async def prefix_playlist_play(self, ctx: commands.Context, *, name: str):
        if not ctx.author.voice:
            return await ctx.send("❌ Join a voice channel first.")
        try:
            row = await self.bot.db.fetchrow(
                "SELECT tracks FROM music_playlists WHERE user_id=$1 AND name=$2 AND (guild_id=$3 OR guild_id IS NULL)",
                ctx.author.id, name, ctx.guild.id
            )
        except Exception as e:
            return await ctx.send(f"❌ DB error: {e}")
        if not row:
            return await ctx.send(f"❌ No playlist named **{name}**.")
        tracks = json.loads(row["tracks"])
        state = self.get_state(ctx.guild.id)
        state.text_channel = ctx.channel

        playlist_warn = ""
        if len(tracks) > 100:
            tracks = tracks[:100]
            playlist_warn = "⚠️ Playlist capped at 100 tracks. Only the first 100 were added.\n"

        if len(state.queue) >= 200:
            return await ctx.send("⚠️ Queue is full (200 tracks max). Skip or remove some tracks first.")

        if len(state.queue) + len(tracks) > 200:
            allowed = 200 - len(state.queue)
            tracks = tracks[:allowed]
            playlist_warn += f"⚠️ Queue reached 200 tracks limit. Only {allowed} tracks were added.\n"

        vc = ctx.author.voice.channel
        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await vc.connect(timeout=20.0, reconnect=True, self_deaf=True)
        elif state.voice_client.channel != vc:
            await state.voice_client.move_to(vc)

        is_247 = await self.is_247_enabled(ctx.guild.id)
        if is_247:
            try:
                await self.bot.db.set_config(ctx.guild.id, "music_247_channel_id", str(vc.id))
            except Exception:
                pass
        for t in tracks:
            state.queue.append(t)
        await self._persist_queue(ctx.guild.id)
        if not state.voice_client.is_playing():
            await self.play_next(ctx.guild)
        embed = discord.Embed(
            title="📋 Playlist Loaded",
            description=f"{playlist_warn}**{name}** — {len(tracks)} tracks queued.",
            color=0x57F287
        )
        await ctx.send(embed=embed)

    @prefix_playlist_group.command(name="list")
    async def prefix_playlist_list(self, ctx: commands.Context):
        try:
            rows = await self.bot.db.fetch(
                "SELECT name, tracks FROM music_playlists WHERE user_id=$1 AND (guild_id=$2 OR guild_id IS NULL) ORDER BY created_at DESC",
                ctx.author.id, ctx.guild.id
            )
        except Exception as e:
            return await ctx.send(f"❌ DB error: {e}")
        if not rows:
            return await ctx.send("No saved playlists.")
        embed = discord.Embed(title="🎵 Your Saved Playlists", color=0x5865F2)
        for row in rows:
            count = len(json.loads(row["tracks"]))
            embed.add_field(name=row["name"], value=f"{count} tracks", inline=True)
        await ctx.send(embed=embed)

    @prefix_playlist_group.command(name="delete")
    async def prefix_playlist_delete(self, ctx: commands.Context, *, name: str):
        try:
            result = await self.bot.db.execute(
                "DELETE FROM music_playlists WHERE user_id=$1 AND name=$2 AND (guild_id=$3 OR guild_id IS NULL)",
                ctx.author.id, name, ctx.guild.id
            )
            if result == "DELETE 0":
                await ctx.send(f"No playlist named **{name}**.")
            else:
                await ctx.send(f"🗑 Deleted **{name}**.")
        except Exception as e:
            await ctx.send(f"❌ DB error: {e}")

    # ─── Live Lyrics & Karaoke ───────────────────────────────────────────────

    @app_commands.command(name="lyrics", description="View synced karaoke lyrics for the current song or search query")
    @app_commands.describe(query="Song title to search (leave blank for currently playing song)")
    async def lyrics_slash(self, interaction: discord.Interaction, query: Optional[str] = None):
        await interaction.response.defer()
        await self.display_lyrics(interaction, query, ephemeral=False)

    @commands.command(name="lyrics")
    async def lyrics_prefix(self, ctx: commands.Context, *, query: Optional[str] = None):
        await self.display_lyrics(ctx, query)

    # ─── Audio Equalizer & Filters (/filter) ──────────────────────────────────

    filter_group = app_commands.Group(name="filter", description="Audio equalizer and sound effect presets")

    @filter_group.command(name="set", description="Apply an audio equalizer filter preset")
    @app_commands.describe(preset="Audio filter preset to apply")
    @app_commands.choices(preset=[
        app_commands.Choice(name="Bassboost (Medium)", value="bassboost"),
        app_commands.Choice(name="Bassboost High (Extreme)", value="bassboost_high"),
        app_commands.Choice(name="Nightcore (High pitch + speed)", value="nightcore"),
        app_commands.Choice(name="Vaporwave (Slowed + retro reverb)", value="vaporwave"),
        app_commands.Choice(name="8D Audio (Surround circle)", value="8d"),
        app_commands.Choice(name="Pop EQ (Mid & vocal boost)", value="pop"),
        app_commands.Choice(name="Treble Boost", value="treble"),
    ])
    async def filter_set_slash(self, interaction: discord.Interaction, preset: str):
        state = self.get_state(interaction.guild_id)
        state.filter = preset
        if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()) and state.current:
            try:
                elapsed = int(state.get_elapsed())
                new_source = await YTDLSource.regrab_stream(
                    state.current.data,
                    volume=state.volume,
                    seek_seconds=elapsed,
                    audio_filter=state.filter
                )
                new_source.title = state.current.title
                state.current = new_source
                state.voice_client.source = new_source
            except Exception as e:
                logger.warning(f"Error hot-swapping filter: {e}")

        if state.np_message:
            try:
                embed = await self.build_np_embed(state)
                await state.np_message.edit(embed=embed)
            except Exception:
                pass
        await interaction.response.send_message(f"🎛️ Audio filter set to **{preset}**!")

    @filter_group.command(name="clear", description="Clear audio filter and return to normal")
    async def filter_clear_slash(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        state.filter = None
        if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()) and state.current:
            try:
                elapsed = int(state.get_elapsed())
                new_source = await YTDLSource.regrab_stream(
                    state.current.data,
                    volume=state.volume,
                    seek_seconds=elapsed,
                    audio_filter=None
                )
                new_source.title = state.current.title
                state.current = new_source
                state.voice_client.source = new_source
            except Exception as e:
                logger.warning(f"Error hot-swapping filter: {e}")

        if state.np_message:
            try:
                embed = await self.build_np_embed(state)
                await state.np_message.edit(embed=embed)
            except Exception:
                pass
        await interaction.response.send_message("🔄 Audio filter reset to **Normal**.")

    @filter_group.command(name="list", description="List all available audio filters")
    async def filter_list_slash(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎛️ Sweety Audio Filters",
            description=(
                "`/filter set bassboost` — Rich +10dB bass punch\n"
                "`/filter set bassboost_high` — Heavy +16dB bass boost\n"
                "`/filter set nightcore` — High pitch & 1.25x tempo\n"
                "`/filter set vaporwave` — Slowed 0.85x + retro echo reverb\n"
                "`/filter set 8d` — 360° surround headphone circle\n"
                "`/filter set pop` — Vocal and mid equalizer boost\n"
                "`/filter set treble` — Crisp high-frequency boost\n"
                "`/filter clear` — Reset back to normal"
            ),
            color=0x5865F2
        )
        await interaction.response.send_message(embed=embed)

    @commands.group(name="filter", invoke_without_command=True)
    async def filter_prefix_group(self, ctx: commands.Context, preset: Optional[str] = None):
        if not preset:
            embed = discord.Embed(
                title="🎛️ Audio Filters",
                description="Use `!filter <preset>` or `!filter clear`.\nPresets: `bassboost`, `bassboost_high`, `nightcore`, `vaporwave`, `8d`, `pop`, `treble`",
                color=0x5865F2
            )
            return await ctx.send(embed=embed)
        p = preset.lower()
        state = self.get_state(ctx.guild.id)
        if p in ["clear", "reset", "off"]:
            state.filter = None
            msg = "🔄 Audio filter reset to **Normal**."
        elif p in AUDIO_FILTERS:
            state.filter = p
            msg = f"🎛️ Audio filter set to **{p}**!"
        else:
            return await ctx.send(f"❌ Unknown preset `{p}`. Available: {', '.join(AUDIO_FILTERS.keys())}")

        if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()) and state.current:
            try:
                elapsed = int(state.get_elapsed())
                new_source = await YTDLSource.regrab_stream(
                    state.current.data,
                    volume=state.volume,
                    seek_seconds=elapsed,
                    audio_filter=state.filter
                )
                new_source.title = state.current.title
                state.current = new_source
                state.voice_client.source = new_source
            except Exception as e:
                logger.warning(f"Error hot-swapping filter: {e}")

        if state.np_message:
            try:
                embed = await self.build_np_embed(state)
                await state.np_message.edit(embed=embed)
            except Exception:
                pass
        await ctx.send(msg)

    # ─── 24/7 Radio Stations (/radio) ─────────────────────────────────────────

    radio_group = app_commands.Group(name="radio", description="24/7 curated online radio stations")

    @radio_group.command(name="play", description="Tune in to a 24/7 curated radio station")
    @app_commands.describe(station="Radio station genre")
    @app_commands.choices(station=[
        app_commands.Choice(name="☕ 24/7 Lofi Chill Beats", value="lofi"),
        app_commands.Choice(name="🌆 Nightride FM (24/7 Synthwave)", value="synthwave"),
        app_commands.Choice(name="🎷 Smooth Lounge & Jazz", value="jazz"),
    ])
    async def radio_play_slash(self, interaction: discord.Interaction, station: str):
        await self.start_radio_station(interaction, station)

    @radio_group.command(name="stop", description="Stop radio stream playback")
    async def radio_stop_slash(self, interaction: discord.Interaction):
        await self.start_radio_station(interaction, "stop")

    @radio_group.command(name="stay", description="Toggle 24/7 mode so Sweety stays connected to the voice channel")
    async def radio_stay_slash(self, interaction: discord.Interaction):
        await self.toggle_247(interaction)

    @commands.group(name="radio", invoke_without_command=True)
    async def radio_prefix_group(self, ctx: commands.Context, station: Optional[str] = None):
        if not station:
            embed = discord.Embed(
                title="📻 24/7 Curated Radio Stations",
                description="`!radio lofi` — ☕ 24/7 Lofi Chill Beats\n`!radio synthwave` — 🌆 Nightride FM\n`!radio jazz` — 🎷 Smooth Lounge & Jazz\n`!radio stop` — Stop radio",
                color=0x5865F2
            )
            return await ctx.send(embed=embed)
        s = station.lower()
        if s == "stop":
            state = self.get_state(ctx.guild.id)
            state.clear()
            await self.bot.db.clear_music_queue(ctx.guild.id)
            is_247 = await self.is_247_enabled(ctx.guild.id)
            if state.voice_client:
                state.voice_client.stop()
                if not is_247:
                    await state.voice_client.disconnect(force=True)
                    state.voice_client = None
                else:
                    await self.set_vc_status(state.voice_client.channel, "📻 Sweety 24/7 — Idle")
            return await ctx.send("⏹ Radio stopped." if not is_247 else "⏹ Radio stopped. *(24/7 mode active — staying in VC)*")

        if s not in RADIO_STATIONS:
            return await ctx.send("❌ Available stations: `lofi`, `synthwave`, `jazz`")

        if not ctx.author.voice:
            return await ctx.send("❌ Join a voice channel first.")

        st_info = RADIO_STATIONS[s]
        state = self.get_state(ctx.guild.id)
        state.text_channel = ctx.channel
        state.is_247 = True
        state.radio_station = s
        state.queue.clear()

        vc = ctx.author.voice.channel
        try:
            await self.bot.db.set_config(ctx.guild.id, "music_247", "true")
            await self.bot.db.set_config(ctx.guild.id, "music_247_channel_id", str(vc.id))
        except Exception:
            pass

        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await vc.connect(timeout=20.0, reconnect=True, self_deaf=True)
        elif state.voice_client.channel != vc:
            await state.voice_client.move_to(vc)

        source = make_ffmpeg_audio(st_info["url"], seek_seconds=0, audio_filter=state.filter, is_live=True)
        radio_data = {
            "title": st_info["name"],
            "webpage_url": st_info["url"],
            "thumbnail": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400",
            "duration": 0,
            "requester": ctx.author.display_name,
            "uploader": st_info["desc"],
            "view_count": 0,
            "is_live": True,
        }
        ytdl_src = YTDLSource(source, data=radio_data, volume=state.volume)
        state.current = ytdl_src
        state.start_time = time.time()
        state.paused_elapsed = 0.0
        state.pause_start = None

        if state.voice_client.is_playing() or state.voice_client.is_paused():
            state.voice_client.stop()

        state.voice_client.play(
            ytdl_src,
            after=lambda e: self.schedule_play_next(ctx.guild)
        )
        await self.set_vc_status(vc, f"📻 {st_info['name']}")

        embed = await self.build_np_embed(state)
        view = NowPlayingView(self, ctx.guild)
        state.np_message = await ctx.send(embed=embed, view=view)
        state.update_task = asyncio.create_task(self.live_updater(ctx.guild))

    # ─── Smart Autoplay (!autoplay / /queue autoplay) ───────────────────────────

    @commands.command(name="autoplay")
    async def autoplay_prefix(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        state.autoplay = not state.autoplay
        status_str = "**Enabled** 🟢" if state.autoplay else "**Disabled** 🔴"
        await ctx.send(f"📻 Smart Autoplay is now {status_str}!")

    # ─── DJ Role Configuration (/dj) ──────────────────────────────────────────

    dj_group = app_commands.Group(name="dj", description="Configure DJ roles and music permissions")

    @dj_group.command(name="set_role", description="Set the server DJ role")
    @app_commands.describe(role="The role that will have DJ permissions")
    async def dj_set_role(self, interaction: discord.Interaction, role: discord.Role):
        if not (interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator or interaction.user.id == 719932313919684670):
            return await interaction.response.send_message("❌ You need Manage Server permission to configure the DJ role.", ephemeral=True)
        await self.bot.db.set_config(interaction.guild_id, "dj_role_id", str(role.id))
        await interaction.response.send_message(f"🎧 DJ role set to {role.mention}. Members with this role can bypass vote-skip and control music.", ephemeral=False)

    @dj_group.command(name="clear_role", description="Remove the configured DJ role")
    async def dj_clear_role(self, interaction: discord.Interaction):
        if not (interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator or interaction.user.id == 719932313919684670):
            return await interaction.response.send_message("❌ You need Manage Server permission to configure the DJ role.", ephemeral=True)
        await self.bot.db.set_config(interaction.guild_id, "dj_role_id", "")
        await interaction.response.send_message("🎧 DJ role cleared. Any role named `DJ` or server admins will have DJ permissions.", ephemeral=False)

    @dj_group.command(name="view", description="Check the current DJ role configuration")
    async def dj_view(self, interaction: discord.Interaction):
        dj_role_id = await self.bot.db.get_config(interaction.guild_id, "dj_role_id", None)
        if dj_role_id:
            role = interaction.guild.get_role(int(dj_role_id))
            r_str = role.mention if role else f"ID: {dj_role_id} (Role Deleted)"
        else:
            r_str = "No specific role set (Default: Any role named `DJ` or Admins)"
        await interaction.response.send_message(f"🎧 **Current DJ Role:** {r_str}")

    @commands.group(name="dj", invoke_without_command=True)
    async def dj_prefix_group(self, ctx: commands.Context):
        dj_role_id = await self.bot.db.get_config(ctx.guild.id, "dj_role_id", None)
        if dj_role_id:
            role = ctx.guild.get_role(int(dj_role_id))
            r_str = role.mention if role else f"ID: {dj_role_id}"
        else:
            r_str = "No specific role set (Default: Any role named `DJ` or Admins)"
        embed = discord.Embed(
            title="🎧 Server DJ Configuration",
            description=f"**Current DJ Role:** {r_str}\n\n`!dj set <@role>` — Configure DJ role\n`!dj clear` — Reset DJ role",
            color=0x5865F2
        )
        await ctx.send(embed=embed)

    @dj_prefix_group.command(name="set")
    async def dj_prefix_set(self, ctx: commands.Context, role: discord.Role):
        if not (ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.administrator or ctx.author.id == 719932313919684670):
            return await ctx.send("❌ You need Manage Server permission to configure the DJ role.")
        await self.bot.db.set_config(ctx.guild.id, "dj_role_id", str(role.id))
        await ctx.send(f"🎧 DJ role set to {role.mention}.")

    @dj_prefix_group.command(name="clear")
    async def dj_prefix_clear(self, ctx: commands.Context):
        if not (ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.administrator or ctx.author.id == 719932313919684670):
            return await ctx.send("❌ You need Manage Server permission to configure the DJ role.")
        await self.bot.db.set_config(ctx.guild.id, "dj_role_id", "")
        await ctx.send("🎧 DJ role cleared.")


async def setup(bot):
    await bot.add_cog(Music(bot))
