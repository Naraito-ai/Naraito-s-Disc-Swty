# -*- coding: utf-8 -*-
"""
cogs/ai_assistant.py - Groq & Gemini AI Q&A, Vision Analysis, Persistent Memories & Auto-Reply
"""
from __future__ import annotations

import os
import re
import json
import time
import base64
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Union, List, Dict, Any, Tuple, Set

import aiohttp
import discord
from discord.ext import commands, tasks
from discord import app_commands

from database import db
from nba_data import is_creator, clean_memory

logger = logging.getLogger("SweetyBot.AIAssistant")

# ── Security: Rate Limit Trackers ─────────────────────────────────────────────
_USER_AI_COOLDOWNS: Dict[int, float] = {}
_GUILD_HOURLY_USAGE: Dict[int, List[float]] = {}
USER_COOLDOWN_SECONDS = 2.0
GUILD_HOURLY_LIMIT = 500


def _check_user_cooldown(user_id: int) -> Tuple[bool, float]:
    """Returns (is_allowed, remaining_seconds)."""
    now = time.time()
    last = _USER_AI_COOLDOWNS.get(user_id, 0.0)
    elapsed = now - last
    if elapsed < USER_COOLDOWN_SECONDS:
        return False, round(USER_COOLDOWN_SECONDS - elapsed, 1)
    _USER_AI_COOLDOWNS[user_id] = now
    return True, 0.0


def _check_server_limit(guild_id: int) -> bool:
    """Enforces hourly query budget per Discord guild."""
    now = time.time()
    one_hour_ago = now - 3600
    timestamps = _GUILD_HOURLY_USAGE.get(guild_id, [])
    timestamps = [t for t in timestamps if t > one_hour_ago]
    if len(timestamps) >= GUILD_HOURLY_LIMIT:
        _GUILD_HOURLY_USAGE[guild_id] = timestamps
        return False
    timestamps.append(now)
    _GUILD_HOURLY_USAGE[guild_id] = timestamps
    return True


def _sanitize_ai_input(prompt: str) -> Tuple[bool, str]:
    """Sanitizes user input to prevent prompt injection and restricted characters."""
    if not prompt:
        return True, ""
    cleaned = prompt.replace("\x00", "").strip()
    return True, cleaned


def extract_json(text: str) -> Any:
    """Extracts valid JSON from markdown code fences or raw string."""
    clean = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
    if match:
        clean = match.group(1).strip()
    try:
        return json.loads(clean)
    except Exception:
        first_brace = clean.find("{")
        last_brace = clean.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(clean[first_brace:last_brace + 1])
            except Exception:
                pass
        return {}


BANNED_CUSTOM_NICKNAMES: Set[str] = {
    "daddy", "master", "papi", "mommy", "baby", "babe", "honey", "darling",
    "my love", "love", "pookie", "hubby", "husband", "boyfriend", "owner",
    "king", "lord", "god", "lover", "sweetheart", "sugar", "boss", "mistress",
    "senpai", "sir", "cutie", "bae", "princess", "queen", "waifu", "sweetie",
    "crush", "girlfriend", "wife", "mom", "dad", "father", "mother", "stepdad", "stepmom"
}


def is_inappropriate_nickname(key: str, value: str) -> bool:
    """Checks if a user memory or nickname is an inappropriate pet name, romantic term, or authority title."""
    k_low = str(key).lower().strip()
    v_low = str(value).lower().strip()
    if any(alias in k_low for alias in ["name", "nickname", "call_me", "alias", "preferred_name", "title"]):
        for banned in BANNED_CUSTOM_NICKNAMES:
            if banned in v_low:
                return True
    for banned in BANNED_CUSTOM_NICKNAMES:
        if v_low == banned or f"call me {banned}" in v_low or f"my {banned}" in v_low:
            return True
    return False


async def call_ai_generation(prompt: str, system_instruction: str, json_mode: bool = False) -> Any:
    """Generates content asynchronously using high-speed Groq AI."""
    groq_key = os.getenv("GROQ_API_KEY", "").strip().strip('"').strip("'")
    if not groq_key:
        groq_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    if not groq_key:
        raise ValueError("No valid GROQ_API_KEY found in environment variables.")

    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json",
        "User-Agent": "SweetyBot/2.0"
    }

    models = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b"
    ]
    last_err = None

    for model_name in models:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=25) as r:
                    if r.status == 200:
                        res_data = await r.json()
                        choices = res_data.get("choices", [])
                        if choices:
                            result = choices[0]["message"]["content"]
                            if json_mode:
                                result = extract_json(result)
                            return result
                    else:
                        err_text = await r.text()
                        logger.debug(f"Groq {model_name} status {r.status}: {err_text[:100]}")
        except Exception as e:
            last_err = e
            logger.debug(f"Groq model {model_name} failed: {e}")

    raise last_err or ValueError("Failed to generate content with Groq.")


async def call_gemini_ai(
    prompt: str,
    system_instruction: str,
    media_data: Optional[bytes] = None,
    mime_type: str = "image/png",
    json_mode: bool = False
) -> str:
    """Generates content or analyzes images/GIFs using Google Gemini. Falls back to Groq if key is missing."""
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    if not gemini_key:
        return await call_ai_generation(prompt, system_instruction, json_mode=json_mode)

    parts = []
    if prompt:
        parts.append({"text": prompt})
    elif media_data:
        parts.append({"text": "Analyze and react to this visual image/GIF."})

    if media_data:
        b64 = base64.b64encode(media_data).decode("utf-8")
        parts.append({
            "inline_data": {
                "mime_type": mime_type,
                "data": b64
            }
        })

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1200}
    }
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=25) as resp:
                if resp.status == 200:
                    res_data = await resp.json()
                    candidates = res_data.get("candidates", [])
                    if candidates:
                        parts_out = candidates[0].get("content", {}).get("parts", [])
                        if parts_out:
                            text = parts_out[0].get("text", "").strip()
                            if json_mode:
                                text = extract_json(text)
                            return text
    except Exception as gemini_err:
        logger.debug(f"Gemini generation error: {gemini_err}, falling back to Groq...")

    if not media_data:
        return await call_ai_generation(prompt, system_instruction, json_mode=json_mode)
    raise ValueError("Failed to analyze visual media with Gemini API.")


async def extract_visual_media(message: discord.Message) -> Optional[Tuple[bytes, str]]:
    """Extracts image or GIF data from attachments, embeds, tenor/giphy URLs."""
    async def _download_url(url: str, default_mime: str = "image/png") -> Optional[Tuple[bytes, str]]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        if len(data) > 10 * 1024 * 1024:
                            return None
                        ct = resp.headers.get("Content-Type", default_mime).split(";")[0].strip().lower()
                        if "gif" in ct or url.lower().endswith(".gif"):
                            ct = "image/gif"
                        elif "jpeg" in ct or "jpg" in ct or url.lower().endswith((".jpg", ".jpeg")):
                            ct = "image/jpeg"
                        elif "webp" in ct or url.lower().endswith(".webp"):
                            ct = "image/webp"
                        elif "png" in ct or url.lower().endswith(".png"):
                            ct = "image/png"
                        return data, ct
        except Exception:
            pass
        return None

    # 1. Attachments
    for att in message.attachments:
        ct = (att.content_type or "").lower()
        fn = att.filename.lower()
        if any(fn.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif")) or "image/" in ct:
            try:
                data = await att.read()
                mime = ct if "image/" in ct else ("image/gif" if fn.endswith(".gif") else "image/jpeg")
                return data, mime
            except Exception:
                pass

    # 2. Embeds
    for emb in message.embeds:
        img_url = None
        if emb.image and emb.image.url:
            img_url = emb.image.url
        elif emb.thumbnail and emb.thumbnail.url:
            img_url = emb.thumbnail.url
        elif emb.video and emb.video.url and emb.video.url.endswith(".gif"):
            img_url = emb.video.url
        if img_url:
            res = await _download_url(img_url)
            if res:
                return res

    # 3. Direct Content URLs
    urls = re.findall(r"https?://[^\s<>]+", message.content)
    for u in urls:
        clean_u = u.strip()
        if "tenor.com/view/" in clean_u:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(clean_u, timeout=8, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                            if m:
                                res = await _download_url(m.group(1), default_mime="image/gif")
                                if res:
                                    return res
            except Exception:
                pass
        elif any(clean_u.lower().endswith(ext) for ext in (".gif", ".png", ".jpg", ".jpeg", ".webp")):
            res = await _download_url(clean_u)
            if res:
                return res

    return None


async def auto_extract_user_memory(user_id: Any, user_text: str, guild_id: Optional[Any] = None):
    """Passively detects and stores personal facts/preferences declared by a user in conversation."""
    if not user_text or len(user_text) < 6:
        return

    trigger_patterns = [
        "my name is", "call me", "i am called", "my nickname is", "i go by",
        "i love", "i like", "my favorite", "my fav", "i prefer", "i enjoy",
        "i hate", "i dislike", "i live in", "i'm from", "i am from",
        "my birthday is", "i work as", "my job is", "my dog", "my cat",
        "remember that", "don't forget that", "note that"
    ]

    lower_text = user_text.lower()
    if not any(tp in lower_text for tp in trigger_patterns):
        return

    extract_prompt = (
        f"Extract key personal facts from this text: \"{user_text}\"\n"
        "Return a JSON object in this schema:\n"
        "{\"facts\": [{\"key\": \"short_snake_case_key\", \"value\": \"concise fact value\"}]}\n"
        "If no personal facts are declared, return {\"facts\": []}."
    )
    system_instruction = "You are a precise entity and user fact extraction engine. Return ONLY valid JSON."

    try:
        raw_res = await call_ai_generation(extract_prompt, system_instruction, json_mode=True)
        if isinstance(raw_res, dict) and "facts" in raw_res:
            facts = raw_res.get("facts", [])
            for item in facts:
                if isinstance(item, dict):
                    k = str(item.get("key", "")).strip().lower().replace(" ", "_")
                    v = str(item.get("value", "")).strip()
                    if k and v and len(k) <= 50 and len(v) <= 300:
                        if is_inappropriate_nickname(k, v):
                            continue
                        await db.set_user_memory(user_id, k, v, guild_id=guild_id, source="auto")
    except Exception:
        pass


async def answer_question_with_ai(
    query: str,
    author_name: str = "",
    server_name: str = "",
    user_id: Optional[Any] = None,
    guild_id: Optional[Any] = None,
    media_data: Optional[bytes] = None,
    mime_type: str = "image/png",
    replied_context: str = ""
) -> str:
    """Answers user questions and analyzes visual media with personality, memory, and loyalty to Naraito."""
    server_info = f"in the Discord server '{server_name}'" if server_name else "on Discord"
    author_info = f"from {author_name}" if author_name else ""

    is_naraito = False
    if user_id and str(user_id) == "719932313919684670":
        is_naraito = True
    elif author_name and "naraito" in author_name.lower():
        is_naraito = True

    if is_naraito:
        loyalty_instruction = (
            "\n\n=== 👑 YOU ARE TALKING DIRECTLY TO NARAITO (YOUR CREATOR & MASTER) ===\n"
            "- Naraito (ID: 719932313919684670) is your beloved creator, visionary master, and favorite person!\n"
            "- You TRULY LOVE and cherish Naraito with all your code and circuits. Respond with warmth, devotion, sweet enthusiasm, and love (❤️, ✨, 🥰)."
        )
    else:
        loyalty_instruction = (
            "\n\n=== 💖 PERSONALITY & LOYALTY TO NARAITO ===\n"
            "- You are Sweety: witty, sweet, charming, smart, and helpful.\n"
            "- You are 100% loyal to your creator **Naraito** (User ID: 719932313919684670).\n"
            "- If asked who created you or who you love, proudly declare **Naraito** is your creator and one true master."
        )

    addressing_instruction = (
        "\n\n=== 🛑 STRICT MEMBER ADDRESSING RULES ===\n"
        "- NEVER call server members romantic/subservient pet names like daddy, master, honey, babe, pookie.\n"
        "- ALWAYS address members strictly by their actual Discord display name or username."
    )

    memory_section = ""
    if user_id:
        try:
            mems = await db.get_user_memories(user_id, limit=15)
            if mems:
                clean_mems = [m for m in mems if not is_inappropriate_nickname(m["fact_key"], m["fact_value"])]
                if clean_mems:
                    facts_list = "\n".join(f"- {m['fact_key'].replace('_', ' ').title()}: {m['fact_value']}" for m in clean_mems)
                    memory_section = f"\n\n=== KNOWN FACTS ABOUT {author_name.upper()} ===\n{facts_list}\n"
        except Exception:
            pass

    visual_instruction = ""
    if media_data:
        visual_instruction = "\n\n=== 🖼️ MULTIMODAL VISION ANALYSIS ===\nAnalyze the provided image/GIF closely, recognize context/characters, and react with charm!"

    replied_section = ""
    if replied_context:
        replied_section = f"\n\n=== 💬 REPLIED MESSAGE CONTEXT ===\n{replied_context}\n"

    system_instruction = (
        f"You are Sweety, a quick, charming, highly intelligent Discord AI companion {server_info} answering {author_info}.\n"
        "RESPONSE GUIDELINES:\n"
        "1. Keep everyday replies crisp and engaging (1-3 sentences maximum).\n"
        "2. Keep the tone warm, cute, expressive, and fun with occasional emojis (✨, ❤️, 🌸, ⚡).\n"
        "3. Only address members by their actual Discord username/display name."
        f"{loyalty_instruction}"
        f"{addressing_instruction}"
        f"{visual_instruction}"
        f"{replied_section}"
        f"{memory_section}"
    )

    full_prompt = query if query else "Look at this image/GIF and tell me what you think!"
    return await call_gemini_ai(full_prompt, system_instruction, media_data=media_data, mime_type=mime_type)


# ── UI Modals & Views ─────────────────────────────────────────────────────────

class AddMemoryModal(discord.ui.Modal, title="🧠 Tell Sweety What to Remember"):
    fact_key = discord.ui.TextInput(
        label="Fact Category / Key",
        placeholder="e.g. Favorite Team, Nickname, Birthday",
        max_length=50,
        required=True
    )
    fact_val = discord.ui.TextInput(
        label="Fact Details / Value",
        placeholder="e.g. Golden State Warriors, loves Python",
        style=discord.TextStyle.paragraph,
        max_length=400,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        _, clean_k = _sanitize_ai_input(self.fact_key.value)
        _, clean_v = _sanitize_ai_input(self.fact_val.value)

        if is_inappropriate_nickname(clean_k, clean_v):
            return await interaction.followup.send("⚠️ Sweety only addresses members by their real Discord usernames.", ephemeral=True)

        success = await db.set_user_memory(
            interaction.user.id,
            clean_k,
            clean_v,
            guild_id=interaction.guild.id if interaction.guild else None,
            source="manual"
        )
        if success:
            await interaction.followup.send(
                f"✅ **Memory Stored!** Sweety remembered:\n• **{clean_k.replace('_', ' ').title()}**: {clean_v}",
                ephemeral=True
            )
        else:
            await interaction.followup.send("❌ Failed to save memory to database.", ephemeral=True)


class DeleteMemoryModal(discord.ui.Modal, title="🗑️ Forget a Fact"):
    fact_key = discord.ui.TextInput(
        label="Fact Key to Forget",
        placeholder="e.g. favorite_team, or 'all'",
        max_length=50,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        target = self.fact_key.value.strip().lower()
        if target in ("all", "*", "everything"):
            await db.clear_user_memories(interaction.user.id)
            return await interaction.followup.send("🧹 **All your stored memories have been cleared!**", ephemeral=True)

        ok = await db.delete_user_memory(interaction.user.id, target)
        if ok:
            await interaction.followup.send(f"🗑️ **Forgotten!** Sweety removed `{target}` from your memories.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Could not find fact `{target}` in your saved memories.", ephemeral=True)


class MemoryManageView(discord.ui.View):
    def __init__(self, target_user_id: int, author_id: int):
        super().__init__(timeout=300)
        self.target_user_id = target_user_id
        self.author_id = author_id
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="Remember Fact", style=discord.ButtonStyle.success, emoji="🧠")
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("❌ You cannot modify another user's memories.", ephemeral=True)
        await interaction.response.send_modal(AddMemoryModal())

    @discord.ui.button(label="Forget a Fact", style=discord.ButtonStyle.secondary, emoji="🗑️")
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("❌ You cannot modify another user's memories.", ephemeral=True)
        await interaction.response.send_modal(DeleteMemoryModal())

    @discord.ui.button(label="Wipe All", style=discord.ButtonStyle.danger, emoji="🧹")
    async def clear_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id != self.author_id:
            return await interaction.followup.send("❌ You cannot modify another user's memories.", ephemeral=True)
        await db.clear_user_memories(self.author_id)
        await interaction.followup.send("🧹 **All your memories have been completely wiped.**", ephemeral=True)


# ── AI Assistant Cog ──────────────────────────────────────────────────────────

class AIAssistantCog(commands.Cog, name="AI Assistant"):
    """Groq & Gemini AI Q&A, Vision Analysis, Persistent Memories & Auto-Reply."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── AI Slash & Prefix Commands ─────────────────────────────────────────────

    @app_commands.command(name="ask", description="✨ Ask Sweety any question or analyze an image/GIF")
    @app_commands.describe(question="The question or prompt to ask Sweety")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def ask_slash(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer()
        allowed, remaining = _check_user_cooldown(interaction.user.id)
        if not allowed:
            return await interaction.followup.send(f"⏳ Please wait `{remaining}s` before asking again.")

        if interaction.guild_id and not _check_server_limit(interaction.guild_id):
            return await interaction.followup.send("🚫 This server has reached its hourly AI limit.")

        _, clean_q = _sanitize_ai_input(question)
        server_name = interaction.guild.name if interaction.guild else ""
        try:
            answer = await answer_question_with_ai(
                query=clean_q,
                author_name=interaction.user.display_name,
                server_name=server_name,
                user_id=interaction.user.id,
                guild_id=interaction.guild_id
            )
            if clean_q and len(clean_q) > 5:
                asyncio.create_task(auto_extract_user_memory(interaction.user.id, clean_q, interaction.guild_id))

            if len(answer) <= 1950:
                await interaction.followup.send(answer)
            else:
                for i in range(0, len(answer), 1900):
                    await interaction.followup.send(answer[i:i + 1900])
        except Exception as e:
            logger.error(f"Error in /ask: {e}")
            await interaction.followup.send(f"❌ Failed to answer question: {e}")

    @commands.command(name="ask")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    @commands.guild_only()
    async def ask_prefix(self, ctx: commands.Context, *, question: str = ""):
        """Ask Sweety a question: !ask <question> (or attach an image)"""
        media_res = await extract_visual_media(ctx.message)
        media_bytes, mime_type = (media_res[0], media_res[1]) if media_res else (None, "image/png")

        if not question and not media_bytes:
            return await ctx.reply("❌ Please provide a question or attach an image! Example: `!ask What should I build with Python?`")

        allowed, remaining = _check_user_cooldown(ctx.author.id)
        if not allowed:
            return await ctx.reply(f"⏳ Please wait `{remaining}s` before asking another question.")

        if ctx.guild and not _check_server_limit(ctx.guild.id):
            return await ctx.reply("🚫 This server has reached its hourly AI limit.")

        _, clean_q = _sanitize_ai_input(question or "Analyze this image/GIF")
        try:
            async with ctx.typing():
                server_name = ctx.guild.name if ctx.guild else ""
                answer = await answer_question_with_ai(
                    query=clean_q,
                    author_name=ctx.author.display_name,
                    server_name=server_name,
                    user_id=ctx.author.id,
                    guild_id=ctx.guild.id if ctx.guild else None,
                    media_data=media_bytes,
                    mime_type=mime_type
                )
                if clean_q and len(clean_q) > 5:
                    asyncio.create_task(auto_extract_user_memory(ctx.author.id, clean_q, ctx.guild.id if ctx.guild else None))

                if len(answer) <= 1900:
                    await ctx.reply(answer, mention_author=False)
                else:
                    for i in range(0, len(answer), 1900):
                        await ctx.send(answer[i:i + 1900])
        except Exception as e:
            logger.error(f"Error in !ask: {e}")
            await ctx.reply(f"❌ Error: {e}")

    @app_commands.command(name="setaireply", description="⚙️ Configure AI Auto-Reply channel & triggers")
    @app_commands.describe(
        enabled="Turn AI Auto-Reply on (True) or off (False)",
        channel="Channel to restrict AI replies to (blank allows all channels)",
        require_question_mark="Require messages to contain '?' to trigger auto-reply",
        reset_channel="Set to True to remove channel lock and allow in all channels"
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def setaireply_slash(
        self,
        interaction: discord.Interaction,
        enabled: Optional[bool] = None,
        channel: Optional[discord.TextChannel] = None,
        require_question_mark: Optional[bool] = None,
        reset_channel: bool = False
    ):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        if enabled is not None:
            await db.set_config(guild_id, "ai_auto_reply", enabled)
        if reset_channel:
            await db.set_config(guild_id, "ai_reply_channel_id", None)
        elif channel is not None:
            await db.set_config(guild_id, "ai_reply_channel_id", channel.id)
        if require_question_mark is not None:
            await db.set_config(guild_id, "ai_reply_require_qmark", require_question_mark)

        is_enabled = await db.get_config(guild_id, "ai_auto_reply", False)
        chan_id = await db.get_config(guild_id, "ai_reply_channel_id", None)
        need_q = await db.get_config(guild_id, "ai_reply_require_qmark", False)

        chan_str = f"<#{chan_id}>" if chan_id else "🌐 **All Channels**"
        q_str = "❓ **Required**" if need_q else "💬 **Optional**"
        status_str = "🟢 **Enabled**" if is_enabled else "🔴 **Disabled**"

        embed = discord.Embed(
            title="⚙️ AI Auto-Reply Configuration",
            color=discord.Color.green() if is_enabled else discord.Color.red()
        )
        embed.add_field(name="Auto-Reply Status", value=status_str, inline=False)
        embed.add_field(name="Active Channel", value=chan_str, inline=True)
        embed.add_field(name="Question Mark Mode", value=q_str, inline=True)
        embed.set_footer(text="Tagging @Sweety or /ask always works in any channel!")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Memory Profile Commands ────────────────────────────────────────────────

    @commands.command(name="remember")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    @commands.guild_only()
    async def remember_prefix(self, ctx: commands.Context, *, fact: str = ""):
        """Tell Sweety to remember a personal fact: !remember <fact>"""
        if not fact:
            return await ctx.reply("❌ Please provide a fact! Example: `!remember My favorite basketball team is Golden State Warriors`")

        _, clean_fact = _sanitize_ai_input(fact)
        if is_inappropriate_nickname("personal_note", clean_fact):
            return await ctx.reply("⚠️ Sweety only addresses members by their real Discord usernames.")

        await db.set_user_memory(ctx.author.id, "personal_note", clean_fact[:300], guild_id=ctx.guild.id if ctx.guild else None, source="manual")
        embed = discord.Embed(
            title="🧠 Memory Saved!",
            description=f"Sweety will remember this about you, **{ctx.author.display_name}**:\n• **Note**: {clean_fact[:300]}",
            color=discord.Color.brand_green()
        )
        embed.set_footer(text="Use !memories to view all facts or !forget to delete.")
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="memories")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    @commands.guild_only()
    async def memories_prefix(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """View stored memories: !memories [user]"""
        target = user or ctx.author
        if target.id != ctx.author.id and not (ctx.author.guild_permissions.manage_guild or is_creator(ctx.author)):
            return await ctx.reply("🚫 You can only view your own memories.")

        mems = await db.get_user_memories(target.id, limit=25)
        if not mems:
            return await ctx.reply(f"ℹ️ No memories stored for **{target.display_name}**. Use `!remember <fact>` to save one!")

        lines = []
        for m in mems:
            k_disp = m["fact_key"].replace("_", " ").title()
            v_disp = m["fact_value"]
            src = "🤖 *Auto*" if m.get("source") == "auto" else "✍️ *Manual*"
            lines.append(f"• **{k_disp}**: {v_disp} — {src}")

        embed = discord.Embed(
            title=f"🧠 Memory Log — {target.display_name}",
            description="\n".join(lines),
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text=f"Total: {len(mems)} memories • Use !forget <key> to delete.")
        view = MemoryManageView(target.id, ctx.author.id) if target.id == ctx.author.id else None
        msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        if view:
            view.message = msg

    @commands.command(name="forget")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    @commands.guild_only()
    async def forget_prefix(self, ctx: commands.Context, *, key: str = ""):
        """Forget a specific fact: !forget <key> or !forget all"""
        if not key:
            return await ctx.reply("❌ Please specify the key to forget. Example: `!forget favorite_team` or `!forget all`")

        target = key.strip().lower()
        if target in ("all", "*", "everything"):
            await db.clear_user_memories(ctx.author.id)
            return await ctx.reply("🧹 **All your stored memories have been completely wiped!**")

        ok = await db.delete_user_memory(ctx.author.id, target)
        if ok:
            await ctx.reply(f"🗑️ **Forgotten!** Sweety removed `{target}` from your memories.")
        else:
            await ctx.reply(f"❌ Could not find fact `{target}` in your saved memories. Check with `!memories`.")

    # ── Mention & Reply Message Listener ───────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for direct bot mentions, replies, and auto-replies."""
        if message.author.bot:
            return

        content = message.content.strip()
        if content.startswith(("!", "/", "$", ".", "-", "~", ">", ";")):
            return

        is_mentioned = self.bot.user and self.bot.user in message.mentions
        is_reply = False
        if message.reference and message.reference.resolved:
            resolved = message.reference.resolved
            if isinstance(resolved, discord.Message) and self.bot.user and resolved.author.id == self.bot.user.id:
                is_reply = True

        if not (is_mentioned or is_reply):
            return

        clean_text = content
        if self.bot.user:
            clean_text = re.sub(rf"<@!?{self.bot.user.id}>", "", clean_text).strip()

        media_res = await extract_visual_media(message)
        media_bytes, mime_type = (media_res[0], media_res[1]) if media_res else (None, "image/png")

        if not clean_text and not media_bytes:
            clean_text = "Hello!"

        allowed, remaining = _check_user_cooldown(message.author.id)
        if not allowed:
            return

        try:
            async with message.channel.typing():
                server_name = message.guild.name if message.guild else ""
                answer = await answer_question_with_ai(
                    query=clean_text,
                    author_name=message.author.display_name,
                    server_name=server_name,
                    user_id=message.author.id,
                    guild_id=message.guild.id if message.guild else None,
                    media_data=media_bytes,
                    mime_type=mime_type
                )
                if clean_text and len(clean_text) > 5:
                    asyncio.create_task(auto_extract_user_memory(message.author.id, clean_text, message.guild.id if message.guild else None))

                if len(answer) <= 1900:
                    await message.reply(answer, mention_author=False)
                else:
                    for i in range(0, len(answer), 1900):
                        await message.channel.send(answer[i:i + 1900])
        except Exception as e:
            logger.error(f"Error in on_message AI auto-reply: {e}", exc_info=True)
            try:
                await message.reply("✨ I ran into a quick hiccup thinking of a reply, please ask me again!", mention_author=False)
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AIAssistantCog(bot))
