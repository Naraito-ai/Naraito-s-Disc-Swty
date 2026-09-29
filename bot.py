# -*- coding: utf-8 -*-
"""
bot.py - SweetyBot Production Entry Point & Backward Compatibility Gateway
Forwards execution to modular main.py and re-exports shared NBA data definitions.
"""
from __future__ import annotations

import os
import sys
import asyncio

# Re-export all database and bot instances
from database import db, DatabaseManager
from main import bot, SweetyBot, GeminiBot, main, COGS_TO_LOAD

# Re-export all shared NBA constants, mappings, and generator helpers
from nba_data import (
    NBA_2K_TIERS,
    NBA_2K_CARD_THEMES,
    NBA_LEGACY_CARD_MAPPINGS,
    NBA_PACK_TYPES,
    NBA_2K_MOBILE_CARDS,
    NBA_CARDS_BY_ID,
    NBA_FUSION_GIF_MAPPINGS,
    NBA_DREAM_PLAYERS,
    DAILY_BOSS_PRESETS,
    GM_RANKS,
    get_nba_card,
    get_nba_card_moment,
    generate_nba_card_graphic,
    get_nba_player_moment_photo,
    get_nba_player_headshot,
    find_nba_player,
    roll_pack_card,
    build_openpack_embed,
    build_pack_shop_embed,
    _build_odds_lines,
    evaluate_dream_team,
    extract_picks_from_row,
    ensure_sweety_ai_team,
    get_gm_rank,
    card_to_player_dict,
    is_creator,
    clean_memory,
    is_valid_drop_channel,
    get_best_drop_channel,
    normalize_nba_text,
    is_correct_player_name,
    generate_player_hint
)

# Re-export fusion handler from nba_cards cog for backward compatibility
from cogs.nba_cards import handle_nbafuse, build_nbacard_embed, build_nbadex_embed

if __name__ == "__main__":
    asyncio.run(main())
