# -*- coding: utf-8 -*-
"""
cogs/nba_cards.py - NBA 2K Mobile Card Collection, Dex, Pack Opening, Card Viewing & Holo Foil Fusion
"""
from __future__ import annotations

import os
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
    NBA_FUSION_GIF_MAPPINGS,
    NBA_PLAYER_MOMENT_ACTION_URLS,
    NBA_CARD_SPECIFIC_MOMENT_URLS,
    NBA_HOLO_EDITION_MOMENT_URLS,
    NBA_2K_MOBILE_CARDS,
    NBA_CARDS_BY_ID,
    get_nba_card,
    get_nba_card_moment,
    generate_nba_card_graphic,
    get_nba_player_moment_photo,
    is_creator
)

logger = logging.getLogger("SweetyBot.NBACards")


class NBADexSelect(discord.ui.Select):
    def __init__(self, card_options: List[discord.SelectOption]):
        super().__init__(
            placeholder="🔍 Select a card to inspect full ratings & moment...",
            min_values=1,
            max_values=1,
            options=card_options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        # Step 1: Defer immediately
        await interaction.response.defer(ephemeral=True)
        try:
            cid = self.values[0]
            card = get_nba_card(cid)
            if not card:
                return await interaction.followup.send("❌ Card not found in catalog.", ephemeral=True)
            
            # Generate card graphic in worker thread
            card_buf = await asyncio.to_thread(generate_nba_card_graphic, card, False)
            file = discord.File(fp=card_buf, filename=f"{card['id']}.png")
            
            tier_info = NBA_2K_TIERS.get(card.get("tier", "gold"), NBA_2K_TIERS["gold"])
            embed = discord.Embed(
                title=f"{tier_info['emoji']} [{card['ovr']} OVR] {card['name']}",
                description=(
                    f"• **Position:** `{card.get('pos', 'SG')}` | **Team:** `{card.get('team', 'NBA')}`\n"
                    f"• **Tier:** {tier_info['emoji']} **{card.get('tier', 'Gold').replace('_', ' ').title()}**\n"
                    f"• **Moment:** *{get_nba_card_moment(card)}*\n"
                    f"• **Quicksell Value:** `💰 {card.get('quicksell_vc', 100):,} VC`\n\n"
                    f"**Player Ratings & Attributes:**\n"
                    f"🎯 `Inside: {card.get('stats', {}).get('ins', 80)}` | 🏹 `Mid: {card.get('stats', {}).get('ath', 80)}` | 🏀 `3PT: {card.get('stats', {}).get('3pt', 80)}`\n"
                    f"🛡️ `Defense: {card.get('stats', {}).get('def', 80)}` | ⚡ `Playmaking: {card.get('stats', {}).get('ply', 80)}` | 🏆 `Clutch: {card.get('stats', {}).get('clu', 80)}`"
                ),
                color=discord.Color.from_rgb(*NBA_2K_CARD_THEMES.get(card.get("tier", "gold"), {}).get("primary", (255, 215, 0)))
            )
            embed.set_image(url=f"attachment://{card['id']}.png")
            embed.set_footer(text=f"NBA 2K Mobile Card Inspector • ID: {card['id']}")
            embed.timestamp = discord.utils.utcnow()
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in NBADexSelect callback: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error inspecting card: {e}", ephemeral=True)


class NBADexView(discord.ui.View):
    def __init__(self, target_user: Union[discord.Member, discord.User], user_cards: List[Dict[str, Any]], tier_filter: Optional[str] = None):
        super().__init__(timeout=180.0)
        self.target_user = target_user
        self.user_cards = user_cards
        self.tier_filter = tier_filter
        self.current_page = 0
        self.page_size = 15

        # Group duplicate counts & resolve unique canonical card objects
        self.card_counts: Dict[str, int] = {}
        all_unique: List[Dict[str, Any]] = []
        seen = set()

        for c in user_cards:
            cid = c.get("card_id", "")
            c_obj = get_nba_card(cid)
            if c_obj:
                canon_id = c_obj["id"].lower()
                self.card_counts[canon_id] = self.card_counts.get(canon_id, 0) + 1
                if canon_id not in seen:
                    seen.add(canon_id)
                    all_unique.append(c_obj)

        if tier_filter:
            tf = tier_filter.lower().replace(" ", "_")
            self.filtered_cards = [c for c in all_unique if c.get("tier", "").lower() == tf]
        else:
            self.filtered_cards = all_unique

        # Sort by OVR descending
        tier_prio = {"exclusive": 7, "dark_matter": 6, "galaxy_opal": 5, "diamond": 4, "amethyst": 3, "ruby": 2, "gold": 1}
        self.filtered_cards.sort(key=lambda x: (tier_prio.get(x.get("tier", "gold"), 0), x.get("ovr", 0)), reverse=True)
        self.total_pages = max(1, (len(self.filtered_cards) + self.page_size - 1) // self.page_size)
        self.message: Optional[discord.Message] = None
        self._update_select_menu()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    def _update_select_menu(self):
        # Remove old select menu if present
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)

        start_idx = self.current_page * self.page_size
        end_idx = start_idx + self.page_size
        page_cards = self.filtered_cards[start_idx:end_idx]

        if page_cards:
            options = []
            seen_opt = set()
            for c in page_cards:
                if c["id"] in seen_opt or len(options) >= 25:
                    continue
                seen_opt.add(c["id"])
                t_info = NBA_2K_TIERS.get(c.get("tier", "gold"), NBA_2K_TIERS["gold"])
                cnt = self.card_counts.get(c["id"].lower(), 1)
                label = f"[{c['ovr']} OVR] {c['name']}"[:80]
                desc = f"{t_info['name']} • {c.get('pos', 'SG')} • Owned: {cnt}x"[:100]
                options.append(discord.SelectOption(label=label, value=c["id"], description=desc, emoji=t_info.get("emoji", "🎴")))
            if options:
                self.add_item(NBADexSelect(options))

    def build_embed(self) -> discord.Embed:
        start_idx = self.current_page * self.page_size
        end_idx = start_idx + self.page_size
        page_cards = self.filtered_cards[start_idx:end_idx]

        total_owned = len(self.user_cards)
        total_unique = len(set(c.get("card_id", "").lower() for c in self.user_cards))
        total_catalog = len(NBA_2K_MOBILE_CARDS)

        title = f"🎴 NBA 2K Mobile Dex • {self.target_user.display_name}'s Binder"
        if self.tier_filter:
            title += f" ({self.tier_filter.replace('_', ' ').title()})"

        desc = (
            f"📊 **Collection Progress:** `{total_unique}/{total_catalog} Unique Cards` ({int(total_unique/total_catalog*100)}% complete)\n"
            f"📦 **Total Cards in Binder:** `{total_owned:,}` cards\n\n"
        )

        if not page_cards:
            desc += "*No cards found matching this filter in binder.*"
        else:
            for i, c in enumerate(page_cards, start=start_idx + 1):
                t_info = NBA_2K_TIERS.get(c.get("tier", "gold"), NBA_2K_TIERS["gold"])
                cnt = self.card_counts.get(c["id"].lower(), 1)
                is_h = bool(c.get("is_holo") or str(c.get("id", "")).startswith("holo_"))
                holo_tag = " ✨ *(Holo Foil)*" if is_h else ""
                cnt_tag = f" `x{cnt}`" if cnt > 1 else ""
                desc += f"`#{i:02d}` {t_info['emoji']} **[{c['ovr']} OVR] {c['name']}**{holo_tag}{cnt_tag} — `{c.get('pos', 'SG')}` | `{c['id']}`\n"

        embed = discord.Embed(title=title, description=desc, color=discord.Color.gold())
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages} • Use /nbacard <id> to inspect any card")
        embed.timestamp = discord.utils.utcnow()
        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if interaction.user.id != self.target_user.id and not is_creator(interaction.user):
            return
        if self.current_page > 0:
            self.current_page -= 1
            self._update_select_menu()
            await interaction.edit_original_response(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if interaction.user.id != self.target_user.id and not is_creator(interaction.user):
            return
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._update_select_menu()
            await interaction.edit_original_response(embed=self.build_embed(), view=self)


async def handle_nbafuse(user: Union[discord.Member, discord.User], card_query: str, send_func: Any, is_interaction: bool = False):
    """Combines 3 duplicate copies of a card into a Holo Foil Edition (+5 OVR & +20% quicksell)."""
    clean_q = card_query.strip().lower()
    card_obj = get_nba_card(clean_q)
    if not card_obj:
        msg = f"❌ Card `{card_query}` was not found in the NBA 2K catalog."
        if is_interaction:
            return await send_func(msg, ephemeral=True)
        return await send_func(msg)

    if card_obj.get("tier") == "exclusive" or str(card_obj.get("id", "")).startswith("excl-"):
        msg = f"❌ **{card_obj['name']}** is an Exclusive Edition card. Exclusive cards are uncraftable and cannot be fused!"
        if is_interaction:
            return await send_func(msg, ephemeral=True)
        return await send_func(msg)

    if card_obj.get("is_holo") or str(card_obj.get("id", "")).startswith("holo_"):
        msg = f"❌ **{card_obj['name']}** is already an upgraded Holo Foil Edition!"
        if is_interaction:
            return await send_func(msg, ephemeral=True)
        return await send_func(msg)

    success, msg, data = await db.fuse_nba_cards(user.id, card_obj["id"], legacy_map=NBA_LEGACY_CARD_MAPPINGS)
    if not success:
        if is_interaction:
            return await send_func(f"❌ {msg}", ephemeral=True)
        return await send_func(f"❌ {msg}")

    holo_card = get_nba_card(data["holo_id"])
    if not holo_card:
        holo_card = dict(card_obj)
        holo_card["ovr"] = min(100, card_obj["ovr"] + 5)
        holo_card["is_holo"] = True

    try:
        card_buf = await asyncio.to_thread(generate_nba_card_graphic, holo_card, is_mystery=False)
        card_file = discord.File(fp=card_buf, filename="holo_card.png")
    except Exception as img_err:
        logger.error(f"Error generating holo card graphic: {img_err}", exc_info=True)
        card_file = None

    tier_info = NBA_2K_TIERS.get(card_obj["tier"], NBA_2K_TIERS["gold"])
    embed = discord.Embed(
        title="🌟 CARD FUSION COMPLETE: HOLO FOIL FORGED!",
        description=(
            f"✨ 3x copies of {tier_info['emoji']} **[{card_obj['ovr']} OVR] {card_obj['name']}** have fused into a **Holo / Foil Edition**!\n\n"
            f"• 📈 **OVR Rating Boost:** `{card_obj['ovr']} OVR` ➔ **`{holo_card['ovr']} OVR` (+5 Upgrade)**\n"
            f"• ⚡ **Stat Boosts:** `+5` Inside, Mid, 3PT, Defense & Playmaking\n"
            f"• 💰 **VC Quick-Sell Boost:** `+{int(holo_card.get('quicksell_vc', 0) - card_obj.get('quicksell_vc', 0))} VC` (+20% value)\n"
            f"• 🌈 **Visual Holo Shimmer:** Equipped with radiant rainbow foil reflections\n\n"
            f"🌟 *Your new Holo Foil card is now permanently in your binder! View with `/nbacard {holo_card['id']}`.*"
        ),
        color=discord.Color.from_rgb(255, 215, 0)
    )
    if card_file:
        embed.set_image(url="attachment://holo_card.png")
    embed.set_footer(text="NBA 2K Card Fusion • Fuse 3 duplicates anytime with /nbafuse")
    embed.timestamp = discord.utils.utcnow()

    # Step 1: Send Card Embed
    if card_file:
        await send_func(embed=embed, file=card_file)
    else:
        await send_func(embed=embed)

    # Step 2: Secondary GIF & Flavor Text for Dark Matter (99 OVR) and Galaxy Opal (97-98 OVR) ONLY
    c_tier = card_obj.get("tier", "").lower()
    if c_tier in ["dark_matter", "galaxy_opal"]:
        base_cid = card_obj["id"].lower()
        gif_info = NBA_FUSION_GIF_MAPPINGS.get(base_cid) or NBA_FUSION_GIF_MAPPINGS.get(NBA_LEGACY_CARD_MAPPINGS.get(base_cid, ""))
        if gif_info and gif_info.get("gif_url"):
            try:
                # Direct Tenor GIF URL in-between for native Discord auto-play animation
                await send_func(content=gif_info["gif_url"])

                # Glowing flavor text embed underneath
                flavor = gif_info.get("flavor_text", f"⚡ {card_obj['name']} has transcended into legend!")
                flavor_embed = discord.Embed(
                    description=f"### *{flavor}*",
                    color=discord.Color.from_rgb(255, 215, 0) if c_tier == "dark_matter" else discord.Color.purple()
                )
                flavor_embed.set_footer(text=f"✨ Holo Foil Transcendence • {card_obj['name']} ({holo_card['ovr']} OVR)")
                flavor_embed.timestamp = discord.utils.utcnow()
                await send_func(embed=flavor_embed)
            except Exception as gif_send_err:
                logger.warning(f"Could not send secondary GIF/flavor for {card_obj['id']}: {gif_send_err}")


def build_nbacard_embed(card: Dict[str, Any], copies_owned: int = 0, is_fav: bool = False, owner_user: Optional[Union[discord.User, discord.Member]] = None) -> discord.Embed:
    """Builds an authentic NBA 2K inspect card embed."""
    tier_info = NBA_2K_TIERS.get(card.get("tier", "gold"), NBA_2K_TIERS["gold"])
    moment = get_nba_card_moment(card)
    is_holo = bool(card.get("is_holo") or str(card.get("id", "")).startswith("holo_"))
    tag = "🌟 **[HOLO FOIL EDITION]** " if is_holo else ""

    embed = discord.Embed(
        title=f"{tier_info['emoji']} {tag}[{card['ovr']} OVR] {card['name'].upper()}",
        description=(
            f"**Player:** `{card['name']}` • **Pos:** `{card['pos']}` • **Team:** `{card['team']}`\n"
            f"⚡ **NBA Moment:** *{moment}*\n"
            f"**Theme:** *{card.get('theme', 'Base')}*\n"
            f"*{card.get('quote', '')}*"
        ),
        color=tier_info["color"]
    )
    stats = card.get("stats", {})
    embed.add_field(
        name="📊 Ratings Breakdown",
        value=(
            f"`🎯 3PT `: **{stats.get('3pt', 80)}** | `🔒 DEF `: **{stats.get('def', 80)}** | `🧠 PLY `: **{stats.get('ply', 80)}**\n"
            f"`💥 INS `: **{stats.get('ins', 80)}** | `⚡ CLU `: **{stats.get('clu', 80)}** | `🏃 ATH `: **{stats.get('ath', 80)}**"
        ),
        inline=False
    )
    if owner_user:
        dup_str = f"x{copies_owned}" if copies_owned > 0 else "Not Owned"
        fav_str = " ⭐ Favorite" if is_fav else ""
        embed.add_field(name="🎴 Collection Status", value=f"• **Copies Owned:** `{dup_str}`{fav_str}\n• **Quick-Sell Value:** `💰 {tier_info['quick_sell']:,} VC`", inline=False)
    embed.set_footer(text=f"NBA 2K Mobile Card Dex • Card ID: {card['id']}")
    embed.timestamp = discord.utils.utcnow()
    return embed


def build_nbadex_embed(
    target_user: Union[discord.User, discord.Member],
    cards_owned: List[Dict[str, Any]],
    tier_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 6,
    vc_balance: int = 1000
) -> Tuple[discord.Embed, int, List[Dict[str, Any]]]:
    """Builds a paginated collection binder embed for a user."""
    view = NBADexView(target_user, cards_owned, tier_filter=tier_filter)
    view.current_page = max(0, min(page - 1, max(0, view.total_pages - 1)))
    embed = view.build_embed()
    return embed, max(1, view.total_pages), view.filtered_cards


class NBACardsCog(commands.Cog, name="NBA Cards"):
    """Card collection, binder dex, inspect, pack opening, and Holo Foil fusion."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Slash Commands ──────────────────────────────────────────────────────────

    @app_commands.command(name="nbadex", description="🎴 View your full NBA 2K Mobile card collection binder")
    @app_commands.describe(user="View another member's binder (optional)", tier="Filter by card tier (optional)")
    @app_commands.choices(tier=[
        app_commands.Choice(name="👑 Exclusive (99 OVR)", value="exclusive"),
        app_commands.Choice(name="🟣 Dark Matter (99 OVR)", value="dark_matter"),
        app_commands.Choice(name="🌌 Galaxy Opal (97-98 OVR)", value="galaxy_opal"),
        app_commands.Choice(name="💎 Diamond (93-96 OVR)", value="diamond"),
        app_commands.Choice(name="🔮 Amethyst (89-92 OVR)", value="amethyst"),
        app_commands.Choice(name="🔴 Ruby (84-88 OVR)", value="ruby"),
        app_commands.Choice(name="🟡 Gold / Emerald (80-83 OVR)", value="gold")
    ])
    @app_commands.guild_only()
    async def nbadex_slash(self, interaction: discord.Interaction, user: Optional[discord.Member] = None, tier: Optional[app_commands.Choice[str]] = None):
        await interaction.response.defer()
        target = user or interaction.user
        tier_val = tier.value if tier else None
        user_cards = await db.get_user_nba_cards(target.id)
        view = NBADexView(target, user_cards, tier_filter=tier_val)
        msg = await interaction.followup.send(embed=view.build_embed(), view=view)
        view.message = msg

    @app_commands.command(name="nbacard", description="🔍 Inspect a specific NBA 2K card's artwork, stats, and real moment")
    @app_commands.describe(card="Card ID or Player Name to inspect (e.g. 'curry', 'dm-jordan-99')")
    @app_commands.guild_only()
    async def nbacard_slash(self, interaction: discord.Interaction, card: str):
        await interaction.response.defer()
        card_obj = get_nba_card(card)
        if not card_obj:
            return await interaction.followup.send(f"❌ Card `{card}` was not found in catalog.", ephemeral=True)

        card_buf = await asyncio.to_thread(generate_nba_card_graphic, card_obj, is_mystery=False)
        file = discord.File(fp=card_buf, filename=f"{card_obj['id']}.png")
        tier_info = NBA_2K_TIERS.get(card_obj.get("tier", "gold"), NBA_2K_TIERS["gold"])
        embed = discord.Embed(
            title=f"{tier_info['emoji']} [{card_obj['ovr']} OVR] {card_obj['name']}",
            description=(
                f"• **Position:** `{card_obj.get('pos', 'SG')}` | **Team:** `{card_obj.get('team', 'NBA')}`\n"
                f"• **Tier:** {tier_info['emoji']} **{card_obj.get('tier', 'Gold').replace('_', ' ').title()}**\n"
                f"• **Real Moment:** *{get_nba_card_moment(card_obj)}*\n"
                f"• **Quicksell VC:** `💰 {card_obj.get('quicksell_vc', 100):,} VC`\n\n"
                f"**Player Ratings & Stats:**\n"
                f"🎯 `Inside: {card_obj.get('stats', {}).get('ins', 80)}` | 🏹 `Mid: {card_obj.get('stats', {}).get('ath', 80)}` | 🏀 `3PT: {card_obj.get('stats', {}).get('3pt', 80)}`\n"
                f"🛡️ `Defense: {card_obj.get('stats', {}).get('def', 80)}` | ⚡ `Playmaking: {card_obj.get('stats', {}).get('ply', 80)}` | 🏆 `Clutch: {card_obj.get('stats', {}).get('clu', 80)}`"
            ),
            color=discord.Color.from_rgb(*NBA_2K_CARD_THEMES.get(card_obj.get("tier", "gold"), {}).get("primary", (255, 215, 0)))
        )
        embed.set_image(url=f"attachment://{card_obj['id']}.png")
        embed.set_footer(text=f"NBA 2K Mobile Catalog • ID: {card_obj['id']}")
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed, file=file)

    @app_commands.command(name="nbafuse", description="🌟 Fuse 3 duplicate cards into a permanent Holo / Foil Edition (+5 OVR & +20% VC)")
    @app_commands.describe(card="Card ID or Player Name to fuse (requires 3 duplicate copies)")
    @app_commands.guild_only()
    async def nbafuse_slash(self, interaction: discord.Interaction, card: str):
        await interaction.response.defer()
        await handle_nbafuse(interaction.user, card, interaction.followup.send, is_interaction=True)

    @app_commands.command(name="nbafav", description="⭐ Favorite or protect an NBA card in your binder")
    @app_commands.describe(card="Card ID or Player Name to favorite/protect")
    @app_commands.guild_only()
    async def nbafav_slash(self, interaction: discord.Interaction, card: str):
        await interaction.response.defer()
        card_obj = get_nba_card(card)
        if not card_obj:
            return await interaction.followup.send(f"❌ Card `{card}` was not found.", ephemeral=True)
        await db.set_favorite_nba_card(interaction.user.id, card_obj["id"])
        await interaction.followup.send(f"⭐ **{card_obj['name']}** (`{card_obj['id']}`) is now set as your favorite / featured showcase card!")

    @app_commands.command(name="nbaprivacy", description="🔒 Toggle your NBA binder privacy (Public / Private)")
    @app_commands.guild_only()
    async def nbaprivacy_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        is_private = await db.toggle_user_binder_privacy(interaction.user.id)
        status_str = "🔒 **Private** (only you can view your binder)" if is_private else "🌐 **Public** (all server members can view)"
        await interaction.followup.send(f"✅ Your NBA card binder is now set to {status_str}.", ephemeral=True)

    # ── Prefix Commands ─────────────────────────────────────────────────────────

    @commands.command(name="nbadex", aliases=["dex", "binder", "cards"])
    @commands.guild_only()
    async def nbadex_prefix(self, ctx: commands.Context, *, raw_args: str = ""):
        """View your NBA card collection binder: !nbadex [@user] [tier]"""
        import re
        target_user = ctx.author
        tier_filter = None
        raw = raw_args.strip()

        if raw:
            tokens = raw.split()
            first_tok = tokens[0]
            m_match = re.match(r'^<@!?(\d+)>$', first_tok)
            if m_match and ctx.guild:
                target_user = ctx.guild.get_member(int(m_match.group(1))) or ctx.author
                tier_filter = " ".join(tokens[1:]).strip() if len(tokens) > 1 else None
            elif first_tok.isdigit() and len(first_tok) >= 17 and ctx.guild:
                target_user = ctx.guild.get_member(int(first_tok)) or ctx.author
                tier_filter = " ".join(tokens[1:]).strip() if len(tokens) > 1 else None
            else:
                tier_filter = raw

        user_cards = await db.get_user_nba_cards(target_user.id)
        view = NBADexView(target_user, user_cards, tier_filter=tier_filter)
        msg = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @commands.command(name="nbacard", aliases=["card", "cardinfo", "inspectcard"])
    @commands.guild_only()
    async def nbacard_prefix(self, ctx: commands.Context, *, query: str):
        """Inspect a specific card's stats and artwork: !nbacard <player/id>"""
        card_obj = get_nba_card(query)
        if not card_obj:
            return await ctx.send(f"❌ Card `{query}` was not found in catalog.")

        card_buf = await asyncio.to_thread(generate_nba_card_graphic, card_obj, is_mystery=False)
        file = discord.File(fp=card_buf, filename=f"{card_obj['id']}.png")
        tier_info = NBA_2K_TIERS.get(card_obj.get("tier", "gold"), NBA_2K_TIERS["gold"])
        embed = discord.Embed(
            title=f"{tier_info['emoji']} [{card_obj['ovr']} OVR] {card_obj['name']}",
            description=(
                f"• **Position:** `{card_obj.get('pos', 'SG')}` | **Team:** `{card_obj.get('team', 'NBA')}`\n"
                f"• **Tier:** {tier_info['emoji']} **{card_obj.get('tier', 'Gold').replace('_', ' ').title()}**\n"
                f"• **Real Moment:** *{get_nba_card_moment(card_obj)}*\n"
                f"• **Quicksell VC:** `💰 {card_obj.get('quicksell_vc', 100):,} VC`\n\n"
                f"**Player Ratings & Stats:**\n"
                f"🎯 `Inside: {card_obj.get('stats', {}).get('ins', 80)}` | 🏹 `Mid: {card_obj.get('stats', {}).get('ath', 80)}` | 🏀 `3PT: {card_obj.get('stats', {}).get('3pt', 80)}`\n"
                f"🛡️ `Defense: {card_obj.get('stats', {}).get('def', 80)}` | ⚡ `Playmaking: {card_obj.get('stats', {}).get('ply', 80)}` | 🏆 `Clutch: {card_obj.get('stats', {}).get('clu', 80)}`"
            ),
            color=discord.Color.from_rgb(*NBA_2K_CARD_THEMES.get(card_obj.get("tier", "gold"), {}).get("primary", (255, 215, 0)))
        )
        embed.set_image(url=f"attachment://{card_obj['id']}.png")
        embed.set_footer(text=f"NBA 2K Mobile Catalog • ID: {card_obj['id']}")
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed, file=file)

    @commands.command(name="nbafuse", aliases=["fuse", "holofuse", "forge"])
    @commands.guild_only()
    async def nbafuse_prefix(self, ctx: commands.Context, *, card: str):
        """Fuse 3 duplicate cards into a Holo Foil Edition: !nbafuse <card>"""
        await handle_nbafuse(ctx.author, card, ctx.send, is_interaction=False)

    @commands.command(name="nbafav", aliases=["favorite", "favcard"])
    @commands.guild_only()
    async def nbafav_prefix(self, ctx: commands.Context, *, card: str):
        """Favorite a card in your binder: !nbafav <card>"""
        card_obj = get_nba_card(card)
        if not card_obj:
            return await ctx.send(f"❌ Card `{card}` was not found.")
        await db.set_favorite_nba_card(ctx.author.id, card_obj["id"])
        await ctx.send(f"⭐ **{card_obj['name']}** (`{card_obj['id']}`) is now set as your favorite card!")

    @commands.command(name="nbaprivacy", aliases=["binderprivacy", "privacy"])
    @commands.guild_only()
    async def nbaprivacy_prefix(self, ctx: commands.Context):
        """Toggle your NBA binder privacy: !nbaprivacy"""
        is_private = await db.toggle_user_binder_privacy(ctx.author.id)
        status_str = "🔒 **Private** (only you can view your binder)" if is_private else "🌐 **Public** (all server members can view)"
        await ctx.send(f"✅ Your NBA card binder is now set to {status_str}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(NBACardsCog(bot))
