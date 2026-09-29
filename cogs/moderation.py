# -*- coding: utf-8 -*-
"""
cogs/moderation.py - Server Moderation, Ban/Kick/Timeout/Warn, Strike Tracking, Purge, Lock, AutoMod & Appeals
"""
from __future__ import annotations

import time
import datetime
import logging
from typing import Optional, Union, List, Dict, Any, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from database import db
from nba_data import is_creator

logger = logging.getLogger("SweetyBot.Moderation")


def is_protected(member: Union[discord.Member, discord.User, int, None]) -> bool:
    """Sole authoritative gatekeeper for bot immunity and protection."""
    if member is None:
        return False
    mem_id = getattr(member, "id", member)
    try:
        mem_id = int(mem_id)
    except (ValueError, TypeError):
        mem_id = None

    if mem_id == 719932313919684670:
        return True

    guild = getattr(member, "guild", None)
    if guild and mem_id is not None and mem_id == getattr(guild, "owner_id", None):
        return True

    perms = getattr(member, "guild_permissions", None)
    if perms and (
        perms.administrator or 
        perms.manage_guild or 
        perms.manage_channels or 
        perms.manage_messages or 
        perms.manage_roles or 
        perms.moderate_members or 
        perms.ban_members or 
        perms.kick_members
    ):
        return True

    return False


class ModerationCog(commands.Cog, name="Moderation"):
    """Server moderation suite, warning system, timeouts, purges, and security."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Slash Commands ──────────────────────────────────────────────────────────

    @app_commands.command(name="ban", description="🔨 Ban a member from the server")
    @app_commands.describe(user="The member to ban", reason="Reason for the ban (optional)")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban_slash(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = "No reason provided"):
        await interaction.response.defer()
        if is_protected(user):
            return await interaction.followup.send("🚫 You cannot ban an administrator, staff member, or the bot creator!", ephemeral=True)
        await user.ban(reason=reason)
        await db.record_moderation_action(interaction.guild_id, interaction.user.id, user.id, "ban", reason)
        await interaction.followup.send(f"🔨 **{user.display_name}** has been banned. *Reason:* {reason}")

    @app_commands.command(name="kick", description="👢 Kick a member from the server")
    @app_commands.describe(user="The member to kick", reason="Reason for the kick (optional)")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick_slash(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = "No reason provided"):
        await interaction.response.defer()
        if is_protected(user):
            return await interaction.followup.send("🚫 You cannot kick an administrator, staff member, or the bot creator!", ephemeral=True)
        await user.kick(reason=reason)
        await db.record_moderation_action(interaction.guild_id, interaction.user.id, user.id, "kick", reason)
        await interaction.followup.send(f"👢 **{user.display_name}** has been kicked. *Reason:* {reason}")

    @app_commands.command(name="timeout", description="⏳ Timeout / Mute a member for a specified duration")
    @app_commands.describe(user="The member to timeout", minutes="Duration in minutes", reason="Reason (optional)")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout_slash(self, interaction: discord.Interaction, user: discord.Member, minutes: int, reason: Optional[str] = "No reason provided"):
        await interaction.response.defer()
        if is_protected(user):
            return await interaction.followup.send("🚫 You cannot timeout an administrator, staff member, or the bot creator!", ephemeral=True)
        dur = datetime.timedelta(minutes=max(1, min(minutes, 40320)))
        await user.timeout(dur, reason=reason)
        await db.record_moderation_action(interaction.guild_id, interaction.user.id, user.id, "timeout", reason)
        await interaction.followup.send(f"⏳ **{user.display_name}** has been timed out for **{minutes} minutes**. *Reason:* {reason}")

    @app_commands.command(name="untimeout", description="🔊 Remove timeout / unmute a member")
    @app_commands.describe(user="The member to unmute")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout_slash(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer()
        await user.timeout(None, reason="Untimeout requested by staff")
        await interaction.followup.send(f"🔊 **{user.display_name}** is no longer timed out.")

    @app_commands.command(name="warn", description="⚠️ Issue an official moderation warning to a member")
    @app_commands.describe(user="The member to warn", reason="Reason for warning")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn_slash(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        await interaction.response.defer()
        if is_protected(user):
            return await interaction.followup.send("🚫 You cannot warn an administrator, staff member, or the bot creator!", ephemeral=True)
        strike_count = await db.add_user_strike(interaction.guild_id, user.id, interaction.user.id, reason)
        await db.record_moderation_action(interaction.guild_id, interaction.user.id, user.id, "warn", reason)
        await interaction.followup.send(f"⚠️ **{user.display_name}** has been warned. *Reason:* {reason} (Total Strikes: `{strike_count}`)")

    @app_commands.command(name="strike", description="⚡ Issue an official strike to a member")
    @app_commands.describe(user="The member to strike", reason="Reason for strike")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(moderate_members=True)
    async def strike_slash(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        await interaction.response.defer()
        if is_protected(user):
            return await interaction.followup.send("🚫 You cannot strike an administrator, staff member, or the bot creator!", ephemeral=True)
        strike_count = await db.add_user_strike(interaction.guild_id, user.id, interaction.user.id, reason)
        await db.record_moderation_action(interaction.guild_id, interaction.user.id, user.id, "strike", reason)
        await interaction.followup.send(f"⚡ **{user.display_name}** has received a strike. *Reason:* {reason} (Total Strikes: `{strike_count}`)")

    @app_commands.command(name="strikes", description="📋 View moderation strikes and warnings for a member")
    @app_commands.describe(user="The member whose strikes to inspect")
    @app_commands.guild_only()
    async def strikes_slash(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer()
        target = user or interaction.user
        rows = await db.get_warnings(interaction.guild_id, target.id)
        count = len(rows)
        embed = discord.Embed(
            title=f"📋 Moderation Strikes • {target.display_name}",
            description=f"Total Strikes on Record: **`{count}`**\n",
            color=discord.Color.orange() if count > 0 else discord.Color.green()
        )
        for i, r in enumerate(rows[:10], 1):
            embed.add_field(name=f"Strike #{i}", value=f"**Reason:** {r.get('reason', 'No reason')}\n**Moderator:** <@{r.get('moderator_id', '')}>", inline=False)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="purge", description="🧹 Bulk delete messages from the current channel")
    @app_commands.describe(count="Number of messages to delete (1-100)")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge_slash(self, interaction: discord.Interaction, count: int):
        await interaction.response.defer(ephemeral=True)
        del_count = max(1, min(count, 100))
        deleted = await interaction.channel.purge(limit=del_count)
        await interaction.followup.send(f"🧹 Successfully purged **`{len(deleted)}` messages**.", ephemeral=True)

    @app_commands.command(name="lock", description="🔒 Lock down the current channel so members cannot send messages")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.followup.send("🔒 **Channel locked.** Members cannot send messages.")

    @app_commands.command(name="unlock", description="🔓 Unlock the current channel")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.followup.send("🔓 **Channel unlocked.**")

    # ── Prefix Commands ─────────────────────────────────────────────────────────

    @commands.command(name="ban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def ban_prefix(self, ctx: commands.Context, user: discord.Member, *, reason: str = "No reason provided"):
        """Ban a member: !ban @user [reason]"""
        if is_protected(user):
            return await ctx.send("🚫 You cannot ban an administrator, staff member, or the bot creator!")
        await user.ban(reason=reason)
        await db.record_moderation_action(ctx.guild.id, ctx.author.id, user.id, "ban", reason)
        await ctx.send(f"🔨 **{user.display_name}** has been banned. *Reason:* {reason}")

    @commands.command(name="kick")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    async def kick_prefix(self, ctx: commands.Context, user: discord.Member, *, reason: str = "No reason provided"):
        """Kick a member: !kick @user [reason]"""
        if is_protected(user):
            return await ctx.send("🚫 You cannot kick an administrator, staff member, or the bot creator!")
        await user.kick(reason=reason)
        await db.record_moderation_action(ctx.guild.id, ctx.author.id, user.id, "kick", reason)
        await ctx.send(f"👢 **{user.display_name}** has been kicked. *Reason:* {reason}")

    @commands.command(name="timeout", aliases=["mute"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def timeout_prefix(self, ctx: commands.Context, user: discord.Member, minutes: int, *, reason: str = "No reason provided"):
        """Timeout a member: !timeout @user <minutes> [reason]"""
        if is_protected(user):
            return await ctx.send("🚫 You cannot timeout an administrator, staff member, or the bot creator!")
        dur = datetime.timedelta(minutes=max(1, min(minutes, 40320)))
        await user.timeout(dur, reason=reason)
        await db.record_moderation_action(ctx.guild.id, ctx.author.id, user.id, "timeout", reason)
        await ctx.send(f"⏳ **{user.display_name}** timed out for **{minutes}m**. *Reason:* {reason}")

    @commands.command(name="untimeout", aliases=["unmute"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def untimeout_prefix(self, ctx: commands.Context, user: discord.Member):
        """Unmute a member: !untimeout @user"""
        await user.timeout(None, reason="Untimeout requested by staff")
        await ctx.send(f"🔊 **{user.display_name}** is no longer timed out.")

    @commands.command(name="warn", aliases=["strike"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def warn_prefix(self, ctx: commands.Context, user: discord.Member, *, reason: str):
        """Warn a member: !warn @user <reason>"""
        if is_protected(user):
            return await ctx.send("🚫 You cannot warn an administrator, staff member, or the bot creator!")
        strike_count = await db.add_user_strike(ctx.guild.id, user.id, ctx.author.id, reason)
        await db.record_moderation_action(ctx.guild.id, ctx.author.id, user.id, "warn", reason)
        await ctx.send(f"⚠️ **{user.display_name}** has been warned. *Reason:* {reason} (Total Strikes: `{strike_count}`)")

    @commands.command(name="strikes", aliases=["warnings", "infractions"])
    @commands.guild_only()
    async def strikes_prefix(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """View strikes for a member: !strikes [@user]"""
        target = user or ctx.author
        rows = await db.get_warnings(ctx.guild.id, target.id)
        count = len(rows)
        embed = discord.Embed(
            title=f"📋 Moderation Strikes • {target.display_name}",
            description=f"Total Strikes on Record: **`{count}`**\n",
            color=discord.Color.orange() if count > 0 else discord.Color.green()
        )
        for i, r in enumerate(rows[:10], 1):
            embed.add_field(name=f"Strike #{i}", value=f"**Reason:** {r.get('reason', 'No reason')}\n**Moderator:** <@{r.get('moderator_id', '')}>", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="purge", aliases=["clear"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def purge_prefix(self, ctx: commands.Context, count: int = 10):
        """Purge messages: !purge [count]"""
        del_count = max(1, min(count, 100))
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=del_count)
        msg = await ctx.send(f"🧹 Purged **`{len(deleted)}` messages**.")
        await msg.delete(delay=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
