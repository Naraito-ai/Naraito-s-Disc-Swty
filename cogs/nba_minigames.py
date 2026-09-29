# -*- coding: utf-8 -*-
"""
cogs/nba_minigames.py - 3-Point Shootout Contest, Wild Card Chat Spawns, Hint & Catch Commands
Features instant UI component deferrals, modal entry, direct chat guessing, and non-blocking image generation.
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


# ── Shootout Helpers ──────────────────────────────────────────────────────────

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
        self.money_made = 0
        self.starry_made = 0
        self.current_streak = 0
        self.is_complete = False
        self.vc_won = 0
        self.last_commentary = ""
        self.message: Optional[discord.Message] = None
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
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("❌ This is not your shootout run!", ephemeral=True)

        cur_st = NBA_SHOOTOUT_STATIONS[self.current_station_idx]
        shots, pts, money, starry, new_streak, commentary = simulate_interactive_shootout_station(
            self.player, cur_st["type"], technique, self.current_streak
        )
        self.station_results.append({"name": cur_st["name"], "shots": shots, "pts": pts})
        self.total_score += pts
        self.money_made += money
        self.starry_made += starry
        self.current_streak = new_streak
        self.last_commentary = commentary
        self.current_station_idx += 1

        if self.current_station_idx >= len(NBA_SHOOTOUT_STATIONS):
            self.is_complete = True
            self.vc_won = int(self.total_score * 15)
            await db.add_user_vc(self.author.id, self.vc_won)
            await db.save_shootout_score(self.author.id, self.player["name"], self.total_score, self.money_made, self.starry_made)
            self._build_controls()

        embed = build_shootout_embed(self.author, self.player, self.station_results, self.current_station_idx, self.total_score, self.is_complete, self.vc_won, self.last_commentary)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


# ── Wild Card Embed & View Construction ────────────────────────────────────────

def build_nba_drop_embed(
    card: Dict[str, Any],
    hint_level: int = 1,
    spawner: Optional[Union[discord.Member, discord.User]] = None
) -> discord.Embed:
    """Builds the mystery card drop embed."""
    tier_info = NBA_2K_TIERS.get(card.get("tier", "gold"), NBA_2K_TIERS["gold"])
    hint_str = generate_player_hint(card["name"], hint_level=hint_level)
    host_line = f"\n• 👑 **Hosted By:** {spawner.mention} *(Host disqualified from catching)*" if spawner else ""
    footer_text = "NBA 2K Mobile Spawns • First to guess catches card + 150 VC! • Event host cannot claim" if spawner else "NBA 2K Mobile Spawns • First to guess catches the card + 150 VC!"

    embed = discord.Embed(
        title="🏀 A wild NBA 2K card appeared!" if not spawner else f"🏀 Special NBA Card Drop Hosted by {spawner.display_name}!",
        description=(
            f"**Guess the player name to catch this card!**\n\n"
            f"• **Type:** `/catch <name>` or `!catch <name>` or guess directly in chat\n"
            f"• **Tier:** {tier_info['emoji']} **{tier_info['name']}**\n"
            f"• **Position:** `{card.get('pos', 'SG')}` | **Team:** `{card.get('team', 'NBA')}`\n"
            f"• **Hint:** `{hint_str}`"
            f"{host_line}"
        ),
        color=discord.Color.from_rgb(*NBA_2K_CARD_THEMES.get(card.get("tier", "gold"), {}).get("primary", (255, 215, 0)))
    )
    embed.set_image(url="attachment://nba_card.png")
    embed.set_footer(text=footer_text)
    embed.timestamp = discord.utils.utcnow()
    return embed


def build_catch_success_embed(
    user: Union[discord.Member, discord.User],
    card: Dict[str, Any],
    new_bal: int,
    copies: int
) -> discord.Embed:
    """Builds the catch celebration embed."""
    tier_info = NBA_2K_TIERS.get(card.get("tier", "gold"), NBA_2K_TIERS["gold"])
    moment = get_nba_card_moment(card)
    embed = discord.Embed(
        title=f"🏀 {tier_info['emoji']} Card Caught by {user.display_name}!",
        description=(
            f"🎉 {user.mention} guessed correctly and caught **[{card['ovr']} OVR] {card['name']}**!\n\n"
            f"• ⚡ **Moment:** *{moment}*\n"
            f"• 🏆 **Tier:** {tier_info['emoji']} **{tier_info['name']}** | `{card.get('pos', 'SG')}` ({card.get('team', 'NBA')})\n"
            f"• 💰 **Reward:** `+150 VC` (Balance: `💰 {new_bal:,} VC`)\n"
            f"• 🎴 **Collection:** You now own `{copies}` copies of this card!"
        ),
        color=discord.Color.green()
    )
    embed.set_image(url="attachment://nba_card.png")
    embed.set_footer(text=f"Card ID: {card['id']} • View in binder: /nbadex")
    embed.timestamp = discord.utils.utcnow()
    return embed


class NBACatchModal(discord.ui.Modal, title="🏀 Catch the NBA 2K Player"):
    player_guess = discord.ui.TextInput(
        label="Player Full Name or Nickname",
        placeholder="e.g. Stephen Curry, Wemby, MJ, LeBron, Jrue Holiday...",
        required=True,
        min_length=2,
        max_length=60
    )

    def __init__(self, channel_id: int, drop_id: str, drop_msg: Optional[discord.Message] = None):
        super().__init__()
        self.channel_id = channel_id
        self.drop_id = drop_id
        self.drop_msg = drop_msg

    async def on_submit(self, interaction: discord.Interaction):
        # Step 1: Immediate deferral on Line 1 to prevent timeout
        await interaction.response.defer(ephemeral=False)
        guess = self.player_guess.value.strip()
        await handle_catch_attempt(interaction, guess, channel_id=self.channel_id, drop_msg=self.drop_msg)


class NBAChatDropView(discord.ui.View):
    def __init__(self, card: Dict[str, Any], drop_id: str, channel_id: int, drop_msg: Optional[discord.Message] = None):
        super().__init__(timeout=300.0)
        self.card = card
        self.drop_id = drop_id
        self.channel_id = channel_id
        self.drop_msg = drop_msg

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        # Clean up the in-memory drop entry
        _active_nba_drops.pop(self.channel_id, None)
        if self.drop_msg:
            try:
                await self.drop_msg.edit(content="⏰ This wild card drop has expired unclaimed.", view=self)
            except Exception:
                pass

    @discord.ui.button(label="🏀 Enter Player Name", style=discord.ButtonStyle.success, emoji="🏀", row=0)
    async def guess_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        drop = _active_nba_drops.get(interaction.channel_id) or _active_nba_drops.get(self.channel_id)
        if not drop or drop.get("claimed"):
            return await interaction.response.send_message("❌ This wild card has already been claimed or expired.", ephemeral=True)
        if drop.get("spawner_id") and interaction.user.id == drop.get("spawner_id"):
            return await interaction.response.send_message("❌ As the event host, you cannot catch your own drop!", ephemeral=True)
        # Opening modal is direct client-side response
        await interaction.response.send_modal(NBACatchModal(self.channel_id, self.drop_id, self.drop_msg))

    @discord.ui.button(label="💡 Get Hint", style=discord.ButtonStyle.secondary, emoji="💡", row=0)
    async def hint_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Step 1: Immediate deferral on Line 1
        await interaction.response.defer(ephemeral=True)
        drop = _active_nba_drops.get(interaction.channel_id) or _active_nba_drops.get(self.channel_id)
        if not drop or drop.get("claimed"):
            return await interaction.followup.send("❌ No active wild card drop in this channel.", ephemeral=True)

        hint_lvl = min(3, drop.get("hint_level", 1) + 1)
        drop["hint_level"] = hint_lvl
        hint_str = generate_player_hint(drop["card"]["name"], hint_level=hint_lvl)
        await interaction.followup.send(f"💡 **Player Name Hint (Level {hint_lvl}):** `{hint_str}`", ephemeral=True)


# ── Unified Catch Handler ──────────────────────────────────────────────────────

async def handle_catch_attempt(
    interaction_or_ctx_or_msg: Any,
    guess: str,
    channel_id: Optional[int] = None,
    drop: Optional[Dict[str, Any]] = None,
    drop_msg: Optional[discord.Message] = None
):
    """Unified handler for catch attempts across slash commands, prefix commands, modals, and direct chat typing."""
    try:
        is_interaction = isinstance(interaction_or_ctx_or_msg, discord.Interaction) or hasattr(interaction_or_ctx_or_msg, "response")
        is_ctx = isinstance(interaction_or_ctx_or_msg, commands.Context) or (hasattr(interaction_or_ctx_or_msg, "author") and hasattr(interaction_or_ctx_or_msg, "channel") and hasattr(interaction_or_ctx_or_msg, "send") and not is_interaction)
        is_msg = isinstance(interaction_or_ctx_or_msg, discord.Message) or (hasattr(interaction_or_ctx_or_msg, "author") and hasattr(interaction_or_ctx_or_msg, "content") and not is_ctx and not is_interaction)

        if is_interaction:
            user = interaction_or_ctx_or_msg.user
            c_id = channel_id or interaction_or_ctx_or_msg.channel_id
            g_id = interaction_or_ctx_or_msg.guild_id
        elif is_ctx:
            user = interaction_or_ctx_or_msg.author
            c_id = interaction_or_ctx_or_msg.channel.id
            g_id = interaction_or_ctx_or_msg.guild.id if interaction_or_ctx_or_msg.guild else None
        elif is_msg:
            user = interaction_or_ctx_or_msg.author
            c_id = interaction_or_ctx_or_msg.channel.id
            g_id = interaction_or_ctx_or_msg.guild.id if interaction_or_ctx_or_msg.guild else None
        else:
            return

        if not drop:
            drop = _active_nba_drops.get(c_id) or (_active_nba_drops.get(g_id) if g_id else None)

        async def _respond_ephemeral(text: str):
            if is_interaction:
                resp = getattr(interaction_or_ctx_or_msg, "response", None)
                done = False
                if resp:
                    is_done_attr = getattr(resp, "is_done", False)
                    done = is_done_attr() if callable(is_done_attr) else bool(is_done_attr)
                if done:
                    await interaction_or_ctx_or_msg.followup.send(text, ephemeral=True)
                else:
                    await interaction_or_ctx_or_msg.response.send_message(text, ephemeral=True)
            elif is_msg:
                await interaction_or_ctx_or_msg.reply(text, mention_author=True)
            elif is_ctx:
                await interaction_or_ctx_or_msg.send(text)

        if not drop:
            return await _respond_ephemeral("❌ There is no active wild NBA card drop in this channel right now. Keep chatting to spawn one!")

        # Check if spawner is attempting to claim their own manual drop
        if drop.get("spawner_id") and user.id == drop.get("spawner_id"):
            return await _respond_ephemeral("❌ **Host Disqualified:** You hosted this drop! Leave it for other members to catch.")

        # Check if already claimed
        if drop.get("claimed"):
            claimed_by = drop.get("claimed_by_name", "another player")
            return await _respond_ephemeral(f"❌ **Too slow!** This player was already caught by **{claimed_by}**! Wait for the next court spawn.")

        card = drop["card"]
        actual_name = card["name"]

        # Check if guess is correct
        if not is_correct_player_name(guess, actual_name):
            return await _respond_ephemeral(f"❌ **'{guess}' is incorrect!** Team: **{card.get('team', 'NBA')}**, Pos: **{card.get('pos', 'SG')}**, or use `/nbahint`!")

        # Defer interaction if valid guess and not already deferred
        if is_interaction:
            resp = getattr(interaction_or_ctx_or_msg, "response", None)
            done = False
            if resp:
                is_done_attr = getattr(resp, "is_done", False)
                done = is_done_attr() if callable(is_done_attr) else bool(is_done_attr)
            if not done:
                await interaction_or_ctx_or_msg.response.defer(ephemeral=False)

        # Mark claimed immediately to lock out race conditions
        drop["claimed"] = True
        drop["claimed_by_id"] = user.id
        drop["claimed_by_name"] = user.display_name

        # Persist rewards
        await db.add_user_nba_card(user.id, card["id"], source="wild_catch")
        await db.add_user_vc(user.id, 150)
        new_bal = await db.get_user_vc(user.id)
        user_cards = await db.get_user_nba_cards(user.id)
        copies = sum(1 for c in user_cards if c.get("card_id", "").lower() == card["id"].lower())

        # Generate revealed card image in a non-blocking background thread
        card_buf = await asyncio.to_thread(generate_nba_card_graphic, card, False)
        card_file = discord.File(fp=card_buf, filename="nba_card.png")
        embed = build_catch_success_embed(user, card, new_bal, copies)

        # Deliver success response
        if is_interaction:
            await interaction_or_ctx_or_msg.followup.send(embed=embed, file=card_file)
        elif is_msg:
            await interaction_or_ctx_or_msg.reply(embed=embed, file=card_file, mention_author=True)
        elif is_ctx:
            await interaction_or_ctx_or_msg.send(embed=embed, file=card_file)

        # Disable buttons on the original drop message
        target_msg = drop_msg or drop.get("message")
        if target_msg:
            try:
                disabled_view = discord.ui.View(timeout=1.0)
                btn = discord.ui.Button(label=f"✅ Caught by {user.display_name}!", style=discord.ButtonStyle.secondary, disabled=True, emoji="🏀")
                disabled_view.add_item(btn)
                await target_msg.edit(view=disabled_view)
            except Exception as edit_err:
                logger.debug(f"Could not edit drop message: {edit_err}")

    except Exception as e:
        logger.error(f"Error in handle_catch_attempt: {e}", exc_info=True)


async def spawn_nba_card_drop(
    channel: discord.TextChannel,
    spawner: Optional[Union[discord.Member, discord.User]] = None,
    interaction: Optional[discord.Interaction] = None,
    card_override: Optional[Dict[str, Any]] = None
) -> Optional[discord.Message]:
    """Spawns a mystery NBA card drop in the designated channel."""
    try:
        card = card_override or random.choice(NBA_2K_MOBILE_CARDS)
        now_ts = time.time()
        g_id = channel.guild.id if (hasattr(channel, "guild") and channel.guild) else 0
        drop_id = f"{g_id}_{channel.id}_{int(now_ts)}"

        drop_info = {
            "card": card,
            "drop_id": drop_id,
            "channel_id": channel.id,
            "guild_id": g_id,
            "spawned_at": now_ts,
            "hint_level": 1,
            "claimed": False,
            "claimed_by_id": None,
            "claimed_by_name": None,
            "spawner_id": spawner.id if spawner else None,
            "message": None
        }
        _active_nba_drops[channel.id] = drop_info
        if g_id:
            _active_nba_drops[g_id] = drop_info

        # Generate mystery card image in non-blocking thread
        card_buf = await asyncio.to_thread(generate_nba_card_graphic, card, True)
        card_file = discord.File(fp=card_buf, filename="nba_card.png")
        embed = build_nba_drop_embed(card, hint_level=1, spawner=spawner)
        view = NBAChatDropView(card, drop_id, channel.id)

        if interaction:
            drop_msg = await interaction.followup.send(embed=embed, file=card_file, view=view)
        else:
            drop_msg = await channel.send(embed=embed, file=card_file, view=view)

        if drop_msg:
            drop_info["message"] = drop_msg
            view.drop_msg = drop_msg

        return drop_msg
    except Exception as e:
        logger.error(f"Error spawning NBA card drop: {e}", exc_info=True)
        return None


# ── NBA Minigames Cog ──────────────────────────────────────────────────────────

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
        last = await db.get_user_shootout_cooldown(interaction.user.id)
        cooldown = 120.0  # 2 minute cooldown
        if now - last < cooldown:
            rem = int(cooldown - (now - last))
            return await interaction.followup.send(f"⏳ Shootout is on cooldown! Come back in `{rem}s`.", ephemeral=True)

        await db.set_user_shootout_cooldown(interaction.user.id, now)
        _SHOOTOUT_USER_COOLDOWNS[interaction.user.id] = now
        shooter = await get_user_best_3pt_shooter(interaction.user.id)
        view = ThreePointShootoutView(interaction.user, shooter)
        embed = build_shootout_embed(interaction.user, shooter, view.station_results, 0, 0, False)
        msg = await interaction.followup.send(embed=embed, view=view)
        view.message = msg

    @commands.command(name="shootout", aliases=["3pt", "contest", "3point"])
    @commands.guild_only()
    async def shootout_prefix(self, ctx: commands.Context):
        """Play the 3-Point Shootout: !shootout"""
        now = time.time()
        last = await db.get_user_shootout_cooldown(ctx.author.id)
        cooldown = 120.0
        if now - last < cooldown:
            rem = int(cooldown - (now - last))
            return await ctx.send(f"⏳ Shootout is on cooldown! Come back in `{rem}s`.")

        await db.set_user_shootout_cooldown(ctx.author.id, now)
        _SHOOTOUT_USER_COOLDOWNS[ctx.author.id] = now
        shooter = await get_user_best_3pt_shooter(ctx.author.id)
        view = ThreePointShootoutView(ctx.author, shooter)
        embed = build_shootout_embed(ctx.author, shooter, view.station_results, 0, 0, False)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    # ── Wild Card Spawn & Catch ────────────────────────────────────────────────

    @app_commands.command(name="nbahint", description="💡 Reveal an extra letter hint for the active wild card drop in this channel")
    @app_commands.guild_only()
    async def nbahint_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        active = _active_nba_drops.get(interaction.channel_id)
        if not active or active.get("claimed"):
            return await interaction.followup.send("ℹ️ No active wild card drop in this channel right now.", ephemeral=True)
        hint_lvl = min(3, active.get("hint_level", 1) + 1)
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
        hint_lvl = min(3, active.get("hint_level", 1) + 1)
        active["hint_level"] = hint_lvl
        hint_str = generate_player_hint(active["card"]["name"], hint_level=hint_lvl)
        await ctx.send(f"💡 **Updated Card Hint (Level {hint_lvl}):** `{hint_str}`")

    @app_commands.command(name="catch", description="🏀 Guess and claim the active wild NBA card in this channel")
    @app_commands.describe(player="Your guess for the active player's name")
    @app_commands.guild_only()
    async def catch_slash(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer()
        await handle_catch_attempt(interaction, player.strip(), channel_id=interaction.channel_id)

    @commands.command(name="catch", aliases=["nbacatch", "claim", "nbaclaim", "c"])
    @commands.guild_only()
    async def catch_prefix(self, ctx: commands.Context, *, player: Optional[str] = None):
        """Guess and catch active card: !catch <player_name>"""
        if not player:
            return await ctx.send("⚠️ **Usage:** `!catch <player_name>` (e.g. `!catch Stephen Curry` or `!catch Wemby`)")
        await handle_catch_attempt(ctx, player.strip(), channel_id=ctx.channel.id)

    # ── Channel Setup ──────────────────────────────────────────────────────────

    async def _handle_setnbachannel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.guild_permissions.manage_guild and not is_creator(interaction.user):
            return await interaction.followup.send("🚫 You need Manage Server permission to configure drop channels.", ephemeral=True)
        target_channel = channel or interaction.channel
        await db.set_config(interaction.guild_id, "nba_drop_channel", str(target_channel.id))
        await interaction.followup.send(f"✅ Wild NBA 2K card spawns are now pinned to {target_channel.mention}!", ephemeral=True)

    @app_commands.command(name="setupnbachannel", description="📌 Configure a dedicated text channel for wild NBA card spawns")
    @app_commands.describe(channel="The channel to pin for NBA card drops (defaults to current channel)")
    @app_commands.guild_only()
    async def setupnbachannel_slash(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await self._handle_setnbachannel(interaction, channel)

    @app_commands.command(name="setnbachannel", description="📌 Configure a dedicated text channel for wild NBA card spawns")
    @app_commands.describe(channel="The channel to pin for NBA card drops (defaults to current channel)")
    @app_commands.guild_only()
    async def setnbachannel_slash(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await self._handle_setnbachannel(interaction, channel)

    @commands.command(name="setnbachannel", aliases=["setupnbachannel", "nbachannel"])
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setnbachannel_prefix(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Configure card drop channel: !setnbachannel [#channel]"""
        target_channel = channel or ctx.channel
        await db.set_config(ctx.guild.id, "nba_drop_channel", str(target_channel.id))
        await ctx.send(f"✅ Wild NBA 2K card spawns pinned to {target_channel.mention}!")

    # ── Chat Message Listener for Direct Guessing & Drops ─────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handles direct chat guessing and automatic activity-based card drops."""
        if message.author.bot or not message.guild:
            return

        content = message.content.strip()

        # 1. Direct chat guessing
        if not content.startswith(("!", "/", "$", ".", "-", "~", ">", ";")):
            active = _active_nba_drops.get(message.channel.id)
            if active and not active.get("claimed"):
                if len(content) >= 2 and is_correct_player_name(content, active["card"]["name"]):
                    await handle_catch_attempt(message, content, channel_id=message.channel.id, drop=active)
                    return
            elif active and active.get("claimed") and (time.time() - active.get("spawned_at", 0) < 45):
                if len(content) >= 2 and is_correct_player_name(content, active["card"]["name"]):
                    claimed_by = active.get("claimed_by_name", "another player")
                    await message.reply(f"❌ **Too slow!** This player was already caught by **{claimed_by}**! Wait for the next wild court spawn.", mention_author=True)
                    return

        # 2. Activity-based random card drops
        c_id = message.channel.id
        _nba_drop_msg_counts[c_id] = _nba_drop_msg_counts.get(c_id, 0) + 1
        now = time.time()
        last_drop = _nba_drop_last_timestamps.get(c_id, 0.0)

        # Trigger every 30-50 messages, min 8-minute cooldown per channel
        if _nba_drop_msg_counts[c_id] >= random.randint(30, 50) and (now - last_drop >= 480):
            _nba_drop_msg_counts[c_id] = 0
            _nba_drop_last_timestamps[c_id] = now
            if is_valid_drop_channel(message.channel):
                await spawn_nba_card_drop(message.channel)


async def setup(bot: commands.Bot):
    await bot.add_cog(NBAMinigamesCog(bot))
