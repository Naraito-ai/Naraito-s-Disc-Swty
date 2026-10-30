import os
import io
import time
import wave
import struct
import asyncio
import tempfile
import logging
from typing import Optional, Dict

import discord
from discord.ext import commands, tasks
from discord import app_commands
import discord.ext.voice_recv as voice_recv
import edge_tts
import speech_recognition as sr

logger = logging.getLogger("SweetyBot.VoiceAssistant")

# Available Natural Neural TTS Voices
VOICE_OPTIONS = {
    "ana": ("en-US-AnaNeural", "Ana (Playful & Friendly Female)"),
    "jenny": ("en-US-JennyNeural", "Jenny (Warm & Natural Female)"),
    "aria": ("en-US-AriaNeural", "Aria (Expressive & Clear Female)"),
    "sonia": ("en-GB-SoniaNeural", "Sonia (British Sophisticated Female)"),
    "guy": ("en-US-GuyNeural", "Guy (Natural Casual Male)"),
}
DEFAULT_VOICE = "en-US-AnaNeural"

def pcm_48k_stereo_to_16k_mono(pcm_bytes: bytes) -> bytes:
    """Downsamples 48kHz 16-bit stereo PCM to 16kHz 16-bit mono PCM."""
    num_frames = len(pcm_bytes) // 4
    if num_frames == 0:
        return b""
    samples = struct.unpack(f"<{num_frames * 2}h", pcm_bytes[:num_frames * 4])
    out = []
    # Take every 3rd frame (48000 / 3 = 16000) and average Left + Right
    for i in range(0, num_frames, 3):
        mono = (samples[i * 2] + samples[i * 2 + 1]) // 2
        out.append(mono)
    return struct.pack(f"<{len(out)}h", *out)

def get_pcm_energy(pcm_bytes: bytes) -> float:
    """Calculates RMS audio energy to distinguish actual voice from ambient silence."""
    num_samples = len(pcm_bytes) // 2
    if num_samples == 0:
        return 0.0
    samples = struct.unpack(f"<{num_samples}h", pcm_bytes)
    # Stride by 8 for sub-millisecond calculation
    stride_samples = samples[::8]
    return sum(abs(s) for s in stride_samples) / max(1, len(stride_samples))

class VoiceSessionSink(voice_recv.AudioSink):
    """Real-time voice receiver audio sink for Discord voice channels."""
    def __init__(self):
        super().__init__()
        self.buffers: Dict[int, bytearray] = {}
        self.last_speech_time: Dict[int, float] = {}
        self.user_cache: Dict[int, discord.Member] = {}

    def wants_opus(self) -> bool:
        return False  # False gives decoded 16-bit 48kHz stereo PCM

    def write(self, user, data: voice_recv.VoiceData):
        if not user or getattr(user, "bot", False):
            return
        pcm = data.pcm
        if not pcm:
            return

        uid = user.id
        self.user_cache[uid] = user
        if uid not in self.buffers:
            self.buffers[uid] = bytearray()
        self.buffers[uid].extend(pcm)
        self.last_speech_time[uid] = time.time()

class VoiceControlView(discord.ui.View):
    """Interactive control panel view for active voice assistant sessions."""
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Disconnect Sweety", style=discord.ButtonStyle.danger, emoji="⏹️", custom_id="btn_va_disconnect")
    async def disconnect_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        session = self.cog.sessions.get(self.guild_id)
        if not session or not session.get("voice_client"):
            return await interaction.followup.send("❌ Sweety is not currently in a voice channel here.", ephemeral=True)
        
        await self.cog.leave_voice_session(self.guild_id)
        await interaction.followup.send("👋 Disconnected Sweety from voice channel.", ephemeral=True)

class VoiceAssistant(commands.Cog):
    """Interactive AI Voice Assistant Cog for Discord Voice Channels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sessions: Dict[int, dict] = {} # guild_id -> session info
        self.recognizer = sr.Recognizer()
        self.process_voice_buffers.start()
        logger.info("VoiceAssistant Cog initialized successfully.")

    def cog_unload(self):
        self.process_voice_buffers.cancel()
        for gid in list(self.sessions.keys()):
            asyncio.create_task(self.leave_voice_session(gid))

    async def generate_speech_audio(self, text: str, voice: str = DEFAULT_VOICE) -> str:
        """Converts text response to natural neural speech MP3 using edge-tts."""
        clean_text = text.replace("*", "").replace("#", "").replace("`", "").strip()
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, f"sweety_tts_{int(time.time()*1000)}.mp3")
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(file_path)
        return file_path

    async def generate_voice_ai_response(self, user: discord.Member, spoken_text: str) -> str:
        """Generates conversational, spoken-friendly AI reply from Gemini/Groq."""
        prompt = (
            "You are Sweety, a charming, witty, friendly, and intelligent AI companion chatting live in a Discord voice channel.\n"
            "Rules for your response:\n"
            "1. Answer in 1 to 2 short conversational sentences (under 30 words).\n"
            "2. Do NOT use markdown, asterisks, bullet points, emojis, or symbols because your output will be spoken aloud via text-to-speech.\n"
            "3. Speak naturally, as if chatting on a phone call.\n\n"
            f"User: {user.display_name}\n"
            f"User said: \"{spoken_text}\"\n"
            "Sweety's response:"
        )

        # Call existing bot AI response generator if available, else direct fallback
        try:
            if hasattr(self.bot, "generate_ai_response"):
                res = await self.bot.generate_ai_response(prompt, user_id=user.id, guild_id=user.guild.id)
                if res and isinstance(res, str):
                    return res.strip()
        except Exception as e:
            logger.warning(f"Error calling bot generate_ai_response: {e}")

        # Fallback to direct Groq/Gemini HTTP query
        from bot import query_gemini_api
        try:
            res = await query_gemini_api(prompt)
            if res:
                return res.strip()
        except Exception as e:
            logger.warning(f"Error calling query_gemini_api for voice: {e}")

        return f"Hey {user.display_name}! I heard you, but my brain had a brief connection hiccup. Could you say that again?"

    @tasks.loop(seconds=0.35)
    async def process_voice_buffers(self):
        """Monitors silence intervals across active voice sessions to trigger transcription."""
        now = time.time()
        for guild_id, session in list(self.sessions.items()):
            sink: VoiceSessionSink = session.get("sink")
            vc = session.get("voice_client")
            if not sink or not vc or not vc.is_connected():
                continue

            # Don't listen to incoming audio while bot itself is speaking
            if vc.is_playing():
                continue

            for uid, buf in list(sink.buffers.items()):
                last_time = sink.last_speech_time.get(uid, 0)
                # If user paused speaking for > 1.0s and recorded between 0.8s and 20s of audio
                if now - last_time > 1.0 and len(buf) >= 153600:
                    pcm_data = bytes(buf)
                    del sink.buffers[uid]
                    if uid in sink.last_speech_time:
                        del sink.last_speech_time[uid]
                    user = sink.user_cache.get(uid)
                    if user:
                        asyncio.create_task(self.handle_user_voice_input(guild_id, user, pcm_data))

    async def handle_user_voice_input(self, guild_id: int, user: discord.Member, pcm_data: bytes):
        """Transcribes user voice input, gets AI response, and plays back TTS in voice."""
        session = self.sessions.get(guild_id)
        if not session:
            return

        vc = session.get("voice_client")
        text_channel = session.get("text_channel")
        if not vc or not vc.is_connected() or vc.is_playing():
            return

        # 1. Downsample to 16kHz mono
        mono_pcm = pcm_48k_stereo_to_16k_mono(pcm_data)
        energy = get_pcm_energy(mono_pcm)
        if energy < 450.0:
            return  # Filter out silence/breathing/static

        # 2. Transcribe via Google Speech Recognition
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(mono_pcm)
        wav_buf.seek(0)

        transcription = None
        try:
            with sr.AudioFile(wav_buf) as source:
                audio_data = self.recognizer.record(source)
            # Run blocking recognize_google in threadpool
            transcription = await asyncio.to_thread(self.recognizer.recognize_google, audio_data)
        except sr.UnknownValueError:
            return  # Inaudible
        except Exception as e:
            logger.debug(f"Speech transcription error: {e}")
            return

        if not transcription or len(transcription.strip()) < 2:
            return

        logger.info(f"🎙️ [Voice Chat] {user.display_name} said: '{transcription}'")

        # 3. Query Gemini AI for voice response
        ai_reply = await self.generate_voice_ai_response(user, transcription)
        logger.info(f"🤖 [Voice Chat Reply] Sweety -> '{ai_reply}'")

        # 4. Generate Neural TTS
        voice_name = session.get("voice", DEFAULT_VOICE)
        audio_file = await self.generate_speech_audio(ai_reply, voice=voice_name)

        # 5. Playback into Discord voice channel
        def cleanup_after(err):
            try:
                if os.path.exists(audio_file):
                    os.remove(audio_file)
            except Exception:
                pass

        if vc.is_connected() and not vc.is_playing():
            audio_source = discord.FFmpegPCMAudio(audio_file)
            vc.play(audio_source, after=cleanup_after)

        # 6. Post chat transcript log to text channel
        if text_channel:
            try:
                log_embed = discord.Embed(
                    description=f"🎙️ **{user.display_name}:** *\"{transcription}\"*\n🤖 **Sweety:** {ai_reply}",
                    color=discord.Color.from_rgb(180, 140, 255)
                )
                await text_channel.send(embed=log_embed)
            except Exception:
                pass

    async def leave_voice_session(self, guild_id: int):
        """Disconnects Sweety from voice and cleans up session."""
        session = self.sessions.pop(guild_id, None)
        if session:
            vc = session.get("voice_client")
            if vc:
                try:
                    if vc.is_playing():
                        vc.stop()
                    await vc.disconnect(force=True)
                except Exception as e:
                    logger.debug(f"Error disconnecting voice client: {e}")

    # ── Voice Assistant Commands ─────────────────────────────────────────────

    @app_commands.command(name="voicechat", description="Connect Sweety to your voice channel to talk with her live via mic!")
    @app_commands.describe(channel="Specific voice channel to join (optional, defaults to your current voice channel)")
    @app_commands.guild_only()
    async def voicechat_slash_cmd(self, interaction: discord.Interaction, channel: Optional[discord.VoiceChannel] = None):
        await self._start_voice_session(interaction, channel=channel)

    @commands.command(name="voicechat", aliases=["joinvoice", "voicestart", "vcchat"])
    @commands.guild_only()
    async def voicechat_prefix_cmd(self, ctx: commands.Context, channel: Optional[discord.VoiceChannel] = None):
        """Join voice channel to talk with Sweety: !voicechat or !joinvoice"""
        await self._start_voice_session(ctx, channel=channel)

    async def _start_voice_session(self, ctx_or_interaction, channel: Optional[discord.VoiceChannel] = None):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author
        guild = ctx_or_interaction.guild

        # Locate voice channel
        target_vc = channel or (user.voice.channel if user.voice else None)
        if not target_vc:
            msg = "❌ You must be connected to a voice channel or specify one: `/voicechat [channel]`"
            if is_slash:
                return await ctx_or_interaction.response.send_message(msg, ephemeral=True)
            return await ctx_or_interaction.send(msg)

        if is_slash:
            await ctx_or_interaction.response.defer()

        # Check existing connection
        existing = guild.voice_client
        if existing and existing.is_connected():
            if existing.channel.id != target_vc.id:
                await existing.move_to(target_vc)
        else:
            try:
                existing = await target_vc.connect(cls=voice_recv.VoiceRecvClient)
            except Exception as ce:
                msg = f"❌ Failed to connect to voice channel: {ce}"
                if is_slash:
                    return await ctx_or_interaction.followup.send(msg)
                return await ctx_or_interaction.send(msg)

        # Initialize voice receive sink
        sink = VoiceSessionSink()
        try:
            existing.listen(sink)
        except Exception as le:
            logger.warning(f"Voice sink listener exception: {le}")

        text_channel = ctx_or_interaction.channel
        self.sessions[guild.id] = {
            "voice_client": existing,
            "sink": sink,
            "text_channel": text_channel,
            "voice": DEFAULT_VOICE
        }

        # Play welcome greeting in voice!
        welcome_text = f"Hey {user.display_name}! I joined your voice call. Speak into your mic whenever you want to talk to me!"
        welcome_audio = await self.generate_speech_audio(welcome_text, voice=DEFAULT_VOICE)
        if existing.is_connected() and not existing.is_playing():
            existing.play(discord.FFmpegPCMAudio(welcome_audio), after=lambda _: os.remove(welcome_audio) if os.path.exists(welcome_audio) else None)

        embed = discord.Embed(
            title="🎙️ Sweety Live Voice Assistant Connected!",
            description=(
                f"Connected to **{target_vc.name}**!\n\n"
                "**How to Talk to Sweety:**\n"
                "• Simply speak into your mic in the voice channel.\n"
                "• When you pause, Sweety will transcribe your speech and answer out loud!\n\n"
                "• Use `/voiceset` or `!voiceset` to change her voice.\n"
                "• Click **Disconnect** below or type `!leavevoice` when finished."
            ),
            color=discord.Color.from_rgb(180, 140, 255)
        )
        embed.set_footer(text="Sweety Live Voice • Powered by Gemini AI & Neural TTS")
        view = VoiceControlView(self, guild.id)

        if is_slash:
            await ctx_or_interaction.followup.send(embed=embed, view=view)
        else:
            await ctx_or_interaction.send(embed=embed, view=view)

    @app_commands.command(name="leavevoice", description="Disconnect Sweety from the voice channel")
    @app_commands.guild_only()
    async def leavevoice_slash_cmd(self, interaction: discord.Interaction):
        await self._stop_voice_session(interaction)

    @commands.command(name="leavevoice", aliases=["stopvoice", "disconnectvoice", "vcleave"])
    @commands.guild_only()
    async def leavevoice_prefix_cmd(self, ctx: commands.Context):
        """Disconnect Sweety from voice: !leavevoice"""
        await self._stop_voice_session(ctx)

    async def _stop_voice_session(self, ctx_or_interaction):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild

        if guild.id not in self.sessions and not guild.voice_client:
            msg = "ℹ️ Sweety is not currently in a voice channel."
            if is_slash:
                return await ctx_or_interaction.response.send_message(msg, ephemeral=True)
            return await ctx_or_interaction.send(msg)

        if is_slash:
            await ctx_or_interaction.response.defer()

        # Say goodbye in voice
        vc = guild.voice_client
        if vc and vc.is_connected() and not vc.is_playing():
            bye_audio = await self.generate_speech_audio("Goodbye everyone! Talk to you later!", voice=DEFAULT_VOICE)
            vc.play(discord.FFmpegPCMAudio(bye_audio))
            await asyncio.sleep(2.0)

        await self.leave_voice_session(guild.id)

        msg = "👋 **Sweety has disconnected from the voice channel.** Thanks for chatting!"
        if is_slash:
            await ctx_or_interaction.followup.send(msg)
        else:
            await ctx_or_interaction.send(msg)

    @app_commands.command(name="voiceset", description="Choose the voice persona Sweety uses when speaking")
    @app_commands.choices(voice=[
        app_commands.Choice(name="Ana (Playful & Friendly Female)", value="ana"),
        app_commands.Choice(name="Jenny (Warm & Natural Female)", value="jenny"),
        app_commands.Choice(name="Aria (Expressive & Clear Female)", value="aria"),
        app_commands.Choice(name="Sonia (British Sophisticated Female)", value="sonia"),
        app_commands.Choice(name="Guy (Natural Casual Male)", value="guy"),
    ])
    @app_commands.guild_only()
    async def voiceset_slash_cmd(self, interaction: discord.Interaction, voice: app_commands.Choice[str]):
        session = self.sessions.get(interaction.guild_id)
        chosen_voice_id, desc = VOICE_OPTIONS.get(voice.value, (DEFAULT_VOICE, "Ana"))
        if session:
            session["voice"] = chosen_voice_id
        await interaction.response.send_message(f"✅ Voice updated to **{desc}**! Sweety will speak with this voice.")

    @commands.command(name="voiceset")
    @commands.guild_only()
    async def voiceset_prefix_cmd(self, ctx: commands.Context, voice_key: str = "ana"):
        """Change Sweety's speaking voice: !voiceset [ana, jenny, aria, sonia, guy]"""
        key = voice_key.lower().strip()
        if key not in VOICE_OPTIONS:
            valid = ", ".join(f"`{k}`" for k in VOICE_OPTIONS.keys())
            return await ctx.send(f"❌ Invalid voice option. Choose from: {valid}")
        chosen_voice_id, desc = VOICE_OPTIONS[key]
        session = self.sessions.get(ctx.guild.id)
        if session:
            session["voice"] = chosen_voice_id
        await ctx.send(f"✅ Voice updated to **{desc}**!")

    @app_commands.command(name="speak", description="Make Sweety speak any custom sentence aloud in your voice channel")
    @app_commands.describe(text="The message for Sweety to speak")
    @app_commands.guild_only()
    async def speak_slash_cmd(self, interaction: discord.Interaction, text: str):
        await self._speak_custom_text(interaction, text)

    @commands.command(name="speak", aliases=["sayvoice", "tts"])
    @commands.guild_only()
    async def speak_prefix_cmd(self, ctx: commands.Context, *, text: str):
        """Make Sweety speak text aloud: !speak <message>"""
        await self._speak_custom_text(ctx, text)

    async def _speak_custom_text(self, ctx_or_interaction, text: str):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_slash else ctx_or_interaction.author

        vc = guild.voice_client
        if not vc or not vc.is_connected():
            msg = "❌ Sweety is not in a voice channel. Use `/voicechat` or `!voicechat` first!"
            if is_slash:
                return await ctx_or_interaction.response.send_message(msg, ephemeral=True)
            return await ctx_or_interaction.send(msg)

        if is_slash:
            await ctx_or_interaction.response.defer()

        session = self.sessions.get(guild.id, {})
        voice_name = session.get("voice", DEFAULT_VOICE)

        clean_text = text[:400].strip()
        audio_file = await self.generate_speech_audio(clean_text, voice=voice_name)

        if vc.is_connected() and not vc.is_playing():
            vc.play(discord.FFmpegPCMAudio(audio_file), after=lambda _: os.remove(audio_file) if os.path.exists(audio_file) else None)

        msg = f"🗣️ **{user.display_name}:** *\"{clean_text}\"*"
        if is_slash:
            await ctx_or_interaction.followup.send(msg)
        else:
            await ctx_or_interaction.send(msg)

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceAssistant(bot))
