# -*- coding: utf-8 -*-
"""
cogs/utilities.py - Utility Commands (Help Guide, Ping, ServerInfo, UserInfo, Avatar, RemindMe, AFK, Polls, Weather)
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

logger = logging.getLogger("SweetyBot.Utilities")

_afk_cache: Dict[Tuple[int, int], Dict[str, Any]] = {}


class HelpCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🏀 NBA 2K Cards & Dex", value="cards", description="Collection, binder, inspect, and Holo Foil fusion", emoji="🎴"),
            discord.SelectOption(label="💰 NBA Economy & Packs", value="economy", description="VC balance, pack odds, selling, trading, gifting", emoji="💵"),
            discord.SelectOption(label="⚔️ NBA Battles & Starting 5", value="battle", description="5v5 battles, lineup builder, GM ranks, boss", emoji="🏆"),
            discord.SelectOption(label="🎯 NBA Minigames & Drops", value="minigames", description="3-Point Shootout, wild court chat drops & catching", emoji="🎯"),
            discord.SelectOption(label="🏆 Server Events & Raids", value="events", description="Tournaments, collector race, and community raids", emoji="👾"),
            discord.SelectOption(label="🛡️ Server Moderation", value="mod", description="Ban, kick, timeout, warn, purge, channel locks", emoji="🔨"),
            discord.SelectOption(label="⚙️ General Utilities", value="utils", description="Ping, serverinfo, userinfo, avatar, reminders, AFK", emoji="🔧"),
            discord.SelectOption(label="🧠 AI Assistant & QA", value="ai", description="Groq AI real-time answering, vision, memory", emoji="🤖")
        ]
        super().__init__(placeholder="📖 Select a category to explore commands...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cat = self.values[0]
        embed = discord.Embed(color=discord.Color.gold())
        embed.set_footer(text="Sweety Bot • Use /help or !help anytime")
        embed.timestamp = discord.utils.utcnow()

        if cat == "cards":
            embed.title = "🎴 NBA 2K Cards & Dex Commands"
            embed.description = (
                "• `/nbadex` (`!nbadex`) — Open your full card binder collection\n"
                "• `/nbacard <card>` (`!nbacard`) — Inspect card artwork, stats, and real moment\n"
                "• `/nbafuse <card>` (`!nbafuse`) — Fuse 3 duplicates into an animated Holo Foil card (+5 OVR)\n"
                "• `/nbafav <card>` (`!nbafav`) — Favorite/protect a card in your showcase\n"
                "• `/nbaprivacy` (`!nbaprivacy`) — Toggle binder public/private visibility"
            )
        elif cat == "economy":
            embed.title = "💰 NBA Economy & Pack Commands"
            embed.description = (
                "• `/nbabal` (`!nbabal`) — Check your liquid VC and binder net worth\n"
                "• `/packodds` (`!packodds`) — View pull rates across all 5 pack tiers\n"
                "• `/nbasell <card> [count]` (`!nbasell`) — Quicksell duplicate cards for VC\n"
                "• `/nbagive @user <card> [count]` (`!nbagive`) — Gift cards to another member\n"
                "• `/nbatrade @user` (`!nbatrade`) — Open a 2-sided interactive card & VC trade\n"
                "• `/nbadaily` (`!nbadaily`) — Claim your daily 500 VC check-in\n"
                "• `/nbaweekly` (`!nbaweekly`) — Claim your weekly 2,500 VC bonus\n"
                "• `/nbamonthly` (`!nbamonthly`) — Claim your monthly 10,000 VC GM salary"
            )
        elif cat == "battle":
            embed.title = "⚔️ NBA Battles & Starting 5 Commands"
            embed.description = (
                "• `/buildteam` (`!buildteam`) — Interactive 5-position Starting 5 lineup builder\n"
                "• `/autoteam` (`!autoteam`) — Automatically equip highest OVR cards owned\n"
                "• `/myteam` (`!myteam`) — View your starting 5 lineup graphic card\n"
                "• `/teambattle [@user]` (`!teambattle`) — 5v5 full court tactical battle for VC\n"
                "• `/nbatop` (`!nbatop`) — Top card collectors & battle GM rankings"
            )
        elif cat == "minigames":
            embed.title = "🎯 NBA Minigames & Drops Commands"
            embed.description = (
                "• `/shootout` (`!shootout`) — 3-Point Contest with green timing releases for VC\n"
                "• `/catch <player>` (`!catch`) — Catch active wild card appearing in chat\n"
                "• `/nbahint` (`!nbahint`) — Reveal an extra letter hint for active drop\n"
                "• `/setupnbachannel #ch` — Pin wild drops to a dedicated channel"
            )
        elif cat == "events":
            embed.title = "🏆 Server Events & Raids Commands"
            embed.description = (
                "• `/event status` — View active tournament or raid boss HP\n"
                "• `/event raid` — Attack Community Raid Boss for damage and prize\n"
                "• `/event create` — Launch a tournament or raid (Creator only)\n"
                "• `/event end` — Conclude active event and award grand prize"
            )
        elif cat == "mod":
            embed.title = "🛡️ Server Moderation Commands"
            embed.description = (
                "• `/ban @user [reason]` (`!ban`) — Ban a member\n"
                "• `/kick @user [reason]` (`!kick`) — Kick a member\n"
                "• `/timeout @user <min>` (`!timeout`) — Timeout/mute a member\n"
                "• `/untimeout @user` (`!untimeout`) — Remove timeout/unmute\n"
                "• `/warn @user <reason>` (`!warn`) — Issue official warning strike\n"
                "• `/purge <count>` (`!purge`) — Bulk delete messages\n"
                "• `/lock` & `/unlock` — Lock/unlock channel messaging"
            )
        elif cat == "utils":
            embed.title = "⚙️ General Utility Commands"
            embed.description = (
                "• `/ping` (`!ping`) — Check gateway latency and response time\n"
                "• `/serverinfo` (`!serverinfo`) — View server statistics and member counts\n"
                "• `/userinfo [@user]` (`!userinfo`) — View user account details and join dates\n"
                "• `/avatar [@user]` (`!avatar`) — View high-res avatar image\n"
                "• `/remindme <time> <msg>` (`!remindme`) — Set a timed reminder\n"
                "• `/afk [reason]` (`!afk`) — Set AFK status when stepped away"
            )
        elif cat == "ai":
            embed.title = "🤖 AI Assistant & QA Commands"
            embed.description = (
                "• `/ask <question>` (`!ask`) — Ask Gemini / Groq AI questions with real-time answers\n"
                "• `@Sweety <question>` — Mention Sweety anywhere to chat naturally in server\n"
                "• `/imagine <prompt>` (`!imagine`) — Generate creative imagery\n"
                "• `/summarize` (`!summarize`) — Summarize chat history"
            )

        await interaction.edit_original_response(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180.0)
        self.add_item(HelpCategorySelect())
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class UtilitiesCog(commands.Cog, name="Utilities"):
    """General utilities, help system, server analytics, reminders, and AFK."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Help System ─────────────────────────────────────────────────────────────

    @app_commands.command(name="help", description="📖 Open the interactive Sweety command guide & help menu")
    @app_commands.guild_only()
    async def help_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = discord.Embed(
            title="🌟 Sweety Bot • Interactive Guide & Help Center",
            description=(
                "👋 Welcome! Sweety is an advanced Discord AI & NBA 2K Mobile bot equipped with complete card collecting, 5v5 battles, moderation, and utility tools.\n\n"
                "📌 **Select a category from the dropdown menu below** to explore all available commands!\n\n"
                "• 🎴 **NBA 2K Cards:** `/nbadex`, `/nbacard`, `/nbafuse`\n"
                "• 💵 **NBA Economy:** `/nbabal`, `/packodds`, `/nbasell`, `/nbatrade`\n"
                "• 🏆 **NBA Battles:** `/buildteam`, `/autoteam`, `/myteam`, `/teambattle`\n"
                "• 🎯 **NBA Minigames:** `/shootout`, `/catch`, `/nbahint`\n"
                "• 🛡️ **Moderation:** `/ban`, `/kick`, `/timeout`, `/warn`, `/purge`\n"
                "• 🔧 **Utilities:** `/ping`, `/serverinfo`, `/userinfo`, `/remindme`, `/afk`"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user else None)
        embed.set_footer(text="Select a category below to view detailed command parameters")
        view = HelpView()
        await interaction.followup.send(embed=embed, view=view)

    @commands.command(name="help", aliases=["commands", "guide", "menu"])
    @commands.guild_only()
    async def help_prefix(self, ctx: commands.Context):
        """Open the interactive help guide: !help"""
        embed = discord.Embed(
            title="🌟 Sweety Bot • Interactive Guide & Help Center",
            description=(
                "👋 Welcome! Select a category from the dropdown below to explore all commands.\n\n"
                "• 🎴 **NBA Cards:** `!nbadex`, `!nbacard`, `!nbafuse`\n"
                "• 💵 **NBA Economy:** `!nbabal`, `!packodds`, `!nbasell`, `!nbatrade`\n"
                "• 🏆 **NBA Battles:** `!buildteam`, `!autoteam`, `!myteam`, `!teambattle`\n"
                "• 🎯 **NBA Minigames:** `!shootout`, `!catch`, `!nbahint`\n"
                "• 🛡️ **Moderation:** `!ban`, `!kick`, `!timeout`, `!warn`, `!purge`\n"
                "• 🔧 **Utilities:** `!ping`, `!serverinfo`, `!userinfo`, `!remindme`, `!afk`"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user else None)
        view = HelpView()
        await ctx.send(embed=embed, view=view)

    # ── Ping & Server Info ──────────────────────────────────────────────────────

    @app_commands.command(name="ping", description="🏓 Check bot latency and Discord API gateway connection")
    @app_commands.guild_only()
    async def ping_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        lat = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"• ⚡ **Gateway Latency:** `{lat}ms`\n• 🌐 **Status:** `Online & Fully Operational`",
            color=discord.Color.green() if lat < 150 else discord.Color.gold()
        )
        await interaction.followup.send(embed=embed)

    @commands.command(name="ping", aliases=["latency"])
    @commands.guild_only()
    async def ping_prefix(self, ctx: commands.Context):
        """Check bot latency: !ping"""
        lat = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 **Pong!** Gateway Latency: `{lat}ms` (Online).")

    @app_commands.command(name="serverinfo", description="📊 View detailed statistics and information about this server")
    @app_commands.guild_only()
    async def serverinfo_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        g = interaction.guild
        embed = discord.Embed(
            title=f"📊 Server Information • {g.name}",
            description=(
                f"• 👑 **Owner:** {g.owner.mention if g.owner else 'Unknown'}\n"
                f"• 👥 **Members:** `{g.member_count:,}`\n"
                f"• 💬 **Text Channels:** `{len(g.text_channels)}` | 🔊 **Voice:** `{len(g.voice_channels)}`\n"
                f"• 🎭 **Roles:** `{len(g.roles)}` | 😃 **Emojis:** `{len(g.emojis)}`\n"
                f"• 📅 **Created:** <t:{int(g.created_at.timestamp())}:R>"
            ),
            color=discord.Color.blue()
        )
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)

    @commands.command(name="serverinfo", aliases=["server", "guildinfo"])
    @commands.guild_only()
    async def serverinfo_prefix(self, ctx: commands.Context):
        """View server info: !serverinfo"""
        g = ctx.guild
        embed = discord.Embed(
            title=f"📊 Server Information • {g.name}",
            description=(
                f"• 👑 **Owner:** {g.owner.mention if g.owner else 'Unknown'}\n"
                f"• 👥 **Members:** `{g.member_count:,}`\n"
                f"• 💬 **Channels:** `{len(g.channels)}` | 🎭 **Roles:** `{len(g.roles)}`\n"
                f"• 📅 **Created:** <t:{int(g.created_at.timestamp())}:R>"
            ),
            color=discord.Color.blue()
        )
        if g.icon: embed.set_thumbnail(url=g.icon.url)
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)

    # ── User Info & Avatar ──────────────────────────────────────────────────────

    @app_commands.command(name="userinfo", description="👤 View details and join dates for a server member")
    @app_commands.describe(user="The member to inspect (optional)")
    @app_commands.guild_only()
    async def userinfo_slash(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer()
        target = user or interaction.user
        joined_str = f"<t:{int(target.joined_at.timestamp())}:R>" if getattr(target, "joined_at", None) else "Unknown"
        top_role_str = target.top_role.mention if hasattr(target, "top_role") else "None"
        embed = discord.Embed(
            title=f"👤 Member Information • {target.display_name}",
            description=(
                f"• 🆔 **User ID:** `{target.id}`\n"
                f"• 📅 **Account Created:** <t:{int(target.created_at.timestamp())}:R>\n"
                f"• 📥 **Joined Server:** {joined_str}\n"
                f"• 🎭 **Top Role:** {top_role_str}"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)

    @commands.command(name="userinfo", aliases=["user", "whois"])
    @commands.guild_only()
    async def userinfo_prefix(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        """View user info: !userinfo [@user]"""
        u = target or ctx.author
        joined_str = f"<t:{int(u.joined_at.timestamp())}:R>" if getattr(u, "joined_at", None) else "Unknown"
        top_role_str = u.top_role.mention if hasattr(u, "top_role") else "None"
        embed = discord.Embed(
            title=f"👤 Member Information • {u.display_name}",
            description=(
                f"• 🆔 **ID:** `{u.id}`\n"
                f"• 📅 **Account Created:** <t:{int(u.created_at.timestamp())}:R>\n"
                f"• 📥 **Joined Server:** {joined_str}\n"
                f"• 🎭 **Top Role:** {top_role_str}"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=u.display_avatar.url)
        await ctx.send(embed=embed)

    @app_commands.command(name="avatar", description="🖼️ View and download high-resolution avatar image for a member")
    @app_commands.describe(user="The member whose avatar to view (optional)")
    @app_commands.guild_only()
    async def avatar_slash(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer()
        target = user or interaction.user
        embed = discord.Embed(title=f"🖼️ Avatar • {target.display_name}", color=discord.Color.purple())
        embed.set_image(url=target.display_avatar.url)
        await interaction.followup.send(embed=embed)

    @commands.command(name="avatar", aliases=["av", "pfp"])
    @commands.guild_only()
    async def avatar_prefix(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        """View avatar: !avatar [@user]"""
        u = target or ctx.author
        embed = discord.Embed(title=f"🖼️ Avatar • {u.display_name}", color=discord.Color.purple())
        embed.set_image(url=u.display_avatar.url)
        await ctx.send(embed=embed)

    # ── AFK System ──────────────────────────────────────────────────────────────

    @app_commands.command(name="afk", description="💤 Set your AFK away message for when members mention you")
    @app_commands.describe(reason="Reason for stepping away (optional)")
    @app_commands.guild_only()
    async def afk_slash(self, interaction: discord.Interaction, reason: Optional[str] = "AFK"):
        await interaction.response.defer()
        _afk_cache[(interaction.guild_id, interaction.user.id)] = {"reason": reason, "since": time.time()}
        await db.set_afk(interaction.user.id, interaction.guild_id, reason, time.time())
        await interaction.followup.send(f"💤 {interaction.user.mention}, you are now marked as AFK: **{reason}**.")

    @commands.command(name="afk")
    @commands.guild_only()
    async def afk_prefix(self, ctx: commands.Context, *, reason: str = "AFK"):
        """Set AFK status: !afk [reason]"""
        _afk_cache[(ctx.guild.id, ctx.author.id)] = {"reason": reason, "since": time.time()}
        await db.set_afk(ctx.author.id, ctx.guild.id, reason, time.time())
        await ctx.send(f"💤 {ctx.author.mention}, you are now marked as AFK: **{reason}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(UtilitiesCog(bot))
