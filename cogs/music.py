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
from typing import Optional
import yt_dlp
import time

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

logger = logging.getLogger("SweetyBot.Music")

# ─── Spotify Client ───────────────────────────────────────────────────────────

spotify_client_id = os.environ.get("SPOTIFY_CLIENT_ID", "fe5d5375021842a698279b2b09bf30fe").strip()
spotify_client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "a6cc6b6d69ed401ca24b59d2a65dec4a").strip()

spotify = None
if spotify_client_id and spotify_client_secret:
    try:
        spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=spotify_client_id,
            client_secret=spotify_client_secret
        ))
    except Exception as e:
        logger.warning(f"Failed to initialize Spotify client: {e}")


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
    """Extracts track items from a Spotify playlist using the public embed JSON or Spotipy."""
    p_id = playlist_id_or_url.strip()
    if "/playlist/" in p_id:
        p_id = p_id.split("/playlist/")[1].split("?")[0].strip("/")

    # 1. Try public embed endpoint (fast, zero auth)
    try:
        req = urllib.request.Request(
            f"https://open.spotify.com/embed/playlist/{p_id}",
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

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "nocheckcertificate": True,
    "ignoreerrors": True,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "socket_timeout": 5,
    "concurrent_fragment_downloads": 4,
    "extractor_args": {
        "youtube": {
            "skip": ["dash", "hls"],
            "player_client": ["android", "ios", "mweb", "web"],
        }
    },
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    },
}

if os.path.exists("cookies.txt"):
    YTDL_OPTIONS["cookiefile"] = "cookies.txt"

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
    "executable": "ffmpeg",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def fmt_duration(seconds):
    if not seconds:
        return "🔴 Live"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def progress_bar(elapsed, total, length=16):
    if not total or total <= 0:
        return "🔴 `LIVE STREAM`"
    percent = min(1.0, max(0.0, elapsed / total))
    filled = int(percent * length)
    filled = min(filled, length)
    unfilled = length - filled
    # Real music player design: bold played track + knob + light remaining track
    return "━" * filled + "🔘" + "─" * unfilled


# ─── Guild Music State ────────────────────────────────────────────────────────

class GuildMusicState:
    def __init__(self):
        self.queue: deque = deque()
        self.current: Optional["YTDLSource"] = None
        self.loop: bool = False
        self.loop_queue: bool = False
        self.volume: float = 0.5
        self.voice_client: Optional[discord.VoiceClient] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.skip_votes: set = set()
        self.np_message: Optional[discord.Message] = None
        self.start_time: Optional[float] = None
        self.paused_elapsed: float = 0.0
        self.pause_start: Optional[float] = None
        self.update_task: Optional[asyncio.Task] = None
        self.is_247: bool = False

    def clear(self):
        self.queue.clear()
        self.current = None
        self.loop = False
        self.loop_queue = False
        self.skip_votes.clear()
        self.np_message = None
        self.start_time = None
        self.paused_elapsed = 0.0
        self.pause_start = None
        if self.update_task:
            self.update_task.cancel()
            self.update_task = None

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
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title", "Unknown")
        self.url = data.get("webpage_url", "")
        self.thumbnail = data.get("thumbnail", "")
        self.duration = data.get("duration", 0)
        self.requester = data.get("requester", "Unknown")
        self.uploader = data.get("uploader", "Unknown")
        self.view_count = data.get("view_count", 0)

    @classmethod
    async def _search_and_extract(cls, search_query: str, *, loop=None, volume=0.5, requester="Unknown"):
        loop = loop or asyncio.get_event_loop()
        data = None

        # 1. Try SoundCloud first (fast, resilient against datacenter bot blocks)
        try:
            sc_data = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: ytdl.extract_info(f"scsearch5:{search_query}", download=False)
                ),
                timeout=5.0
            )
            sc_entries = [e for e in sc_data.get("entries", []) if e]
            for candidate in sc_entries:
                s_url = candidate.get("url")
                if not s_url:
                    fmts = [f for f in candidate.get("formats", []) if f.get("acodec") != "none" and f.get("url")]
                    if fmts:
                        s_url = fmts[-1]["url"]
                if s_url and not candidate.get("drm"):
                    data = candidate
                    break
        except Exception as sc_err:
            logger.warning(f"SoundCloud primary search failed for '{search_query}': {sc_err}")
            data = None

        # 2. Fallback to YouTube if SoundCloud didn't return a playable stream
        if not data or not (data.get("url") or data.get("formats")):
            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch1:{search_query}", download=False)),
                    timeout=5.0
                )
                entries = [e for e in data.get("entries", []) if e]
                if entries:
                    data = entries[0]
                    if not data.get("url"):
                        web_url = data.get("webpage_url") or data.get("url") or f"https://www.youtube.com/watch?v={data.get('id', '')}"
                        data = await asyncio.wait_for(
                            loop.run_in_executor(None, lambda: ytdl.extract_info(web_url, download=False)),
                            timeout=5.0
                        )
                else:
                    data = None
            except Exception as e:
                logger.warning(f"YouTube search extraction failed for '{search_query}': {e}")
                data = None

        if not data:
            raise ValueError(f"Could not find or stream '{search_query}'. Try a different song name.")

        stream_url = data.get("url")
        if not stream_url:
            formats = data.get("formats", [])
            audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("url")]
            if not audio_formats:
                raise ValueError(f"No streamable audio found for '{search_query}'.")
            stream_url = audio_formats[-1]["url"]

        data["requester"] = requester
        source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
        return cls(source, data=data, volume=volume), False

    @classmethod
    async def from_url(cls, url, *, loop=None, volume=0.5, requester="Unknown"):
        loop = loop or asyncio.get_event_loop()
        url = url.strip()

        # ── 1. Spotify URL Handler ───────────────────────────────────────────
        if "spotify.com" in url or url.startswith("spotify:"):
            # Check for Spotify playlist or album
            if "/playlist/" in url or "/album/" in url:
                if spotify:
                    try:
                        if "/playlist/" in url:
                            playlist_id = url.split("/playlist/")[1].split("?")[0]
                            res = await loop.run_in_executor(None, lambda: spotify.playlist_items(playlist_id, limit=50))
                            raw_items = res.get("items", [])
                            items = [i.get("track") for i in raw_items if i and i.get("track")]
                        else:
                            album_id = url.split("/album/")[1].split("?")[0]
                            res = await loop.run_in_executor(None, lambda: spotify.album_tracks(album_id, limit=50))
                            items = [i for i in res.get("items", []) if i]

                        entries = []
                        for t in items:
                            t_title = f"{t.get('name', 'Unknown')} {t['artists'][0]['name'] if t.get('artists') else ''}".strip()
                            entries.append({
                                "title": t_title,
                                "webpage_url": t_title,
                                "duration": int(t.get("duration_ms", 0) / 1000),
                                "requester": requester,
                            })
                        if entries:
                            return entries, True
                    except Exception as sp_err:
                        logger.warning(f"Spotify playlist extraction failed: {sp_err}")

            # Single Spotify Track
            track_search_term = None
            if spotify and "/track/" in url:
                try:
                    track_id = url.split("/track/")[1].split("?")[0]
                    t_data = await loop.run_in_executor(None, lambda: spotify.track(track_id))
                    if t_data and t_data.get("name"):
                        artist = t_data["artists"][0]["name"] if t_data.get("artists") else ""
                        track_search_term = f"{t_data['name']} {artist}".strip()
                except Exception as e:
                    logger.debug(f"Spotify API track lookup failed: {e}")

            if not track_search_term:
                # Fallback to public Spotify oEmbed
                oembed_data = await loop.run_in_executor(
                    None,
                    lambda: fetch_oembed(f"https://open.spotify.com/oembed?url={urllib.parse.quote(url)}")
                )
                if oembed_data and oembed_data.get("title"):
                    track_search_term = oembed_data["title"]

            if track_search_term:
                return await cls._search_and_extract(track_search_term, loop=loop, volume=volume, requester=requester)
            else:
                raise ValueError("Could not extract song info from Spotify link. Try searching by song name.")

        # ── 2. Direct HTTP/HTTPS URLs (YouTube, SoundCloud, direct audio) ─────
        if url.startswith("http://") or url.startswith("https://"):
            data = None
            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False)),
                    timeout=7.0
                )
            except Exception as e:
                logger.warning(f"Direct yt-dlp extraction failed for {url}: {e}")
                data = None

            # Handle playlists
            if data and "entries" in data:
                entries = [e for e in data["entries"] if e]
                if not entries:
                    raise ValueError("Playlist is empty or all entries failed.")

                is_playlist_url = any(param in url for param in ("list=", "/playlist"))
                if is_playlist_url:
                    for entry in entries:
                        entry["requester"] = requester
                    return entries, True
                else:
                    data = entries[0]
                    if not data.get("url"):
                        web_url = data.get("webpage_url") or data.get("url") or f"https://www.youtube.com/watch?v={data.get('id', '')}"
                        try:
                            data = await asyncio.wait_for(
                                loop.run_in_executor(None, lambda: ytdl.extract_info(web_url, download=False)),
                                timeout=5.0
                            )
                        except Exception:
                            pass

            # If direct extraction failed on YouTube URL, fallback to YouTube oEmbed + search!
            if (not data or not (data.get("url") or data.get("formats"))) and ("youtube.com" in url or "youtu.be" in url):
                logger.info(f"YouTube direct extraction failed for {url}, attempting oEmbed fallback...")
                oembed = await loop.run_in_executor(
                    None,
                    lambda: fetch_oembed(f"https://www.youtube.com/oembed?url={urllib.parse.quote(url)}&format=json")
                )
                if oembed and oembed.get("title"):
                    title = oembed["title"]
                    return await cls._search_and_extract(title, loop=loop, volume=volume, requester=requester)

            if not data:
                raise ValueError("Could not stream this link. Please try searching by song name instead.")

            stream_url = data.get("url")
            if not stream_url:
                formats = data.get("formats", [])
                audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("url")]
                if not audio_formats:
                    # Final fallback: if title exists, search via SoundCloud
                    title = data.get("title")
                    if title:
                        return await cls._search_and_extract(title, loop=loop, volume=volume, requester=requester)
                    raise ValueError("No streamable audio URL found.")
                stream_url = audio_formats[-1]["url"]

            data["requester"] = requester
            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            return cls(source, data=data, volume=volume), False

        # ── 3. Plain Text Search Query ────────────────────────────────────────
        return await cls._search_and_extract(url, loop=loop, volume=volume, requester=requester)

    @classmethod
    async def regrab_stream(cls, data, volume=0.5):
        loop = asyncio.get_event_loop()
        web_url = data.get("webpage_url") or data.get("url") or f"https://www.youtube.com/watch?v={data.get('id', '')}"
        fresh = None

        if web_url and web_url.startswith("http"):
            try:
                fresh = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: ytdl.extract_info(web_url, download=False)),
                    timeout=5.0
                )
            except Exception:
                fresh = None

        if not fresh or not (fresh.get("url") or fresh.get("formats")):
            # Fallback to searching track by title
            title = data.get("title", "")
            if title and title != "Unknown":
                source, _ = await cls._search_and_extract(
                    title, loop=loop, volume=volume, requester=data.get("requester", "Unknown")
                )
                return source

        if not fresh:
            raise ValueError("Could not regrab stream for this track.")

        fresh["requester"] = data.get("requester", "Unknown")
        stream_url = fresh.get("url")
        if not stream_url:
            formats = fresh.get("formats", [])
            audio_formats = [
                f for f in formats
                if f.get("acodec") != "none" and f.get("url")
            ]
            if not audio_formats:
                # Fallback to searching track by title
                title = data.get("title", "")
                if title and title != "Unknown":
                    source, _ = await cls._search_and_extract(
                        title, loop=loop, volume=volume, requester=data.get("requester", "Unknown")
                    )
                    return source
                raise ValueError("Could not regrab audio stream URL.")
            stream_url = audio_formats[-1]["url"]

        source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
        return cls(source, data=fresh, volume=volume)


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

        is_admin = (
            interaction.user.id == 719932313919684670
            or interaction.user.guild_permissions.manage_guild
        )
        if is_admin:
            state.voice_client.stop()
            return await interaction.response.send_message("⏭ Skipped.", ephemeral=True)

        vc_members = [m for m in state.voice_client.channel.members if not m.bot]
        state.skip_votes.add(interaction.user.id)
        needed = max(2, len(vc_members) // 2)

        if len(state.skip_votes) >= needed:
            state.voice_client.stop()
            await interaction.response.send_message("⏭ Vote passed — skipped!", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"🗳 {len(state.skip_votes)}/{needed} votes to skip.", ephemeral=True
            )

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.danger, row=0)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
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
        await interaction.response.send_message("🔀 Queue shuffled.", ephemeral=True)

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, row=1)
    async def vol_down_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        state.volume = max(0.1, state.volume - 0.1)
        if state.current:
            state.current.volume = state.volume
        embed = await self.cog.build_np_embed(state)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, row=1)
    async def vol_up_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        state.volume = min(1.0, state.volume + 0.1)
        if state.current:
            state.current.volume = state.volume
        embed = await self.cog.build_np_embed(state)
        await interaction.response.edit_message(embed=embed, view=self)

    # ── Row 2 ─────────────────────────────────────────────────────────────────

    @discord.ui.button(emoji="❤️", label="Save", style=discord.ButtonStyle.secondary, row=2)
    async def save_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.get_state()
        if not state.current:
            return await interaction.response.send_message("Nothing playing to save.", ephemeral=True)
        modal = SavePlaylistModal(self.cog, state)
        await interaction.response.send_modal(modal)

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


# ─── Search Results View ──────────────────────────────────────────────────────

class SearchResultsView(discord.ui.View):
    def __init__(self, cog: "Music", interaction: discord.Interaction, entries: list):
        super().__init__(timeout=30)
        self.cog = cog
        self.interaction = interaction
        self.entries = entries

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

            if not state.voice_client or not state.voice_client.is_connected():
                state.voice_client = await vc.connect()
            elif state.voice_client.channel != vc:
                await state.voice_client.move_to(vc)

            try:
                result, _ = await YTDLSource.from_url(
                    url, volume=state.volume, requester=str(interaction.user.display_name)
                )
            except Exception as e:
                return await interaction.followup.send(f"❌ Error: `{e}`")

            if state.voice_client.is_playing() or state.voice_client.is_paused():
                state.queue.append(result.data)
                embed = discord.Embed(
                    title="➕ Added to Queue",
                    description=f"[{result.title}]({result.url})",
                    color=0x5865F2
                )
                embed.set_thumbnail(url=result.thumbnail)
                embed.add_field(name="Duration", value=fmt_duration(result.duration))
                embed.add_field(name="Position", value=f"#{len(state.queue)}")
                await interaction.edit_original_response(embed=embed, view=None)
            else:
                state.current = result
                state.start_time = time.time()
                state.paused_elapsed = 0.0
                state.pause_start = None
                state.voice_client.play(
                    result,
                    after=lambda e: self.cog.bot.loop.create_task(
                        self.cog.play_next(interaction.guild)
                    )
                )
                await self.cog.set_vc_status(state.voice_client.channel, f"🎶 {result.title}")
                np_embed = await self.cog.build_np_embed(state)
                np_view = NowPlayingView(self.cog, interaction.guild)
                msg = await interaction.edit_original_response(embed=np_embed, view=np_view)
                state.np_message = msg
                state.update_task = self.cog.bot.loop.create_task(
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
            await self.interaction.edit_original_response(
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
                INSERT INTO music_playlists (user_id, name, tracks, created_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id, name)
                DO UPDATE SET tracks = $3, updated_at = NOW()
            """, interaction.user.id, name, json.dumps(tracks))
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
    q = current.strip().lower()
    if len(q) < 2:
        return []
    if q in _autocomplete_cache:
        return _autocomplete_cache[q]
    try:
        loop = asyncio.get_event_loop()
        choices = []
        if spotify:
            try:
                results = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: spotify.search(q=current, type="track", limit=5)
                    ),
                    timeout=2.0
                )
                tracks = results.get("tracks", {}).get("items", [])
                choices = [
                    app_commands.Choice(
                        name=f"{t['name']} — {t['artists'][0]['name']}"[:80],
                        value=f"{t['name']} {t['artists'][0]['name']}"
                    )
                    for t in tracks if t and t.get("name") and t.get("artists")
                ]
            except Exception as e:
                logger.debug(f"Spotify autocomplete search failed: {e}")

        if not choices:
            # Fallback to fast SoundCloud autocomplete search (never blocked, super fast)
            try:
                data = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: ytdl.extract_info(f"scsearch5:{current}", download=False)
                    ),
                    timeout=2.5
                )
                entries = data.get("entries", [])
                choices = [
                    app_commands.Choice(
                        name=f"{e.get('title', 'Unknown')[:80]}",
                        value=f"{e.get('title', current)}"
                    )
                    for e in entries if e and e.get("title")
                ][:5]
            except Exception as e:
                logger.debug(f"SoundCloud autocomplete search failed: {e}")

        if choices:
            if len(_autocomplete_cache) > 200:
                _autocomplete_cache.clear()
            _autocomplete_cache[q] = choices
        return choices
    except Exception as e:
        logger.warning(f"Autocomplete error: {e}")
        return []


# ─── Spotify Playlists View ───────────────────────────────────────────────────

class SpotifyPlaylistsView(discord.ui.View):
    def __init__(self, cog: "Music", user: discord.User | discord.Member, profile_data: dict):
        super().__init__(timeout=120)
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
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌ This menu belongs to someone else.", ephemeral=True)
        self.selected_url = interaction.data["values"][0]
        for p in self.playlists:
            if p["url"] == self.selected_url:
                self.selected_name = p["name"]
                break
        await interaction.response.defer()

    @discord.ui.button(label="Play in VC", style=discord.ButtonStyle.success, emoji="▶️", row=1)
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_url:
            return await interaction.response.send_message("❌ No playlist selected.", ephemeral=True)

        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Join a voice channel first.", ephemeral=True)

        await interaction.response.defer()
        vc = interaction.user.voice.channel
        state = self.cog.get_state(interaction.guild_id)
        state.text_channel = interaction.channel

        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await vc.connect()
        elif state.voice_client.channel != vc:
            await state.voice_client.move_to(vc)

        tracks = await self.cog.bot.loop.run_in_executor(
            None, lambda: extract_spotify_playlist_tracks_public(self.selected_url)
        )
        if not tracks:
            return await interaction.followup.send("❌ Could not load tracks from this Spotify playlist.", ephemeral=True)

        for t in tracks:
            t["requester"] = str(interaction.user.display_name)
            state.queue.append(t)

        embed = discord.Embed(
            title="📋 Spotify Playlist Queued",
            description=f"Added **{len(tracks)} tracks** from **{self.selected_name}** to the queue.",
            color=0x1DB954
        )
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

        if not state.voice_client.is_playing() and not state.voice_client.is_paused():
            await self.cog.play_next(interaction.guild)

    @discord.ui.button(label="Save to Sweety", style=discord.ButtonStyle.primary, emoji="💾", row=1)
    async def save_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_url:
            return await interaction.response.send_message("❌ No playlist selected.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        tracks = await self.cog.bot.loop.run_in_executor(
            None, lambda: extract_spotify_playlist_tracks_public(self.selected_url)
        )
        if not tracks:
            return await interaction.followup.send("❌ Could not fetch tracks to save.", ephemeral=True)

        save_name = self.selected_name[:32] if self.selected_name else "spotify_mix"
        try:
            await self.cog.bot.db.execute("""
                INSERT INTO music_playlists (user_id, name, tracks, created_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id, name)
                DO UPDATE SET tracks = $3, updated_at = NOW()
            """, interaction.user.id, save_name, json.dumps(tracks))
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

    def get_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self.states:
            self.states[guild_id] = GuildMusicState()
            if hasattr(self.bot, "db") and self.bot.db:
                self.bot.loop.create_task(self._restore_247(guild_id))
        return self.states[guild_id]

    async def _restore_247(self, guild_id: int):
        try:
            val = await self.bot.db.get_config(guild_id, "music_247", "false")
            if str(val).lower() == "true":
                if guild_id in self.states:
                    self.states[guild_id].is_247 = True
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Auto-reconnect if 24/7 mode is active and bot gets disconnected."""
        if member.id == self.bot.user.id and after.channel is None and before.channel is not None:
            state = self.get_state(member.guild.id)
            if state.is_247:
                await asyncio.sleep(2.0)
                try:
                    if not state.voice_client or not state.voice_client.is_connected():
                        state.voice_client = await before.channel.connect()
                        logger.info(f"Reconnected 24/7 voice client in {member.guild.name} ({before.channel.name})")
                except Exception as e:
                    logger.warning(f"24/7 auto-reconnect failed in {member.guild.name}: {e}")

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
        status = "⏸ Paused" if is_paused else "▶️ Playing"

        if state.loop:
            loop_str = "🔂 Track"
        elif state.loop_queue:
            loop_str = "🔁 Queue"
        else:
            loop_str = "Off"

        bar = progress_bar(elapsed, total)
        elapsed_str = fmt_duration(elapsed)
        total_str = fmt_duration(total)
        percent_str = f"{int(min(1.0, elapsed / total) * 100)}%" if total else "Live"

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
        else:
            views_str = str(views)

        embed = discord.Embed(
            title=src.title,
            url=src.url,
            color=0x5865F2
        )
        embed.set_author(
            name=f"🎵  {status}  •  Vol {int(state.volume * 100)}%  •  Loop {loop_str}"
        )
        embed.set_thumbnail(url=src.thumbnail)
        embed.add_field(
            name=f"Progress  •  {percent_str}",
            value=f"`{elapsed_str}` {bar} `{total_str}`\n{wave}  •  *Live Audio*",
            inline=False
        )
        embed.add_field(name="👤 Requested by", value=src.requester, inline=True)
        embed.add_field(name="🎙️ Channel", value=src.uploader, inline=True)
        embed.add_field(name="👁️ Views", value=views_str, inline=True)
        embed.add_field(
            name=f"📋 Queue — {queue_len} track{'s' if queue_len != 1 else ''} up next",
            value=f"Next: **{next_track}**" if queue_len else "Nothing queued",
            inline=False
        )
        embed.set_footer(text="Sweety Music  •  Live Dynamic Progress")
        return embed

    async def live_updater(self, guild: discord.Guild):
        state = self.get_state(guild.id)
        while True:
            await asyncio.sleep(2)
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

    async def play_next(self, guild: discord.Guild):
        state = self.get_state(guild.id)

        if not state.voice_client or not state.voice_client.is_connected():
            return

        if state.update_task:
            state.update_task.cancel()
            state.update_task = None

        if state.loop and state.current:
            source = await YTDLSource.regrab_stream(state.current.data, state.volume)
            state.start_time = time.time()
            state.paused_elapsed = 0.0
            state.pause_start = None
            state.voice_client.play(
                source,
                after=lambda e: self.bot.loop.create_task(self.play_next(guild))
            )
            state.current = source
            await self.set_vc_status(state.voice_client.channel, f"🎶 {source.title}")
            if state.np_message:
                embed = await self.build_np_embed(state)
                view = NowPlayingView(self, guild)
                await state.np_message.edit(embed=embed, view=view)
            state.update_task = self.bot.loop.create_task(self.live_updater(guild))
            return

        if state.loop_queue and state.current:
            state.queue.append(state.current.data)

        if not state.queue:
            state.current = None
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
        source = await YTDLSource.regrab_stream(track_data, state.volume)
        state.current = source
        state.skip_votes.clear()
        state.start_time = time.time()
        state.paused_elapsed = 0.0
        state.pause_start = None

        state.voice_client.play(
            source,
            after=lambda e: self.bot.loop.create_task(self.play_next(guild))
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

        state.update_task = self.bot.loop.create_task(self.live_updater(guild))

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
                state.voice_client = await vc.connect()
            elif state.voice_client.channel != vc:
                await state.voice_client.move_to(vc)

            result, is_playlist = await YTDLSource.from_url(
                query, volume=state.volume, requester=str(interaction.user.display_name)
            )

            if is_playlist:
                for track in result:
                    state.queue.append(track)
                embed = discord.Embed(
                    title="📋 Playlist Queued",
                    description=f"Added **{len(result)} tracks** to the queue.",
                    color=0x57F287
                )
                embed.set_footer(text=f"Requested by {interaction.user.display_name}")
                await interaction.followup.send(embed=embed)
                if not state.voice_client.is_playing():
                    await self.play_next(interaction.guild)
            else:
                if state.voice_client.is_playing() or state.voice_client.is_paused():
                    state.queue.append(result.data)
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
                        after=lambda e: self.bot.loop.create_task(self.play_next(interaction.guild))
                    )
                    await self.set_vc_status(state.voice_client.channel, f"🎶 {result.title}")
                    embed = await self.build_np_embed(state)
                    view = NowPlayingView(self, interaction.guild)
                    state.np_message = await interaction.followup.send(embed=embed, view=view)
                    state.update_task = self.bot.loop.create_task(self.live_updater(interaction.guild))
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Error in /play: {tb}")
            return await interaction.followup.send(f"❌ Error:\n```{tb[-1500:]}```")

    @app_commands.command(name="search", description="Search for a song and pick from results")
    @app_commands.describe(query="Song name to search")
    @app_commands.autocomplete(query=play_autocomplete)
    async def search(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        if not interaction.user.voice:
            return await interaction.followup.send("❌ Join a voice channel first.", ephemeral=True)

        try:
            data = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: ytdl.extract_info(f"ytsearch5:{query}", download=False)
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ Search failed: `{e}`")

        entries = [e for e in data.get("entries", []) if e]
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
        is_admin = (
            interaction.user.id == 719932313919684670
            or interaction.user.guild_permissions.manage_guild
        )
        if is_admin:
            state.voice_client.stop()
            return await interaction.response.send_message("⏭ Skipped.")
        vc_members = [m for m in state.voice_client.channel.members if not m.bot]
        state.skip_votes.add(interaction.user.id)
        needed = max(2, len(vc_members) // 2)
        if len(state.skip_votes) >= needed:
            state.voice_client.stop()
            await interaction.response.send_message("⏭ Vote passed — skipped!")
        else:
            await interaction.response.send_message(f"🗳 {len(state.skip_votes)}/{needed} votes to skip.")

    @app_commands.command(name="stop", description="Stop music and clear queue")
    async def stop(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        if state.voice_client:
            vc_channel = state.voice_client.channel
            state.clear()
            state.voice_client.stop()
            if not state.is_247:
                await state.voice_client.disconnect()
                state.voice_client = None
                await self.set_vc_status(vc_channel, None)
                await interaction.response.send_message("⏹ Stopped and disconnected.")
            else:
                await self.set_vc_status(vc_channel, "📻 Sweety 24/7 — Idle")
                await interaction.response.send_message("⏹ Stopped playback. *(24/7 mode active — staying in VC)*")
        else:
            await interaction.response.send_message("Nothing playing.", ephemeral=True)

    @app_commands.command(name="247", description="Toggle 24/7 mode so Sweety stays in the voice channel")
    async def toggle_247(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)

        if not state.voice_client or not state.voice_client.is_connected():
            if not interaction.user.voice:
                return await interaction.response.send_message(
                    "❌ Join a voice channel first to enable 24/7 mode.", ephemeral=True
                )
            vc = interaction.user.voice.channel
            state.voice_client = await vc.connect()
            state.text_channel = interaction.channel

        state.is_247 = not state.is_247

        try:
            await self.bot.db.set_config(
                interaction.guild_id, "music_247", "true" if state.is_247 else "false"
            )
        except Exception as e:
            logger.debug(f"Failed to persist 24/7 config: {e}")

        ch_name = state.voice_client.channel.name if state.voice_client and state.voice_client.channel else "voice channel"

        if state.is_247:
            embed = discord.Embed(
                title="📻 24/7 Mode Enabled",
                description=f"Sweety will now stay in **{ch_name}** 24/7, even when the queue finishes.",
                color=0x57F287
            )
            embed.set_footer(text="Use /247 again to disable.")
        else:
            embed = discord.Embed(
                title="📻 24/7 Mode Disabled",
                description="Sweety will now leave the voice channel when inactive.",
                color=0xED4245
            )
            if not state.queue and not state.current and state.voice_client:
                vc_channel = state.voice_client.channel
                await state.voice_client.disconnect()
                state.voice_client = None
                await self.set_vc_status(vc_channel, None)

        await interaction.response.send_message(embed=embed)

    @commands.command(name="247", help="Toggle 24/7 mode in voice channel")
    async def toggle_247_prefix(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)

        if not state.voice_client or not state.voice_client.is_connected():
            if not ctx.author.voice:
                return await ctx.send("❌ Join a voice channel first to enable 24/7 mode.")
            vc = ctx.author.voice.channel
            state.voice_client = await vc.connect()
            state.text_channel = ctx.channel

        state.is_247 = not state.is_247

        try:
            await self.bot.db.set_config(
                ctx.guild.id, "music_247", "true" if state.is_247 else "false"
            )
        except Exception as e:
            logger.debug(f"Failed to persist 24/7 config: {e}")

        ch_name = state.voice_client.channel.name if state.voice_client and state.voice_client.channel else "voice channel"

        if state.is_247:
            embed = discord.Embed(
                title="📻 24/7 Mode Enabled",
                description=f"Sweety will now stay in **{ch_name}** 24/7, even when the queue finishes.",
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
                await state.voice_client.disconnect()
                state.voice_client = None
                await self.set_vc_status(vc_channel, None)

        await ctx.send(embed=embed)

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

    @app_commands.command(name="volume", description="Set volume (1-100)")
    async def volume(self, interaction: discord.Interaction, level: int):
        if not 1 <= level <= 100:
            return await interaction.response.send_message("Between 1 and 100.", ephemeral=True)
        state = self.get_state(interaction.guild_id)
        state.volume = level / 100
        if state.current:
            state.current.volume = state.volume
        await interaction.response.send_message(f"🔊 Volume → **{level}%**")

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

    @app_commands.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction):
        import random
        state = self.get_state(interaction.guild_id)
        if not state.queue:
            return await interaction.response.send_message("Queue empty.", ephemeral=True)
        q = list(state.queue)
        random.shuffle(q)
        state.queue = deque(q)
        await interaction.response.send_message("🔀 Shuffled.")

    @app_commands.command(name="queue", description="Show the queue")
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

    @app_commands.command(name="remove", description="Remove a track from the queue by position")
    async def remove(self, interaction: discord.Interaction, position: int):
        state = self.get_state(interaction.guild_id)
        if position < 1 or position > len(state.queue):
            return await interaction.response.send_message("Invalid position.", ephemeral=True)
        q = list(state.queue)
        removed = q.pop(position - 1)
        state.queue = deque(q)
        await interaction.response.send_message(f"🗑 Removed **{removed.get('title','Unknown')}**.")

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
        info = await self.bot.loop.run_in_executor(
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

        info = await self.bot.loop.run_in_executor(
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

        info = await self.bot.loop.run_in_executor(
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
            info = await self.bot.loop.run_in_executor(
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
            state.voice_client = await vc.connect()
        elif state.voice_client.channel != vc:
            await state.voice_client.move_to(vc)

        tracks = await self.bot.loop.run_in_executor(
            None, lambda: extract_spotify_playlist_tracks_public(playlist_url)
        )
        if not tracks:
            return await interaction.followup.send("❌ Failed to retrieve tracks from this Spotify playlist.", ephemeral=True)

        for t in tracks:
            t["requester"] = str(interaction.user.display_name)
            state.queue.append(t)

        embed = discord.Embed(
            title="📋 Spotify Playlist Queued",
            description=f"Queued **{len(tracks)} tracks** from **{playlist_name}**.",
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

        tracks = await self.bot.loop.run_in_executor(
            None, lambda: extract_spotify_playlist_tracks_public(playlist_url)
        )
        if not tracks:
            return await interaction.followup.send("❌ Could not extract tracks from this playlist link.")

        save_name = (name or "spotify_import").strip()[:32]
        try:
            await self.bot.db.execute("""
                INSERT INTO music_playlists (user_id, name, tracks, created_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id, name)
                DO UPDATE SET tracks = $3, updated_at = NOW()
            """, interaction.user.id, save_name, json.dumps(tracks))
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
        info = await self.bot.loop.run_in_executor(
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
                "SELECT tracks FROM music_playlists WHERE user_id=$1 AND name=$2",
                interaction.user.id, name
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ DB error: {e}")
        if not row:
            return await interaction.followup.send(f"❌ No playlist named **{name}**.", ephemeral=True)
        tracks = json.loads(row["tracks"])
        state = self.get_state(interaction.guild_id)
        state.text_channel = interaction.channel
        vc = interaction.user.voice.channel
        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await vc.connect()
        for t in tracks:
            state.queue.append(t)
        if not state.voice_client.is_playing():
            await self.play_next(interaction.guild)
        embed = discord.Embed(
            title="📋 Playlist Loaded",
            description=f"**{name}** — {len(tracks)} tracks queued.",
            color=0x57F287
        )
        await interaction.followup.send(embed=embed)

    @spotify_group.command(name="saved_list", description="Show your saved playlists")
    async def playlist_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            rows = await self.bot.db.fetch(
                "SELECT name, tracks FROM music_playlists WHERE user_id=$1 ORDER BY created_at DESC",
                interaction.user.id
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
                "DELETE FROM music_playlists WHERE user_id=$1 AND name=$2",
                interaction.user.id, name
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
                "SELECT tracks FROM music_playlists WHERE user_id=$1 AND name=$2",
                ctx.author.id, name
            )
        except Exception as e:
            return await ctx.send(f"❌ DB error: {e}")
        if not row:
            return await ctx.send(f"❌ No playlist named **{name}**.")
        tracks = json.loads(row["tracks"])
        state = self.get_state(ctx.guild.id)
        state.text_channel = ctx.channel
        vc = ctx.author.voice.channel
        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await vc.connect()
        for t in tracks:
            state.queue.append(t)
        if not state.voice_client.is_playing():
            await self.play_next(ctx.guild)
        embed = discord.Embed(
            title="📋 Playlist Loaded",
            description=f"**{name}** — {len(tracks)} tracks queued.",
            color=0x57F287
        )
        await ctx.send(embed=embed)

    @prefix_playlist_group.command(name="list")
    async def prefix_playlist_list(self, ctx: commands.Context):
        try:
            rows = await self.bot.db.fetch(
                "SELECT name, tracks FROM music_playlists WHERE user_id=$1 ORDER BY created_at DESC",
                ctx.author.id
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
                "DELETE FROM music_playlists WHERE user_id=$1 AND name=$2",
                ctx.author.id, name
            )
            if result == "DELETE 0":
                await ctx.send(f"No playlist named **{name}**.")
            else:
                await ctx.send(f"🗑 Deleted **{name}**.")
        except Exception as e:
            await ctx.send(f"❌ DB error: {e}")


async def setup(bot):
    await bot.add_cog(Music(bot))
