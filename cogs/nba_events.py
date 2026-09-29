# -*- coding: utf-8 -*-
"""
cogs/nba_events.py - Tournaments, Card Collector Races, Fuse Frenzies, Pack Marathons & Raid Boss Battles
"""
from __future__ import annotations

import io
import time
import random
import logging
import asyncio
from typing import Optional, Union, List, Dict, Any, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from database import db
from nba_data import (
    NBA_2K_TIERS,
    NBA_2K_CARD_THEMES,
    get_nba_card,
    generate_nba_card_graphic,
    is_creator
)

logger = logging.getLogger("SweetyBot.NBAEvents")


def is_event_creator(user: Union[discord.User, discord.Member]) -> bool:
    return is_creator(user)


class NBAEventsCog(commands.Cog, name="NBA Events"):
    """Server event tournaments, collector races, fuse frenzies, pack marathons, and raid bosses."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    event_group = app_commands.Group(name="event", description="🏆 Server Event & Tournament System")

    @event_group.command(name="create", description="👑 Launch a new server tournament or event (Creator Only)")
    @app_commands.describe(
        name="Event name (e.g. 'Summer Championship')",
        prize_card="Card ID or player name to award as grand prize",
        prize_count="Number of copies of the prize card to award (default 1)",
        duration_hours="Duration in hours (e.g. 24, 48, 72)",
        event_type="Select event format",
        description="Event description and lore",
        rules="Specific rules or winning conditions",
        boss_name="Name of Raid Boss (for Raid events only)",
        boss_hp="Boss HP (for Raid events only, default 50000)"
    )
    @app_commands.choices(event_type=[
        app_commands.Choice(name="🎯 Custom / Manual Challenge", value="custom"),
        app_commands.Choice(name="🏆 Card Collector Race (First to complete tier)", value="collector_race"),
        app_commands.Choice(name="🌟 Fuse Frenzy (Most Holo Foil cards created)", value="fuse_frenzy"),
        app_commands.Choice(name="📦 Pack Opening Marathon (Most packs opened)", value="pack_marathon"),
        app_commands.Choice(name="👾 Community Raid Boss (Server defeats Boss together)", value="raid"),
    ])
    @app_commands.guild_only()
    async def event_create(
        self,
        interaction: discord.Interaction,
        name: str,
        prize_card: str,
        prize_count: Optional[int] = 1,
        duration_hours: Optional[float] = 48.0,
        event_type: Optional[str] = "custom",
        description: Optional[str] = "",
        rules: Optional[str] = "",
        boss_name: Optional[str] = "Titan Mecha Giannis",
        boss_hp: Optional[int] = 50000
    ):
        if not is_event_creator(interaction.user):
            return await interaction.response.send_message("❌ Only the Bot Creator can create server events.", ephemeral=True)

        await interaction.response.defer()
        active = await db.get_active_nba_event(interaction.guild_id)
        if active:
            return await interaction.followup.send(f"❌ There is already an active event: **{active['name']}** (ID #{active['id']}). Use `/event end` or `/event cancel` first.", ephemeral=True)

        prize_obj = get_nba_card(prize_card)
        if not prize_obj:
            return await interaction.followup.send(f"❌ Prize card `{prize_card}` not found in catalog.", ephemeral=True)

        ev_type = event_type or "custom"
        b_name = boss_name if ev_type == "raid" else ""
        b_hp = max(1000, boss_hp or 50000) if ev_type == "raid" else 0
        dur = max(0.5, float(duration_hours or 48.0))
        p_count = max(1, min(prize_count or 1, 50))

        event_id = await db.create_nba_event(
            guild_id=interaction.guild_id,
            name=name,
            description=description or f"Compete in the {name} event!",
            event_type=ev_type,
            prize_card_id=prize_obj["id"],
            prize_card_name=prize_obj["name"],
            channel_id=interaction.channel_id,
            duration_hours=dur,
            rules=rules or "Standard server event rules apply.",
            boss_name=b_name,
            boss_hp=b_hp
        )

        ends_at = int(time.time() + (dur * 3600))
        tier_info = NBA_2K_TIERS.get(prize_obj.get("tier", "dark_matter"), NBA_2K_TIERS["gold"])
        ann_embed = discord.Embed(
            title=f"🏆 NEW SERVER EVENT: {name}",
            description=(
                f"📝 **Description:**\n{description or 'The Creator has initiated a new competitive event!'}\n\n"
                f"📜 **Rules:** {rules or 'Play fair and have fun!'}\n\n"
                f"👑 **Grand Prize:** {tier_info['emoji']} **[{prize_obj['ovr']} OVR] {prize_obj['name']}** (x{p_count})\n"
                f"⏳ **Event Ends:** <t:{ends_at}:R> (<t:{ends_at}:F>)"
            ),
            color=0xFF1493
        )
        img_io = await asyncio.to_thread(generate_nba_card_graphic, prize_obj)
        ann_file = discord.File(img_io, filename=f"prize_{prize_obj['id']}.png")
        ann_embed.set_image(url=f"attachment://prize_{prize_obj['id']}.png")
        await interaction.followup.send(embed=ann_embed, file=ann_file)

    @event_group.command(name="status", description="📊 View current active server event status and rankings")
    @app_commands.guild_only()
    async def event_status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        active = await db.get_active_nba_event(interaction.guild_id)
        if not active:
            return await interaction.followup.send("ℹ️ No active event is currently running in this server.")

        ends_at = int(active.get("ends_at", active.get("end_time", time.time())))
        prize_obj = get_nba_card(active.get("prize_card_id", ""))
        pname = prize_obj["name"] if prize_obj else active.get("prize_card_name", "Rare Card")

        desc = (
            f"• **Event Name:** **{active['name']}** (ID #{active['id']})\n"
            f"• **Format:** `{active.get('event_type', 'custom').replace('_', ' ').title()}`\n"
            f"• **Grand Prize:** 👑 **{pname}**\n"
            f"• **Time Remaining:** <t:{ends_at}:R>\n\n"
        )

        if active.get("event_type") == "raid":
            hp_cur = active.get("boss_hp", active.get("boss_hp_current", 0))
            hp_max = active.get("boss_max_hp", active.get("boss_hp_max", 1))
            pct = max(0.0, min(100.0, (hp_cur / hp_max) * 100))
            bars = int(pct / 10)
            hp_bar = "█" * bars + "░" * (10 - bars)
            desc += (
                f"👾 **Raid Boss:** **{active.get('boss_name', 'Titan Boss')}**\n"
                f"❤️ **Boss HP:** `{hp_cur:,} / {hp_max:,}` (`{pct:.1f}%`)\n"
                f"`[{hp_bar}]`\n\n"
                f"⚔️ Attack with `/event raid` to deal damage and win the prize!"
            )

        embed = discord.Embed(title=f"🏆 Active Server Event • {active['name']}", description=desc, color=discord.Color.gold())
        await interaction.followup.send(embed=embed)

    @event_group.command(name="raid", description="⚔️ Attack the active Community Raid Boss to deal damage")
    @app_commands.guild_only()
    async def event_raid(self, interaction: discord.Interaction):
        await interaction.response.defer()
        active = await db.get_active_nba_event(interaction.guild_id)
        if not active or active.get("event_type") != "raid":
            return await interaction.followup.send("❌ There is no active Raid Boss event right now.", ephemeral=True)

        user_team = await db.get_dream_team(interaction.user.id)
        team_ovr = user_team.get("ovr_rating", 85.0) if user_team else 85.0
        dmg = int(team_ovr * random.randint(10, 25))

        new_hp, defeated = await db.apply_nba_raid_damage(active["id"], interaction.user.id, dmg)
        embed = discord.Embed(
            title="⚔️ Raid Boss Attack!",
            description=(
                f"💥 {interaction.user.mention} attacked **{active.get('boss_name', 'Boss')}** for **`{dmg:,} DMG`**!\n\n"
                f"❤️ **Remaining Boss HP:** `{max(0, new_hp):,}`"
            ),
            color=discord.Color.red()
        )
        if defeated:
            embed.description += f"\n\n🎉 **THE RAID BOSS HAS BEEN DEFEATED!** Calculating top damage dealer..."
        await interaction.followup.send(embed=embed)

    @event_group.command(name="end", description="👑 End the active event and finalize rewards (Creator Only)")
    @app_commands.guild_only()
    async def event_end(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not is_event_creator(interaction.user):
            return await interaction.followup.send("❌ Only the Bot Creator can end events.", ephemeral=True)
        active = await db.get_active_nba_event(interaction.guild_id)
        if not active:
            return await interaction.followup.send("❌ No active event to end.", ephemeral=True)
        await db.end_nba_event(active["id"])
        await interaction.followup.send(f"✅ Event **{active['name']}** has been concluded.", ephemeral=True)

    @event_group.command(name="cancel", description="👑 Cancel the active event without awarding prizes (Creator Only)")
    @app_commands.guild_only()
    async def event_cancel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not is_event_creator(interaction.user):
            return await interaction.followup.send("❌ Only the Bot Creator can cancel events.", ephemeral=True)
        active = await db.get_active_nba_event(interaction.guild_id)
        if not active:
            return await interaction.followup.send("❌ No active event to cancel.", ephemeral=True)
        await db.cancel_nba_event(active["id"])
        await interaction.followup.send(f"✅ Event **{active['name']}** has been cancelled.", ephemeral=True)

    @event_group.command(name="reward", description="👑 Award event prize cards & VC to a winner (Creator Only)")
    @app_commands.describe(user="The winner to receive the rewards", card="Card ID or Player Name", count="Number of copies", vc="VC reward amount")
    @app_commands.guild_only()
    async def event_reward(self, interaction: discord.Interaction, user: discord.Member, card: str, count: Optional[int] = 1, vc: Optional[int] = 0):
        await interaction.response.defer(ephemeral=True)
        if not is_event_creator(interaction.user):
            return await interaction.followup.send("❌ Only the Bot Creator can award event prizes.", ephemeral=True)
        active = await db.get_active_nba_event(interaction.guild_id)
        event_id = active["id"] if active else 0
        card_obj = get_nba_card(card)
        if not card_obj:
            return await interaction.followup.send(f"❌ Card `{card}` was not found.", ephemeral=True)
        p_count = max(1, min(count or 1, 50))
        vc_amt = max(0, vc or 0)
        await db.reward_nba_event_winner(event_id, user.id, card_obj["id"], card_obj["name"], count=p_count, vc_amount=vc_amt, rewarded_by=str(interaction.user.id))
        tier_info = NBA_2K_TIERS.get(card_obj.get("tier", "dark_matter"), NBA_2K_TIERS["gold"])
        embed = discord.Embed(
            title="🏆 Event Prize Awarded!",
            description=f"🎉 Successfully awarded **{p_count}x** {tier_info['emoji']} **[{card_obj['ovr']} OVR] {card_obj['name']}** and **`{vc_amt:,} VC`** to {user.mention}!",
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @event_group.command(name="setchannel", description="📢 Designate a specific channel for NBA events & drops (Admin Only)")
    @app_commands.describe(channel="Channel to designate")
    @app_commands.guild_only()
    async def event_setchannel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.manage_guild and not is_creator(interaction.user):
            return await interaction.followup.send("🚫 You need Manage Server permission to set the event channel.", ephemeral=True)
        target_ch = channel or interaction.channel
        await db.set_nba_event_channel(interaction.guild_id, target_ch.id)
        await interaction.followup.send(f"✅ NBA Events channel set to {target_ch.mention}!")

    @event_group.command(name="list", description="📜 View recent and active server events")
    @app_commands.guild_only()
    async def event_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        events = await db.get_all_nba_events(interaction.guild_id, limit=5)
        if not events:
            return await interaction.followup.send("ℹ️ No events found for this server.")
        embed = discord.Embed(title="📜 Server NBA Events History", color=discord.Color.gold())
        for ev in events:
            status_emoji = "🟢 Active" if ev.get("status") == "active" else ("🔴 Ended" if ev.get("status") == "ended" else "⚪ Cancelled")
            embed.add_field(
                name=f"#{ev['id']} • {ev['name']} ({status_emoji})",
                value=f"**Type:** `{ev.get('event_type', 'custom')}`\n**Prize:** {ev.get('prize_card_name', 'Card')}",
                inline=False
            )
        await interaction.followup.send(embed=embed)

    # ── Prefix Commands ─────────────────────────────────────────────────────────

    @commands.group(name="event", invoke_without_command=True)
    @commands.guild_only()
    async def event_prefix_group(self, ctx: commands.Context):
        """Server Events: !event [status|raid|create|end|cancel|reward|setchannel|list]"""
        await self.event_status_prefix(ctx)

    @event_prefix_group.command(name="status")
    @commands.guild_only()
    async def event_status_prefix(self, ctx: commands.Context):
        active = await db.get_active_nba_event(ctx.guild.id)
        if not active:
            return await ctx.send("ℹ️ No active event is currently running in this server.")
        ends_at = int(active.get("ends_at", active.get("end_time", time.time())))
        prize_obj = get_nba_card(active.get("prize_card_id", ""))
        pname = prize_obj["name"] if prize_obj else active.get("prize_card_name", "Rare Card")
        desc = (
            f"• **Event Name:** **{active['name']}** (ID #{active['id']})\n"
            f"• **Format:** `{active.get('event_type', 'custom').replace('_', ' ').title()}`\n"
            f"• **Grand Prize:** 👑 **{pname}**\n"
            f"• **Time Remaining:** <t:{ends_at}:R>\n\n"
        )
        if active.get("event_type") == "raid":
            hp_cur = active.get("boss_hp", active.get("boss_hp_current", 0))
            hp_max = active.get("boss_max_hp", active.get("boss_hp_max", 1))
            pct = max(0.0, min(100.0, (hp_cur / hp_max) * 100))
            bars = int(pct / 10)
            hp_bar = "█" * bars + "░" * (10 - bars)
            desc += (
                f"👾 **Raid Boss:** **{active.get('boss_name', 'Titan Boss')}**\n"
                f"❤️ **Boss HP:** `{hp_cur:,} / {hp_max:,}` (`{pct:.1f}%`)\n"
                f"`[{hp_bar}]`\n\n"
                f"⚔️ Attack with `!event raid` to deal damage!"
            )
        embed = discord.Embed(title=f"🏆 Active Server Event • {active['name']}", description=desc, color=discord.Color.gold())
        await ctx.send(embed=embed)

    @event_prefix_group.command(name="raid", aliases=["attack"])
    @commands.guild_only()
    async def event_raid_prefix(self, ctx: commands.Context):
        active = await db.get_active_nba_event(ctx.guild.id)
        if not active or active.get("event_type") != "raid":
            return await ctx.send("❌ There is no active Raid Boss event right now.")
        user_team = await db.get_dream_team(ctx.author.id)
        team_ovr = user_team.get("ovr_rating", 85.0) if user_team else 85.0
        dmg = int(team_ovr * random.randint(10, 25))
        new_hp, defeated = await db.apply_nba_raid_damage(active["id"], ctx.author.id, dmg)
        embed = discord.Embed(
            title="⚔️ Raid Boss Attack!",
            description=(
                f"💥 {ctx.author.mention} attacked **{active.get('boss_name', 'Boss')}** for **`{dmg:,} DMG`**!\n\n"
                f"❤️ **Remaining Boss HP:** `{max(0, new_hp):,}`"
            ),
            color=discord.Color.red()
        )
        if defeated:
            embed.description += f"\n\n🎉 **THE RAID BOSS HAS BEEN DEFEATED!**"
        await ctx.send(embed=embed)

    @event_prefix_group.command(name="create")
    @commands.guild_only()
    async def event_create_prefix(self, ctx: commands.Context, name: str, prize_card: str, duration_hours: float = 48.0):
        if not is_event_creator(ctx.author):
            return await ctx.send("❌ Only the Bot Creator can create server events.")
        active = await db.get_active_nba_event(ctx.guild.id)
        if active:
            return await ctx.send(f"❌ An event is already active: **{active['name']}**.")
        prize_obj = get_nba_card(prize_card)
        if not prize_obj:
            return await ctx.send(f"❌ Prize card `{prize_card}` not found in catalog.")
        event_id = await db.create_nba_event(
            guild_id=ctx.guild.id,
            name=name,
            description=f"Compete in the {name} event!",
            event_type="custom",
            prize_card_id=prize_obj["id"],
            prize_card_name=prize_obj["name"],
            channel_id=ctx.channel.id,
            duration_hours=duration_hours,
            rules="Standard rules apply."
        )
        ends_at = int(time.time() + (duration_hours * 3600))
        tier_info = NBA_2K_TIERS.get(prize_obj.get("tier", "dark_matter"), NBA_2K_TIERS["gold"])
        embed = discord.Embed(
            title=f"🏆 NEW SERVER EVENT: {name}",
            description=f"👑 **Grand Prize:** {tier_info['emoji']} **[{prize_obj['ovr']} OVR] {prize_obj['name']}**\n⏳ **Ends:** <t:{ends_at}:R>",
            color=0xFF1493
        )
        await ctx.send(embed=embed)

    @event_prefix_group.command(name="end")
    @commands.guild_only()
    async def event_end_prefix(self, ctx: commands.Context):
        if not is_event_creator(ctx.author):
            return await ctx.send("❌ Only the Bot Creator can end events.")
        active = await db.get_active_nba_event(ctx.guild.id)
        if not active:
            return await ctx.send("❌ No active event to end.")
        await db.end_nba_event(active["id"])
        await ctx.send(f"✅ Event **{active['name']}** has been concluded.")

    @event_prefix_group.command(name="cancel")
    @commands.guild_only()
    async def event_cancel_prefix(self, ctx: commands.Context):
        if not is_event_creator(ctx.author):
            return await ctx.send("❌ Only the Bot Creator can cancel events.")
        active = await db.get_active_nba_event(ctx.guild.id)
        if not active:
            return await ctx.send("❌ No active event to cancel.")
        await db.cancel_nba_event(active["id"])
        await ctx.send(f"✅ Event **{active['name']}** has been cancelled.")

    @event_prefix_group.command(name="reward")
    @commands.guild_only()
    async def event_reward_prefix(self, ctx: commands.Context, user: discord.Member, card: str, count: int = 1, vc: int = 0):
        if not is_event_creator(ctx.author):
            return await ctx.send("❌ Only the Bot Creator can award event prizes.")
        active = await db.get_active_nba_event(ctx.guild.id)
        event_id = active["id"] if active else 0
        card_obj = get_nba_card(card)
        if not card_obj:
            return await ctx.send(f"❌ Card `{card}` was not found.")
        p_count = max(1, min(count, 50))
        vc_amt = max(0, vc)
        await db.reward_nba_event_winner(event_id, user.id, card_obj["id"], card_obj["name"], count=p_count, vc_amount=vc_amt, rewarded_by=str(ctx.author.id))
        tier_info = NBA_2K_TIERS.get(card_obj.get("tier", "dark_matter"), NBA_2K_TIERS["gold"])
        embed = discord.Embed(
            title="🏆 Event Prize Awarded!",
            description=f"🎉 Successfully awarded **{p_count}x** {tier_info['emoji']} **[{card_obj['ovr']} OVR] {card_obj['name']}** and **`{vc_amt:,} VC`** to {user.mention}!",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @event_prefix_group.command(name="setchannel")
    @commands.guild_only()
    async def event_setchannel_prefix(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        if not ctx.author.guild_permissions.manage_guild and not is_creator(ctx.author):
            return await ctx.send("🚫 You need Manage Server permission to set the event channel.")
        target_ch = channel or ctx.channel
        await db.set_nba_event_channel(ctx.guild.id, target_ch.id)
        await ctx.send(f"✅ NBA Events channel set to {target_ch.mention}!")

    @event_prefix_group.command(name="list")
    @commands.guild_only()
    async def event_list_prefix(self, ctx: commands.Context):
        events = await db.get_all_nba_events(ctx.guild.id, limit=5)
        if not events:
            return await ctx.send("ℹ️ No events found for this server.")
        embed = discord.Embed(title="📜 Server NBA Events History", color=discord.Color.gold())
        for ev in events:
            status_emoji = "🟢 Active" if ev.get("status") == "active" else ("🔴 Ended" if ev.get("status") == "ended" else "⚪ Cancelled")
            embed.add_field(
                name=f"#{ev['id']} • {ev['name']} ({status_emoji})",
                value=f"**Type:** `{ev.get('event_type', 'custom')}`\n**Prize:** {ev.get('prize_card_name', 'Card')}",
                inline=False
            )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(NBAEventsCog(bot))
