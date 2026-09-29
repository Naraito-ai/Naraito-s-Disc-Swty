# -*- coding: utf-8 -*-
"""
cogs/nba_minigames.py - 3-Point Shootout Contest, Wild Card Chat Spawns, Hint & Catch Commands
"""
from __future__ import annotations

import io
import time
import random
import logging
from typing import Optional, Union, List, Dict, Any, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from database import db
from nba_data import (
    NBA_2K_TIERS,
    NBA_2K_CARD_THEMES,
    NBA_2K_MOBILE_CARDS,
    get_nba_card,
    get_nba_card_moment,
    generate_nba_card_graphic,
    generate_player_hint,
    is_correct_player_name,
    is_valid_drop_channel,
    get_best_drop_channel,
    extract_picks_from_row,
    card_to_player_dict,
    is_creator
)

logger = logging.getLogger("SweetyBot.NBAMinigames")

_SHOOTOUT_USER_COOLDOWNS: Dict[int, float] = {}
_active_nba_drops: Dict[int, Dict[str, Any]] = {}
_nba_drop_msg_counts: Dict[int, int] = {}
_nba_drop_last_timestamps: Dict[int, float] = {}

NBA_SHOOTOUT_STATIONS: List[Dict[str, Any]] = [
    {"name": "Left Corner Rack", "icon": "📍", "type": "standard", "balls": 5, "max_pts": 6},
    {"name": "Left Wing Rack", "icon": "📍", "type": "standard", "balls": 5, "max_pts": 6},
    {"name": "Starry Deep Ball 1 (30ft)", "icon": "⭐", "type": "starry", "balls": 1, "max_pts": 3},
    {"name": "Top of Arc Rack", "icon": "📍", "type": "standard", "balls": 5, "max_pts": 6},
    {"name": "Starry Deep Ball 2 (30ft)", "icon": "⭐", "type": "starry", "balls": 1, "max_pts": 3},
    {"name": "Right Wing Rack", "icon": "📍", "type": "standard", "balls": 5, "max_pts": 6},
    {"name": "Money Ball Rack (Right Corner)", "icon": "💰", "type": "all_money", "balls": 5, "max_pts": 10},
]


async def get_user_best_3pt_shooter(user_id: int) -> Dict[str, Any]:
    row = await db.get_dream_team(user_id)
    if row:
        picks = extract_picks_from_row(row)
        if picks:
            return max(picks.values(), key=lambda p: p.get("pts_3", p.get("stats", {}).get("3pt", 80)))

    owned = await db.get_user_nba_cards(user_id)
    if owned:
        best_c = None
        best_val = -1
        for entry in owned:
            c = get_nba_card(entry["card_id"])
            if c:
                val = c.get("stats", {}).get("3pt", 80)
                if val > best_val:
                    best_val = val
                    best_c = c
        if best_c:
            return card_to_player_dict(best_c)

    return {"name": "Stephen Curry", "pts_3": 99, "team": "GSW", "emoji": "🎯", "tag": "Unanimous MVP • Greatest Shooter Ever"}


def simulate_interactive_shootout_station(player: Dict[str, Any], station_type: str, technique: str, current_streak: int = 0):
    stat_3pt = player.get("pts_3", player.get("stats", {}).get("3pt", 85))
    base_acc = max(0.35, min(0.92, 0.45 + ((stat_3pt - 70) / 30.0) * 0.42))
    acc_mod = 0.10 if technique == "green_precision" and stat_3pt >= 88 else (0.05 if technique == "quick_trigger" else (0.14 if technique == "deep_heatcheck" and current_streak >= 2 else 0.0))
    commentary = "🎯 **Precision Release**!" if technique == "green_precision" else ("⚡ **Quick Catch-and-Shoot**!" if technique == "quick_trigger" else "🔥 **Heat Check Release**!")
    streak_bonus = 0.08 if current_streak >= 3 else (0.04 if current_streak >= 2 else 0.0)
    effective_acc = max(0.25, min(0.96, base_acc + acc_mod + streak_bonus))

    shots = []
    pts_made, money_made, starry_made = 0, 0, 0
    streak = current_streak

    if station_type == "starry":
        made = random.random() < (effective_acc * 0.70 + (0.12 if technique == "deep_heatcheck" else 0.0))
        if made:
            streak += 1; pts_made += 3; starry_made += 1
            shots.append({"icon": "⭐", "pts": 3, "made": True, "label": "BANG! 30-Footer"})
        else:
            streak = 0
            shots.append({"icon": "⚪", "pts": 0, "made": False, "label": "Miss"})
    elif station_type == "all_money":
        for _ in range(5):
            made = random.random() < effective_acc
            if made:
                streak += 1; pts_made += 2; money_made += 1
                shots.append({"icon": "🟡", "pts": 2, "made": True, "label": "Money Ball Swish"})
            else:
                streak = 0
                shots.append({"icon": "⚪", "pts": 0, "made": False, "label": "Miss"})
    else:
        for _ in range(4):
            made = random.random() < effective_acc
            if made:
                streak += 1; pts_made += 1
                shots.append({"icon": "🟢", "pts": 1, "made": True, "label": "Swish"})
            else:
                streak = 0
                shots.append({"icon": "⚪", "pts": 0, "made": False, "label": "Miss"})
        made = random.random() < min(0.95, effective_acc + 0.02)
        if made:
            streak += 1; pts_made += 2; money_made += 1
            shots.append({"icon": "🟡", "pts": 2, "made": True, "label": "Money Ball Swish"})
        else:
            streak = 0
            shots.append({"icon": "⚪", "pts": 0, "made": False, "label": "Money Ball Miss"})

    return shots, pts_made, money_made, starry_made, streak, commentary


def build_shootout_embed(user: Union[discord.Member, discord.User], player: Dict[str, Any], station_results: List[Dict[str, Any]], current_station_idx: int, total_score: int, is_complete: bool = False, vc_won: int = 0, last_commentary: str = "") -> discord.Embed:
    stat_3pt = player.get("pts_3", player.get("stats", {}).get("3pt", 85))
    status_tag = "🏆 **SHOOTOUT COMPLETE!**" if is_complete else f"🏀 **Round in Progress — Station {current_station_idx + 1}/7**"
    color = discord.Color.gold() if is_complete else discord.Color.green()

    desc = (
        f"{status_tag}\n\n"
        f"👤 **Shooter:** {player.get('emoji', '🎯')} **{player['name']}** (`🏹 {stat_3pt} 3PT Rating`)\n"
        f"🎯 **Total Score:** `🔥 {total_score} / 40 PTS`\n"
    )
    if is_complete and vc_won > 0:
        desc += f"💰 **VC Reward Earned:** `+{vc_won:,} VC`\n"
    if last_commentary:
        desc += f"\n📢 {last_commentary}\n"

    desc += "\n**Shooting Racks Breakdown:**\n"
    for idx, st in enumerate(NBA_SHOOTOUT_STATIONS):
        if idx < len(station_results):
            res = station_results[idx]
            shot_str = " ".join(s["icon"] for s in res["shots"])
            desc += f"`{idx+1}.` **{st['name']}:** {shot_str} (`{res['pts']} PTS`)\n"
        elif idx == current_station_idx and not is_complete:
            desc += f"`{idx+1}.` ▶ **{st['name']}:** ⏳ *Shooting now...*\n"
        else:
            desc += f"`{idx+1}.` ⚪ **{st['name']}:** *Upcoming*\n"

    embed = discord.Embed(title=f"🏀 NBA All-Star 3-Point Contest • {user.display_name}", description=desc, color=color)
    embed.set_thumbnail(url=user.display_avatar.url)
    return embed


class ThreePointShootoutView(discord.ui.View):
    def __init__(self, author: Union[discord.Member, discord.User], player: Dict[str, Any]):
        super().__init__(timeout=120.0)
        self.author = author
        self.player = player
        self.current_station_idx = 0
        self.station_results: List[Dict[str, Any]] = []
        self.total_score = 0
        self.current_streak = 0
        self.is_complete = False
        self.vc_won = 0
        self.last_commentary = ""
        self._build_controls()

    def _build_controls(self):
        self.clear_items()
        if not self.is_complete:
            btn_green = discord.ui.Button(label="🎯 Green Release", style=discord.ButtonStyle.success, emoji="🟢", row=0)
            btn_green.callback = lambda i: self.shoot_with_technique(i, "green_precision")
            self.add_item(btn_green)

            btn_quick = discord.ui.Button(label="⚡ Quick Trigger", style=discord.ButtonStyle.primary, emoji="🟡", row=0)
            btn_quick.callback = lambda i: self.shoot_with_technique(i, "quick_trigger")
            self.add_item(btn_quick)

            btn_heat = discord.ui.Button(label="🔥 Deep Heat Check", style=discord.ButtonStyle.danger, emoji="🌟", row=0)
            btn_heat.callback = lambda i: self.shoot_with_technique(i, "deep_heatcheck")
            self.add_item(btn_heat)

    async def shoot_with_technique(self, interaction: discord.Interaction, technique: str):
        await interaction.response.defer()
        if interaction.user.id != self.author.id:
            return await interaction.followup.send("❌ This is not your shootout run!", ephemeral=True)

        cur_st = NBA_SHOOTOUT_STATIONS[self.current_station_idx]
        shots, pts, money, starry, new_streak, commentary = simulate_interactive_shootout_station(
            self.player, cur_st["type"], technique, self.current_streak
        )
        self.station_results.append({"name": cur_st["name"], "shots": shots, "pts": pts})
        self.total_score += pts
        self.current_streak = new_streak
        self.last_commentary = commentary
        self.current_station_idx += 1

        if self.current_station_idx >= len(NBA_SHOOTOUT_STATIONS):
            self.is_complete = True
            self.vc_won = int(self.total_score * 15)
            await db.add_user_vc(self.author.id, self.vc_won)
            self._build_controls()

        embed = build_shootout_embed(self.author, self.player, self.station_results, self.current_station_idx, self.total_score, self.is_complete, self.vc_won, self.last_commentary)
        await interaction.edit_original_response(embed=embed, view=self)


class NBAMinigamesCog(commands.Cog, name="NBA Minigames"):
    """3-Point Shootout contest, wild court card spawns, and interactive guessing."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── 3-Point Shootout ────────────────────────────────────────────────────────

    @app_commands.command(name="shootout", description="🎯 Enter the 3-Point Shootout contest to test your shooting timing for VC")
    @app_commands.guild_only()
    async def shootout_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        now = time.time()
        last = _SHOOTOUT_USER_COOLDOWNS.get(interaction.user.id, 0.0)
        cooldown = 120.0  # 2 minute cooldown
        if now - last < cooldown:
            rem = int(cooldown - (now - last))
            return await interaction.followup.send(f"⏳ Shootout is on cooldown! Come back in `{rem}s`.", ephemeral=True)

        _SHOOTOUT_USER_COOLDOWNS[interaction.user.id] = now
        shooter = await get_user_best_3pt_shooter(interaction.user.id)
        view = ThreePointShootoutView(interaction.user, shooter)
        embed = build_shootout_embed(interaction.user, shooter, view.station_results, 0, 0, False)
        await interaction.followup.send(embed=embed, view=view)

    @commands.command(name="shootout", aliases=["3pt", "contest", "3point"])
    @commands.guild_only()
    async def shootout_prefix(self, ctx: commands.Context):
        """Play the 3-Point Shootout: !shootout"""
        now = time.time()
        last = _SHOOTOUT_USER_COOLDOWNS.get(ctx.author.id, 0.0)
        cooldown = 120.0
        if now - last < cooldown:
            rem = int(cooldown - (now - last))
            return await ctx.send(f"⏳ Shootout is on cooldown! Come back in `{rem}s`.")

        _SHOOTOUT_USER_COOLDOWNS[ctx.author.id] = now
        shooter = await get_user_best_3pt_shooter(ctx.author.id)
        view = ThreePointShootoutView(ctx.author, shooter)
        embed = build_shootout_embed(ctx.author, shooter, view.station_results, 0, 0, False)
        await ctx.send(embed=embed, view=view)

    # ── Wild Card Spawn & Catch ────────────────────────────────────────────────

    @app_commands.command(name="nbahint", description="💡 Reveal an extra letter hint for the active wild card drop in this channel")
    @app_commands.guild_only()
    async def nbahint_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        active = _active_nba_drops.get(interaction.channel_id)
        if not active or active.get("claimed"):
            return await interaction.followup.send("ℹ️ No active wild card drop in this channel right now.", ephemeral=True)
        hint_lvl = active.get("hint_level", 1) + 1
        active["hint_level"] = hint_lvl
        hint_str = generate_player_hint(active["card"]["name"], hint_level=hint_lvl)
        await interaction.followup.send(f"💡 **Updated Card Hint (Level {hint_lvl}):** `{hint_str}`")

    @commands.command(name="nbahint", aliases=["hint", "cardhint"])
    @commands.guild_only()
    async def nbahint_prefix(self, ctx: commands.Context):
        """Reveal drop hint: !nbahint"""
        active = _active_nba_drops.get(ctx.channel.id)
        if not active or active.get("claimed"):
            return await ctx.send("ℹ️ No active wild card drop in this channel right now.")
        hint_lvl = active.get("hint_level", 1) + 1
        active["hint_level"] = hint_lvl
        hint_str = generate_player_hint(active["card"]["name"], hint_level=hint_lvl)
        await ctx.send(f"💡 **Updated Card Hint (Level {hint_lvl}):** `{hint_str}`")

    @app_commands.command(name="catch", description="🏀 Guess and claim the active wild NBA card in this channel")
    @app_commands.describe(player="Your guess for the active player's name")
    @app_commands.guild_only()
    async def catch_slash(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer()
        active = _active_nba_drops.get(interaction.channel_id)
        if not active or active.get("claimed"):
            return await interaction.followup.send("❌ No wild card is currently available to catch in this channel!", ephemeral=True)

        card = active["card"]
        if is_correct_player_name(player, card["name"]):
            active["claimed"] = True
            active["claimed_by_name"] = interaction.user.display_name
            await db.add_user_nba_card(interaction.user.id, card["id"], source="wild_catch")
            await db.add_user_vc(interaction.user.id, 150)
            new_bal = await db.get_user_vc(interaction.user.id)
            user_cards = await db.get_user_nba_cards(interaction.user.id)
            owned_count = sum(1 for c in user_cards if c.get("card_id", "").lower() == card["id"].lower())
            tier_info = NBA_2K_TIERS.get(card.get("tier", "gold"), NBA_2K_TIERS["gold"])

            embed = discord.Embed(
                title=f"🏀 {tier_info['emoji']} Card Caught by {interaction.user.display_name}!",
                description=(
                    f"🎉 {interaction.user.mention} guessed correctly and caught **[{card['ovr']} OVR] {card['name']}**!\n\n"
                    f"• ⚡ **Moment:** *{get_nba_card_moment(card)}*\n"
                    f"• 🏆 **Tier:** {tier_info['emoji']} **{tier_info['name']}** | `{card.get('pos', 'SG')}` ({card.get('team', 'NBA')})\n"
                    f"• 💰 **Reward:** `+150 VC` (Balance: `💰 {new_bal:,} VC`)\n"
                    f"• 🎴 **Collection:** You now own `{owned_count}` copies of this card!"
                ),
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Card ID: {card['id']} • View in binder: /nbadex")
            embed.timestamp = discord.utils.utcnow()
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ **Incorrect guess!** `{player}` is not the active player. Try again!", ephemeral=True)

    @commands.command(name="catch", aliases=["nbacatch", "claim", "nbaclaim"])
    @commands.guild_only()
    async def catch_prefix(self, ctx: commands.Context, *, player: str):
        """Guess and catch active card: !catch <player_name>"""
        active = _active_nba_drops.get(ctx.channel.id)
        if not active or active.get("claimed"):
            return await ctx.send("❌ No wild card is currently available to catch in this channel!")

        card = active["card"]
        if is_correct_player_name(player, card["name"]):
            active["claimed"] = True
            active["claimed_by_name"] = ctx.author.display_name
            await db.add_user_nba_card(ctx.author.id, card["id"], source="wild_catch")
            await db.add_user_vc(ctx.author.id, 150)
            new_bal = await db.get_user_vc(ctx.author.id)
            user_cards = await db.get_user_nba_cards(ctx.author.id)
            owned_count = sum(1 for c in user_cards if c.get("card_id", "").lower() == card["id"].lower())
            tier_info = NBA_2K_TIERS.get(card.get("tier", "gold"), NBA_2K_TIERS["gold"])

            embed = discord.Embed(
                title=f"🏀 {tier_info['emoji']} Card Caught by {ctx.author.display_name}!",
                description=(
                    f"🎉 {ctx.author.mention} caught **[{card['ovr']} OVR] {card['name']}**!\n\n"
                    f"• ⚡ **Moment:** *{get_nba_card_moment(card)}*\n"
                    f"• 🏆 **Tier:** {tier_info['emoji']} **{tier_info['name']}** | `{card.get('pos', 'SG')}`\n"
                    f"• 💰 **Reward:** `+150 VC` (Balance: `💰 {new_bal:,} VC`)\n"
                    f"• 🎴 **Collection:** You now own `{owned_count}` copies!"
                ),
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Card ID: {card['id']} • View in binder: !nbadex")
            embed.timestamp = discord.utils.utcnow()
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ `{player}` is incorrect! Keep guessing.")

    # ── Channel Setup ──────────────────────────────────────────────────────────

    @app_commands.command(name="setupnbachannel", description="📌 Configure a dedicated text channel for wild NBA card spawns")
    @app_commands.describe(channel="The channel to pin for NBA card drops")
    @app_commands.guild_only()
    async def setupnbachannel_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.guild_permissions.manage_guild and not is_creator(interaction.user):
            return await interaction.followup.send("🚫 You need Manage Server permission to configure drop channels.", ephemeral=True)
        await db.set_config(interaction.guild_id, "nba_drop_channel", str(channel.id))
        await interaction.followup.send(f"✅ Wild NBA 2K card spawns are now pinned to {channel.mention}!", ephemeral=True)

    @commands.command(name="setnbachannel", aliases=["setupnbachannel", "nbachannel"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setnbachannel_prefix(self, ctx: commands.Context, channel: discord.TextChannel):
        """Configure card drop channel: !setnbachannel #channel"""
        await db.set_config(ctx.guild.id, "nba_drop_channel", str(channel.id))
        await ctx.send(f"✅ Wild NBA 2K card spawns pinned to {channel.mention}!")


async def setup(bot: commands.Bot):
    await bot.add_cog(NBAMinigamesCog(bot))
