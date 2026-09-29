# -*- coding: utf-8 -*-
"""
cogs/nba_admin.py - Creator & Admin NBA Management Commands (nbagrant, grantallcards, stripexclusives, spawndrop)
"""
from __future__ import annotations

import re
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
    is_creator
)

logger = logging.getLogger("SweetyBot.NBAAdmin")


class NBAAdminCog(commands.Cog, name="NBA Admin"):
    """Bot Creator & Server Admin NBA 2K management commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Card Granting ───────────────────────────────────────────────────────────

    @app_commands.command(name="nbagrant", description="👑 Grant any NBA 2K card to a member's binder (Creator Only)")
    @app_commands.describe(user="Target member to receive the card", card="Card ID or Player Name (e.g. 'dm-jordan-99')", count="Number of copies (default: 1)")
    @app_commands.guild_only()
    async def nbagrant_slash(self, interaction: discord.Interaction, user: discord.Member, card: str, count: int = 1):
        await interaction.response.defer(ephemeral=True)
        if not is_creator(interaction.user):
            return await interaction.followup.send("❌ This command is strictly restricted to the Bot Creator (`<@719932313919684670>`).", ephemeral=True)

        card_obj = get_nba_card(card)
        if not card_obj:
            return await interaction.followup.send(f"❌ Card `{card}` was not found in catalog.", ephemeral=True)

        count = max(1, min(count, 50))
        for _ in range(count):
            await db.add_user_nba_card(user.id, card_obj["id"], source="creator_grant")

        tier_info = NBA_2K_TIERS.get(card_obj["tier"], NBA_2K_TIERS["gold"])
        embed = discord.Embed(
            title="👑 Creator Card Grant Protocol",
            description=f"✅ Successfully granted **{count}x** {tier_info['emoji']} **[{card_obj['ovr']} OVR] {card_obj['name']}** (`{card_obj['id']}`) to {user.mention}!",
            color=discord.Color.gold()
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed, ephemeral=True)

    @commands.command(name="nbagrant", aliases=["grantcard", "exclgrant", "grantexclusive", "grant"])
    @commands.guild_only()
    async def nbagrant_prefix(self, ctx: commands.Context, *, raw_args: str = ""):
        """Grant any card: !nbagrant [@user] [count] <card_name>"""
        if not is_creator(ctx.author):
            return await ctx.send("❌ This command is strictly restricted to the Bot Creator (ID: `719932313919684670`).")

        raw = raw_args.strip()
        if not raw:
            return await ctx.send(
                "👑 **NBA Card Grant Usage:**\n"
                "• `!nbagrant <card_name>` — Grant to yourself\n"
                "• `!nbagrant @user <card_name>` — Grant to a member\n"
                "• `!nbagrant @user 3 <card_name>` — Grant multiple copies"
            )

        tokens = raw.split()
        target = ctx.author
        count = 1
        idx = 0

        first_tok = tokens[0]
        m_match = re.match(r'^<@!?(\d+)>$', first_tok)
        if m_match:
            uid = int(m_match.group(1))
            found = ctx.guild.get_member(uid) if ctx.guild else None
            if found: target = found
            idx += 1
        elif first_tok.isdigit() and len(first_tok) >= 17:
            uid = int(first_tok)
            found = ctx.guild.get_member(uid) if ctx.guild else None
            if found: target = found
            idx += 1

        if idx < len(tokens) and tokens[idx].isdigit() and len(tokens[idx]) <= 3:
            count = max(1, min(int(tokens[idx]), 50))
            idx += 1

        query = " ".join(tokens[idx:]).strip()
        card_obj = get_nba_card(query)
        if not card_obj:
            return await ctx.send(f"❌ Card `{query}` was not found in the catalog.")

        for _ in range(count):
            await db.add_user_nba_card(target.id, card_obj["id"], source="creator_grant")

        tier_info = NBA_2K_TIERS.get(card_obj["tier"], NBA_2K_TIERS["gold"])
        await ctx.send(f"👑 Successfully granted **{count}x** {tier_info['emoji']} **[{card_obj['ovr']} OVR] {card_obj['name']}** (`{card_obj['id']}`) to {target.mention}!")

    @commands.command(name="grantallcards", aliases=["unlockeverything", "godmode"])
    @commands.guild_only()
    async def grantallcards_prefix(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        """Grant 1x copy of every single card in catalog (Creator Only)"""
        if not is_creator(ctx.author):
            return await ctx.send("❌ Restricted to Bot Creator.")

        target_user = target or ctx.author
        for card in NBA_2K_MOBILE_CARDS:
            await db.add_user_nba_card(target_user.id, card["id"], source="creator_godmode")
        await ctx.send(f"👑 **Godmode Activated:** Granted 1x copy of all **`{len(NBA_2K_MOBILE_CARDS)}` cards** to {target_user.mention}!")

    @commands.command(name="grantvc", aliases=["givevc", "addvc"])
    @commands.guild_only()
    async def grantvc_prefix(self, ctx: commands.Context, target: discord.Member, amount: int):
        """Grant VC to a user (Creator Only)"""
        if not is_creator(ctx.author):
            return await ctx.send("❌ Restricted to Bot Creator.")
        await db.add_user_vc(target.id, amount)
        new_bal = await db.get_user_vc(target.id)
        await ctx.send(f"💰 Successfully granted **`{amount:,} VC`** to {target.mention}! Balance: `💰 {new_bal:,} VC`.")

    @commands.command(name="stripexclusives", aliases=["revokeeveryoneexclusives"])
    @commands.guild_only()
    async def stripexclusives_prefix(self, ctx: commands.Context):
        """Strip exclusive cards from all non-creators (Creator Only)"""
        if not is_creator(ctx.author):
            return await ctx.send("❌ Restricted to Bot Creator.")
        await db.execute("DELETE FROM user_nba_cards WHERE card_id LIKE 'excl-%' AND user_id != '719932313919684670' AND user_id != 719932313919684670;")
        await ctx.send("🛡️ **Exclusive Cards Stripped:** All non-creator exclusive cards have been purged.")

    @commands.command(name="wipeallmycards", aliases=["selfwipe"])
    @commands.guild_only()
    async def wipeallmycards_prefix(self, ctx: commands.Context):
        """Wipe your own binder cleanly: !wipeallmycards"""
        await db.execute("DELETE FROM user_nba_cards WHERE user_id = ?;", str(ctx.author.id))
        await db.execute("DELETE FROM user_nba_lineups WHERE user_id = ?;", str(ctx.author.id))
        await ctx.send(f"✅ Successfully wiped all cards from your account ({ctx.author.mention})!")

    # ── Force Drop Spawning ────────────────────────────────────────────────────

    @app_commands.command(name="spawndrop", description="⚡ Force-spawn a wild NBA card drop in this channel (Staff / Admin Only)")
    @app_commands.guild_only()
    async def spawndrop_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.manage_guild and not is_creator(interaction.user):
            return await interaction.followup.send("🚫 You need Manage Server permission to spawn drops.", ephemeral=True)

        card = random.choice(NBA_2K_MOBILE_CARDS)
        from cogs.nba_minigames import _active_nba_drops
        _active_nba_drops[interaction.channel_id] = {
            "card": card,
            "spawned_at": time.time(),
            "hint_level": 1,
            "claimed": False
        }

        tier_info = NBA_2K_TIERS.get(card.get("tier", "gold"), NBA_2K_TIERS["gold"])
        hint = generate_player_hint(card["name"], hint_level=1)
        embed = discord.Embed(
            title="🏀 A wild NBA 2K card appeared!",
            description=(
                f"**Guess the player name to catch this card!**\n\n"
                f"• **Type:** `/catch <name>` or guess in chat\n"
                f"• **Tier:** {tier_info['emoji']} **{tier_info['name']}**\n"
                f"• **Position:** `{card.get('pos', 'SG')}` | **Team:** `{card.get('team', 'NBA')}`\n"
                f"• **Hint:** `{hint}`"
            ),
            color=discord.Color.from_rgb(*NBA_2K_CARD_THEMES.get(card.get("tier", "gold"), {}).get("primary", (255, 215, 0)))
        )
        embed.set_footer(text="NBA 2K Mobile Spawns • First to guess catches the card + 150 VC!")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(NBAAdminCog(bot))
