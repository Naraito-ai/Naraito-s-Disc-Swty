# -*- coding: utf-8 -*-
"""
main.py - SweetyBot Production Entry Point & Cog Orchestrator
Modular Architecture with 9 Isolated Cogs, Resilient Database & Fast Interaction Response.
"""
from __future__ import annotations

import os
import sys
import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
load_dotenv()

import aiohttp
import discord
from discord.ext import commands, tasks
from discord import app_commands

from database import db
from nba_data import clean_memory, is_creator

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SweetyBot.Main")

# ── Cog Extensions to Load ───────────────────────────────────────────────────
COGS_TO_LOAD = [
    "cogs.nba_cards",
    "cogs.nba_economy",
    "cogs.nba_battle",
    "cogs.nba_events",
    "cogs.nba_minigames",
    "cogs.nba_admin",
    "cogs.moderation",
    "cogs.utilities",
    "cogs.ai_assistant"
]


class SweetyBot(commands.Bot):
    """Authoritative Discord Bot for Sweety with modular cog architecture."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.guilds = True
        intents.message_content = True
        intents.voice_states = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            max_messages=100,
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.watching, name="/help | @Sweety")
        )
        self.start_time = time.time()
        self._fastapi_started = False

    async def setup_hook(self):
        """Initializes database, loads all modular cogs, starts background tasks, and syncs tree."""
        logger.info("Initializing Database...")
        await db.initialize()

        logger.info(f"Loading {len(COGS_TO_LOAD)} Modular Cogs...")
        for cog_name in COGS_TO_LOAD:
            try:
                await self.load_extension(cog_name)
                logger.info(f"  + Cog Loaded: {cog_name}")
            except Exception as e:
                logger.error(f"  x Failed to load cog {cog_name}: {e}", exc_info=True)

        # Start background tasks
        self.presence_task.start()
        self.reminders_task.start()
        self.cleanup_task.start()
        self.keepalive_pinger_task.start()

        # Start FastAPI Dashboard / Health Server for Render
        port = int(os.getenv("PORT", 8080))
        disable_api = os.getenv("DISABLE_DASHBOARD_API", "false").lower() == "true"
        if not disable_api and not self._fastapi_started:
            try:
                from api import start_fastapi
                self._fastapi_started = True
                asyncio.create_task(start_fastapi(self, db, port))
                logger.info(f"FastAPI dashboard task scheduled on port {port}.")
            except Exception as api_err:
                logger.warning(f"FastAPI startup skipped or failed: {api_err}")

        # Register tree error handler
        self.tree.on_error = self.on_app_command_error

        # Sync application commands
        try:
            logger.info("Syncing Application Slash Commands with Discord...")
            synced = await self.tree.sync()
            logger.info(f"Successfully synced {len(synced)} application commands.")
        except Exception as sync_err:
            logger.error(f"Failed to sync slash commands: {sync_err}")

    async def on_ready(self):
        """Dispatched when the bot is fully logged in and ready."""
        logger.info(f"SweetyBot logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guilds with {len(self.users)} cached users.")

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Global error handler for prefix commands."""
        if isinstance(error, commands.CommandNotFound):
            return  # Silently ignore invalid command prefixes

        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.reply(f"⏳ **Cooldown Active:** Please wait `{error.retry_after:.1f}s` before using this command again.", mention_author=False)

        if isinstance(error, commands.MissingPermissions):
            perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            return await ctx.reply(f"🚫 **Permission Denied:** You need {perms} permission(s) to run this command.", mention_author=False)

        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.reply(f"⚠️ **Missing Argument:** `{error.param.name}` is required. Use `!help {ctx.command.name}` for details.", mention_author=False)

        if isinstance(error, commands.BadArgument):
            return await ctx.reply(f"⚠️ **Invalid Argument:** {error}", mention_author=False)

        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.reply("❌ This command cannot be used in private direct messages.", mention_author=False)

        if isinstance(error, commands.CheckFailure):
            return await ctx.reply("❌ You do not meet the requirements to run this command.", mention_author=False)

        logger.error(f"Unhandled error in command '{ctx.command}': {error}", exc_info=error)
        try:
            await ctx.reply(f"❌ **Command Error:** An unexpected error occurred. Please try again later.", mention_author=False)
        except Exception:
            pass

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Global error handler for application slash commands."""
        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ **Cooldown Active:** Please wait `{error.retry_after:.1f}s` before using this command again."
        elif isinstance(error, app_commands.MissingPermissions):
            perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            msg = f"🚫 **Permission Denied:** You need {perms} permissions to run this command."
        elif isinstance(error, app_commands.CheckFailure):
            msg = "❌ You do not have permission or requirements to run this command."
        else:
            logger.error(f"Unhandled slash command error in /{interaction.command.name if interaction.command else 'unknown'}: {error}", exc_info=error)
            msg = f"❌ An error occurred while executing this command."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass

    # ── Background Loops ────────────────────────────────────────────────────────

    @tasks.loop(minutes=2)
    async def presence_task(self):
        """Rotates presence activity to show live status and guild count."""
        try:
            guild_count = len(self.guilds)
            activity_name = f"/help | @Sweety | {guild_count} servers"
            await self.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(type=discord.ActivityType.watching, name=activity_name)
            )
        except Exception as e:
            logger.debug(f"Presence update skipped: {e}")

    @tasks.loop(seconds=30)
    async def reminders_task(self):
        """Polls database for due user reminders and delivers them."""
        try:
            now_ts = time.time()
            rows = await db.fetch("SELECT * FROM reminders WHERE reminder_time <= ? AND completed = 0 LIMIT 20", now_ts)
            if not rows:
                return

            for r in rows:
                r_id = r["id"]
                u_id = int(r["user_id"])
                note = r.get("reminder_text") or r.get("note", "Reminder")
                c_id = r.get("channel_id")

                await db.execute("UPDATE reminders SET completed = 1 WHERE id = ?", r_id)

                user = self.get_user(u_id)
                if not user:
                    try:
                        user = await self.fetch_user(u_id)
                    except Exception:
                        user = None

                embed = discord.Embed(
                    title="⏰ Reminder Alert!",
                    description=f"👋 **{user.mention if user else f'<@{u_id}>'}**, here is your scheduled reminder:\n\n**{note}**",
                    color=discord.Color.gold()
                )
                embed.timestamp = discord.utils.utcnow()

                sent = False
                if c_id:
                    chan = self.get_channel(int(c_id))
                    if chan:
                        try:
                            await chan.send(content=f"🔔 {user.mention if user else f'<@{u_id}>'}", embed=embed)
                            sent = True
                        except Exception:
                            pass

                if not sent and user:
                    try:
                        await user.send(embed=embed)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Reminders background loop error: {e}")

    @tasks.loop(minutes=10)
    async def cleanup_task(self):
        """Periodically runs garbage collection to maintain minimal RAM usage."""
        try:
            clean_memory()
        except Exception as e:
            logger.debug(f"Cleanup task error: {e}")

    @tasks.loop(minutes=5)
    async def keepalive_pinger_task(self):
        """Pings the Render/Railway external URL or local health check to prevent idle spin-down."""
        ext_url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("APP_URL") or os.getenv("PUBLIC_URL")
        port = int(os.getenv("PORT", 8080))
        urls = []
        if ext_url:
            urls.append(ext_url.rstrip("/") + "/health")
        urls.append(f"http://127.0.0.1:{port}/health")

        for u in urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(u, timeout=10) as resp:
                        if resp.status == 200:
                            logger.debug(f"Keepalive self-ping OK: {u}")
            except Exception as e:
                logger.debug(f"Keepalive ping {u} failed: {e}")

    @presence_task.before_loop
    @reminders_task.before_loop
    @cleanup_task.before_loop
    @keepalive_pinger_task.before_loop
    async def before_tasks(self):
        await self.wait_until_ready()


# Backward compatibility alias
GeminiBot = SweetyBot

# Global Bot Instance
bot = SweetyBot()


async def main():
    """Main execution function for SweetyBot."""
    token = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("FATAL: No DISCORD_BOT_TOKEN or DISCORD_TOKEN found in environment variables.")
        sys.exit(1)

    clean_token = token.strip().strip('"').strip("'")
    logger.info("Starting SweetyBot...")
    async with bot:
        await bot.start(clean_token)


if __name__ == "__main__":
    asyncio.run(main())
