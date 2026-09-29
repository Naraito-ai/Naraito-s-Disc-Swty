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
        card_targets = {card["id"]: 1 for card in NBA_2K_MOBILE_CARDS}
        await db.grant_bulk_nba_cards(target_user.id, card_targets)
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

    @app_commands.command(name="stripexclusives", description="🛡️ Strip exclusive cards from all non-creators (Creator Only)")
    @app_commands.guild_only()
    async def stripexclusives_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not is_creator(interaction.user):
            return await interaction.followup.send("❌ Restricted to Bot Creator.", ephemeral=True)
        await db.execute("DELETE FROM user_nba_cards WHERE card_id LIKE 'excl-%' AND user_id != '719932313919684670';")
        await interaction.followup.send("🛡️ **Exclusive Cards Stripped:** All non-creator exclusive cards have been purged.", ephemeral=True)

    @commands.command(name="stripexclusives", aliases=["revokeeveryoneexclusives"])
    @commands.guild_only()
    async def stripexclusives_prefix(self, ctx: commands.Context):
        """Strip exclusive cards from all non-creators (Creator Only)"""
        if not is_creator(ctx.author):
            return await ctx.send("❌ Restricted to Bot Creator.")
        await db.execute("DELETE FROM user_nba_cards WHERE card_id LIKE 'excl-%' AND user_id != '719932313919684670';")
        await ctx.send("🛡️ **Exclusive Cards Stripped:** All non-creator exclusive cards have been purged.")

    @commands.command(name="wipeallmycards", aliases=["selfwipe"])
    @commands.guild_only()
    async def wipeallmycards_prefix(self, ctx: commands.Context):
        """Wipe your own binder cleanly: !wipeallmycards"""
        await db.execute("DELETE FROM user_nba_cards WHERE user_id = ?;", str(ctx.author.id))
        await db.delete_dream_team(ctx.author.id)
        await ctx.send(f"✅ Successfully wiped all cards from your account ({ctx.author.mention})!")

    # ── Force Drop Spawning ────────────────────────────────────────────────────

    @app_commands.command(name="spawndrop", description="⚡ Force-spawn a wild NBA card drop in this channel (Staff / Admin Only)")
    @app_commands.guild_only()
    async def spawndrop_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.manage_guild and not is_creator(interaction.user):
            return await interaction.followup.send("🚫 You need Manage Server permission to spawn drops.", ephemeral=True)

        from cogs.nba_minigames import spawn_nba_card_drop
        msg = await spawn_nba_card_drop(interaction.channel, spawner=interaction.user, interaction=interaction)
        if not msg:
            await interaction.followup.send("❌ Failed to spawn card drop.", ephemeral=True)

    @commands.command(name="spawndrop", aliases=["drop", "forcespawn", "spawncard"])
    @commands.guild_only()
    async def spawndrop_prefix(self, ctx: commands.Context, *, card_name: Optional[str] = None):
        """Force-spawn a drop: !spawndrop [card_name]"""
        if not ctx.author.guild_permissions.manage_guild and not is_creator(ctx.author):
            embed = discord.Embed(
                title="🚫 Permission Denied",
                description="You need **Manage Server** permissions or Bot Creator access to spawn card drops.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        card_override = None
        if card_name:
            card_override = get_nba_card(card_name.strip())
            if not card_override:
                embed = discord.Embed(
                    title="❌ Card Not Found",
                    description=f"Card `{card_name}` was not found in the NBA catalog.",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)

        from cogs.nba_minigames import spawn_nba_card_drop
        await spawn_nba_card_drop(ctx.channel, spawner=ctx.author, card_override=card_override)

    # ── Slash Tree Sync Commands ───────────────────────────────────────────────

    @commands.command(name="sync", aliases=["treesync", "synccommands"])
    @commands.guild_only()
    async def sync_prefix(self, ctx: commands.Context, spec: Optional[str] = None):
        """Sync slash commands: !sync (instant guild sync) or !sync global"""
        if not is_creator(ctx.author) and not ctx.author.guild_permissions.administrator:
            return await ctx.send("🚫 Only the Bot Creator or Server Administrators can sync slash commands.")

        msg = await ctx.send("🔄 **Syncing slash commands with Discord...**")
        try:
            if spec == "global":
                synced = await ctx.bot.tree.sync()
                await msg.edit(content=f"🌍 **Global Sync Complete!** Synced `{len(synced)}` application commands globally. *(Note: Global updates may take up to an hour to propagate in Discord client caches).*")
            elif spec == "clear":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                await msg.edit(content=f"🧹 **Guild Tree Cleared!** Cleared custom guild commands for **{ctx.guild.name}**.")
            else:
                # Instant guild sync: copies all global commands directly into the current guild
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
                await msg.edit(content=f"⚡ **Instant Guild Sync Complete!** Synced `{len(synced)}` slash commands directly to **{ctx.guild.name}**! They are now available immediately in chat.")
        except Exception as e:
            logger.error(f"Error syncing commands: {e}", exc_info=True)
            await msg.edit(content=f"❌ **Sync Failed:** `{e}`")

    @app_commands.command(name="sync", description="🔄 Force-sync all slash commands immediately to this server (Admin/Creator)")
    @app_commands.describe(scope="Sync scope: 'guild' (instant local) or 'global'")
    @app_commands.guild_only()
    async def sync_slash(self, interaction: discord.Interaction, scope: Optional[str] = "guild"):
        await interaction.response.defer(ephemeral=True)
        if not is_creator(interaction.user) and not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send("🚫 Only the Bot Creator or Server Administrators can sync slash commands.", ephemeral=True)

        try:
            if scope == "global":
                synced = await interaction.client.tree.sync()
                await interaction.followup.send(f"🌍 **Global Sync Complete!** Synced `{len(synced)}` slash commands globally.", ephemeral=True)
            else:
                interaction.client.tree.copy_global_to(guild=interaction.guild)
                synced = await interaction.client.tree.sync(guild=interaction.guild)
                await interaction.followup.send(f"⚡ **Instant Guild Sync Complete!** Synced `{len(synced)}` slash commands directly to **{interaction.guild.name}**! All slash commands are now active immediately.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /sync: {e}", exc_info=True)
            await interaction.followup.send(f"❌ **Sync Failed:** `{e}`", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(NBAAdminCog(bot))
