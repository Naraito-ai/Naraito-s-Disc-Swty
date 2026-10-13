import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import json
from collections import deque
from typing import Optional
import time

import logging
import urllib.parse

logger = logging.getLogger("SweetyBot.Music")

# ─── YT-DLP Config ───────────────────────────────────────────────────────────

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
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


# ─── Guild Music State ────────────────────────────────────────────────────────

class GuildMusicState:
    def __init__(self):
        self.queue: deque = deque()
        self.current: Optional[dict] = None
        self.loop: bool = False
        self.loop_queue: bool = False
        self.volume: float = 0.5
        self.voice_client: Optional[discord.VoiceClient] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.skip_votes: set = set()

    def clear(self):
        self.queue.clear()
        self.current = None
        self.loop = False
        self.loop_queue = False
        self.skip_votes.clear()


# ─── Source ───────────────────────────────────────────────────────────────────

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title", "Unknown")
        self.url = data.get("webpage_url", "")
        self.thumbnail = data.get("thumbnail", "")
        self.duration = data.get("duration", 0)
        self.requester = data.get("requester", "Unknown")

    @classmethod
    async def from_url(cls, url, *, loop=None, volume=0.5, requester="Unknown"):
        loop = loop or asyncio.get_event_loop()
        parsed = urllib.parse.urlparse(url)
        is_url = bool(parsed.scheme and parsed.netloc)
        target = url if is_url else f"ytsearch:{url}"

        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(target, download=False)
        )
        if not data:
            raise ValueError("No video or audio stream found for query.")

        if "entries" in data:
            entries = [e for e in data["entries"] if e]
            if not entries:
                raise ValueError("No matching track results found.")
            
            # If query was a natural search phrase rather than an explicit playlist URL
            is_playlist_url = is_url and any(param in url for param in ("list=", "/playlist"))
            if not is_playlist_url:
                # Use top search result
                entry = entries[0]
                if not entry.get("url"):
                    # Extract single video details if entries only has partial info
                    web_url = entry.get("webpage_url") or entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}"
                    entry = await loop.run_in_executor(
                        None, lambda: ytdl.extract_info(web_url, download=False)
                    )
                entry["requester"] = requester
                stream_url = entry.get("url")
                if not stream_url:
                    raise ValueError("Could not extract playable stream URL.")
                source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
                return cls(source, data=entry, volume=volume), False
            else:
                tracks = []
                for entry in entries:
                    entry["requester"] = requester
                    tracks.append(entry)
                return tracks, True

        data["requester"] = requester
        stream_url = data.get("url")
        if not stream_url:
            raise ValueError("Could not extract playable stream URL.")
        source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
        return cls(source, data=data, volume=volume), False

    @classmethod
    async def regrab_stream(cls, data, volume=0.5):
        loop = asyncio.get_event_loop()
        web_url = data.get("webpage_url") or data.get("url") or f"https://www.youtube.com/watch?v={data.get('id', '')}"
        fresh = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(web_url, download=False)
        )
        fresh["requester"] = data.get("requester", "Unknown")
        stream_url = fresh.get("url")
        if not stream_url:
            raise ValueError("Could not regrab audio stream URL.")
        source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
        return cls(source, data=fresh, volume=volume)

    @staticmethod
    def format_duration(seconds):
        if not seconds:
            return "Live"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


# ─── Cog ──────────────────────────────────────────────────────────────────────

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.states: dict[int, GuildMusicState] = {}

    def get_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self.states:
            self.states[guild_id] = GuildMusicState()
        return self.states[guild_id]

    async def play_next(self, guild: discord.Guild):
        state = self.get_state(guild.id)

        if not state.voice_client or not state.voice_client.is_connected():
            return

        if state.loop and state.current:
            source = await YTDLSource.regrab_stream(state.current.data, state.current.volume)
            state.voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(guild)))
            state.current = source
            return

        if state.loop_queue and state.current:
            state.queue.append(state.current.data)

        if not state.queue:
            state.current = None
            if state.text_channel:
                await state.text_channel.send("✅ Queue finished.")
            return

        track_data = state.queue.popleft()
        source = await YTDLSource.regrab_stream(track_data, state.volume)
        state.current = source
        state.skip_votes.clear()

        state.voice_client.play(
            source,
            after=lambda e: self.bot.loop.create_task(self.play_next(guild))
        )

        if state.text_channel:
            embed = self.now_playing_embed(source)
            await state.text_channel.send(embed=embed)

    def now_playing_embed(self, source: YTDLSource) -> discord.Embed:
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"[{source.title}]({source.url})",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Duration", value=YTDLSource.format_duration(source.duration))
        embed.add_field(name="Requested by", value=source.requester)
        if source.thumbnail:
            embed.set_thumbnail(url=source.thumbnail)
        return embed

    @app_commands.command(name="play", description="Play a song or playlist from YouTube/SoundCloud")
    @app_commands.describe(query="Song name, YouTube URL, or playlist URL")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        if not interaction.user.voice:
            return await interaction.followup.send("❌ You need to be in a voice channel.", ephemeral=True)

        vc = interaction.user.voice.channel
        state = self.get_state(interaction.guild_id)
        state.text_channel = interaction.channel

        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await vc.connect()
        elif state.voice_client.channel != vc:
            await state.voice_client.move_to(vc)

        try:
            result, is_playlist = await YTDLSource.from_url(
                query, volume=state.volume, requester=str(interaction.user)
            )
        except Exception as e:
            logger.error(f"Error extracting audio for query '{query}': {e}", exc_info=True)
            return await interaction.followup.send(f"❌ Could not load track: `{e}`")

        if is_playlist:
            for track in result:
                state.queue.append(track)
            added = len(result)
            embed = discord.Embed(
                title="📋 Playlist Added",
                description=f"Added **{added} tracks** to the queue.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)
        else:
            if state.voice_client.is_playing() or state.voice_client.is_paused():
                state.queue.append(result.data)
                embed = discord.Embed(
                    title="➕ Added to Queue",
                    description=f"[{result.title}]({result.url})",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Position", value=str(len(state.queue)))
                embed.add_field(name="Duration", value=YTDLSource.format_duration(result.duration))
                return await interaction.followup.send(embed=embed)
            else:
                state.current = result
                state.voice_client.play(
                    result,
                    after=lambda e: self.bot.loop.create_task(self.play_next(interaction.guild))
                )
                embed = self.now_playing_embed(result)
                await interaction.followup.send(embed=embed)

    @app_commands.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        if state.voice_client and state.voice_client.is_playing():
            state.voice_client.pause()
            await interaction.response.send_message("⏸ Paused.")
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        if state.voice_client and state.voice_client.is_paused():
            state.voice_client.resume()
            await interaction.response.send_message("▶️ Resumed.")
        else:
            await interaction.response.send_message("Nothing is paused.", ephemeral=True)

    @app_commands.command(name="skip", description="Skip the current track")
    async def skip(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        if not state.voice_client or not state.voice_client.is_playing():
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)

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
            await interaction.response.send_message(f"⏭ Skip voted — skipped! ({len(state.skip_votes)}/{needed})")
        else:
            await interaction.response.send_message(
                f"🗳 Skip vote: {len(state.skip_votes)}/{needed} needed."
            )

    @app_commands.command(name="stop", description="Stop music and clear queue")
    async def stop(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        if state.voice_client:
            state.clear()
            state.voice_client.stop()
            await state.voice_client.disconnect()
            state.voice_client = None
        await interaction.response.send_message("⏹ Stopped and disconnected.")

    @app_commands.command(name="queue", description="Show the current queue")
    async def queue(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        if not state.current and not state.queue:
            return await interaction.response.send_message("Queue is empty.", ephemeral=True)

        embed = discord.Embed(title="🎶 Music Queue", color=discord.Color.blurple())

        if state.current:
            embed.add_field(
                name="Now Playing",
                value=f"[{state.current.title}]({state.current.url}) `{YTDLSource.format_duration(state.current.duration)}`",
                inline=False
            )

        if state.queue:
            lines = []
            for i, track in enumerate(list(state.queue)[:10], 1):
                title = track.get("title", "Unknown")
                url = track.get("webpage_url", "")
                dur = YTDLSource.format_duration(track.get("duration", 0))
                lines.append(f"`{i}.` [{title}]({url}) `{dur}`")
            if len(state.queue) > 10:
                lines.append(f"... and {len(state.queue) - 10} more")
            embed.add_field(name="Up Next", value="\n".join(lines), inline=False)

        loop_status = "🔂 Track" if state.loop else ("🔁 Queue" if state.loop_queue else "Off")
        embed.set_footer(text=f"Loop: {loop_status} | Volume: {int(state.volume * 100)}%")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Show what's currently playing")
    async def nowplaying(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        if not state.current:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        embed = self.now_playing_embed(state.current)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="volume", description="Set playback volume (1-100)")
    @app_commands.describe(level="Volume level 1-100")
    async def volume(self, interaction: discord.Interaction, level: int):
        if not 1 <= level <= 100:
            return await interaction.response.send_message("Volume must be between 1 and 100.", ephemeral=True)
        state = self.get_state(interaction.guild_id)
        state.volume = level / 100
        if state.current:
            state.current.volume = state.volume
        await interaction.response.send_message(f"🔊 Volume set to **{level}%**")

    @app_commands.command(name="loop", description="Toggle loop mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Track", value="track"),
        app_commands.Choice(name="Queue", value="queue"),
        app_commands.Choice(name="Off", value="off"),
    ])
    async def loop(self, interaction: discord.Interaction, mode: str):
        state = self.get_state(interaction.guild_id)
        if mode == "track":
            state.loop = True
            state.loop_queue = False
            await interaction.response.send_message("🔂 Looping current track.")
        elif mode == "queue":
            state.loop = False
            state.loop_queue = True
            await interaction.response.send_message("🔁 Looping queue.")
        else:
            state.loop = False
            state.loop_queue = False
            await interaction.response.send_message("Loop disabled.")

    @app_commands.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction):
        import random
        state = self.get_state(interaction.guild_id)
        if not state.queue:
            return await interaction.response.send_message("Queue is empty.", ephemeral=True)
        q = list(state.queue)
        random.shuffle(q)
        state.queue = deque(q)
        await interaction.response.send_message("🔀 Queue shuffled.")

    @app_commands.command(name="remove", description="Remove a track from the queue by position")
    @app_commands.describe(position="Position in queue (1 = next up)")
    async def remove(self, interaction: discord.Interaction, position: int):
        state = self.get_state(interaction.guild_id)
        if position < 1 or position > len(state.queue):
            return await interaction.response.send_message("Invalid position.", ephemeral=True)
        q = list(state.queue)
        removed = q.pop(position - 1)
        state.queue = deque(q)
        await interaction.response.send_message(f"🗑 Removed **{removed.get('title', 'Unknown')}** from queue.")

    playlist_group = app_commands.Group(name="playlist", description="Manage and play your custom saved playlists")

    @playlist_group.command(name="save", description="Save the current queue as a named playlist")
    @app_commands.describe(name="Name for your playlist")
    async def playlist_save(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        state = self.get_state(interaction.guild_id)

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
            return await interaction.followup.send("Nothing in queue to save.")

        try:
            await self.bot.db.execute("""
                INSERT INTO music_playlists (user_id, name, tracks, created_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id, name)
                DO UPDATE SET tracks = $3, updated_at = NOW()
            """, interaction.user.id, name, json.dumps(tracks))
            await interaction.followup.send(f"✅ Playlist **{name}** saved with {len(tracks)} tracks.")
        except Exception as e:
            await interaction.followup.send(f"❌ DB error: {e}")

    @playlist_group.command(name="play", description="Load and play one of your saved playlists")
    @app_commands.describe(name="Playlist name")
    async def playlist_play(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()

        if not interaction.user.voice:
            return await interaction.followup.send("❌ Join a voice channel first.", ephemeral=True)

        try:
            row = await self.bot.db.fetchrow(
                "SELECT tracks FROM music_playlists WHERE user_id = $1 AND name = $2",
                interaction.user.id, name
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ DB error: {e}")

        if not row:
            return await interaction.followup.send(f"❌ No playlist named **{name}** found.", ephemeral=True)

        raw_tracks = row["tracks"]
        tracks = json.loads(raw_tracks) if isinstance(raw_tracks, str) else raw_tracks
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
            description=f"**{name}** — {len(tracks)} tracks added to queue.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)

    @playlist_group.command(name="list", description="Show all your saved playlists")
    async def playlist_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            rows = await self.bot.db.fetch(
                "SELECT name, tracks, created_at FROM music_playlists WHERE user_id = $1 ORDER BY created_at DESC",
                interaction.user.id
            )
        except Exception as e:
            return await interaction.followup.send(f"❌ DB error: {e}")

        if not rows:
            return await interaction.followup.send("You have no saved playlists.")

        embed = discord.Embed(title="🎵 Your Playlists", color=discord.Color.blurple())
        for row in rows:
            raw_tracks = row["tracks"]
            count = len(json.loads(raw_tracks)) if isinstance(raw_tracks, str) else len(raw_tracks)
            embed.add_field(name=row["name"], value=f"{count} tracks", inline=True)
        await interaction.followup.send(embed=embed)

    @playlist_group.command(name="delete", description="Delete one of your saved playlists")
    @app_commands.describe(name="Playlist name to delete")
    async def playlist_delete(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.bot.db.execute(
                "DELETE FROM music_playlists WHERE user_id = $1 AND name = $2",
                interaction.user.id, name
            )
            if result == "DELETE 0":
                await interaction.followup.send(f"No playlist named **{name}** found.")
            else:
                await interaction.followup.send(f"🗑 Playlist **{name}** deleted.")
        except Exception as e:
            await interaction.followup.send(f"❌ DB error: {e}")


async def setup(bot):
    await bot.add_cog(Music(bot))
