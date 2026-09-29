# -*- coding: utf-8 -*-
"""
cogs/nba_battle.py - Starting 5 Lineup Builder, Tactical Battles, Matchmaking Queue, Daily Boss, Stats & Leaderboards
"""
from __future__ import annotations

import io
import time
import json
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
    NBA_DREAM_PLAYERS,
    DAILY_BOSS_PRESETS,
    GM_RANKS,
    get_nba_card,
    get_gm_rank,
    card_to_player_dict,
    generate_dream_team_card,
    evaluate_dream_team,
    extract_picks_from_row,
    ensure_sweety_ai_team,
    is_creator
)

logger = logging.getLogger("SweetyBot.NBABattle")


# In-memory matchmaking queue: Dict[guild_id, Dict[user_id, timestamp]]
MATCHMAKING_QUEUE: Dict[int, Dict[int, float]] = {}


class BuildTeamView(discord.ui.View):
    def __init__(self, author_id: int, user_cards: Optional[List[Dict[str, Any]]] = None):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.user_cards = user_cards or []
        self.current_pos = "PG"
        self.picks: Dict[str, Dict[str, Any]] = {}
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    async def initialize(self):
        """Populates owned cards and existing active lineup from database."""
        if not self.user_cards:
            self.user_cards = await db.get_user_nba_cards(self.author_id)

        owned_cids = {c["card_id"].lower() for c in self.user_cards if isinstance(c, dict) and "card_id" in c}
        saved_row = await db.get_dream_team(self.author_id)
        if saved_row:
            saved_picks = extract_picks_from_row(saved_row)
            validated_picks = {}
            for pos, p in saved_picks.items():
                cid = p.get("card_id", "").lower() if isinstance(p, dict) else ""
                if cid and (cid in owned_cids or cid.replace("holo_", "") in owned_cids):
                    validated_picks[pos] = p
                else:
                    card_by_name = get_nba_card(p.get("name", "")) if isinstance(p, dict) else None
                    if card_by_name and (card_by_name["id"].lower() in owned_cids or card_by_name["id"].lower().replace("holo_", "") in owned_cids):
                        validated_picks[pos] = card_to_player_dict(card_by_name)
            self.picks = validated_picks
        self._update_components()

    def _get_eligible_cards_for_pos(self, pos: str) -> List[Dict[str, Any]]:
        """Finds all unique owned cards eligible for this position."""
        owned_cids = {c["card_id"].lower() for c in self.user_cards if isinstance(c, dict) and "card_id" in c}
        eligible = []
        seen = set()
        for cid in owned_cids:
            card = get_nba_card(cid)
            if card:
                canonical_id = card["id"].lower()
                if canonical_id in seen:
                    continue
                seen.add(canonical_id)
                p_pos = card.get("pos", "").upper()
                s_pos = (card.get("sec_pos") or "").upper()
                if pos == p_pos or pos == s_pos or pos in p_pos:
                    eligible.append(card)
        eligible.sort(key=lambda x: x.get("ovr", 80), reverse=True)
        return eligible

    def _update_components(self):
        self.clear_items()

        # Position Select Menu
        pos_options = []
        for p in ["PG", "SG", "SF", "PF", "C"]:
            chosen = self.picks.get(p)
            label = f"{p}: {chosen['name']} ({chosen['ovr']} OVR)" if chosen else f"{p}: [Empty Slot]"
            pos_options.append(discord.SelectOption(
                label=label[:100],
                value=p,
                default=(p == self.current_pos),
                emoji="🏀" if chosen else "⚪"
            ))

        pos_select = discord.ui.Select(
            placeholder="📍 Select Position to Fill/Edit",
            options=pos_options,
            row=0
        )
        pos_select.callback = self.on_position_select
        self.add_item(pos_select)

        # Player Select Menu for current position
        eligible = self._get_eligible_cards_for_pos(self.current_pos)
        player_options = []
        if not eligible:
            player_options.append(discord.SelectOption(
                label=f"No {self.current_pos} cards owned!",
                value="none",
                description="Open packs or catch drops to acquire cards"
            ))
        else:
            seen_values = set()
            found_default = False
            for c in eligible:
                val = c["id"]
                if val in seen_values:
                    continue
                seen_values.add(val)
                t_info = NBA_2K_TIERS.get(c.get("tier", "gold"), NBA_2K_TIERS["gold"])
                
                is_curr = False
                curr_pick = self.picks.get(self.current_pos, {})
                if not found_default and (curr_pick.get("card_id", "").lower() == val.lower() or (curr_pick.get("name") and curr_pick.get("name") == c.get("name"))):
                    is_curr = True
                    found_default = True

                player_options.append(discord.SelectOption(
                    label=f"[{c.get('ovr', 80)}] {c.get('name', 'Player')} ({c.get('team', 'NBA')})"[:100],
                    value=val,
                    description=f"{t_info.get('name', 'Gold')} • {c.get('theme', 'Base')}"[:100],
                    default=is_curr
                ))
                if len(player_options) >= 25:
                    break

        player_select = discord.ui.Select(
            placeholder=f"⭐ Choose {self.current_pos} Player",
            options=player_options,
            row=1,
            disabled=(len(eligible) == 0)
        )
        player_select.callback = self.on_player_select
        self.add_item(player_select)

        # Action Buttons
        save_btn = discord.ui.Button(label="Save Starting 5 💾", style=discord.ButtonStyle.success, row=2)
        save_btn.callback = self.on_save
        self.add_item(save_btn)

        auto_btn = discord.ui.Button(label="Auto-Fill Best ⚡", style=discord.ButtonStyle.primary, row=2)
        auto_btn.callback = self.on_auto_fill
        self.add_item(auto_btn)

        clear_btn = discord.ui.Button(label="Clear 🗑️", style=discord.ButtonStyle.danger, row=2)
        clear_btn.callback = self.on_clear
        self.add_item(clear_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This lineup builder session belongs to another GM.", ephemeral=True)
            return False
        return True

    async def on_position_select(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_pos = interaction.data["values"][0]
        self._update_components()
        embed = self.build_builder_embed(interaction.user)
        await interaction.edit_original_response(embed=embed, view=self)

    async def on_player_select(self, interaction: discord.Interaction):
        await interaction.response.defer()
        val = interaction.data["values"][0]
        if val != "none":
            card = get_nba_card(val)
            if card:
                self.picks[self.current_pos] = card_to_player_dict(card)
        self._update_components()
        embed = self.build_builder_embed(interaction.user)
        await interaction.edit_original_response(embed=embed, view=self)

    async def on_auto_fill(self, interaction: discord.Interaction):
        await interaction.response.defer()
        used_names = set()
        for pos in ["PG", "SG", "SF", "PF", "C"]:
            eligible = self._get_eligible_cards_for_pos(pos)
            chosen = None
            for card in eligible:
                c_name = card.get("name", "").strip().lower()
                if c_name not in used_names:
                    chosen = card
                    used_names.add(c_name)
                    break
            if not chosen and eligible:
                chosen = eligible[0]
            if chosen:
                self.picks[pos] = card_to_player_dict(chosen)
        self._update_components()
        embed = self.build_builder_embed(interaction.user)
        await interaction.edit_original_response(embed=embed, view=self)

    async def on_clear(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.picks.clear()
        self._update_components()
        embed = self.build_builder_embed(interaction.user)
        await interaction.edit_original_response(embed=embed, view=self)

    async def on_save(self, interaction: discord.Interaction):
        await interaction.response.defer()
        missing = [p for p in ["PG", "SG", "SF", "PF", "C"] if p not in self.picks]
        if missing:
            return await interaction.followup.send(f"⚠️ You must fill all 5 positions! Missing: `{', '.join(missing)}`", ephemeral=True)

        eval_res = evaluate_dream_team(self.picks)
        now = time.time()
        await db.save_dream_team(
            user_id=interaction.user.id,
            guild_id=interaction.guild.id if interaction.guild else None,
            pg=self.picks["PG"]["name"],
            sg=self.picks["SG"]["name"],
            sf=self.picks["SF"]["name"],
            pf=self.picks["PF"]["name"],
            c=self.picks["C"]["name"],
            total_cost=25,
            ovr_rating=eval_res["ovr"],
            team_data=json.dumps(self.picks),
            updated_at=now
        )
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)
        await interaction.followup.send(f"✅ **Starting 5 Lineup Saved!** Team OVR: `⭐ {eval_res['ovr']:.1f}`. Ready for `/teambattle`!")

    def build_builder_embed(self, user: Union[discord.User, discord.Member]) -> discord.Embed:
        eval_res = evaluate_dream_team(self.picks) if len(self.picks) == 5 else {"ovr": 0.0}
        embed = discord.Embed(
            title=f"🏀 NBA 2K Starting 5 Builder • {user.display_name}",
            description="Equip your highest-rated player cards to build an unbeatable 5-man roster!\n",
            color=discord.Color.gold()
        )
        for pos in ["PG", "SG", "SF", "PF", "C"]:
            p = self.picks.get(pos)
            if p:
                t_info = NBA_2K_TIERS.get(p.get("tier", "gold"), NBA_2K_TIERS["gold"])
                p_3pt = p.get("pts_3") or p.get("3pt") or p.get("inside", 80)
                p_def = p.get("defense") or p.get("def", 80)
                p_clu = p.get("clutch") or p.get("clu", 80)
                embed.add_field(
                    name=f"{pos}: {t_info['emoji']} [{p.get('ovr', 80)}] {p['name']}",
                    value=f"🎯 3PT: `{p_3pt}` • 🔒 DEF: `{p_def}` • ⚡ CLU: `{p_clu}`",
                    inline=False
                )
            else:
                embed.add_field(name=f"{pos}: [Empty Slot]", value="*Select a player below*", inline=False)

        if len(self.picks) == 5:
            embed.add_field(name="⭐ Starting 5 Rating", value=f"**`{eval_res['ovr']:.1f} OVR`** (Synergies Active!)", inline=False)
        embed.set_footer(text="Select slots to swap players • Click Save when ready")
        embed.timestamp = discord.utils.utcnow()
        return embed


class NBABattleCog(commands.Cog, name="NBA Battle"):
    """Starting 5 Lineup Builder, Tactical Battles, Matchmaking Queue, Daily Boss & Leaderboards."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Lineup Builder Commands ────────────────────────────────────────────────

    @app_commands.command(name="buildteam", description="📋 Build or customize your 5-man Starting Lineup for battles")
    @app_commands.guild_only()
    async def buildteam_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = BuildTeamView(interaction.user.id)
        await view.initialize()
        embed = view.build_builder_embed(interaction.user)
        msg = await interaction.followup.send(embed=embed, view=view)
        view.message = msg

    @commands.command(name="buildteam", aliases=["draftteam", "nbadraft", "lineup"])
    @commands.guild_only()
    async def buildteam_prefix(self, ctx: commands.Context):
        """Build your Starting 5: !buildteam"""
        view = BuildTeamView(ctx.author.id)
        await view.initialize()
        embed = view.build_builder_embed(ctx.author)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @app_commands.command(name="autoteam", description="⚡ Automatically equip your highest OVR cards into your Starting 5")
    @app_commands.guild_only()
    async def autoteam_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cards = await db.get_user_nba_cards(interaction.user.id)
        if not cards:
            return await interaction.followup.send("❌ You don't have any cards in your collection. Open packs with `/openpack` first!", ephemeral=True)

        picks: Dict[str, Dict[str, Any]] = {}
        owned_cids = {c["card_id"].lower() for c in cards}
        used_names = set()
        for pos in ["PG", "SG", "SF", "PF", "C"]:
            eligible = []
            seen = set()
            for cid in owned_cids:
                c_obj = get_nba_card(cid)
                if c_obj:
                    canon_id = c_obj["id"].lower()
                    if canon_id in seen:
                        continue
                    seen.add(canon_id)
                    p_pos = c_obj.get("pos", "").upper()
                    s_pos = (c_obj.get("sec_pos") or "").upper()
                    if pos == p_pos or pos == s_pos or pos in p_pos:
                        eligible.append(c_obj)
            eligible.sort(key=lambda x: x.get("ovr", 80), reverse=True)
            chosen = None
            for c_cand in eligible:
                cand_name = c_cand.get("name", "").strip().lower()
                if cand_name not in used_names:
                    chosen = c_cand
                    used_names.add(cand_name)
                    break
            if not chosen and eligible:
                chosen = eligible[0]
            if chosen:
                picks[pos] = card_to_player_dict(chosen)

        missing = [p for p in ["PG", "SG", "SF", "PF", "C"] if p not in picks]
        if missing:
            return await interaction.followup.send(f"⚠️ Could not auto-fill: You do not own cards for positions: `{', '.join(missing)}`.", ephemeral=True)

        eval_res = evaluate_dream_team(picks)
        now = time.time()
        await db.save_dream_team(
            user_id=interaction.user.id,
            guild_id=interaction.guild.id if interaction.guild else None,
            pg=picks["PG"]["name"],
            sg=picks["SG"]["name"],
            sf=picks["SF"]["name"],
            pf=picks["PF"]["name"],
            c=picks["C"]["name"],
            total_cost=25,
            ovr_rating=eval_res["ovr"],
            team_data=json.dumps(picks),
            updated_at=now
        )
        embed = discord.Embed(
            title="⚡ Starting 5 Lineup Auto-Optimized!",
            description=(
                f"Equipped your highest-rated cards for all 5 positions:\n\n"
                f"• **PG:** [{picks['PG']['ovr']}] {picks['PG']['name']}\n"
                f"• **SG:** [{picks['SG']['ovr']}] {picks['SG']['name']}\n"
                f"• **SF:** [{picks['SF']['ovr']}] {picks['SF']['name']}\n"
                f"• **PF:** [{picks['PF']['ovr']}] {picks['PF']['name']}\n"
                f"• **C:** [{picks['C']['ovr']}] {picks['C']['name']}\n\n"
                f"⭐ **Team Rating:** `⭐ {eval_res['ovr']:.1f} OVR`"
            ),
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)

    @commands.command(name="autoteam", aliases=["autolineup", "bestteam", "autoequip"])
    @commands.guild_only()
    async def autoteam_prefix(self, ctx: commands.Context):
        """Auto-fill best lineup: !autoteam"""
        cards = await db.get_user_nba_cards(ctx.author.id)
        if not cards:
            return await ctx.send("❌ You don't have any cards in your collection. Open packs with `!openpack` first!")

        picks: Dict[str, Dict[str, Any]] = {}
        owned_cids = {c["card_id"].lower() for c in cards}
        used_names = set()
        for pos in ["PG", "SG", "SF", "PF", "C"]:
            eligible = []
            seen = set()
            for cid in owned_cids:
                c_obj = get_nba_card(cid)
                if c_obj:
                    canon_id = c_obj["id"].lower()
                    if canon_id in seen:
                        continue
                    seen.add(canon_id)
                    p_pos = c_obj.get("pos", "").upper()
                    s_pos = (c_obj.get("sec_pos") or "").upper()
                    if pos == p_pos or pos == s_pos or pos in p_pos:
                        eligible.append(c_obj)
            eligible.sort(key=lambda x: x.get("ovr", 80), reverse=True)
            chosen = None
            for c_cand in eligible:
                cand_name = c_cand.get("name", "").strip().lower()
                if cand_name not in used_names:
                    chosen = c_cand
                    used_names.add(cand_name)
                    break
            if not chosen and eligible:
                chosen = eligible[0]
            if chosen:
                picks[pos] = card_to_player_dict(chosen)

        missing = [p for p in ["PG", "SG", "SF", "PF", "C"] if p not in picks]
        if missing:
            return await ctx.send(f"⚠️ Could not auto-fill: Missing cards for `{', '.join(missing)}`.")

        eval_res = evaluate_dream_team(picks)
        now = time.time()
        await db.save_dream_team(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id if ctx.guild else None,
            pg=picks["PG"]["name"],
            sg=picks["SG"]["name"],
            sf=picks["SF"]["name"],
            pf=picks["PF"]["name"],
            c=picks["C"]["name"],
            total_cost=25,
            ovr_rating=eval_res["ovr"],
            team_data=json.dumps(picks),
            updated_at=now
        )
        embed = discord.Embed(
            title="⚡ Starting 5 Lineup Auto-Optimized!",
            description=(
                f"Equipped your highest-rated cards for all 5 positions:\n\n"
                f"• **PG:** [{picks['PG']['ovr']}] {picks['PG']['name']}\n"
                f"• **SG:** [{picks['SG']['ovr']}] {picks['SG']['name']}\n"
                f"• **SF:** [{picks['SF']['ovr']}] {picks['SF']['name']}\n"
                f"• **PF:** [{picks['PF']['ovr']}] {picks['PF']['name']}\n"
                f"• **C:** [{picks['C']['ovr']}] {picks['C']['name']}\n\n"
                f"⭐ **Team Rating:** `⭐ {eval_res['ovr']:.1f} OVR`"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @app_commands.command(name="myteam", description="📊 View your (or another GM's) active Starting 5 lineup & synergies")
    @app_commands.describe(user="Member whose lineup to inspect (optional)")
    @app_commands.guild_only()
    async def myteam_slash(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer()
        target = user or interaction.user
        row = await db.get_dream_team(target.id)
        if not row:
            return await interaction.followup.send(f"❌ {target.display_name} has not built a Starting 5 yet. Use `/buildteam` or `/autoteam`!")

        picks = extract_picks_from_row(row)
        eval_res = evaluate_dream_team(picks)
        stats = await db.get_team_battle_stats(target.id)

        embed = discord.Embed(
            title=f"🏀 NBA 2K Starting 5 • {target.display_name}",
            description=f"⭐ **Overall Team Rating:** `⭐ {eval_res.get('ovr', 85):.1f} OVR`\n",
            color=discord.Color.gold()
        )
        for pos in ["PG", "SG", "SF", "PF", "C"]:
            p = picks.get(pos, {})
            if p:
                t_info = NBA_2K_TIERS.get(p.get("tier", "gold"), NBA_2K_TIERS["gold"])
                p_3pt = p.get("pts_3") or p.get("3pt") or p.get("ins", 80)
                p_def = p.get("defense") or p.get("def", 80)
                p_clu = p.get("clutch") or p.get("clu", 80)
                embed.add_field(
                    name=f"{pos}: {t_info['emoji']} [{p.get('ovr', 80)}] {p.get('name', 'Unknown')}",
                    value=f"🎯 3PT: `{p_3pt}` • 🔒 DEF: `{p_def}` • ⚡ CLU: `{p_clu}`",
                    inline=False
                )

        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        streak = stats.get("streak", stats.get("win_streak", 0))
        rank_info = get_gm_rank(wins)
        embed.add_field(
            name="🏆 GM Career Record",
            value=f"• **Record:** `{wins}W - {losses}L`\n• **Win Streak:** `{streak} wins`\n• **GM Tier:** {rank_info.get('title', 'Rookie GM')}",
            inline=False
        )
        embed.set_footer(text="Use /teambattle to challenge other GMs • /buildteam to edit")
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)

    @commands.command(name="myteam", aliases=["squad", "dreamteam"])
    @commands.guild_only()
    async def myteam_prefix(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        """View Starting 5: !myteam [@user]"""
        target_user = target or ctx.author
        row = await db.get_dream_team(target_user.id)
        if not row:
            return await ctx.send(f"❌ {target_user.display_name} has not built a Starting 5 yet. Run `!buildteam` or `!autoteam`!")

        picks = extract_picks_from_row(row)
        eval_res = evaluate_dream_team(picks)
        stats = await db.get_team_battle_stats(target_user.id)

        embed = discord.Embed(
            title=f"🏀 NBA 2K Starting 5 • {target_user.display_name}",
            description=f"⭐ **Overall Team Rating:** `⭐ {eval_res.get('ovr', 85):.1f} OVR`\n",
            color=discord.Color.gold()
        )
        for pos in ["PG", "SG", "SF", "PF", "C"]:
            p = picks.get(pos, {})
            if p:
                t_info = NBA_2K_TIERS.get(p.get("tier", "gold"), NBA_2K_TIERS["gold"])
                p_3pt = p.get("pts_3") or p.get("3pt") or p.get("ins", 80)
                p_def = p.get("defense") or p.get("def", 80)
                p_clu = p.get("clutch") or p.get("clu", 80)
                embed.add_field(
                    name=f"{pos}: {t_info['emoji']} [{p.get('ovr', 80)}] {p.get('name', 'Unknown')}",
                    value=f"🎯 3PT: `{p_3pt}` • 🔒 DEF: `{p_def}` • ⚡ CLU: `{p_clu}`",
                    inline=False
                )

        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        streak = stats.get("streak", stats.get("win_streak", 0))
        rank_info = get_gm_rank(wins)
        embed.add_field(
            name="🏆 GM Career Record",
            value=f"• **Record:** `{wins}W - {losses}L`\n• **Win Streak:** `{streak} wins`\n• **GM Tier:** {rank_info.get('title', 'Rookie GM')}",
            inline=False
        )
        embed.set_footer(text="Use !teambattle to play matches")
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)

    # ── Battle Engine ───────────────────────────────────────────────────────────

    @app_commands.command(name="teambattle", description="⚔️ Challenge Sweety AI or another server member to a 5v5 tactical NBA battle")
    @app_commands.describe(opponent="Opponent to challenge (leave empty to battle Sweety AI)")
    @app_commands.guild_only()
    async def teambattle_slash(self, interaction: discord.Interaction, opponent: Optional[discord.Member] = None):
        await interaction.response.defer()
        row_a = await db.get_dream_team(interaction.user.id)
        if not row_a:
            return await interaction.followup.send("❌ You don't have a Starting 5 lineup saved! Run `/buildteam` or `/autoteam` first.", ephemeral=True)

        target = opponent or interaction.guild.me
        if target.id == interaction.user.id:
            return await interaction.followup.send("❌ You cannot battle against yourself.", ephemeral=True)

        if target.bot:
            await ensure_sweety_ai_team(interaction.guild.id)

        row_b = await db.get_dream_team(target.id)
        if not row_b:
            return await interaction.followup.send(f"❌ {target.mention} does not have a Starting 5 lineup saved yet!", ephemeral=True)

        picks_a = extract_picks_from_row(row_a)
        picks_b = extract_picks_from_row(row_b)
        eval_a = evaluate_dream_team(picks_a)
        eval_b = evaluate_dream_team(picks_b)

        score_a = random.randint(88, 125) + int(eval_a.get("ovr", 85) - 85) * 2
        score_b = random.randint(88, 125) + int(eval_b.get("ovr", 85) - 85) * 2
        if score_a == score_b: score_a += 1

        winner = interaction.user if score_a > score_b else target
        reward_vc = 350
        if winner.id == interaction.user.id:
            await db.add_user_vc(interaction.user.id, reward_vc)
            await db.record_team_battle_result(interaction.user.id, won=True, is_ai=(target.bot))
            outcome_msg = f"🏆 **Victory!** You won `+350 VC`!"
        else:
            await db.record_team_battle_result(interaction.user.id, won=False, is_ai=(target.bot))
            outcome_msg = f"💔 **Defeat!** {winner.display_name} took the victory."

        embed = discord.Embed(
            title="⚔️ NBA 2K Full-Court Match Simulation",
            description=(
                f"🏟️ **Final Score:**\n"
                f"• {interaction.user.mention} (`⭐ {eval_a.get('ovr', 85):.1f} OVR`): **`{score_a} PTS`**\n"
                f"• {target.mention} (`⭐ {eval_b.get('ovr', 85):.1f} OVR`): **`{score_b} PTS`**\n\n"
                f"{outcome_msg}"
            ),
            color=discord.Color.green() if winner.id == interaction.user.id else discord.Color.red()
        )
        embed.set_footer(text="NBA 2K Tactical Battle Engine")
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)

    @commands.command(name="teambattle", aliases=["nbabattle", "battle", "vs"])
    @commands.guild_only()
    async def teambattle_prefix(self, ctx: commands.Context, opponent: Optional[discord.Member] = None):
        """Simulate a 5v5 battle: !teambattle [@user]"""
        row_a = await db.get_dream_team(ctx.author.id)
        if not row_a:
            return await ctx.send("❌ You don't have a Starting 5 lineup saved! Run `!buildteam` or `!autoteam` first.")

        target = opponent or ctx.guild.me
        if target.id == ctx.author.id:
            return await ctx.send("❌ You cannot battle against yourself.")

        if target.bot:
            await ensure_sweety_ai_team(ctx.guild.id)

        row_b = await db.get_dream_team(target.id)
        if not row_b:
            return await ctx.send(f"❌ {target.mention} does not have a Starting 5 lineup saved yet!")

        picks_a = extract_picks_from_row(row_a)
        picks_b = extract_picks_from_row(row_b)
        eval_a = evaluate_dream_team(picks_a)
        eval_b = evaluate_dream_team(picks_b)

        score_a = random.randint(88, 125) + int(eval_a.get("ovr", 85) - 85) * 2
        score_b = random.randint(88, 125) + int(eval_b.get("ovr", 85) - 85) * 2
        if score_a == score_b: score_a += 1

        winner = ctx.author if score_a > score_b else target
        if winner.id == ctx.author.id:
            await db.add_user_vc(ctx.author.id, 350)
            await db.record_team_battle_result(ctx.author.id, won=True, is_ai=(target.bot))
            outcome_msg = f"🏆 **Victory!** You earned `+350 VC`!"
        else:
            await db.record_team_battle_result(ctx.author.id, won=False, is_ai=(target.bot))
            outcome_msg = f"💔 **Defeat!** {winner.display_name} won."

        embed = discord.Embed(
            title="⚔️ NBA 2K Full-Court Match Simulation",
            description=(
                f"🏟️ **Final Score:**\n"
                f"• {ctx.author.mention} (`⭐ {eval_a.get('ovr', 85):.1f} OVR`): **`{score_a} PTS`**\n"
                f"• {target.mention} (`⭐ {eval_b.get('ovr', 85):.1f} OVR`): **`{score_b} PTS`**\n\n"
                f"{outcome_msg}"
            ),
            color=discord.Color.green() if winner.id == ctx.author.id else discord.Color.red()
        )
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)

    # ── Matchmaking Queue ───────────────────────────────────────────────────────

    @app_commands.command(name="teamqueue", description="🎮 Enter the matchmaking queue to find an opponent for a 5v5 battle")
    @app_commands.guild_only()
    async def teamqueue_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = interaction.guild_id
        if guild_id not in MATCHMAKING_QUEUE:
            MATCHMAKING_QUEUE[guild_id] = {}

        queue = MATCHMAKING_QUEUE[guild_id]
        now = time.time()

        # Clean stale entries (> 10 mins)
        for uid in list(queue.keys()):
            if now - queue[uid] > 600:
                del queue[uid]

        row_a = await db.get_dream_team(interaction.user.id)
        if not row_a:
            return await interaction.followup.send("❌ You need a Starting 5 lineup before entering matchmaking. Run `/buildteam` or `/autoteam`!", ephemeral=True)

        # Look for existing waiting opponent
        waiting_opponents = [uid for uid in queue if uid != interaction.user.id]
        if waiting_opponents:
            opp_id = waiting_opponents[0]
            del queue[opp_id]
            opp_member = interaction.guild.get_member(opp_id)
            if opp_member:
                row_b = await db.get_dream_team(opp_id)
                if row_b:
                    picks_a = extract_picks_from_row(row_a)
                    picks_b = extract_picks_from_row(row_b)
                    eval_a = evaluate_dream_team(picks_a)
                    eval_b = evaluate_dream_team(picks_b)

                    score_a = random.randint(88, 125) + int(eval_a.get("ovr", 85) - 85) * 2
                    score_b = random.randint(88, 125) + int(eval_b.get("ovr", 85) - 85) * 2
                    if score_a == score_b: score_a += 1

                    winner = interaction.user if score_a > score_b else opp_member
                    await db.add_user_vc(winner.id, 500)
                    await db.record_team_battle_result(interaction.user.id, won=(winner.id == interaction.user.id), is_ai=False)
                    await db.record_team_battle_result(opp_member.id, won=(winner.id == opp_member.id), is_ai=False)

                    embed = discord.Embed(
                        title="🎮 MATCHMAKING OPPONENT FOUND • 5v5 RESULT",
                        description=(
                            f"⚔️ **Matchup:** {interaction.user.mention} vs {opp_member.mention}\n\n"
                            f"🏟️ **Final Score:**\n"
                            f"• {interaction.user.display_name}: **`{score_a} PTS`** (`⭐ {eval_a.get('ovr', 85):.1f} OVR`)\n"
                            f"• {opp_member.display_name}: **`{score_b} PTS`** (`⭐ {eval_b.get('ovr', 85):.1f} OVR`)\n\n"
                            f"🏆 **Winner:** {winner.mention} (Earned `+500 VC`!)"
                        ),
                        color=discord.Color.gold()
                    )
                    return await interaction.followup.send(embed=embed)

        queue[interaction.user.id] = now
        embed = discord.Embed(
            title="🎮 Entered Matchmaking Queue",
            description=(
                f"**{interaction.user.display_name}** is waiting for an opponent!\n"
                f"Another member can run `/teamqueue` to immediately battle."
            ),
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)

    @commands.command(name="teamqueue", aliases=["matchmaking", "queue", "findmatch"])
    @commands.guild_only()
    async def teamqueue_prefix(self, ctx: commands.Context):
        """Enter battle queue: !teamqueue"""
        guild_id = ctx.guild.id
        if guild_id not in MATCHMAKING_QUEUE:
            MATCHMAKING_QUEUE[guild_id] = {}

        queue = MATCHMAKING_QUEUE[guild_id]
        now = time.time()
        for uid in list(queue.keys()):
            if now - queue[uid] > 600:
                del queue[uid]

        row_a = await db.get_dream_team(ctx.author.id)
        if not row_a:
            return await ctx.send("❌ You need a Starting 5 lineup before queueing. Run `!buildteam`!")

        waiting = [uid for uid in queue if uid != ctx.author.id]
        if waiting:
            opp_id = waiting[0]
            del queue[opp_id]
            opp_member = ctx.guild.get_member(opp_id)
            if opp_member:
                row_b = await db.get_dream_team(opp_id)
                if row_b:
                    picks_a = extract_picks_from_row(row_a)
                    picks_b = extract_picks_from_row(row_b)
                    eval_a = evaluate_dream_team(picks_a)
                    eval_b = evaluate_dream_team(picks_b)

                    score_a = random.randint(88, 125) + int(eval_a.get("ovr", 85) - 85) * 2
                    score_b = random.randint(88, 125) + int(eval_b.get("ovr", 85) - 85) * 2
                    if score_a == score_b: score_a += 1

                    winner = ctx.author if score_a > score_b else opp_member
                    await db.add_user_vc(winner.id, 500)
                    await db.record_team_battle_result(ctx.author.id, won=(winner.id == ctx.author.id), is_ai=False)
                    await db.record_team_battle_result(opp_member.id, won=(winner.id == opp_member.id), is_ai=False)

                    embed = discord.Embed(
                        title="🎮 MATCHMAKING OPPONENT FOUND • 5v5 RESULT",
                        description=(
                            f"⚔️ **Matchup:** {ctx.author.mention} vs {opp_member.mention}\n\n"
                            f"🏟️ **Final Score:**\n"
                            f"• {ctx.author.display_name}: **`{score_a} PTS`**\n"
                            f"• {opp_member.display_name}: **`{score_b} PTS`**\n\n"
                            f"🏆 **Winner:** {winner.mention} (Earned `+500 VC`!)"
                        ),
                        color=discord.Color.gold()
                    )
                    return await ctx.send(embed=embed)

        queue[ctx.author.id] = now
        await ctx.send(f"🎮 **{ctx.author.display_name}** entered the matchmaking queue! Another GM run `!teamqueue` to battle.")

    # ── Daily Boss Challenge ────────────────────────────────────────────────────

    @app_commands.command(name="dailynba", description="🏀 Face today's AI NBA Boss Starting 5 for VC rewards and win streaks")
    @app_commands.guild_only()
    async def dailynba_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        row = await db.get_dream_team(interaction.user.id)
        if not row:
            return await interaction.followup.send("❌ You don't have a Starting 5 lineup saved! Run `/buildteam` first.", ephemeral=True)

        boss_preset = random.choice(DAILY_BOSS_PRESETS)
        picks_user = extract_picks_from_row(row)
        eval_user = evaluate_dream_team(picks_user)

        boss_picks = boss_preset.get("lineup", {})
        eval_boss = evaluate_dream_team(boss_picks) if boss_picks else {"ovr": boss_preset.get("ovr", 92.0)}

        score_user = random.randint(88, 120) + int(eval_user.get("ovr", 85) - 85) * 2
        score_boss = random.randint(88, 120) + int(eval_boss.get("ovr", 85) - 85) * 2
        if score_user == score_boss: score_user += 1

        won = score_user > score_boss
        if won:
            reward_vc = 1200
            await db.add_user_vc(interaction.user.id, reward_vc)
            await db.record_team_battle_result(interaction.user.id, won=True, is_ai=True)
            outcome = f"🏆 **VICTORY OVER THE BOSS!** Earned `💰 +{reward_vc:,} VC`!"
            color = discord.Color.gold()
        else:
            await db.record_team_battle_result(interaction.user.id, won=False, is_ai=True)
            outcome = "💔 **DEFEAT!** The Daily Boss defended the court."
            color = discord.Color.red()

        embed = discord.Embed(
            title=f"👾 NBA 2K DAILY BOSS: {boss_preset.get('name', 'Boss Team')}",
            description=(
                f"*{boss_preset.get('description', 'A legendary challenge!')}*\n\n"
                f"🏟️ **Final Score:**\n"
                f"• {interaction.user.mention} (`⭐ {eval_user.get('ovr', 85):.1f} OVR`): **`{score_user} PTS`**\n"
                f"• 👾 **{boss_preset.get('name', 'Boss')}** (`⭐ {eval_boss.get('ovr', 92):.1f} OVR`): **`{score_boss} PTS`**\n\n"
                f"{outcome}"
            ),
            color=color
        )
        embed.set_footer(text="Daily Boss refreshes every 24 hours")
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)

    @commands.command(name="dailynba", aliases=["dailyboss", "dailygame"])
    @commands.guild_only()
    async def dailynba_prefix(self, ctx: commands.Context):
        """Play daily boss game: !dailynba"""
        row = await db.get_dream_team(ctx.author.id)
        if not row:
            return await ctx.send("❌ You don't have a Starting 5 saved! Run `!buildteam` first.")

        boss_preset = random.choice(DAILY_BOSS_PRESETS)
        picks_user = extract_picks_from_row(row)
        eval_user = evaluate_dream_team(picks_user)
        boss_picks = boss_preset.get("lineup", {})
        eval_boss = evaluate_dream_team(boss_picks) if boss_picks else {"ovr": boss_preset.get("ovr", 92.0)}

        score_user = random.randint(88, 120) + int(eval_user.get("ovr", 85) - 85) * 2
        score_boss = random.randint(88, 120) + int(eval_boss.get("ovr", 85) - 85) * 2
        if score_user == score_boss: score_user += 1

        won = score_user > score_boss
        if won:
            reward_vc = 1200
            await db.add_user_vc(ctx.author.id, reward_vc)
            await db.record_team_battle_result(ctx.author.id, won=True, is_ai=True)
            outcome = f"🏆 **VICTORY OVER THE BOSS!** Earned `💰 +{reward_vc:,} VC`!"
            color = discord.Color.gold()
        else:
            await db.record_team_battle_result(ctx.author.id, won=False, is_ai=True)
            outcome = "💔 **DEFEAT!** The Daily Boss defended the court."
            color = discord.Color.red()

        embed = discord.Embed(
            title=f"👾 NBA 2K DAILY BOSS: {boss_preset.get('name', 'Boss Team')}",
            description=(
                f"*{boss_preset.get('description', 'A legendary challenge!')}*\n\n"
                f"🏟️ **Final Score:**\n"
                f"• {ctx.author.mention} (`⭐ {eval_user.get('ovr', 85):.1f} OVR`): **`{score_user} PTS`**\n"
                f"• 👾 **{boss_preset.get('name', 'Boss')}** (`⭐ {eval_boss.get('ovr', 92):.1f} OVR`): **`{score_boss} PTS`**\n\n"
                f"{outcome}"
            ),
            color=color
        )
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)

    # ── GM Stats & Career Ladder ────────────────────────────────────────────────

    @app_commands.command(name="teamstats", description="📊 View your General Manager career battle record, streak & GM tier")
    @app_commands.describe(user="Member to inspect (optional)")
    @app_commands.guild_only()
    async def teamstats_slash(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer()
        target = user or interaction.user
        stats = await db.get_team_battle_stats(target.id)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        total = wins + losses
        win_rate = (wins / total * 100.0) if total > 0 else 0.0
        streak = stats.get("streak", stats.get("win_streak", 0))
        rank_info = get_gm_rank(wins)

        embed = discord.Embed(
            title=f"🏆 NBA General Manager Profile • {target.display_name}",
            description=(
                f"• **GM Tier:** {rank_info.get('emoji', '🥉')} **{rank_info.get('title', 'Rookie GM')}**\n"
                f"• **Career Record:** `{wins}W - {losses}L` (`{win_rate:.1f}% Win Rate`)\n"
                f"• **Current Win Streak:** `🔥 {streak} in a row`\n"
                f"• **Next Promotion:** `{max(0, rank_info.get('next_req', 10) - wins)} wins needed`"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Play matches with /teambattle or /dailynba to rank up!")
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)

    @commands.command(name="teamstats", aliases=["gmstats", "mycareer", "nba_stats"])
    @commands.guild_only()
    async def teamstats_prefix(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        """View GM stats: !teamstats [@user]"""
        target_user = target or ctx.author
        stats = await db.get_team_battle_stats(target_user.id)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        total = wins + losses
        win_rate = (wins / total * 100.0) if total > 0 else 0.0
        streak = stats.get("streak", stats.get("win_streak", 0))
        rank_info = get_gm_rank(wins)

        embed = discord.Embed(
            title=f"🏆 NBA General Manager Profile • {target_user.display_name}",
            description=(
                f"• **GM Tier:** {rank_info.get('emoji', '🥉')} **{rank_info.get('title', 'Rookie GM')}**\n"
                f"• **Career Record:** `{wins}W - {losses}L` (`{win_rate:.1f}% Win Rate`)\n"
                f"• **Current Win Streak:** `🔥 {streak} in a row`\n"
                f"• **Next Promotion:** `{max(0, rank_info.get('next_req', 10) - wins)} wins needed`"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)

    # ── Leaderboards & Admin ────────────────────────────────────────────────────

    @app_commands.command(name="nbatop", description="🏆 View the top NBA card collectors and battle leaderboard")
    @app_commands.guild_only()
    async def nbatop_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        top_collectors = await db.get_nba_top_collectors(limit=10)
        embed = discord.Embed(
            title="🏆 NBA 2K Mobile • Top Card Collectors Leaderboard",
            description=f"The greatest card collectors across the server ({len(NBA_2K_MOBILE_CARDS)} cards in catalog)!\n",
            color=discord.Color.gold()
        )
        medals = ["🥇", "🥈", "🥉", "#4", "#5", "#6", "#7", "#8", "#9", "#10"]
        for i, row in enumerate(top_collectors):
            uid = int(row["user_id"])
            total_cards = int(row.get("total_cards", 0))
            unique_cards = int(row.get("unique_cards", 0))
            member = interaction.guild.get_member(uid)
            uname = member.display_name if member else f"<@{uid}>"
            medal = medals[i] if i < len(medals) else f"#{i+1}"
            embed.add_field(
                name=f"{medal} {uname}",
                value=f"🎴 **`{total_cards:,}` Cards** (`{unique_cards}/{len(NBA_2K_MOBILE_CARDS)}` unique)",
                inline=False
            )
        embed.set_footer(text="Use /nbadex to view your personal card collection")
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)

    @commands.command(name="nbatop", aliases=["nbaleaderboard", "topcards", "nbalb", "gmtop", "teamtop", "teamleaderboard"])
    @commands.guild_only()
    async def nbatop_prefix(self, ctx: commands.Context):
        """View card collectors leaderboard: !nbatop"""
        top_collectors = await db.get_nba_top_collectors(limit=10)
        embed = discord.Embed(
            title="🏆 NBA 2K Mobile • Top Card Collectors Leaderboard",
            description=f"The greatest card collectors on the server ({len(NBA_2K_MOBILE_CARDS)} cards in catalog)!\n",
            color=discord.Color.gold()
        )
        medals = ["🥇", "🥈", "🥉", "#4", "#5", "#6", "#7", "#8", "#9", "#10"]
        for i, row in enumerate(top_collectors):
            uid = int(row["user_id"])
            total_cards = int(row.get("total_cards", 0))
            unique_cards = int(row.get("unique_cards", 0))
            member = ctx.guild.get_member(uid)
            uname = member.display_name if member else f"<@{uid}>"
            medal = medals[i] if i < len(medals) else f"#{i+1}"
            embed.add_field(
                name=f"{medal} {uname}",
                value=f"🎴 **`{total_cards:,}` Cards** (`{unique_cards}/{len(NBA_2K_MOBILE_CARDS)}` unique)",
                inline=False
            )
        embed.set_footer(text="Use !nbadex to view your collection")
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)

    @app_commands.command(name="resetalllineups", description="👑 Reset all member starting lineups (Bot Creator Only)")
    @app_commands.guild_only()
    async def resetalllineups_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not is_creator(interaction.user):
            return await interaction.followup.send("❌ This command is strictly restricted to the Bot Creator.", ephemeral=True)
        await db.reset_all_dream_teams()
        await interaction.followup.send("👑 **All starting lineups have been cleanly reset.**", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(NBABattleCog(bot))
