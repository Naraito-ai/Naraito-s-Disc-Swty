import sys
from unittest.mock import MagicMock

# Mock external modules that are installed in production environment
for mod in ["dotenv", "discord", "discord.ext", "discord.ext.commands", "discord.ext.tasks", "discord.app_commands", "aiosqlite", "asyncpg", "aiohttp", "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "PIL.ImageFilter", "psutil", "feedparser", "bs4", "jwt", "fastapi", "uvicorn", "google.generativeai"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import unittest
import asyncio
import sqlite3
import bot
import database

class TestNBASystemStability(unittest.TestCase):

    def test_catalog_integrity(self):
        """Test that NBA_2K_MOBILE_CARDS has no duplicate card IDs and has clean canonical cards."""
        card_ids = [c["id"].lower() for c in bot.NBA_2K_MOBILE_CARDS]
        self.assertEqual(len(card_ids), len(set(card_ids)), "Duplicate card IDs found in NBA_2K_MOBILE_CARDS!")
        self.assertGreater(len(card_ids), 150, "Catalog should have all stars & legends.")
        print(f"✅ NBA_2K_MOBILE_CARDS has {len(card_ids)} unique canonical cards.")

    def test_all_67_fusion_gifs(self):
        """Test that all 67 Dark Matter and Galaxy Opal cards have mapped GIFs and flavor texts."""
        dm_ids = [
            "dm-jordan-99", "dm-kobe-99", "dm-lebron-99", "dm-curry-99", "dm-shaq-99",
            "dm-kd-99", "dm-giannis-99", "dm-magic-99", "dm-bird-99", "dm-kareemabduljabbar-99",
            "dm-wiltchamberlain-99", "dm-billrussell-99", "dm-timduncan-99", "dm-hakeemolajuwon-99",
            "dm-wemby-99"
        ]
        go_98_ids = [
            "go-luka-98", "go-jokic-98", "go-embiid-98", "go-tatum-98", "go-tmac-98",
            "go-iverson-97", "go-alleniverson-97", "go-dwyanewade-98", "go-kevingarnett-98",
            "go-dirknowitzki-98", "go-charlesbarkley-98", "go-scottiepippen-98", "go-davidrobinson-98",
            "go-mosesmalone-98", "go-juliuserving-98", "go-johnstockton-98", "go-karlmalone-98",
            "go-clydedrexler-98", "go-patrickewing-98", "go-oscarrobertson-98", "go-jerrywest-98",
            "go-elginbaylor-98", "go-waltfrazier-98", "go-stevenash-98", "go-jasonkidd-98",
            "go-isiahthomas-98", "go-dominiquewilkins-98", "go-damianlillard-98", "go-kyrieirving-98",
            "go-paulgeorge-98"
        ]
        go_97_ids = [
            "go-ad-97", "go-kawhi-97", "go-butler-97", "go-jamesharden-97", "go-russellwestbrook-97",
            "go-chrispaul-97", "go-carmeloanthony-97", "go-vincecarter-97", "go-rayallen-97",
            "go-reggiemiller-97", "go-paulpierce-97", "go-garypayton-97", "go-dwighthoward-97",
            "go-alonzomourning-97", "go-dikembemutombo-97", "go-granthill-97", "go-tonyparker-97",
            "go-timhardaway-97", "go-petemaravich-97", "go-willisreed-97", "go-bobcousy-97",
            "go-rickbarry-97", "go-donovanmitchell-97"
        ]

        all_required = dm_ids + go_98_ids + go_97_ids
        self.assertEqual(len(all_required), 68)  # 68 including the 2 Iverson IDs

        for cid in all_required:
            self.assertIn(cid, bot.NBA_FUSION_GIF_MAPPINGS, f"Missing GIF mapping for {cid}")
            info = bot.NBA_FUSION_GIF_MAPPINGS[cid]
            self.assertTrue(info.get("gif_url"), f"Empty gif_url for {cid}")
            self.assertTrue(info.get("flavor_text"), f"Empty flavor_text for {cid}")

        # Check Iverson sharing
        self.assertEqual(
            bot.NBA_FUSION_GIF_MAPPINGS["go-iverson-97"]["gif_url"],
            bot.NBA_FUSION_GIF_MAPPINGS["go-alleniverson-97"]["gif_url"],
            "Allen Iverson cards must share the exact same GIF!"
        )
        print(f"✅ All 68 Dark Matter & Galaxy Opal card IDs verified in NBA_FUSION_GIF_MAPPINGS.")

    def test_legacy_and_alias_lookups(self):
        """Test that get_nba_card correctly resolves legacy IDs, player names, and aliases."""
        # 1. Mikal Bridges issue test
        card_bridges = bot.get_nba_card("bridges")
        self.assertIsNotNone(card_bridges)
        self.assertEqual(card_bridges["name"], "Mikal Bridges")

        card_legacy = bot.get_nba_card("ruby-mikalbridges-85")
        self.assertIsNotNone(card_legacy)
        self.assertEqual(card_legacy["name"], "Mikal Bridges")
        self.assertEqual(card_legacy["id"], "ruby-mikal-85")

        # 2. Derrick White legacy
        card_white = bot.get_nba_card("ruby-derrickwhite-86")
        self.assertIsNotNone(card_white)
        self.assertEqual(card_white["name"], "Derrick White")
        self.assertEqual(card_white["id"], "ruby-white-86")

        # 3. SGA legacy
        card_sga = bot.get_nba_card("dia-shaigilgeousalexander-95")
        self.assertIsNotNone(card_sga)
        self.assertEqual(card_sga["name"], "Shai Gilgeous-Alexander")
        self.assertEqual(card_sga["id"], "dia-sga-95")

        # 4. Jordan legacy
        card_mj = bot.get_nba_card("dm-mj-99")
        self.assertIsNotNone(card_mj)
        self.assertEqual(card_mj["id"], "dm-jordan-99")

        # 5. Caruso legacy
        card_caruso = bot.get_nba_card("gold-alexcaruso-81")
        self.assertIsNotNone(card_caruso)
        self.assertEqual(card_caruso["id"], "gold-caruso-81")

        print("✅ Legacy card lookups and canonical resolutions verified.")

    def test_selling_canonical_matching(self):
        """Test that user cards match canonical ID even if user owned legacy ID."""
        user_cards = [
            {"id": 101, "card_id": "ruby-mikalbridges-85"},
            {"id": 102, "card_id": "ruby-mikal-85"},
            {"id": 103, "card_id": "gold-curry-82"},
        ]
        target_card = bot.get_nba_card("bridges")
        cid = target_card["id"].lower()  # ruby-mikal-85

        matching = [
            c for c in user_cards
            if c["card_id"].lower() == cid
            or bot.NBA_LEGACY_CARD_MAPPINGS.get(c["card_id"].lower(), c["card_id"].lower()) == cid
            or (bot.get_nba_card(c["card_id"]) and bot.get_nba_card(c["card_id"])["id"].lower() == cid)
        ]
        self.assertEqual(len(matching), 2, "Should have found both ruby-mikal-85 and ruby-mikalbridges-85!")
        print(f"✅ Canonical seller matching found {len(matching)} copies for query 'bridges'.")

    def test_fusion_tier_rules(self):
        """Test tier rules: only Dark Matter & Galaxy Opal get GIFs, Diamond/Ruby/Gold do NOT."""
        dm_card = bot.get_nba_card("dm-jordan-99")
        self.assertIn(dm_card["tier"], ["dark_matter", "galaxy_opal"])
        self.assertIn(dm_card["id"], bot.NBA_FUSION_GIF_MAPPINGS)

        go_card = bot.get_nba_card("go-luka-98")
        self.assertIn(go_card["tier"], ["dark_matter", "galaxy_opal"])
        self.assertIn(go_card["id"], bot.NBA_FUSION_GIF_MAPPINGS)

        dia_card = bot.get_nba_card("dia-sga-95")
        self.assertNotIn(dia_card["tier"], ["dark_matter", "galaxy_opal"])

        ruby_card = bot.get_nba_card("ruby-mikal-85")
        self.assertNotIn(ruby_card["tier"], ["dark_matter", "galaxy_opal"])

        gold_card = bot.get_nba_card("gold-caruso-81")
        self.assertNotIn(gold_card["tier"], ["dark_matter", "galaxy_opal"])

        print("✅ Tier-based GIF gating verified (Dark Matter/Galaxy Opal only).")

    def test_holo_card_boosts(self):
        """Test that get_nba_card with holo flag boosts OVR by +5 and sets is_holo flag."""
        card = bot.get_nba_card("dm-jordan-99")
        holo = bot.get_nba_card("holo_dm-jordan-99")
        self.assertTrue(holo["is_holo"])
        self.assertEqual(holo["ovr"], min(100, card["ovr"] + 5))
        self.assertTrue(holo["id"].startswith("holo_"))
        print(f"✅ Holo boost calculation verified ({card['ovr']} OVR -> {holo['ovr']} OVR).")

if __name__ == "__main__":
    unittest.main()
