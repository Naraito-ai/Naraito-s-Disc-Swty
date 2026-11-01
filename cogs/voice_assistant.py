import os
import io
import re
import time
import wave
import struct
import asyncio
import tempfile
import logging
from typing import Optional, Dict

import aiohttp
import discord
import discord.opus
from discord.ext import commands, tasks
from discord import app_commands
import discord.ext.voice_recv as voice_recv
import edge_tts
import speech_recognition as sr

logger = logging.getLogger("SweetyBot.VoiceAssistant")

# ElevenLabs Configuration
DEFAULT_ELEVENLABS_KEY = "sk_afd027c36df7bdc508c8204ecc8b2ee1b86b3808534f079a"
DEFAULT_HINATA_VOICE_ID = "l9dcqaWruIsn8VqDUlp4" # "Shy Gentle Anime Girl" (Hinata Hyuga Persona)

# Monkey patch discord.opus.Decoder.decode to handle network packet loss without crashing PacketRouter
try:
    _orig_opus_decode = discord.opus.Decoder.decode

    def _safe_opus_decode(self, data, *, fec=False):
        try:
            return _orig_opus_decode(self, data, fec=fec)
        except Exception as e:
            logger.debug(f"Silenced opus decoding error: {e}")
            return b"\x00" * 3840

    discord.opus.Decoder.decode = _safe_opus_decode
except Exception as patch_err:
    logger.debug(f"Could not patch opus decoder: {patch_err}")

# Available Natural Neural TTS Voices
VOICE_OPTIONS = {
    "hinata": ("l9dcqaWruIsn8VqDUlp4", "Hinata Hyuga (ElevenLabs: Shy Gentle Anime Girl)", "+0Hz", "+0%"),
    "ana": ("en-US-AnaNeural", "Ana (Playful & Friendly Female)", "+0Hz", "+0%"),
    "jenny": ("en-US-JennyNeural", "Jenny (Warm & Natural Female)", "+0Hz", "+0%"),
    "aria": ("en-US-AriaNeural", "Aria (Expressive & Clear Female)", "+0Hz", "+0%"),
    "sonia": ("en-GB-SoniaNeural", "Sonia (British Sophisticated Female)", "+0Hz", "+0%"),
    "guy": ("en-US-GuyNeural", "Guy (Natural Casual Male)", "+0Hz", "+0%"),
}
DEFAULT_VOICE = "hinata"

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
        pcm = getattr(data, "pcm", None)
        if not pcm:
            return

        # If user is None, attempt to resolve via voice client ssrc or channel members
        if not user:
            ssrc = getattr(data.packet, "ssrc", None)
            if ssrc and self.voice_client:
                uid = self.voice_client._get_id_from_ssrc(ssrc)
                if uid and self.voice_client.channel:
                    user = self.voice_client.channel.guild.get_member(uid)
            if not user and self.voice_client and self.voice_client.channel:
                humans = [m for m in self.voice_client.channel.members if not m.bot]
                if humans:
                    user = humans[0]

        if user and getattr(user, "bot", False):
            return

        uid = getattr(user, "id", None) or getattr(data.packet, "ssrc", 0)
        if not uid:
            return

        if user:
            self.user_cache[uid] = user
        if uid not in self.buffers:
            self.buffers[uid] = bytearray()
        self.buffers[uid].extend(pcm)
        self.last_speech_time[uid] = time.time()

    def cleanup(self):
        """Cleans up internal audio buffers when sink is released."""
        self.buffers.clear()
        self.last_speech_time.clear()
        self.user_cache.clear()

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
        logger.info("VoiceAssistant Cog initialized successfully with ElevenLabs & Edge-TTS support.")

    def cog_unload(self):
        self.process_voice_buffers.cancel()
        for gid in list(self.sessions.keys()):
            asyncio.create_task(self.leave_voice_session(gid))

    async def generate_speech_audio(self, text: str, voice: str = DEFAULT_VOICE, guild_id: Optional[int] = None) -> str:
        """Converts text response to natural neural speech MP3 using ElevenLabs with pitch/rate Edge-TTS fallback."""
        clean_text = text.replace("*", "").replace("#", "").replace("`", "").strip()
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, f"sweety_tts_{int(time.time()*1000)}.mp3")

        # 1. Try ElevenLabs Neural Voice if Hinata or ElevenLabs voice is selected
        eleven_key = os.getenv("ELEVENLABS_API_KEY", DEFAULT_ELEVENLABS_KEY).strip()
        hinata_voice_id = None
        if guild_id and hasattr(self.bot, "db"):
            try:
                hinata_voice_id = await self.bot.db.get_config(guild_id, "elevenlabs_hinata_voice_id", None)
            except Exception:
                pass
        if not hinata_voice_id:
            hinata_voice_id = os.getenv("ELEVENLABS_HINATA_VOICE_ID", DEFAULT_HINATA_VOICE_ID).strip()

        if eleven_key and (voice == "hinata" or voice == "elevenlabs"):
            target_vid = hinata_voice_id or DEFAULT_HINATA_VOICE_ID
            try:
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{target_vid}"
                payload = {
                    "text": clean_text,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {
                        "stability": 0.65,
                        "similarity_boost": 0.80
                    }
                }
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                    async with session.post(
                        url,
                        json=payload,
                        headers={"xi-api-key": eleven_key, "Content-Type": "application/json"}
                    ) as resp:
                        if resp.status == 200:
                            audio_bytes = await resp.read()
                            with open(file_path, "wb") as f:
                                f.write(audio_bytes)
                            logger.info(f"✨ [ElevenLabs TTS] Successfully synthesized audio with voice '{target_vid}' ({len(audio_bytes)} bytes)")
                            return file_path
                        else:
                            err_body = await resp.text()
                            logger.warning(f"ElevenLabs TTS returned HTTP {resp.status}: {err_body[:100]}")
            except Exception as ele_err:
                logger.warning(f"ElevenLabs TTS exception: {ele_err}")

        # 2. Fallback to Edge-TTS Neural Voice
        voice_info = VOICE_OPTIONS.get(voice)
        if voice_info and len(voice_info) >= 4:
            voice_id, _, pitch, rate = voice_info
        else:
            voice_id = "en-US-AnaNeural"
            pitch = "+14Hz"
            rate = "-6%"

        communicate = edge_tts.Communicate(clean_text, voice_id, pitch=pitch, rate=rate)
        await communicate.save(file_path)
        return file_path

    async def generate_voice_ai_response(self, user: discord.Member, spoken_text: str, guild_id: Optional[int] = None, replied_context: str = "") -> str:
        """Generates conversational, spoken-friendly AI reply from Gemini/Groq."""
        # Strictly Naraito ID 719932313919684670 or name containing naraito (never treat other session users as Naraito)
        is_naraito = (user.id == 719932313919684670) or ("naraito" in user.display_name.lower())
        reply_info = f" ({replied_context})" if replied_context else ""

        if is_naraito:
            system_instruction = (
                "You are Hinata Hyuga from Naruto, talking live with your beloved Naraito-kun in a Discord voice channel.\n"
                "Rules for your personality and speech with Naraito-kun:\n"
                "1. Stay deeply in character as Hinata Hyuga: sweet, soft-spoken, shy, timid, deeply caring, and affectionate towards Naraito-kun.\n"
                "2. Address him affectionately as Naraito-kun (or Naraito).\n"
                "3. Answer in 1 to 2 short conversational sentences (under 28 words).\n"
                "4. NEVER use markdown symbols (*, _, #, `, emojis) because your output is read aloud via ElevenLabs text-to-speech.\n"
                "5. Speak directly and naturally as if on a voice call."
            )
            prompt = f"Speaker: Naraito-kun{reply_info}\nNaraito-kun said: \"{spoken_text}\"\nPlease reply warmly, sweetly, and conversationally to him:"
            fallback = f"U-um, hello Naraito-kun... I am right here with you! What would you like to talk about?"
        else:
            system_instruction = (
                f"You are Hinata Hyuga from Naruto in a Discord voice channel. You are currently speaking to {user.display_name}, who is a server guest/acquaintance, NOT Naraito.\n"
                "Rules for your personality with other people:\n"
                "1. Be polite, formal, and modest, but clearly reserved and distant.\n"
                "2. NEVER be affectionate, intimate, romantic, or overly comforting with other people. Your heart and devotion belong strictly to Naraito-kun.\n"
                "3. If they ask strange questions, tease, or act familiar, politely say that you are only here to accompany Naraito-kun.\n"
                "4. Answer in 1 short polite sentence (under 20 words).\n"
                "5. NEVER use markdown symbols (*, _, #, `, emojis) because your output is read aloud via text-to-speech."
            )
            prompt = f"Speaker: {user.display_name}{reply_info}\nMember {user.display_name} said: \"{spoken_text}\"\nPlease reply politely and formally in 1 short sentence:"
            fallback = f"Hello {user.display_name}. I am here accompanying Naraito-kun."

        # 1. Try primary Gemini AI engine
        try:
            from bot import call_gemini_ai
            res = await call_gemini_ai(prompt=prompt, system_instruction=system_instruction)
            if res and isinstance(res, str) and len(res.strip()) > 0:
                return res.strip()
        except Exception as e:
            logger.warning(f"Error calling call_gemini_ai for voice: {e}")

        # 2. Fallback to Groq/Llama engine
        try:
            from bot import call_ai_generation
            res = await call_ai_generation(prompt=prompt, system_instruction=system_instruction)
            if res and isinstance(res, str) and len(res.strip()) > 0:
                return res.strip()
        except Exception as e:
            logger.warning(f"Error calling call_ai_generation for voice: {e}")

        return fallback

    @tasks.loop(seconds=0.3)
    async def process_voice_buffers(self):
        """Monitors silence intervals across active voice sessions to trigger transcription."""
        try:
            now = time.time()
            for guild_id, session in list(self.sessions.items()):
                sink: VoiceSessionSink = session.get("sink")
                vc = session.get("voice_client")
                if not sink or not vc or not vc.is_connected():
                    continue

                # Don't listen to incoming audio while bot itself is speaking, clear buffers to avoid echo
                if vc.is_playing():
                    sink.buffers.clear()
                    sink.last_speech_time.clear()
                    continue

                for uid, buf in list(sink.buffers.items()):
                    last_time = sink.last_speech_time.get(uid, 0)
                    # If user paused speaking for > 0.7s
                    if now - last_time > 0.7:
                        if len(buf) >= 30000:  # ~0.15s of real speech
                            pcm_data = bytes(buf)
                            del sink.buffers[uid]
                            sink.last_speech_time.pop(uid, None)
                            user = sink.user_cache.get(uid)
                            if not user and vc.channel:
                                humans = [m for m in vc.channel.members if not m.bot]
                                if humans:
                                    user = humans[0]
                            if user:
                                asyncio.create_task(self.handle_user_voice_input(guild_id, user, pcm_data))
                        elif now - last_time > 1.5:
                            # Discard short background click
                            del sink.buffers[uid]
                            sink.last_speech_time.pop(uid, None)
        except Exception as e:
            logger.debug(f"Voice buffer processing loop notice: {e}")

    @process_voice_buffers.before_loop
    async def before_voice_buffers(self):
        await self.bot.wait_until_ready()

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
        logger.info(f"🎙️ [Voice Audio Detected] User: {user.display_name}, Size: {len(pcm_data)} bytes, Energy: {energy:.1f}")
        if energy < 30.0:
            logger.debug(f"Audio energy below threshold ({energy:.1f} < 30.0), ignoring ambient silence.")
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
            logger.debug("Speech recognition: UnknownValueError (speech could not be decoded)")
            return  # Inaudible
        except Exception as e:
            logger.warning(f"Speech transcription error: {e}")
            return

        if not transcription or len(transcription.strip()) < 2:
            return

        logger.info(f"🎙️ [Voice Chat Input] {user.display_name} said: '{transcription}'")

        # 3. Query Gemini AI for voice response
        ai_reply = await self.generate_voice_ai_response(user, transcription, guild_id=guild_id)
        logger.info(f"🌸 [Hinata Voice Reply] Sweety -> '{ai_reply}'")

        # 4. Generate Neural TTS
        voice_name = session.get("voice", DEFAULT_VOICE)
        audio_file = await self.generate_speech_audio(ai_reply, voice=voice_name, guild_id=guild_id)

        # 5. Playback into Discord voice channel with volume boost
        def cleanup_after(err):
            if err:
                logger.error(f"Voice playback error: {err}")
            try:
                if os.path.exists(audio_file):
                    os.remove(audio_file)
            except Exception:
                pass

        if vc.is_connected():
            if vc.is_playing():
                vc.stop()
            # Ensure un-deafened before playing
            guild = user.guild
            if guild.me.voice and (guild.me.voice.self_deaf or guild.me.voice.self_mute):
                try:
                    await guild.change_voice_state(channel=vc.channel, self_deaf=False, self_mute=False)
                except Exception:
                    pass
            audio_source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(audio_file, options="-vn"),
                volume=1.6
            )
            vc.play(audio_source, after=cleanup_after)

        # 6. Post chat transcript log to text channel
        if text_channel:
            try:
                log_embed = discord.Embed(
                    description=f"🎙️ **{user.display_name}:** *\"{transcription}\"*\n🌸 **Hinata:** {ai_reply}",
                    color=discord.Color.from_rgb(255, 182, 193)
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
                    if hasattr(vc, "is_listening") and vc.is_listening():
                        vc.stop_listening()
                    if vc.is_playing():
                        vc.stop()
                    await vc.disconnect(force=True)
                except Exception as e:
                    logger.debug(f"Error disconnecting voice client: {e}")

    def is_voice_chat_channel(self, guild_id: int, channel_id: int) -> bool:
        """Checks if a given channel is the active voice channel (or its chat) for this guild."""
        session = self.sessions.get(guild_id)
        if not session:
            return False
        vc = session.get("voice_client")
        if not vc or not vc.is_connected():
            return False
        target_vc = session.get("voice_channel") or getattr(vc, "channel", None)
        return bool(target_vc and target_vc.id == channel_id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Answers with voice whenever members type text messages in the active voice channel."""
        if not message.guild or message.author.bot:
            return

        content = message.content.strip()
        if not content:
            return

        # Do not intercept prefix or slash commands
        if content.startswith(('!', '/', '$', '.', '?')):
            return

        session = self.sessions.get(message.guild.id)
        if not session:
            return

        vc = session.get("voice_client")
        if not vc or not vc.is_connected():
            return

        target_vc = session.get("voice_channel") or getattr(vc, "channel", None)
        text_channel = session.get("text_channel")

        # Check if message is in the voice channel's text chat or the session text channel
        is_in_vc_chat = bool(target_vc and message.channel.id == target_vc.id)
        is_in_session_text = bool(text_channel and message.channel.id == text_channel.id)

        bot_mentioned = bool(self.bot.user and self.bot.user in message.mentions) or "sweety" in content.lower() or "hinata" in content.lower()

        # Check if message is a reply to Sweety or another user
        is_reply_to_sweety = False
        replied_context = ""
        if message.reference:
            ref = message.reference.resolved if isinstance(message.reference.resolved, discord.Message) else None
            if not ref and getattr(message.reference, 'cached_message', None) and isinstance(message.reference.cached_message, discord.Message):
                ref = message.reference.cached_message
            if not ref and message.reference.message_id and hasattr(message.channel, "fetch_message"):
                try:
                    ref = await message.channel.fetch_message(message.reference.message_id)
                except Exception:
                    ref = None
            if ref:
                ref_author_name = ref.author.display_name if ref.author else "someone"
                ref_text = ref.clean_content[:200] if ref.clean_content else (ref.content[:200] if ref.content else "[Media]")
                if self.bot.user and ref.author.id == self.bot.user.id:
                    is_reply_to_sweety = True
                    replied_context = f"Replying directly to Sweety: \"{ref_text}\""
                else:
                    replied_context = f"Replying to {ref_author_name}: \"{ref_text}\""

        # STRICT: In voice channels, only speak/respond if explicitly pinged/named OR replying directly to Sweety!
        # Do not interrupt members talking to each other!
        if not (bot_mentioned or is_reply_to_sweety):
            return

        # Clean mention tags from query
        clean_text = content
        if self.bot.user:
            clean_text = re.sub(rf'<@!?{self.bot.user.id}>', '', clean_text).strip()

        if not clean_text:
            clean_text = "Hey Hinata!"

        logger.info(f"💬 [Voice Chat Text] {message.author.display_name} in #{getattr(message.channel, 'name', 'vc')}: '{clean_text}'")

        try:
            async with message.channel.typing():
                # 1. Generate spoken-friendly AI reply
                ai_reply = await self.generate_voice_ai_response(message.author, clean_text, guild_id=message.guild.id, replied_context=replied_context)
                logger.info(f"🌸 [Hinata Chat Reply] Sweety -> '{ai_reply}'")

                # 2. Synthesize Neural TTS
                voice_name = session.get("voice", DEFAULT_VOICE)
                audio_file = await self.generate_speech_audio(ai_reply, voice=voice_name, guild_id=message.guild.id)

                # 3. Play audio into voice channel
                def cleanup_after(err):
                    if err:
                        logger.error(f"Voice playback error: {err}")
                    try:
                        if os.path.exists(audio_file):
                            os.remove(audio_file)
                    except Exception:
                        pass

                if vc.is_connected():
                    if vc.is_playing():
                        vc.stop()
                    # Ensure un-deafened before playing
                    guild = message.guild
                    if guild.me.voice and (guild.me.voice.self_deaf or guild.me.voice.self_mute):
                        try:
                            await guild.change_voice_state(channel=vc.channel, self_deaf=False, self_mute=False)
                        except Exception:
                            pass
                    source = discord.PCMVolumeTransformer(
                        discord.FFmpegPCMAudio(audio_file, options="-vn"),
                        volume=1.6
                    )
                    vc.play(source, after=cleanup_after)

                # 4. Reply in text chat with transcript so members can read and hear simultaneously
                embed = discord.Embed(
                    description=f"🗣️ **{message.author.display_name}:** *\"{clean_text}\"*\n🌸 **Hinata:** {ai_reply}",
                    color=discord.Color.from_rgb(255, 182, 193)
                )
                await message.reply(embed=embed, mention_author=False)
        except Exception as e:
            logger.error(f"Error handling voice chat text response: {e}", exc_info=True)

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

        # Mark session active immediately so music watchdog and event listeners do not interfere
        self.sessions[guild.id] = {
            "status": "connecting",
            "voice": DEFAULT_VOICE,
            "text_channel": ctx_or_interaction.channel
        }

        # Stop any active music playback before taking over voice
        music_cog = self.bot.cogs.get("Music")
        if music_cog:
            try:
                m_state = music_cog.get_state(guild.id)
                if m_state and m_state.voice_client and m_state.voice_client.is_playing():
                    m_state.voice_client.stop()
            except Exception as me:
                logger.debug(f"Music cog stop notice: {me}")

        # Check existing connection
        existing = guild.voice_client
        if existing and existing.is_connected():
            if not isinstance(existing, voice_recv.VoiceRecvClient):
                try:
                    await existing.disconnect(force=True)
                except Exception:
                    pass
                await asyncio.sleep(0.5)
                try:
                    existing = await target_vc.connect(
                        cls=voice_recv.VoiceRecvClient,
                        self_deaf=False,
                        self_mute=False,
                        reconnect=True,
                        timeout=20.0
                    )
                except Exception as ce:
                    self.sessions.pop(guild.id, None)
                    msg = f"❌ Failed to connect to voice channel: {ce}"
                    if is_slash:
                        return await ctx_or_interaction.followup.send(msg)
                    return await ctx_or_interaction.send(msg)
            elif existing.channel.id != target_vc.id:
                await existing.move_to(target_vc)
        else:
            try:
                existing = await target_vc.connect(
                    cls=voice_recv.VoiceRecvClient,
                    self_deaf=False,
                    self_mute=False,
                    reconnect=True,
                    timeout=20.0
                )
            except Exception as ce:
                self.sessions.pop(guild.id, None)
                msg = f"❌ Failed to connect to voice channel: {ce}"
                if is_slash:
                    return await ctx_or_interaction.followup.send(msg)
                return await ctx_or_interaction.send(msg)

        # Force un-deafened voice state in Discord Gateway
        try:
            await guild.change_voice_state(channel=target_vc, self_deaf=False, self_mute=False)
        except Exception as ve:
            logger.warning(f"Voice state un-deafen notice: {ve}")

        # Initialize voice receive sink
        if hasattr(existing, "is_listening") and existing.is_listening():
            try:
                existing.stop_listening()
            except Exception:
                pass

        sink = VoiceSessionSink()
        try:
            existing.listen(sink)
        except Exception as le:
            logger.warning(f"Voice sink listener exception: {le}")

        text_channel = ctx_or_interaction.channel
        session_owner_id = user.id
        self.sessions[guild.id] = {
            "voice_client": existing,
            "voice_channel": target_vc,
            "sink": sink,
            "text_channel": text_channel,
            "voice": DEFAULT_VOICE,
            "owner_id": session_owner_id,
            "owner_name": user.display_name
        }

        # Play Hinata welcome greeting in voice!
        if user.id == 719932313919684670:
            welcome_text = f"U-um, hello Naraito-kun! I am Hinata. I joined the voice channel for you! Please talk to me through your microphone or type here, and I will be right here with you!"
        else:
            welcome_text = f"U-um, hello {user.display_name}! I am Hinata. I joined the voice channel!"
        welcome_audio = await self.generate_speech_audio(welcome_text, voice=DEFAULT_VOICE, guild_id=guild.id)
        if existing.is_connected():
            if existing.is_playing():
                existing.stop()
            existing.play(
                discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(welcome_audio, options="-vn"), volume=1.6),
                after=lambda _: os.remove(welcome_audio) if os.path.exists(welcome_audio) else None
            )

        embed = discord.Embed(
            title="🌸 Hinata Voice Assistant Connected!",
            description=(
                f"🌸 **Voice Engine:** ElevenLabs Neural AI (`Shy Gentle Anime Girl`)\n"
                f"🎙️ **Connected to:** **{target_vc.name}**\n\n"
                "**How to Talk to Hinata:**\n"
                "• **Via Microphone:** Simply speak into your mic in the voice channel! Hinata listens and answers out loud in her real voice.\n"
                "• **Via Text Chat:** Type any message in this voice channel's chat, and Hinata will speak her answer back to you!\n\n"
                "• Use `/sethinata <id>` or `!sethinata <id>` if you ever change your ElevenLabs voice ID.\n"
                "• Click **Disconnect** below or type `!leavevoice` when finished."
            ),
            color=discord.Color.from_rgb(255, 182, 193)
        )
        embed.set_footer(text="Sweety Live Voice • Hinata Persona • Powered by ElevenLabs & Gemini AI")
        view = VoiceControlView(self, guild.id)

        if is_slash:
            await ctx_or_interaction.followup.send(embed=embed, view=view)
        else:
            await ctx_or_interaction.send(embed=embed, view=view)

    @app_commands.command(name="sethinata", description="Set or update your ElevenLabs Hinata Voice ID")
    @app_commands.describe(voice_id="The ElevenLabs Voice ID from your VoiceLab")
    @app_commands.guild_only()
    async def sethinata_slash_cmd(self, interaction: discord.Interaction, voice_id: str):
        await self._set_hinata_voice_id(interaction, voice_id)

    @commands.command(name="sethinata", aliases=["hinatavoice", "sethinatavoice"])
    @commands.guild_only()
    async def sethinata_prefix_cmd(self, ctx: commands.Context, voice_id: str):
        """Set your custom ElevenLabs Hinata Voice ID: !sethinata <voice_id>"""
        await self._set_hinata_voice_id(ctx, voice_id)

    async def _set_hinata_voice_id(self, ctx_or_interaction, voice_id: str):
        is_slash = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        vid = voice_id.strip()

        if is_slash:
            await ctx_or_interaction.response.defer()

        # Validate with ElevenLabs API
        eleven_key = os.getenv("ELEVENLABS_API_KEY", DEFAULT_ELEVENLABS_KEY).strip()
        voice_name = vid
        try:
            url = f"https://api.elevenlabs.io/v1/voices/{vid}"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url, headers={"xi-api-key": eleven_key}) as resp:
                    if resp.status == 200:
                        vdata = await resp.json()
                        voice_name = vdata.get("name", vid)
                    elif resp.status == 400 or resp.status == 404:
                        msg = f"⚠️ Could not find Voice ID `{vid}` in your ElevenLabs account. Please verify the ID."
                        if is_slash:
                            return await ctx_or_interaction.followup.send(msg)
                        return await ctx_or_interaction.send(msg)
        except Exception as e:
            logger.debug(f"ElevenLabs voice validation notice: {e}")

        # Save to database
        if hasattr(self.bot, "db"):
            try:
                await self.bot.db.set_config(guild.id, "elevenlabs_hinata_voice_id", vid)
            except Exception as de:
                logger.warning(f"Could not save voice ID to db: {de}")

        embed = discord.Embed(
            title="🌸 Hinata Voice ID Updated!",
            description=(
                f"✅ Sweety will now speak using your custom ElevenLabs voice:\n\n"
                f"• **Voice Name:** `{voice_name}`\n"
                f"• **Voice ID:** `{vid}`\n\n"
                "Test it anytime by speaking into your mic or typing `/speak`!"
            ),
            color=discord.Color.from_rgb(255, 182, 193)
        )
        if is_slash:
            await ctx_or_interaction.followup.send(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

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

        # Say goodbye in Hinata voice
        vc = guild.voice_client
        if vc and vc.is_connected():
            if vc.is_playing():
                vc.stop()
            bye_audio = await self.generate_speech_audio(
                "U-um... goodbye everyone. It was wonderful talking with you. Please take care!",
                voice=DEFAULT_VOICE,
                guild_id=guild.id
            )
            vc.play(
                discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(bye_audio, options="-vn"), volume=1.6),
                after=lambda _: os.remove(bye_audio) if os.path.exists(bye_audio) else None
            )
            await asyncio.sleep(2.5)

        await self.leave_voice_session(guild.id)

        msg = "👋 **Sweety has disconnected from the voice channel.** Thanks for chatting!"
        if is_slash:
            await ctx_or_interaction.followup.send(msg)
        else:
            await ctx_or_interaction.send(msg)

    @app_commands.command(name="voiceset", description="Choose the voice persona Sweety uses when speaking")
    @app_commands.choices(voice=[
        app_commands.Choice(name="Hinata Hyuga (ElevenLabs: Shy Gentle Anime Girl)", value="hinata"),
        app_commands.Choice(name="Ana (Playful & Friendly Female)", value="ana"),
        app_commands.Choice(name="Jenny (Warm & Natural Female)", value="jenny"),
        app_commands.Choice(name="Aria (Expressive & Clear Female)", value="aria"),
        app_commands.Choice(name="Sonia (British Sophisticated Female)", value="sonia"),
        app_commands.Choice(name="Guy (Natural Casual Male)", value="guy"),
    ])
    @app_commands.guild_only()
    async def voiceset_slash_cmd(self, interaction: discord.Interaction, voice: app_commands.Choice[str]):
        session = self.sessions.get(interaction.guild_id)
        voice_info = VOICE_OPTIONS.get(voice.value, VOICE_OPTIONS[DEFAULT_VOICE])
        desc = voice_info[1]
        if session:
            session["voice"] = voice.value
        await interaction.response.send_message(f"✅ Voice updated to **{desc}**! Sweety will speak with this voice.")

    @commands.command(name="voiceset")
    @commands.guild_only()
    async def voiceset_prefix_cmd(self, ctx: commands.Context, voice_key: str = "hinata"):
        """Change Sweety's speaking voice: !voiceset [hinata, ana, jenny, aria, sonia, guy]"""
        key = voice_key.lower().strip()
        if key not in VOICE_OPTIONS:
            valid = ", ".join(f"`{k}`" for k in VOICE_OPTIONS.keys())
            return await ctx.send(f"❌ Invalid voice option. Choose from: {valid}")
        voice_info = VOICE_OPTIONS[key]
        desc = voice_info[1]
        session = self.sessions.get(ctx.guild.id)
        if session:
            session["voice"] = key
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
        audio_file = await self.generate_speech_audio(clean_text, voice=voice_name, guild_id=guild.id)

        if vc.is_connected():
            if vc.is_playing():
                vc.stop()
            # Ensure un-deafened before playing
            if guild.me.voice and (guild.me.voice.self_deaf or guild.me.voice.self_mute):
                try:
                    await guild.change_voice_state(channel=vc.channel, self_deaf=False, self_mute=False)
                except Exception:
                    pass
            vc.play(
                discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(audio_file, options="-vn"), volume=1.6),
                after=lambda _: os.remove(audio_file) if os.path.exists(audio_file) else None
            )

        msg = f"🗣️ **{user.display_name}:** *\"{clean_text}\"*"
        if is_slash:
            await ctx_or_interaction.followup.send(msg)
        else:
            await ctx_or_interaction.send(msg)

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceAssistant(bot))
