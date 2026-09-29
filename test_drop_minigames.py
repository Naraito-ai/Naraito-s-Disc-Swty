# -*- coding: utf-8 -*-
"""
test_drop_minigames.py - Unit test suite for wild card drops, modal guessing, and timeout prevention
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from database import db
from nba_data import get_nba_card, is_correct_player_name, generate_player_hint, NBA_2K_MOBILE_CARDS
from cogs.nba_minigames import (
    NBAChatDropView,
    NBACatchModal,
    handle_catch_attempt,
    spawn_nba_card_drop,
    _active_nba_drops
)


class TestDropMinigames(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await db.initialize()
        _active_nba_drops.clear()

    def test_player_name_matching(self):
        """Test flexible player name matching for chat guessing."""
        # Jrue Holiday
        self.assertTrue(is_correct_player_name("Jrue Holiday", "Jrue Holiday"))
        self.assertTrue(is_correct_player_name("jrue holiday", "Jrue Holiday"))
        self.assertTrue(is_correct_player_name("jrue", "Jrue Holiday"))
        self.assertTrue(is_correct_player_name("holiday", "Jrue Holiday"))

        # Stephen Curry / Steph / Curry
        self.assertTrue(is_correct_player_name("Stephen Curry", "Stephen Curry"))
        self.assertTrue(is_correct_player_name("Steph Curry", "Stephen Curry"))
        self.assertTrue(is_correct_player_name("curry", "Stephen Curry"))

        # Victor Wembanyama / Wemby
        self.assertTrue(is_correct_player_name("Wemby", "Victor Wembanyama"))
        self.assertTrue(is_correct_player_name("Wembanyama", "Victor Wembanyama"))

        # Michael Jordan / MJ
        self.assertTrue(is_correct_player_name("MJ", "Michael Jordan"))
        self.assertTrue(is_correct_player_name("Jordan", "Michael Jordan"))

    def test_progressive_hint_generation(self):
        """Test hint levels reveal progressive letters."""
        name = "Jrue Holiday"
        h1 = generate_player_hint(name, hint_level=1)
        h2 = generate_player_hint(name, hint_level=2)
        h3 = generate_player_hint(name, hint_level=3)
        self.assertIn(r"\_", h1)
        self.assertTrue(len(h1) > 0)
        self.assertTrue(len(h2) > 0)
        self.assertTrue(len(h3) > 0)

    async def test_catch_attempt_success(self):
        """Test handle_catch_attempt successfully grants card, VC, and edits drop message."""
        card = get_nba_card("ruby-jrue-86") or NBA_2K_MOBILE_CARDS[0]
        channel_id = 999111222
        guild_id = 888777666
        user_id = 719932313919684670

        drop_info = {
            "card": card,
            "drop_id": f"{guild_id}_{channel_id}_12345",
            "channel_id": channel_id,
            "guild_id": guild_id,
            "spawned_at": 1000000.0,
            "hint_level": 1,
            "claimed": False,
            "claimed_by_id": None,
            "claimed_by_name": None,
            "spawner_id": None,
            "message": AsyncMock()
        }
        _active_nba_drops[channel_id] = drop_info

        # Mock interaction
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.user.id = user_id
        mock_interaction.user.display_name = "Naraito"
        mock_interaction.channel_id = channel_id
        mock_interaction.guild_id = guild_id
        mock_interaction.response.is_done.return_value = False
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()

        init_vc = await db.get_user_vc(user_id)
        await handle_catch_attempt(mock_interaction, "Jrue Holiday", channel_id=channel_id, drop=drop_info)

        # Assert drop marked claimed
        self.assertTrue(drop_info["claimed"])
        self.assertEqual(drop_info["claimed_by_id"], user_id)

        # Assert VC rewarded
        new_vc = await db.get_user_vc(user_id)
        self.assertEqual(new_vc, init_vc + 150)

        # Assert response sent
        mock_interaction.followup.send.assert_called_once()
        sent_embed = mock_interaction.followup.send.call_args.kwargs.get("embed")
        self.assertIsNotNone(sent_embed)
        self.assertIn("Card Caught by Naraito", sent_embed.title)

    async def test_modal_and_view_deferral_protection(self):
        """Test that NBACatchModal and NBAChatDropView hint button defer immediately on line 1."""
        channel_id = 999111222
        drop_id = "test_drop_123"
        card = get_nba_card("ruby-jrue-86") or NBA_2K_MOBILE_CARDS[0]
        drop_info = {
            "card": card,
            "drop_id": drop_id,
            "channel_id": channel_id,
            "guild_id": 888777666,
            "spawned_at": 1000000.0,
            "hint_level": 1,
            "claimed": False,
            "claimed_by_id": None,
            "claimed_by_name": None,
            "spawner_id": None,
            "message": AsyncMock()
        }
        _active_nba_drops[channel_id] = drop_info

        # 1. Test modal submit
        modal = NBACatchModal(channel_id, drop_id)
        modal.player_guess._value = "Jrue Holiday"

        mock_modal_interaction = MagicMock(spec=discord.Interaction)
        mock_modal_interaction.user.id = 719932313919684670
        mock_modal_interaction.user.display_name = "Naraito"
        mock_modal_interaction.channel_id = channel_id
        mock_modal_interaction.guild_id = 888777666
        mock_modal_interaction.response.is_done.return_value = False
        def mock_modal_defer(**kwargs):
            mock_modal_interaction.response.is_done.return_value = True
        mock_modal_interaction.response.defer = AsyncMock(side_effect=mock_modal_defer)
        mock_modal_interaction.followup.send = AsyncMock()

        await modal.on_submit(mock_modal_interaction)
        self.assertTrue(mock_modal_interaction.response.is_done())

        # 2. Test hint button
        drop_info["claimed"] = False
        drop_info["hint_level"] = 1
        view = NBAChatDropView(card, drop_id, channel_id)

        mock_btn_interaction = MagicMock(spec=discord.Interaction)
        mock_btn_interaction.user.id = 719932313919684670
        mock_btn_interaction.channel_id = channel_id
        mock_btn_interaction.guild_id = 888777666
        mock_btn_interaction.response.is_done.return_value = False
        mock_btn_interaction.response.defer = AsyncMock()
        mock_btn_interaction.followup.send = AsyncMock()

        await view.hint_btn.callback(mock_btn_interaction)
        mock_btn_interaction.response.defer.assert_called_once_with(ephemeral=True)
        self.assertEqual(drop_info["hint_level"], 2)

    async def test_spawn_nba_card_drop(self):
        """Test spawn_nba_card_drop builds mystery image, embed, and registers active drop."""
        mock_channel = AsyncMock(spec=discord.TextChannel)
        mock_channel.id = 123456789
        mock_channel.guild.id = 987654321
        mock_msg = MagicMock(spec=discord.Message)
        mock_channel.send.return_value = mock_msg

        card = get_nba_card("ruby-jrue-86") or NBA_2K_MOBILE_CARDS[0]
        res = await spawn_nba_card_drop(mock_channel, card_override=card)

        self.assertIsNotNone(res)
        self.assertIn(mock_channel.id, _active_nba_drops)
        active = _active_nba_drops[mock_channel.id]
        self.assertEqual(active["card"]["id"], card["id"])
        mock_channel.send.assert_called_once()
        sent_embed = mock_channel.send.call_args.kwargs.get("embed")
        self.assertIsNotNone(sent_embed)
        self.assertIn("A wild NBA 2K card appeared!", sent_embed.title)


if __name__ == "__main__":
    unittest.main()
