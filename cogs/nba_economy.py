# -*- coding: utf-8 -*-
"""
cogs/nba_economy.py - VC Balance, Pack Opening, Selling, Trading, Gifting, Wager Battles & Daily/Weekly/Monthly Rewards
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
    NBA_LEGACY_CARD_MAPPINGS,
    NBA_PACK_TYPES,
    NBA_2K_MOBILE_CARDS,
    NBA_CARDS_BY_ID,
    get_nba_card,
    get_nba_card_moment,
    generate_nba_card_graphic,
    get_nba_player_moment_photo,
    roll_pack_card,
    build_openpack_embed,
    _build_odds_lines,
    build_pack_shop_embed,
    evaluate_dream_team,
    extract_picks_from_row,
    ensure_sweety_ai_team,
    is_creator
)

logger = logging.getLogger("SweetyBot.NBAEconomy")


def build_multi_trade_embed(
    user_a: Union[discord.Member, discord.User],
    user_b: Union[discord.Member, discord.User],
    cards_a: List[Dict[str, Any]],
    cards_b: List[Dict[str, Any]],
    status: str = "pending",
    vc_a: int = 0,
    vc_b: int = 0
) -> discord.Embed:
    """Builds an interactive 2-sided trade panel embed for cards and VC."""
    color = discord.Color.gold() if status == "pending" else (discord.Color.green() if status == "completed" else discord.Color.red())
    status_icon = "⏳ **Trade Offer Pending**" if status == "pending" else ("✅ **Trade Accepted & Transferred!**" if status == "completed" else "❌ **Trade Cancelled / Rejected**")

    embed = discord.Embed(
        title="🤝 NBA 2K Mobile • Player Card & VC Trade",
        description=f"{status_icon}\n*Review the proposed trade terms below:*",
        color=color
    )

    # Side A (Proposer)
    desc_a = ""
    if vc_a > 0:
        desc_a += f"💰 **`{vc_a:,} VC`**\n"
    if cards_a:
        for c in cards_a:
            t_info = NBA_2K_TIERS.get(c.get("tier", "gold"), NBA_2K_TIERS["gold"])
            is_h = bool(c.get("is_holo") or str(c.get("id", "")).startswith("holo_"))
            htag = " *(Holo)*" if is_h else ""
            desc_a += f"• {t_info['emoji']} **[{c['ovr']} OVR] {c['name']}**{htag} (`{c['id']}`)\n"
    if not desc_a:
        desc_a = "*No cards or VC offered*"
    embed.add_field(name=f"📤 {user_a.display_name} Offers:", value=desc_a, inline=True)

    # Side B (Target)
    desc_b = ""
    if vc_b > 0:
        desc_b += f"💰 **`{vc_b:,} VC`**\n"
    if cards_b:
        for c in cards_b:
            t_info = NBA_2K_TIERS.get(c.get("tier", "gold"), NBA_2K_TIERS["gold"])
            is_h = bool(c.get("is_holo") or str(c.get("id", "")).startswith("holo_"))
            htag = " *(Holo)*" if is_h else ""
            desc_b += f"• {t_info['emoji']} **[{c['ovr']} OVR] {c['name']}**{htag} (`{c['id']}`)\n"
    if not desc_b:
        desc_b = "*No cards or VC requested*"
    embed.add_field(name=f"📥 {user_b.display_name} Offers:", value=desc_b, inline=True)

    embed.set_footer(text="NBA 2K Trade Protocol • Both members must click Accept to finalize.")
    embed.timestamp = discord.utils.utcnow()
    return embed


class NBACardTradeView(discord.ui.View):
    def __init__(
        self,
        author: Union[discord.Member, discord.User],
        target: Union[discord.Member, discord.User],
        cards_a: List[Dict[str, Any]],
        cards_b: List[Dict[str, Any]],
        vc_a: int = 0,
        vc_b: int = 0
    ):
        super().__init__(timeout=120.0)
        self.author = author
        self.target = target
        self.cards_a = cards_a
        self.cards_b = cards_b
        self.vc_a = vc_a
        self.vc_b = vc_b
        self.accepted_by = set()
        self.finished = False
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        if not self.finished:
            for item in self.children:
                item.disabled = True
            if self.message:
                try:
                    await self.message.edit(content="⏰ Trade offer expired (no response in 2 minutes).", view=self)
                except Exception:
                    pass

    @discord.ui.button(label="Accept Trade ✅", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if interaction.user.id not in (self.author.id, self.target.id):
            return await interaction.followup.send("❌ You are not part of this trade.", ephemeral=True)
        if self.finished:
            return

        self.accepted_by.add(interaction.user.id)
        if self.author.id in self.accepted_by and self.target.id in self.accepted_by:
            self.finished = True
            card_a_id = self.cards_a[0]["id"] if self.cards_a else None
            card_b_id = self.cards_b[0]["id"] if self.cards_b else None

            success, msg = await db.execute_card_trade(
                self.author.id, self.target.id,
                card_a_id=card_a_id, card_b_id=card_b_id,
                vc_a=self.vc_a, vc_b=self.vc_b
            )

            if success:
                embed = build_multi_trade_embed(self.author, self.target, self.cards_a, self.cards_b, status="completed", vc_a=self.vc_a, vc_b=self.vc_b)
                for item in self.children:
                    item.disabled = True
                await interaction.edit_original_response(embed=embed, view=self)
                await interaction.followup.send(f"🎉 **Trade Successful!** Both parties have received their items.")
            else:
                for item in self.children:
                    item.disabled = True
                await interaction.edit_original_response(view=self)
                await interaction.followup.send(f"❌ **Trade Failed:** {msg}")
        else:
            await interaction.followup.send(f"✅ {interaction.user.mention} accepted the trade! Waiting for the other party...")

    @discord.ui.button(label="Cancel / Decline ❌", style=discord.ButtonStyle.danger)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if interaction.user.id not in (self.author.id, self.target.id):
            return await interaction.followup.send("❌ You are not part of this trade.", ephemeral=True)
        self.finished = True
        for item in self.children:
            item.disabled = True
        embed = build_multi_trade_embed(self.author, self.target, self.cards_a, self.cards_b, status="cancelled", vc_a=self.vc_a, vc_b=self.vc_b)
        await interaction.edit_original_response(embed=embed, view=self)
        await interaction.followup.send(f"❌ Trade cancelled by {interaction.user.mention}.")


class NBAPackOpenView(discord.ui.View):
    def __init__(self, user: Union[discord.User, discord.Member], pack_id: str, card: Dict[str, Any], new_bal: int, is_new: bool, copies: int):
        super().__init__(timeout=120.0)
        self.user = user
        self.pack_id = pack_id
        self.card = card
        self.new_bal = new_bal
        self.is_new = is_new
        self.copies = copies
        self.message: Optional[discord.Message] = None

        pack_data = NBA_PACK_TYPES.get(pack_id, NBA_PACK_TYPES["starter"])
        self.open_another_btn = discord.ui.Button(
            label=f"Open Another ({pack_data['cost']:,} VC)",
            style=discord.ButtonStyle.success,
            emoji="📦",
            row=0
        )
        self.open_another_btn.callback = self.open_another
        self.add_item(self.open_another_btn)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ This pack opening session belongs to someone else.", ephemeral=True)
            return False
        return True

    async def open_another(self, interaction: discord.Interaction):
        await interaction.response.defer()
        pack_data = NBA_PACK_TYPES.get(self.pack_id, NBA_PACK_TYPES["starter"])
        cost = pack_data["cost"]
        bal = await db.get_user_vc(interaction.user.id)
        if bal < cost:
            return await interaction.followup.send(
                f"❌ **Insufficient VC!** You need `💰 {cost:,} VC`, but currently have `💰 {bal:,} VC`.\n"
                f"Claim daily VC with `/nbadaily` or quick-sell duplicates with `/nbasell`.",
                ephemeral=True
            )

        deducted = await db.deduct_user_vc(interaction.user.id, cost)
        if not deducted:
            return await interaction.followup.send("❌ Failed to process VC transaction.", ephemeral=True)

        card = roll_pack_card(self.pack_id, interaction.user.id)
        existing_cards = await db.get_user_nba_cards(interaction.user.id)
        existing_cids = [c["card_id"].lower() for c in existing_cards]
        is_new = card["id"].lower() not in existing_cids
        copies_now = existing_cids.count(card["id"].lower()) + 1

        await db.add_user_nba_card(interaction.user.id, card["id"], source=f"pack_{self.pack_id}")
        new_bal = await db.get_user_vc(interaction.user.id)

        self.card = card
        self.new_bal = new_bal
        self.is_new = is_new
        self.copies = copies_now

        embed = build_openpack_embed(interaction.user, pack_data, card, new_bal, is_new=is_new, copies=copies_now)
        new_view = NBAPackOpenView(interaction.user, self.pack_id, card, new_bal, is_new, copies_now)
        try:
            card_buf = await asyncio.to_thread(generate_nba_card_graphic, card, is_mystery=False)
            card_file = discord.File(fp=card_buf, filename="nba_card.png")
            await interaction.followup.send(embed=embed, file=card_file, view=new_view)
        except Exception:
            await interaction.followup.send(embed=embed, view=new_view)


class VCBetChallengeView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, bet_amount: int):
        super().__init__(timeout=90.0)
        self.challenger = challenger
        self.opponent = opponent
        self.bet_amount = bet_amount
        self.resolved = False
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        if not self.resolved:
            self.resolved = True
            for item in self.children:
                item.disabled = True
            if self.message:
                try:
                    await self.message.edit(content="⏰ Wager challenge expired — no response in 90 seconds.", view=self)
                except Exception:
                    pass

    @discord.ui.button(label="Accept Wager ⚔️", style=discord.ButtonStyle.success)
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if interaction.user.id != self.opponent.id:
            return await interaction.followup.send("❌ Only the challenged opponent can accept this wager.", ephemeral=True)
        if self.resolved:
            return
        self.resolved = True

        # Check balances
        bal_a = await db.get_user_vc(self.challenger.id)
        bal_b = await db.get_user_vc(self.opponent.id)
        if bal_a < self.bet_amount:
            return await interaction.followup.send(f"❌ {self.challenger.mention} no longer has enough VC (`{self.bet_amount:,} VC`)!")
        if bal_b < self.bet_amount:
            return await interaction.followup.send(f"❌ {self.opponent.mention} no longer has enough VC (`{self.bet_amount:,} VC`)!")

        # Deduct from both
        ded_a = await db.deduct_user_vc(self.challenger.id, self.bet_amount)
        ded_b = await db.deduct_user_vc(self.opponent.id, self.bet_amount)
        if not ded_a or not ded_b:
            if ded_a: await db.add_user_vc(self.challenger.id, self.bet_amount)
            if ded_b: await db.add_user_vc(self.opponent.id, self.bet_amount)
            return await interaction.followup.send("❌ Transaction failed. Wager cancelled.")

        # Simulate 5v5 battle
        row_a = await db.get_dream_team(self.challenger.id)
        row_b = await db.get_dream_team(self.opponent.id)
        picks_a = extract_picks_from_row(row_a) if row_a else {}
        picks_b = extract_picks_from_row(row_b) if row_b else {}
        eval_a = evaluate_dream_team(picks_a) if picks_a else {"ovr": 80.0}
        eval_b = evaluate_dream_team(picks_b) if picks_b else {"ovr": 80.0}

        score_a = random.randint(85, 120) + int(eval_a.get("ovr", 80) - 80) * 2
        score_b = random.randint(85, 120) + int(eval_b.get("ovr", 80) - 80) * 2
        if score_a == score_b: score_a += 1

        total_pot = self.bet_amount * 2
        if score_a > score_b:
            winner = self.challenger
            loser = self.opponent
            win_score, lose_score = score_a, score_b
        else:
            winner = self.opponent
            loser = self.challenger
            win_score, lose_score = score_b, score_a

        await db.add_user_vc(winner.id, total_pot)
        await db.record_team_battle_result(winner.id, won=True, is_ai=False)
        await db.record_team_battle_result(loser.id, won=False, is_ai=False)

        for child in self.children:
            child.disabled = True

        embed = discord.Embed(
            title="💰 VC WAGER MATCH CONCLUDED!",
            description=(
                f"🏆 **Winner:** {winner.mention} (`{win_score} PTS`)\n"
                f"💔 **Defeated:** {loser.mention} (`{lose_score} PTS`)\n\n"
                f"💰 **Total Pot Won:** `+{total_pot:,} VC`!\n"
                f"*(Wager: `{self.bet_amount:,} VC` per player)*"
            ),
            color=discord.Color.gold()
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Decline ❌", style=discord.ButtonStyle.danger)
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if interaction.user.id not in (self.challenger.id, self.opponent.id):
            return await interaction.followup.send("❌ You are not part of this wager.", ephemeral=True)
        self.resolved = True
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(content=f"❌ Wager challenge was declined by {interaction.user.mention}.", view=self)


class NBAEconomyCog(commands.Cog, name="NBA Economy"):
    """VC balance, pack opening, card selling, trading, gifting, and daily rewards."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── VC Balance ──────────────────────────────────────────────────────────────

    @app_commands.command(name="nbabal", description="💰 View your NBA 2K Virtual Currency (VC) balance & binder value")
    @app_commands.describe(user="View another member's VC balance (optional)")
    @app_commands.guild_only()
    async def nbabal_slash(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        await interaction.response.defer()
        target = user or interaction.user
        vc = await db.get_user_vc(target.id)
        cards = await db.get_user_nba_cards(target.id)
        binder_val = 0
        for c in cards:
            c_obj = get_nba_card(c.get("card_id", ""))
            if c_obj:
                tier_info = NBA_2K_TIERS.get(c_obj.get("tier", "gold"), NBA_2K_TIERS["gold"])
                binder_val += tier_info.get("quick_sell", 100)

        embed = discord.Embed(
            title=f"💰 NBA 2K Economy • {target.display_name}",
            description=(
                f"• 💵 **Liquid VC Balance:** `💰 {vc:,} VC`\n"
                f"• 🎴 **Binder Valuation:** `💰 {binder_val:,} VC` ({len(cards):,} cards)\n"
                f"• 💎 **Total Net Worth:** `💰 {vc + binder_val:,} VC`\n\n"
                f"💡 *Earn more VC by winning `/nbabattle`, opening `/nbadaily`, or selling duplicates with `/nbasell`.*"
            ),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="NBA 2K Mobile Virtual Currency System")
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)

    @commands.command(name="nbabal", aliases=["bal", "vc", "balance", "nbabalance"])
    @commands.guild_only()
    async def nbabal_prefix(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        """View your VC balance and binder valuation: !nbabal [@user]"""
        target_user = target or ctx.author
        vc = await db.get_user_vc(target_user.id)
        cards = await db.get_user_nba_cards(target_user.id)
        binder_val = 0
        for c in cards:
            c_obj = get_nba_card(c.get("card_id", ""))
            if c_obj:
                tier_info = NBA_2K_TIERS.get(c_obj.get("tier", "gold"), NBA_2K_TIERS["gold"])
                binder_val += tier_info.get("quick_sell", 100)

        embed = discord.Embed(
            title=f"💰 NBA 2K Economy • {target_user.display_name}",
            description=(
                f"• 💵 **Liquid VC Balance:** `💰 {vc:,} VC`\n"
                f"• 🎴 **Binder Valuation:** `💰 {binder_val:,} VC` ({len(cards):,} cards)\n"
                f"• 💎 **Total Net Worth:** `💰 {vc + binder_val:,} VC`\n\n"
                f"💡 *Earn more VC with `!nbadaily`, `!nbabattle`, or `!nbasell`.*"
            ),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.set_footer(text="NBA 2K Mobile Virtual Currency System")
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)

    # ── Pack Opening ────────────────────────────────────────────────────────────

    @app_commands.command(name="openpack", description="📦 Open an authentic NBA 2K Mobile card pack")
    @app_commands.describe(pack_type="Select pack tier to open")
    @app_commands.choices(pack_type=[
        app_commands.Choice(name="Starter Pack (250 VC)", value="starter"),
        app_commands.Choice(name="Standard Pro Pack (750 VC)", value="standard"),
        app_commands.Choice(name="All-Star Gold Pack (1,500 VC)", value="allstar"),
        app_commands.Choice(name="Hall of Fame Elite Pack (3,000 VC)", value="hof"),
        app_commands.Choice(name="G.O.A.T. Dynasty Pack (5,000 VC)", value="goat"),
    ])
    @app_commands.guild_only()
    async def openpack_slash(self, interaction: discord.Interaction, pack_type: Optional[str] = "starter"):
        await interaction.response.defer()
        pack_id = (pack_type or "starter").lower().strip()
        pack_data = NBA_PACK_TYPES.get(pack_id, NBA_PACK_TYPES["starter"])
        cost = pack_data["cost"]
        bal = await db.get_user_vc(interaction.user.id)

        if bal < cost:
            embed = discord.Embed(
                title="❌ Insufficient Virtual Currency (VC)",
                description=(
                    f"You need `💰 {cost:,} VC` to open a **{pack_data['name']}**, but you only have `💰 {bal:,} VC`.\n\n"
                    f"• Claim daily VC with `/nbadaily`\n"
                    f"• Quick-sell duplicate cards with `/nbasell`"
                ),
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed)

        deducted = await db.deduct_user_vc(interaction.user.id, cost)
        if not deducted:
            return await interaction.followup.send("❌ Failed to process VC transaction. Please try again.")

        card = roll_pack_card(pack_id, interaction.user.id)
        existing_cards = await db.get_user_nba_cards(interaction.user.id)
        existing_cids = [c["card_id"].lower() for c in existing_cards]
        is_new = card["id"].lower() not in existing_cids
        copies_now = existing_cids.count(card["id"].lower()) + 1

        await db.add_user_nba_card(interaction.user.id, card["id"], source=f"pack_{pack_id}")
        new_bal = await db.get_user_vc(interaction.user.id)

        embed = build_openpack_embed(interaction.user, pack_data, card, new_bal, is_new=is_new, copies=copies_now)
        reveal_view = NBAPackOpenView(interaction.user, pack_id, card, new_bal, is_new, copies_now)
        try:
            card_buf = await asyncio.to_thread(generate_nba_card_graphic, card, is_mystery=False)
            card_file = discord.File(fp=card_buf, filename="nba_card.png")
            await interaction.followup.send(embed=embed, file=card_file, view=reveal_view)
        except Exception:
            await interaction.followup.send(embed=embed, view=reveal_view)

    @commands.command(name="openpack", aliases=["pack", "buypack", "2kpack", "ripcard", "packopen"])
    @commands.guild_only()
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def openpack_prefix(self, ctx: commands.Context, pack_type: Optional[str] = "starter"):
        """Open a card pack: !openpack [starter|standard|allstar|hof|goat]"""
        pack_id = (pack_type or "starter").lower().strip()
        if pack_id not in NBA_PACK_TYPES:
            pack_id = "starter"
        pack_data = NBA_PACK_TYPES[pack_id]
        cost = pack_data["cost"]
        bal = await db.get_user_vc(ctx.author.id)

        if bal < cost:
            embed = discord.Embed(
                title="❌ Insufficient Virtual Currency (VC)",
                description=(
                    f"You need `💰 {cost:,} VC` to open a **{pack_data['name']}**, but you only have `💰 {bal:,} VC`.\n\n"
                    f"• Claim daily VC with `!nbadaily`\n"
                    f"• Quick-sell duplicates with `!nbasell`"
                ),
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        deducted = await db.deduct_user_vc(ctx.author.id, cost)
        if not deducted:
            return await ctx.send("❌ Failed to process VC transaction.")

        card = roll_pack_card(pack_id, ctx.author.id)
        existing_cards = await db.get_user_nba_cards(ctx.author.id)
        existing_cids = [c["card_id"].lower() for c in existing_cards]
        is_new = card["id"].lower() not in existing_cids
        copies_now = existing_cids.count(card["id"].lower()) + 1

        await db.add_user_nba_card(ctx.author.id, card["id"], source=f"pack_{pack_id}")
        new_bal = await db.get_user_vc(ctx.author.id)

        embed = build_openpack_embed(ctx.author, pack_data, card, new_bal, is_new=is_new, copies=copies_now)
        reveal_view = NBAPackOpenView(ctx.author, pack_id, card, new_bal, is_new, copies_now)
        try:
            card_buf = await asyncio.to_thread(generate_nba_card_graphic, card, is_mystery=False)
            card_file = discord.File(fp=card_buf, filename="nba_card.png")
            await ctx.send(embed=embed, file=card_file, view=reveal_view)
        except Exception:
            await ctx.send(embed=embed, view=reveal_view)

    # ── Daily / Weekly / Monthly Rewards ───────────────────────────────────────

    @app_commands.command(name="nbadaily", description="🎁 Claim your daily 1,000 VC reward & bonus card roll")
    @app_commands.guild_only()
    async def nbadaily_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        last_claim = await db.get_user_reward_timestamp(interaction.user.id, "daily")
        now = time.time()
        cooldown = 86400  # 24 hours

        if (now - last_claim) < cooldown:
            remaining = int(cooldown - (now - last_claim))
            hrs, rem = divmod(remaining, 3600)
            mins, _ = divmod(rem, 60)
            return await interaction.followup.send(f"⏳ **Daily VC Cooldown:** You can claim again in **{hrs}h {mins}m**.")

        await db.add_user_vc(interaction.user.id, 1000)
        await db.set_user_reward_timestamp(interaction.user.id, "daily", now)
        card = roll_pack_card("starter", interaction.user.id)
        await db.add_user_nba_card(interaction.user.id, card["id"], source="daily_reward")
        new_vc = await db.get_user_vc(interaction.user.id)

        embed = discord.Embed(
            title="🎁 NBA 2K Mobile • Daily Reward Claimed!",
            description=(
                f"🎉 **+1,000 VC** deposited to your account!\n"
                f"🎴 **Bonus Card Pulled:** {NBA_2K_TIERS.get(card['tier'], {}).get('emoji', '')} **[{card['ovr']} OVR] {card['name']}** (`{card['id']}`)\n\n"
                f"💰 **Current VC Balance:** `💰 {new_vc:,} VC`"
            ),
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=embed)

    @commands.command(name="nbadaily", aliases=["dailyvc", "nbareward", "claimvc"])
    @commands.guild_only()
    async def nbadaily_prefix(self, ctx: commands.Context):
        """Claim your daily 1,000 VC reward: !nbadaily"""
        last_claim = await db.get_user_reward_timestamp(ctx.author.id, "daily")
        now = time.time()
        cooldown = 86400

        if (now - last_claim) < cooldown:
            remaining = int(cooldown - (now - last_claim))
            hrs, rem = divmod(remaining, 3600)
            mins, _ = divmod(rem, 60)
            return await ctx.send(f"⏳ **Daily VC Cooldown:** You can claim again in **{hrs}h {mins}m**.")

        await db.add_user_vc(ctx.author.id, 1000)
        await db.set_user_reward_timestamp(ctx.author.id, "daily", now)
        card = roll_pack_card("starter", ctx.author.id)
        await db.add_user_nba_card(ctx.author.id, card["id"], source="daily_reward")
        new_vc = await db.get_user_vc(ctx.author.id)

        embed = discord.Embed(
            title="🎁 NBA 2K Mobile • Daily Reward Claimed!",
            description=(
                f"🎉 **+1,000 VC** deposited!\n"
                f"🎴 **Bonus Card Pulled:** {NBA_2K_TIERS.get(card['tier'], {}).get('emoji', '')} **[{card['ovr']} OVR] {card['name']}** (`{card['id']}`)\n\n"
                f"💰 **Current VC Balance:** `💰 {new_vc:,} VC`"
            ),
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @app_commands.command(name="nbaweekly", description="📅 Claim your weekly 5,000 VC stipend & All-Star card roll")
    @app_commands.guild_only()
    async def nbaweekly_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        last_claim = await db.get_user_reward_timestamp(interaction.user.id, "weekly")
        now = time.time()
        cooldown = 7 * 86400

        if (now - last_claim) < cooldown:
            remaining = int(cooldown - (now - last_claim))
            days, rem = divmod(remaining, 86400)
            hrs, _ = divmod(rem, 3600)
            return await interaction.followup.send(f"⏳ **Weekly VC Cooldown:** You can claim again in **{days}d {hrs}h**.")

        await db.add_user_vc(interaction.user.id, 5000)
        await db.set_user_reward_timestamp(interaction.user.id, "weekly", now)
        card = roll_pack_card("allstar", interaction.user.id)
        await db.add_user_nba_card(interaction.user.id, card["id"], source="weekly_reward")
        new_vc = await db.get_user_vc(interaction.user.id)

        embed = discord.Embed(
            title="📅 NBA 2K Mobile • Weekly Reward Claimed!",
            description=(
                f"🎉 **+5,000 VC** deposited!\n"
                f"🎴 **All-Star Card:** {NBA_2K_TIERS.get(card['tier'], {}).get('emoji', '')} **[{card['ovr']} OVR] {card['name']}** (`{card['id']}`)\n\n"
                f"💰 **Current VC Balance:** `💰 {new_vc:,} VC`"
            ),
            color=discord.Color.purple()
        )
        await interaction.followup.send(embed=embed)

    @commands.command(name="nbaweekly", aliases=["weeklyvc", "claimweekly"])
    @commands.guild_only()
    async def nbaweekly_prefix(self, ctx: commands.Context):
        """Claim your weekly 5,000 VC: !nbaweekly"""
        last_claim = await db.get_user_reward_timestamp(ctx.author.id, "weekly")
        now = time.time()
        cooldown = 7 * 86400

        if (now - last_claim) < cooldown:
            remaining = int(cooldown - (now - last_claim))
            days, rem = divmod(remaining, 86400)
            hrs, _ = divmod(rem, 3600)
            return await ctx.send(f"⏳ **Weekly VC Cooldown:** You can claim again in **{days}d {hrs}h**.")

        await db.add_user_vc(ctx.author.id, 5000)
        await db.set_user_reward_timestamp(ctx.author.id, "weekly", now)
        card = roll_pack_card("allstar", ctx.author.id)
        await db.add_user_nba_card(ctx.author.id, card["id"], source="weekly_reward")
        new_vc = await db.get_user_vc(ctx.author.id)

        embed = discord.Embed(
            title="📅 NBA 2K Mobile • Weekly Reward Claimed!",
            description=(
                f"🎉 **+5,000 VC** deposited!\n"
                f"🎴 **All-Star Card:** {NBA_2K_TIERS.get(card['tier'], {}).get('emoji', '')} **[{card['ovr']} OVR] {card['name']}** (`{card['id']}`)\n\n"
                f"💰 **Current VC Balance:** `💰 {new_vc:,} VC`"
            ),
            color=discord.Color.purple()
        )
        await ctx.send(embed=embed)

    @app_commands.command(name="nbamonthly", description="🏆 Claim your monthly 25,000 VC executive grant & HOF card roll")
    @app_commands.guild_only()
    async def nbamonthly_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        last_claim = await db.get_user_reward_timestamp(interaction.user.id, "monthly")
        now = time.time()
        cooldown = 30 * 86400

        if (now - last_claim) < cooldown:
            remaining = int(cooldown - (now - last_claim))
            days, _ = divmod(remaining, 86400)
            return await interaction.followup.send(f"⏳ **Monthly VC Cooldown:** You can claim again in **{days} days**.")

        await db.add_user_vc(interaction.user.id, 25000)
        await db.set_user_reward_timestamp(interaction.user.id, "monthly", now)
        card = roll_pack_card("hof", interaction.user.id)
        await db.add_user_nba_card(interaction.user.id, card["id"], source="monthly_reward")
        new_vc = await db.get_user_vc(interaction.user.id)

        embed = discord.Embed(
            title="🏆 NBA 2K Mobile • Monthly Executive Reward Claimed!",
            description=(
                f"🎉 **+25,000 VC** executive grant deposited!\n"
                f"🎴 **HOF Elite Card:** {NBA_2K_TIERS.get(card['tier'], {}).get('emoji', '')} **[{card['ovr']} OVR] {card['name']}** (`{card['id']}`)\n\n"
                f"💰 **Current VC Balance:** `💰 {new_vc:,} VC`"
            ),
            color=discord.Color.from_rgb(255, 215, 0)
        )
        await interaction.followup.send(embed=embed)

    @commands.command(name="nbamonthly", aliases=["monthlyvc", "claimmonthly"])
    @commands.guild_only()
    async def nbamonthly_prefix(self, ctx: commands.Context):
        """Claim your monthly 25,000 VC reward: !nbamonthly"""
        last_claim = await db.get_user_reward_timestamp(ctx.author.id, "monthly")
        now = time.time()
        cooldown = 30 * 86400

        if (now - last_claim) < cooldown:
            remaining = int(cooldown - (now - last_claim))
            days, _ = divmod(remaining, 86400)
            return await ctx.send(f"⏳ **Monthly VC Cooldown:** You can claim again in **{days} days**.")

        await db.add_user_vc(ctx.author.id, 25000)
        await db.set_user_reward_timestamp(ctx.author.id, "monthly", now)
        card = roll_pack_card("hof", ctx.author.id)
        await db.add_user_nba_card(ctx.author.id, card["id"], source="monthly_reward")
        new_vc = await db.get_user_vc(ctx.author.id)

        embed = discord.Embed(
            title="🏆 NBA 2K Mobile • Monthly Executive Reward Claimed!",
            description=(
                f"🎉 **+25,000 VC** executive grant deposited!\n"
                f"🎴 **HOF Elite Card:** {NBA_2K_TIERS.get(card['tier'], {}).get('emoji', '')} **[{card['ovr']} OVR] {card['name']}** (`{card['id']}`)\n\n"
                f"💰 **Current VC Balance:** `💰 {new_vc:,} VC`"
            ),
            color=discord.Color.from_rgb(255, 215, 0)
        )
        await ctx.send(embed=embed)

    # ── Card Quick-Selling ──────────────────────────────────────────────────────

    @app_commands.command(name="nbasell", description="💵 Quick-sell cards for VC (id, dupes, tier, or alldupes)")
    @app_commands.describe(option="Choose what to sell: card ID, 'dupes', 'tier <name>', or 'alldupes'")
    @app_commands.guild_only()
    async def nbasell_slash(self, interaction: discord.Interaction, option: str):
        await interaction.response.defer()
        opt = option.strip().lower()
        cards = await db.get_user_nba_cards(interaction.user.id)
        if not cards:
            return await interaction.followup.send("❌ You don't have any cards in your collection.")

        # Scenario 1: alldupes / dupes
        if opt in ("dupes", "alldupes", "all_dupes"):
            counts: Dict[str, int] = {}
            for c in cards:
                cid = c["card_id"].lower()
                counts[cid] = counts.get(cid, 0) + 1

            sold_count = 0
            total_vc = 0
            for cid, count in counts.items():
                if count > 1:
                    c_obj = get_nba_card(cid)
                    if c_obj and not c_obj.get("is_exclusive") and not c_obj.get("is_holo"):
                        tier_info = NBA_2K_TIERS.get(c_obj.get("tier", "gold"), NBA_2K_TIERS["gold"])
                        val_per = tier_info.get("quick_sell", 100)
                        to_remove = count - 1
                        for _ in range(to_remove):
                            await db.remove_user_nba_card(interaction.user.id, cid)
                        sold_count += to_remove
                        total_vc += val_per * to_remove

            if sold_count == 0:
                return await interaction.followup.send("ℹ️ No eligible duplicate cards found to sell.")

            await db.add_user_vc(interaction.user.id, total_vc)
            new_vc = await db.get_user_vc(interaction.user.id)
            return await interaction.followup.send(f"✅ **Sold `{sold_count}` duplicate cards** for `💰 +{total_vc:,} VC`! New balance: `💰 {new_vc:,} VC`.")

        # Scenario 2: specific card by ID / Name
        c_obj = get_nba_card(opt)
        if c_obj:
            cid = c_obj["id"].lower()
            owned = [c for c in cards if c["card_id"].lower() == cid]
            if not owned:
                return await interaction.followup.send(f"❌ You do not own **{c_obj['name']}** (`{cid}`).")

            if c_obj.get("is_exclusive"):
                return await interaction.followup.send(f"🛡️ Exclusive cards cannot be sold.")

            tier_info = NBA_2K_TIERS.get(c_obj.get("tier", "gold"), NBA_2K_TIERS["gold"])
            vc_earned = tier_info.get("quick_sell", 100)
            await db.remove_user_nba_card(interaction.user.id, cid)
            await db.add_user_vc(interaction.user.id, vc_earned)
            new_vc = await db.get_user_vc(interaction.user.id)
            return await interaction.followup.send(f"✅ **Sold 1x {c_obj['name']}** for `💰 +{vc_earned:,} VC`! New balance: `💰 {new_vc:,} VC`.")

        await interaction.followup.send("❌ Card not found. Specify a valid card ID, player name, or `dupes`.")

    @commands.command(name="nbasell", aliases=["sellcard", "quicksell"])
    @commands.guild_only()
    async def nbasell_prefix(self, ctx: commands.Context, *, args: str = ""):
        """Sell cards: !nbasell <card_id|dupes>"""
        if not args:
            return await ctx.send("❌ Please specify what to sell: `!nbasell <card_id>` or `!nbasell dupes`.")

        opt = args.strip().lower()
        cards = await db.get_user_nba_cards(ctx.author.id)
        if not cards:
            return await ctx.send("❌ You don't have any cards in your collection.")

        if opt in ("dupes", "alldupes", "all_dupes"):
            counts: Dict[str, int] = {}
            for c in cards:
                cid = c["card_id"].lower()
                counts[cid] = counts.get(cid, 0) + 1

            sold_count = 0
            total_vc = 0
            for cid, count in counts.items():
                if count > 1:
                    c_obj = get_nba_card(cid)
                    if c_obj and not c_obj.get("is_exclusive") and not c_obj.get("is_holo"):
                        tier_info = NBA_2K_TIERS.get(c_obj.get("tier", "gold"), NBA_2K_TIERS["gold"])
                        val_per = tier_info.get("quick_sell", 100)
                        to_remove = count - 1
                        for _ in range(to_remove):
                            await db.remove_user_nba_card(ctx.author.id, cid)
                        sold_count += to_remove
                        total_vc += val_per * to_remove

            if sold_count == 0:
                return await ctx.send("ℹ️ No eligible duplicate cards found to sell.")

            await db.add_user_vc(ctx.author.id, total_vc)
            new_vc = await db.get_user_vc(ctx.author.id)
            return await ctx.send(f"✅ **Sold `{sold_count}` duplicate cards** for `💰 +{total_vc:,} VC`! New balance: `💰 {new_vc:,} VC`.")

        c_obj = get_nba_card(opt)
        if c_obj:
            cid = c_obj["id"].lower()
            owned = [c for c in cards if c["card_id"].lower() == cid]
            if not owned:
                return await ctx.send(f"❌ You do not own **{c_obj['name']}** (`{cid}`).")

            if c_obj.get("is_exclusive"):
                return await ctx.send(f"🛡️ Exclusive cards cannot be sold.")

            tier_info = NBA_2K_TIERS.get(c_obj.get("tier", "gold"), NBA_2K_TIERS["gold"])
            vc_earned = tier_info.get("quick_sell", 100)
            await db.remove_user_nba_card(ctx.author.id, cid)
            await db.add_user_vc(ctx.author.id, vc_earned)
            new_vc = await db.get_user_vc(ctx.author.id)
            return await ctx.send(f"✅ **Sold 1x {c_obj['name']}** for `💰 +{vc_earned:,} VC`! New balance: `💰 {new_vc:,} VC`.")

        await ctx.send("❌ Card not found. Specify a valid card ID or `dupes`.")

    # ── Gifting & Trading ──────────────────────────────────────────────────────

    @app_commands.command(name="nbagive", description="🎁 Gift an NBA card from your collection to another member")
    @app_commands.describe(user="Member to gift the card to", card="Card ID or player name to gift")
    @app_commands.guild_only()
    async def nbagive_slash(self, interaction: discord.Interaction, user: discord.Member, card: str):
        await interaction.response.defer()
        if user.id == interaction.user.id:
            return await interaction.followup.send("❌ You cannot gift cards to yourself.")

        c_obj = get_nba_card(card)
        if not c_obj:
            return await interaction.followup.send("❌ Card not found in catalog.")

        cid = c_obj["id"].lower()
        cards = await db.get_user_nba_cards(interaction.user.id)
        owned = [c for c in cards if c["card_id"].lower() == cid]
        if not owned:
            return await interaction.followup.send(f"❌ You do not own **{c_obj['name']}** (`{cid}`).")

        await db.remove_user_nba_card(interaction.user.id, cid)
        await db.add_user_nba_card(user.id, cid, source=f"gift_from_{interaction.user.id}")

        embed = discord.Embed(
            title="🎁 NBA 2K Mobile • Card Gifted!",
            description=f"🎉 **{interaction.user.mention}** has gifted {NBA_2K_TIERS.get(c_obj['tier'], {}).get('emoji', '')} **[{c_obj['ovr']} OVR] {c_obj['name']}** (`{cid}`) to {user.mention}!",
            color=discord.Color.gold()
        )
        await interaction.followup.send(embed=embed)

    @commands.command(name="nbagive", aliases=["nbasend", "giftcard", "cardgive", "givecard"])
    @commands.guild_only()
    async def nbagive_prefix(self, ctx: commands.Context, target: discord.Member, *, args: str):
        """Gift a card: !nbagive @user <card_id>"""
        if target.id == ctx.author.id:
            return await ctx.send("❌ You cannot gift cards to yourself.")

        c_obj = get_nba_card(args)
        if not c_obj:
            return await ctx.send("❌ Card not found in catalog.")

        cid = c_obj["id"].lower()
        cards = await db.get_user_nba_cards(ctx.author.id)
        owned = [c for c in cards if c["card_id"].lower() == cid]
        if not owned:
            return await ctx.send(f"❌ You do not own **{c_obj['name']}** (`{cid}`).")

        await db.remove_user_nba_card(ctx.author.id, cid)
        await db.add_user_nba_card(target.id, cid, source=f"gift_from_{ctx.author.id}")

        embed = discord.Embed(
            title="🎁 NBA 2K Mobile • Card Gifted!",
            description=f"🎉 **{ctx.author.mention}** has gifted {NBA_2K_TIERS.get(c_obj['tier'], {}).get('emoji', '')} **[{c_obj['ovr']} OVR] {c_obj['name']}** (`{cid}`) to {target.mention}!",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @app_commands.command(name="nbatrade", description="🤝 Initiate a safe 2-sided card trade with another member")
    @app_commands.describe(user="Member to trade with", your_card="Your card ID/name to offer", their_card="Their card ID/name you want")
    @app_commands.guild_only()
    async def nbatrade_slash(self, interaction: discord.Interaction, user: discord.Member, your_card: Optional[str] = None, their_card: Optional[str] = None):
        await interaction.response.defer()
        if user.id == interaction.user.id:
            return await interaction.followup.send("❌ You cannot trade with yourself.")

        c_a = [get_nba_card(your_card)] if your_card and get_nba_card(your_card) else []
        c_b = [get_nba_card(their_card)] if their_card and get_nba_card(their_card) else []

        embed = build_multi_trade_embed(interaction.user, user, c_a, c_b)
        view = NBACardTradeView(interaction.user, user, c_a, c_b)
        await interaction.followup.send(content=f"🔔 {user.mention}, you have a trade offer from {interaction.user.mention}!", embed=embed, view=view)

    @commands.command(name="nbatrade", aliases=["tradecard", "trade"])
    @commands.guild_only()
    async def nbatrade_prefix(self, ctx: commands.Context, target: discord.Member, your_card: Optional[str] = None, their_card: Optional[str] = None):
        """Trade cards: !nbatrade @user [your_card] [their_card]"""
        if target.id == ctx.author.id:
            return await ctx.send("❌ You cannot trade with yourself.")

        c_a = [get_nba_card(your_card)] if your_card and get_nba_card(your_card) else []
        c_b = [get_nba_card(their_card)] if their_card and get_nba_card(their_card) else []

        embed = build_multi_trade_embed(ctx.author, target, c_a, c_b)
        view = NBACardTradeView(ctx.author, target, c_a, c_b)
        await ctx.send(content=f"🔔 {target.mention}, trade offer from {ctx.author.mention}!", embed=embed, view=view)

    # ── VC Wager Battles ────────────────────────────────────────────────────────

    @app_commands.command(name="vcbet", description="💰 Challenge a member to a Starting 5 VC wager battle")
    @app_commands.describe(opponent="Member to challenge", bet_amount="Amount of VC to wager (1 - 50,000)")
    @app_commands.guild_only()
    async def vcbet_slash(self, interaction: discord.Interaction, opponent: discord.Member, bet_amount: int):
        await interaction.response.defer()
        if opponent.id == interaction.user.id:
            return await interaction.followup.send("❌ You cannot wager against yourself.", ephemeral=True)
        if opponent.bot:
            return await interaction.followup.send("❌ You cannot wager against a bot.", ephemeral=True)
        if bet_amount < 1:
            return await interaction.followup.send("❌ Minimum wager is `1 VC`.", ephemeral=True)
        if bet_amount > 50000:
            return await interaction.followup.send("❌ Maximum wager is `50,000 VC`.", ephemeral=True)

        bal_a = await db.get_user_vc(interaction.user.id)
        bal_b = await db.get_user_vc(opponent.id)
        if bal_a < bet_amount:
            return await interaction.followup.send(f"❌ You only have `💰 {bal_a:,} VC`, which is less than the wager amount.", ephemeral=True)
        if bal_b < bet_amount:
            return await interaction.followup.send(f"❌ {opponent.display_name} only has `💰 {bal_b:,} VC`, which is less than the wager amount.", ephemeral=True)

        embed = discord.Embed(
            title="💰 NBA 2K VC WAGER BATTLE CHALLENGE!",
            description=(
                f"⚔️ {interaction.user.mention} has challenged {opponent.mention} to a **Starting 5 Wager Match**!\n\n"
                f"• **Wager Amount:** `💰 {bet_amount:,} VC` each\n"
                f"• **Total Winner Pot:** `💰 {bet_amount * 2:,} VC`\n\n"
                f"*Click `Accept Wager` below to lock in the VC and run the match!*"
            ),
            color=discord.Color.gold()
        )
        embed.timestamp = discord.utils.utcnow()
        view = VCBetChallengeView(interaction.user, opponent, bet_amount)
        await interaction.followup.send(content=f"🔔 {opponent.mention}, you have been challenged to a VC wager battle!", embed=embed, view=view)

    @commands.command(name="vcbet", aliases=["betbattle", "betvc", "wagerbattle", "nbavet", "betfight"])
    @commands.guild_only()
    async def vcbet_prefix(self, ctx: commands.Context, opponent: discord.Member, bet_amount: int = 0):
        """Wager VC on a team battle: !vcbet @user <amount>"""
        if opponent.id == ctx.author.id:
            return await ctx.send("❌ You cannot wager against yourself.")
        if opponent.bot:
            return await ctx.send("❌ You cannot wager against a bot.")
        if bet_amount < 1:
            return await ctx.send("❌ Please specify a valid bet amount: `!vcbet @user 500`")
        if bet_amount > 50000:
            return await ctx.send("❌ Maximum wager is `50,000 VC`.")

        bal_a = await db.get_user_vc(ctx.author.id)
        bal_b = await db.get_user_vc(opponent.id)
        if bal_a < bet_amount:
            return await ctx.send(f"❌ You only have `💰 {bal_a:,} VC`.")
        if bal_b < bet_amount:
            return await ctx.send(f"❌ {opponent.display_name} only has `💰 {bal_b:,} VC`.")

        embed = discord.Embed(
            title="💰 NBA 2K VC WAGER BATTLE CHALLENGE!",
            description=(
                f"⚔️ {ctx.author.mention} challenged {opponent.mention} to a **Starting 5 Wager Match**!\n\n"
                f"• **Wager:** `💰 {bet_amount:,} VC` each\n"
                f"• **Winner Takes:** `💰 {bet_amount * 2:,} VC`\n\n"
                f"*{opponent.mention}, click Accept below to battle!*"
            ),
            color=discord.Color.gold()
        )
        embed.timestamp = discord.utils.utcnow()
        view = VCBetChallengeView(ctx.author, opponent, bet_amount)
        await ctx.send(content=f"🔔 {opponent.mention}, challenge received from {ctx.author.mention}!", embed=embed, view=view)

    # ── Pack Odds ───────────────────────────────────────────────────────────────

    @app_commands.command(name="packodds", description="📊 View the official pull odds and probabilities for all 5 pack tiers")
    @app_commands.guild_only()
    async def packodds_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = discord.Embed(
            title="📦 NBA 2K Mobile • Official Pack Odds & Probabilities",
            description="All packs feature certified provably-fair pull rates directly tied to NBA 2K card tiers:\n",
            color=discord.Color.gold()
        )
        for pid, pdata in NBA_PACK_TYPES.items():
            if pid == "boss_raid": continue
            odds_str = " • ".join(f"{NBA_2K_TIERS.get(t, {}).get('emoji', '🎴')} {t.replace('_', ' ').title()}: `{int(prob * 100)}%`" for t, prob in pdata.get("odds", {}).items())
            embed.add_field(
                name=f"{pdata['name']} — 💰 {pdata['cost']:,} VC",
                value=f"*{pdata['description']}*\n📊 **Odds:** {odds_str}",
                inline=False
            )
        embed.set_footer(text="Use /openpack <pack> to open any pack anytime!")
        await interaction.followup.send(embed=embed)

    @commands.command(name="packodds", aliases=["odds", "packrates", "packinfo", "cardprobability"])
    @commands.guild_only()
    async def packodds_prefix(self, ctx: commands.Context):
        """View pack odds: !packodds"""
        embed = discord.Embed(
            title="📦 NBA 2K Mobile • Official Pack Odds",
            description="Certified drop rates for each pack tier:\n",
            color=discord.Color.gold()
        )
        for pid, pdata in NBA_PACK_TYPES.items():
            if pid == "boss_raid": continue
            odds_str = " • ".join(f"{t.replace('_', ' ').title()}: `{int(prob * 100)}%`" for t, prob in pdata.get("odds", {}).items())
            embed.add_field(
                name=f"{pdata['name']} — 💰 {pdata['cost']:,} VC",
                value=f"📊 **Odds:** {odds_str}",
                inline=False
            )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(NBAEconomyCog(bot))
