from __future__ import annotations

import os
import re
import json
import logging
import asyncio
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Union, Set

logger = logging.getLogger("GeminiBot.Database")

class DatabaseManager:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.is_postgres = False
        self.pg_pool = None
        self.sqlite_conn = None
        self._sqlite_lock = asyncio.Lock()  # Prevent SQLite write locks
        self._config_cache: Dict[tuple, Any] = {}  # Cache for guild configurations

        # Detect database type
        if self.db_url and (self.db_url.startswith("postgres://") or self.db_url.startswith("postgresql://")):
            self.is_postgres = True
            # asyncpg requires postgresql:// protocol
            if self.db_url.startswith("postgres://"):
                self.db_url = self.db_url.replace("postgres://", "postgresql://", 1)

    async def initialize(self):
        """Initializes connection pools and creates tables if they do not exist."""
        if self.is_postgres:
            try:
                import asyncpg
                logger.info("Initializing PostgreSQL database connection...")
                self.pg_pool = await asyncpg.create_pool(
                    self.db_url,
                    min_size=0,
                    max_size=5,
                    statement_cache_size=0,
                    max_inactive_connection_lifetime=60.0,
                    command_timeout=30.0
                )
                logger.info("PostgreSQL connection pool created successfully.")
            except ImportError:
                logger.error("asyncpg is not installed, falling back to SQLite!")
                self.is_postgres = False
            except Exception as e:
                logger.error(f"Failed to connect to PostgreSQL: {e}. Falling back to SQLite!")
                self.is_postgres = False

        if not self.is_postgres:
            import aiosqlite
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_data.db")
            logger.info(f"Initializing local SQLite database at {db_path}...")
            self.sqlite_conn = await aiosqlite.connect(db_path)
            # Enable WAL mode for better concurrency in SQLite
            await self.sqlite_conn.execute("PRAGMA journal_mode=WAL;")
            await self.sqlite_conn.commit()

        # Create tables
        await self._create_tables()

    async def _create_tables(self):
        """Creates database schema for all bot modules and dashboard tracking."""
        queries = [
            # Guilds Table
            """
            CREATE TABLE IF NOT EXISTS guilds (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                icon TEXT,
                owner_id TEXT,
                member_count INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ai_enabled BOOLEAN DEFAULT TRUE,
                logging_enabled BOOLEAN DEFAULT FALSE
            );
            """,
            # Guild Resources
            """
            CREATE TABLE IF NOT EXISTS guild_resources (
                guild_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id BIGINT NOT NULL
            );
            """,
            # Guild Config
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (guild_id, key)
            );
            """,
            # Users Table
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                discriminator TEXT,
                avatar TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Commands Tracking Table
            """
            CREATE TABLE IF NOT EXISTS commands (
                id SERIAL PRIMARY KEY,
                guild_id TEXT,
                user_id TEXT,
                command_name TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                latency REAL
            );
            """,
            # Warnings Table
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                moderator_id TEXT NOT NULL,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Timeouts Table
            """
            CREATE TABLE IF NOT EXISTS timeouts (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                moderator_id TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Bans Table
            """
            CREATE TABLE IF NOT EXISTS bans (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                moderator_id TEXT NOT NULL,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # AI Usage Tracking Table
            """
            CREATE TABLE IF NOT EXISTS ai_usage (
                id SERIAL PRIMARY KEY,
                guild_id TEXT,
                user_id TEXT,
                prompt TEXT,
                response TEXT,
                model TEXT,
                tokens_used INTEGER DEFAULT 0,
                latency REAL DEFAULT 0.0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # API Usage Table
            """
            CREATE TABLE IF NOT EXISTS api_usage (
                id SERIAL PRIMARY KEY,
                guild_id TEXT,
                endpoint TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Backups Table
            """
            CREATE TABLE IF NOT EXISTS backups (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                backup_data TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Audit Logs Table
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Notifications Table
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                guild_id TEXT,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                type TEXT NOT NULL,
                read BOOLEAN DEFAULT FALSE,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Errors Table
            """
            CREATE TABLE IF NOT EXISTS errors (
                id SERIAL PRIMARY KEY,
                guild_id TEXT,
                error_type TEXT NOT NULL,
                message TEXT NOT NULL,
                stack_trace TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Analytics Table
            """
            CREATE TABLE IF NOT EXISTS analytics (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                date DATE DEFAULT CURRENT_DATE,
                messages_count INTEGER DEFAULT 0,
                commands_count INTEGER DEFAULT 0,
                joins_count INTEGER DEFAULT 0,
                leaves_count INTEGER DEFAULT 0,
                warnings_count INTEGER DEFAULT 0,
                mutes_count INTEGER DEFAULT 0,
                bans_count INTEGER DEFAULT 0,
                voice_active_seconds INTEGER DEFAULT 0
            );
            """,
            # Reminders Table
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                guild_id TEXT,
                channel_id TEXT NOT NULL,
                reminder_text TEXT NOT NULL,
                remind_at REAL NOT NULL,
                created_at REAL NOT NULL,
                delivery_method TEXT DEFAULT 'dm'
            );
            """,
            # AFK Users Table
            """
            CREATE TABLE IF NOT EXISTS afk_users (
                user_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                afk_since REAL NOT NULL,
                PRIMARY KEY (user_id, guild_id)
            );
            """,
            # Dream Teams Table ($15 All-Time Lineup Builder)
            """
            CREATE TABLE IF NOT EXISTS dream_teams (
                user_id TEXT PRIMARY KEY,
                guild_id TEXT,
                pg TEXT NOT NULL,
                sg TEXT NOT NULL,
                sf TEXT NOT NULL,
                pf TEXT NOT NULL,
                c TEXT NOT NULL,
                total_cost INTEGER NOT NULL,
                ovr_rating REAL NOT NULL,
                team_data TEXT,
                updated_at REAL NOT NULL
            );
            """,
            # Team Battle Stats & Career Records Table
            """
            CREATE TABLE IF NOT EXISTS team_battle_stats (
                user_id TEXT PRIMARY KEY,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                ties INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0,
                total_duels_won INTEGER DEFAULT 0,
                total_points INTEGER DEFAULT 0,
                daily_wins INTEGER DEFAULT 0,
                last_daily_win_date TEXT DEFAULT '',
                achievements TEXT DEFAULT '[]',
                coaching_dna TEXT DEFAULT '{}',
                updated_at REAL NOT NULL
            );
            """,
            # Head-to-Head NBA Member Rivalries Table
            """
            CREATE TABLE IF NOT EXISTS nba_rivalries (
                player_a TEXT NOT NULL,
                player_b TEXT NOT NULL,
                wins_a INTEGER DEFAULT 0,
                wins_b INTEGER DEFAULT 0,
                ties INTEGER DEFAULT 0,
                last_5 TEXT DEFAULT '[]',
                updated_at REAL NOT NULL,
                PRIMARY KEY (player_a, player_b)
            );
            """,
            # User Snipe 30-Day History Table
            """
            CREATE TABLE IF NOT EXISTS user_snipe_history (
                id SERIAL PRIMARY KEY,
                message_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                channel_name TEXT DEFAULT '',
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                user_display_name TEXT DEFAULT '',
                user_avatar TEXT,
                content TEXT,
                attachments_json TEXT DEFAULT '[]',
                stickers_json TEXT DEFAULT '[]',
                message_type TEXT DEFAULT 'deleted',
                before_content TEXT,
                after_content TEXT,
                created_at REAL NOT NULL,
                recorded_at REAL NOT NULL
            );
            """,
            # Fast index for 30-day user snipe lookup
            """
            CREATE INDEX IF NOT EXISTS idx_user_snipe_lookup ON user_snipe_history(guild_id, user_id, recorded_at);
            """,
            # Active Scheduled Mutes Table (7-Day Role Mute Tracking)
            """
            CREATE TABLE IF NOT EXISTS active_mutes (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role_id TEXT,
                unmute_at REAL NOT NULL,
                reason TEXT,
                created_at REAL NOT NULL,
                UNIQUE(guild_id, user_id)
            );
            """,
            # Appeal Tickets Table
            """
            CREATE TABLE IF NOT EXISTS appeal_tickets (
                id SERIAL PRIMARY KEY,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                reason TEXT,
                additional_info TEXT,
                created_at REAL NOT NULL,
                resolved_at REAL,
                resolved_by TEXT
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_active_mutes ON active_mutes(guild_id, user_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_appeal_tickets ON appeal_tickets(channel_id, status);
            """,
            # User Memories Table (Persistent AI Memory & Personalization)
            """
            CREATE TABLE IF NOT EXISTS user_memories (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                guild_id TEXT,
                fact_key TEXT NOT NULL,
                fact_value TEXT NOT NULL,
                source TEXT DEFAULT 'manual',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(user_id, fact_key)
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_user_memories_lookup ON user_memories(user_id, updated_at);
            """,
            # Permanent User Blacklist Table
            """
            CREATE TABLE IF NOT EXISTS blacklisted_users (
                user_id TEXT PRIMARY KEY,
                reason TEXT DEFAULT 'No reason provided',
                blacklisted_by TEXT,
                blacklisted_at REAL NOT NULL
            );
            """,
            # NBA 2K Mobile Cards Inventory Table
            """
            CREATE TABLE IF NOT EXISTS user_nba_cards (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                card_id TEXT NOT NULL,
                obtained_at REAL NOT NULL,
                source TEXT DEFAULT 'pack',
                is_favorite BOOLEAN DEFAULT FALSE,
                lineup_pos TEXT DEFAULT ''
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_user_nba_cards_lookup ON user_nba_cards(user_id, card_id);
            """,
            # NBA 2K Mobile Economy & Stats Table
            """
            CREATE TABLE IF NOT EXISTS user_nba_economy (
                user_id TEXT PRIMARY KEY,
                vc_balance INTEGER DEFAULT 1000,
                packs_opened INTEGER DEFAULT 0,
                cards_claimed INTEGER DEFAULT 0,
                last_daily_claim REAL DEFAULT 0.0,
                last_weekly_claim REAL DEFAULT 0.0,
                last_monthly_claim REAL DEFAULT 0.0,
                is_private INTEGER DEFAULT 0
            );
            """,
            # NBA 3-Point Shootout Contest Records Table
            """
            CREATE TABLE IF NOT EXISTS nba_shootout_scores (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                score INTEGER NOT NULL,
                money_made INTEGER DEFAULT 0,
                starry_made INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_nba_shootout_scores_user ON nba_shootout_scores(user_id);
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_nba_shootout_scores_score ON nba_shootout_scores(score DESC);
            """,
            # NBA Events System Table
            """
            CREATE TABLE IF NOT EXISTS nba_events (
                id SERIAL PRIMARY KEY,
                guild_id TEXT,
                name TEXT NOT NULL,
                description TEXT,
                event_type TEXT DEFAULT 'custom',
                target_tier TEXT,
                prize_card_id TEXT NOT NULL,
                prize_card_name TEXT,
                channel_id TEXT,
                creator_id TEXT DEFAULT '719932313919684670',
                created_at REAL NOT NULL,
                ends_at REAL NOT NULL,
                status TEXT DEFAULT 'active',
                rules TEXT,
                boss_name TEXT,
                boss_hp INTEGER DEFAULT 0,
                boss_max_hp INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            );
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_nba_events_status ON nba_events(status, guild_id);
            """,
            # NBA Event Winners Table
            """
            CREATE TABLE IF NOT EXISTS nba_event_winners (
                id SERIAL PRIMARY KEY,
                event_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                card_id TEXT NOT NULL,
                card_name TEXT,
                rewarded_at REAL NOT NULL,
                rewarded_by TEXT DEFAULT '719932313919684670'
            );
            """,
            # NBA Event Raid Boss Damage Tracking Table
            """
            CREATE TABLE IF NOT EXISTS nba_event_raid_damage (
                event_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                damage_dealt INTEGER DEFAULT 0,
                last_attack_at REAL NOT NULL,
                PRIMARY KEY (event_id, user_id)
            );
            """
        ]
        
        for query in queries:
            await self.execute(query)

        # Non-destructive column migrations
        try:
            if not self.is_postgres:
                cols = await self.fetch("PRAGMA table_info(team_battle_stats);")
                col_names = [c["name"] for c in cols] if cols else []
                if "daily_wins" not in col_names:
                    await self.execute("ALTER TABLE team_battle_stats ADD COLUMN daily_wins INTEGER DEFAULT 0;")
                if "last_daily_win_date" not in col_names:
                    await self.execute("ALTER TABLE team_battle_stats ADD COLUMN last_daily_win_date TEXT DEFAULT '';")
                if "coaching_dna" not in col_names:
                    await self.execute("ALTER TABLE team_battle_stats ADD COLUMN coaching_dna TEXT DEFAULT '{}';")
            if not self.is_postgres:
                eco_cols = await self.fetch("PRAGMA table_info(user_nba_economy);")
                eco_col_names = [c["name"] for c in eco_cols] if eco_cols else []
                if "is_private" not in eco_col_names:
                    await self.execute("ALTER TABLE user_nba_economy ADD COLUMN is_private INTEGER DEFAULT 0;")
                if "last_weekly_claim" not in eco_col_names:
                    await self.execute("ALTER TABLE user_nba_economy ADD COLUMN last_weekly_claim REAL DEFAULT 0.0;")
                if "last_monthly_claim" not in eco_col_names:
                    await self.execute("ALTER TABLE user_nba_economy ADD COLUMN last_monthly_claim REAL DEFAULT 0.0;")
            else:
                await self.execute("ALTER TABLE user_nba_economy ADD COLUMN IF NOT EXISTS is_private INTEGER DEFAULT 0;")
                await self.execute("ALTER TABLE user_nba_economy ADD COLUMN IF NOT EXISTS last_weekly_claim REAL DEFAULT 0.0;")
                await self.execute("ALTER TABLE user_nba_economy ADD COLUMN IF NOT EXISTS last_monthly_claim REAL DEFAULT 0.0;")
        except Exception as alter_err:
            logger.debug(f"Column check for team_battle_stats/economy: {alter_err}")
            
        logger.info("Database tables verified/created successfully.")

    async def execute(self, query: str, *args):
        """Executes a write query (INSERT, UPDATE, DELETE)."""
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                # asyncpg uses $1, $2 for placeholders instead of ? (SQLite)
                pg_query = query
                if "?" in query:
                    parts = query.split("?")
                    pg_query = "".join(f"{part}${i+1}" for i, part in enumerate(parts[:-1])) + parts[-1]
                await conn.execute(pg_query, *args)
        else:
            async with self._sqlite_lock:
                sqlite_query = query
                if re.search(r'\$\d+', sqlite_query):
                    sqlite_query = re.sub(r'\$\d+', '?', sqlite_query)
                if "SERIAL PRIMARY KEY" in sqlite_query:
                    sqlite_query = sqlite_query.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                await self.sqlite_conn.execute(sqlite_query, args)
                await self.sqlite_conn.commit()

    async def executemany(self, query: str, args_list: List[tuple]):
        """Executes a parameterized write query across multiple parameter tuples in a single transaction."""
        if not args_list:
            return
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                pg_query = query
                if "?" in query:
                    parts = query.split("?")
                    pg_query = "".join(f"{part}${i+1}" for i, part in enumerate(parts[:-1])) + parts[-1]
                await conn.executemany(pg_query, args_list)
        else:
            async with self._sqlite_lock:
                sqlite_query = query
                if re.search(r'\$\d+', sqlite_query):
                    sqlite_query = re.sub(r'\$\d+', '?', sqlite_query)
                if "SERIAL PRIMARY KEY" in sqlite_query:
                    sqlite_query = sqlite_query.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                await self.sqlite_conn.executemany(sqlite_query, args_list)
                await self.sqlite_conn.commit()

    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        """Fetches multiple records as a list of dicts."""
        if self.is_postgres:
            async with self.pg_pool.acquire() as conn:
                pg_query = query
                if "?" in query:
                    parts = query.split("?")
                    pg_query = "".join(f"{part}${i+1}" for i, part in enumerate(parts[:-1])) + parts[-1]
                records = await conn.fetch(pg_query, *args)
                return [dict(r) for r in records]
        else:
            async with self._sqlite_lock:
                sqlite_query = query
                if re.search(r'\$\d+', sqlite_query):
                    sqlite_query = re.sub(r'\$\d+', '?', sqlite_query)
                if "SERIAL PRIMARY KEY" in sqlite_query:
                    sqlite_query = sqlite_query.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                async with self.sqlite_conn.execute(sqlite_query, args) as cursor:
                    rows = await cursor.fetchall()
                    if cursor.description is None:
                        return []
                    columns = [description[0] for description in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]

    async def fetchrow(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """Fetches a single record as a dict."""
        results = await self.fetch(query, *args)
        return results[0] if results else None

    # ── Resource Management Queries ─────────────────────────────────────────

    async def add_resource(self, guild_id: Any, resource_type: str, resource_id: Any):
        """Saves a created role, channel, or category to the database."""
        query = "INSERT INTO guild_resources (guild_id, resource_type, resource_id) VALUES (?, ?, ?)"
        await self.execute(query, str(guild_id), resource_type, int(resource_id))

    async def get_resources(self, guild_id: Any, resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Gets all resources of a type for a guild."""
        if resource_type:
            query = "SELECT resource_id FROM guild_resources WHERE guild_id = ? AND resource_type = ?"
            rows = await self.fetch(query, str(guild_id), resource_type)
        else:
            query = "SELECT resource_type, resource_id FROM guild_resources WHERE guild_id = ?"
            rows = await self.fetch(query, str(guild_id))
        return rows

    async def clear_resources(self, guild_id: Any):
        """Deletes all tracked resource records for a guild from the database."""
        query = "DELETE FROM guild_resources WHERE guild_id = ?"
        await self.execute(query, str(guild_id))

    async def delete_resources_by_type(self, guild_id: Any, resource_type: str):
        """Deletes all tracked resource records of a specific type for a guild."""
        query = "DELETE FROM guild_resources WHERE guild_id = ? AND resource_type = ?"
        await self.execute(query, str(guild_id), str(resource_type))

    async def delete_resource_by_id(self, resource_id: Any):
        """Deletes all tracked resource records matching a resource_id."""
        query = "DELETE FROM guild_resources WHERE resource_id = ?"
        await self.execute(query, int(resource_id))

    async def delete_resource(self, guild_id: Any, resource_id: Any):
        """Deletes a specific resource record in a guild."""
        query = "DELETE FROM guild_resources WHERE guild_id = ? AND resource_id = ?"
        await self.execute(query, str(guild_id), int(resource_id))

    async def get_temp_voice_resources(self) -> List[Dict[str, Any]]:
        """Fetches all temporary voice channel resource IDs."""
        return await self.fetch("SELECT resource_id FROM guild_resources WHERE resource_type IN ('temp_voice', 'temp_voice_channels')")

    # ── Guild Configuration Queries ──────────────────────────────────────────

    async def set_config(self, guild_id: Any, key: str, value: Any):
        """Sets a configuration option with atomic upsert."""
        query = """
            INSERT INTO guild_config (guild_id, key, value) 
            VALUES (?, ?, ?) 
            ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value
        """
        await self.execute(query, str(guild_id), key, str(value))
        
        # Update cache
        self._config_cache[(str(guild_id), key)] = str(value)

    def _parse_config_value(self, val: Any) -> Any:
        if val == "True" or val is True: return True
        if val == "False" or val is False: return False
        if val == "None" or val is None: return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return val

    async def get_config(self, guild_id: Any, key: str, default: Any = None) -> Any:
        """Gets a configuration option with caching."""
        cache_key = (str(guild_id), key)
        if cache_key in self._config_cache:
            val = self._config_cache[cache_key]
            return self._parse_config_value(val)

        query = "SELECT value FROM guild_config WHERE guild_id = ? AND key = ?"
        row = await self.fetchrow(query, str(guild_id), key)
        if row:
            val = row["value"]
            self._config_cache[cache_key] = val
            return self._parse_config_value(val)
        
        # Cache negative/default values too to prevent repeat misses
        self._config_cache[cache_key] = "None" if default is None else str(default)
        return default

    async def get_promo_channels(self, guild_id: Any) -> List[int]:
        """Gets all designated links-only / promo channel IDs for a guild."""
        val = await self.get_config(guild_id, "promo_channels", "[]")
        if isinstance(val, list):
            return [int(x) for x in val]
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [int(x) for x in parsed]
            except Exception:
                pass
        return []

    async def add_promo_channel(self, guild_id: Any, channel_id: int) -> bool:
        """Adds a channel to the links-only promo list."""
        channels = await self.get_promo_channels(guild_id)
        cid = int(channel_id)
        if cid not in channels:
            channels.append(cid)
            await self.set_config(guild_id, "promo_channels", json.dumps(channels))
            return True
        return False

    async def remove_promo_channel(self, guild_id: Any, channel_id: int) -> bool:
        """Removes a channel from the links-only promo list."""
        channels = await self.get_promo_channels(guild_id)
        cid = int(channel_id)
        if cid in channels:
            channels.remove(cid)
            await self.set_config(guild_id, "promo_channels", json.dumps(channels))
            return True
        return False

    # ── Dashboard Helper Queries ──────────────────────────────────────────

    async def increment_analytics(self, guild_id: Any, column_name: str, amount: int = 1):
        """Increments a specific statistic counter in the analytics table for today."""
        # Whitelist columns to prevent any arbitrary injection
        valid_columns = {
            "messages_count", "commands_count", "joins_count", "leaves_count",
            "warnings_count", "mutes_count", "bans_count", "voice_active_seconds"
        }
        if column_name not in valid_columns:
            logger.warning(f"Invalid analytics column name: {column_name}")
            return

        try:
            today_val = datetime.now().date() if self.is_postgres else datetime.now().date().isoformat()
            rows = await self.fetch(
                "SELECT id FROM analytics WHERE guild_id = ? AND date = ?",
                str(guild_id),
                today_val
            )
            if rows:
                query = f"UPDATE analytics SET {column_name} = {column_name} + ? WHERE guild_id = ? AND date = ?"
                await self.execute(query, amount, str(guild_id), today_val)
            else:
                query = f"INSERT INTO analytics (guild_id, date, {column_name}) VALUES (?, ?, ?)"
                await self.execute(query, str(guild_id), today_val, amount)
        except Exception as e:
            logger.error(f"Failed to increment analytics: {e}")

    async def log_command(self, guild_id: Any, user_id: Any, command_name: str, status: str, latency: float):
        """Logs a slash command execution."""
        query = "INSERT INTO commands (guild_id, user_id, command_name, status, latency) VALUES (?, ?, ?, ?, ?)"
        await self.execute(query, str(guild_id) if guild_id else None, str(user_id), command_name, status, latency)
        if guild_id:
            await self.increment_analytics(guild_id, "commands_count")

    async def log_ai_usage(self, guild_id: Any, user_id: Any, prompt: str, response: str, model: str, tokens_used: int, latency: float):
        """Logs an AI query usage entry."""
        query = "INSERT INTO ai_usage (guild_id, user_id, prompt, response, model, tokens_used, latency) VALUES (?, ?, ?, ?, ?, ?, ?)"
        await self.execute(query, str(guild_id) if guild_id else None, str(user_id), prompt, response, model, tokens_used, latency)

    async def add_warning(self, guild_id: Any, user_id: Any, moderator_id: Any, reason: str):
        """Logs a member warning."""
        query = "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)"
        await self.execute(query, str(guild_id), str(user_id), str(moderator_id), reason)
        await self.increment_analytics(guild_id, "warnings_count")

    async def get_warnings(self, guild_id: Any, user_id: Any) -> list:
        """Retrieves all warnings for a user in a guild."""
        query = "SELECT id, moderator_id, reason, timestamp FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC"
        return await self.fetch(query, str(guild_id), str(user_id))

    async def clear_warnings(self, guild_id: Any, user_id: Any, amount: Optional[int] = None) -> int:
        """Deletes warnings for a user in a guild (all or limited amount) and returns count deleted."""
        if amount is not None and amount > 0:
            rows = await self.fetch(
                "SELECT id FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC, id DESC LIMIT ?",
                str(guild_id), str(user_id), int(amount)
            )
            if not rows:
                return 0
            ids = [r["id"] if isinstance(r, dict) and "id" in r else r[0] for r in rows]
            placeholders = ", ".join(["?"] * len(ids))
            query = f"DELETE FROM warnings WHERE id IN ({placeholders})"
            await self.execute(query, *ids)
            return len(ids)
        else:
            rows = await self.fetch("SELECT COUNT(*) as count FROM warnings WHERE guild_id = ? AND user_id = ?", str(guild_id), str(user_id))
            count = rows[0]["count"] if rows and isinstance(rows[0], dict) and "count" in rows[0] else (rows[0][0] if rows else 0)
            query = "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?"
            await self.execute(query, str(guild_id), str(user_id))
            return int(count)

    async def delete_warning_by_id(self, guild_id: Any, warn_id: int) -> bool:
        """Deletes a specific warning by its ID. Returns True if deleted, False if not found."""
        rows = await self.fetch("SELECT id FROM warnings WHERE guild_id = ? AND id = ?", str(guild_id), int(warn_id))
        if not rows:
            return False
        await self.execute("DELETE FROM warnings WHERE guild_id = ? AND id = ?", str(guild_id), int(warn_id))
        return True

    async def get_warnings_leaderboard(self, guild_id: Any, limit: int = 10) -> list:
        """Retrieves top warned members in a guild."""
        query = """
            SELECT user_id, COUNT(*) as warn_count, MAX(timestamp) as latest_warn
            FROM warnings
            WHERE guild_id = ?
            GROUP BY user_id
            ORDER BY warn_count DESC, latest_warn DESC
            LIMIT ?
        """
        return await self.fetch(query, str(guild_id), int(limit))

    async def get_member_moderation_stats(self, guild_id: Any, user_id: Any) -> Dict[str, int]:
        """Fetches counts of warnings, timeouts, and commands for a user in a guild."""
        gid = str(guild_id)
        uid = str(user_id)
        w_rows = await self.fetch("SELECT COUNT(*) as c FROM warnings WHERE guild_id = ? AND user_id = ?", gid, uid)
        t_rows = await self.fetch("SELECT COUNT(*) as c FROM timeouts WHERE guild_id = ? AND user_id = ?", gid, uid)
        c_rows = await self.fetch("SELECT COUNT(*) as c FROM commands WHERE guild_id = ? AND user_id = ?", gid, uid)
        w_cnt = w_rows[0]['c'] if (w_rows and 'c' in w_rows[0]) else (w_rows[0][0] if w_rows else 0)
        t_cnt = t_rows[0]['c'] if (t_rows and 'c' in t_rows[0]) else (t_rows[0][0] if t_rows else 0)
        c_cnt = c_rows[0]['c'] if (c_rows and 'c' in c_rows[0]) else (c_rows[0][0] if c_rows else 0)
        return {"warnings": int(w_cnt or 0), "timeouts": int(t_cnt or 0), "commands": int(c_cnt or 0)}

    async def add_timeout(self, guild_id: Any, user_id: Any, moderator_id: Any, duration_seconds: int, reason: str):
        """Logs a member timeout."""
        query = "INSERT INTO timeouts (guild_id, user_id, moderator_id, duration_seconds, reason) VALUES (?, ?, ?, ?, ?)"
        await self.execute(query, str(guild_id), str(user_id), str(moderator_id), duration_seconds, reason)
        await self.increment_analytics(guild_id, "mutes_count")

    async def add_ban(self, guild_id: Any, user_id: Any, moderator_id: Any, reason: str):
        """Logs a member ban."""
        query = "INSERT INTO bans (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)"
        await self.execute(query, str(guild_id), str(user_id), str(moderator_id), reason)
        await self.increment_analytics(guild_id, "bans_count")

    async def log_audit(self, guild_id: Any, user_id: Any, action: str, details: str = None):
        """Logs a dashboard or moderator action."""
        query = "INSERT INTO audit_logs (guild_id, user_id, action, details) VALUES (?, ?, ?, ?)"
        await self.execute(query, str(guild_id), str(user_id), action, details)

    # ── Reminders Methods ───────────────────────────────────────────────────
    async def add_reminder(self, reminder_id: str, user_id: Any, guild_id: Any, channel_id: Any, reminder_text: str, remind_at: float, created_at: float, delivery_method: str = "dm") -> bool:
        """Stores a scheduled reminder."""
        await self.execute(
            "INSERT INTO reminders (id, user_id, guild_id, channel_id, reminder_text, remind_at, created_at, delivery_method) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            str(reminder_id), str(user_id), str(guild_id) if guild_id else None, str(channel_id), reminder_text, float(remind_at), float(created_at), delivery_method
        )
        return True

    async def get_due_reminders(self, current_time: float) -> List[Dict[str, Any]]:
        """Fetches all reminders that are due to be delivered."""
        return await self.fetch(
            "SELECT id, user_id, guild_id, channel_id, reminder_text, remind_at, created_at, delivery_method FROM reminders WHERE remind_at <= ?",
            float(current_time)
        )

    async def delete_reminder(self, reminder_id: str) -> bool:
        """Deletes a reminder after delivery or upon user cancellation."""
        await self.execute(
            "DELETE FROM reminders WHERE id = ?",
            str(reminder_id)
        )
        return True

    async def get_user_reminders(self, user_id: Any) -> List[Dict[str, Any]]:
        """Fetches all active pending reminders for a user."""
        return await self.fetch(
            "SELECT id, guild_id, channel_id, reminder_text, remind_at, created_at, delivery_method FROM reminders WHERE user_id = ? ORDER BY remind_at ASC",
            str(user_id)
        )

    async def update_reminder_delivery(self, reminder_id: str, delivery_method: str = "channel") -> bool:
        """Updates the delivery method for a reminder."""
        query = "UPDATE reminders SET delivery_method = ? WHERE id = ?"
        await self.execute(query, str(delivery_method), str(reminder_id))
        return True

    # ── AFK System Methods ──────────────────────────────────────────────────
    async def set_afk(self, user_id: Any, guild_id: Any, reason: str, afk_since: float) -> bool:
        """Sets AFK status for a user in a specific guild."""
        if self.is_postgres:
            query = "INSERT INTO afk_users (user_id, guild_id, reason, afk_since) VALUES (?, ?, ?, ?) ON CONFLICT (user_id, guild_id) DO UPDATE SET reason = EXCLUDED.reason, afk_since = EXCLUDED.afk_since"
        else:
            query = "INSERT OR REPLACE INTO afk_users (user_id, guild_id, reason, afk_since) VALUES (?, ?, ?, ?)"
        return await self.execute(query, str(user_id), str(guild_id), reason, float(afk_since))

    async def remove_afk(self, user_id: Any, guild_id: Any) -> bool:
        """Removes AFK status for a user in a guild."""
        return await self.execute(
            "DELETE FROM afk_users WHERE user_id = ? AND guild_id = ?",
            str(user_id), str(guild_id)
        )

    async def get_all_afk_users(self) -> List[Dict[str, Any]]:
        """Loads all AFK records from database on startup."""
        return await self.fetch("SELECT user_id, guild_id, reason, afk_since FROM afk_users")

    # ── Starting 5 Teams (Lineup Builder) ──────────────────────────────────
    async def save_dream_team(self, user_id: Any, guild_id: Any, pg: str, sg: str, sf: str, pf: str, c: str, total_cost: int, ovr_rating: float, team_data: str, updated_at: float) -> bool:
        """Saves or updates a user's Starting 5 lineup."""
        if self.is_postgres:
            query = "INSERT INTO dream_teams (user_id, guild_id, pg, sg, sf, pf, c, total_cost, ovr_rating, team_data, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (user_id) DO UPDATE SET guild_id = EXCLUDED.guild_id, pg = EXCLUDED.pg, sg = EXCLUDED.sg, sf = EXCLUDED.sf, pf = EXCLUDED.pf, c = EXCLUDED.c, total_cost = EXCLUDED.total_cost, ovr_rating = EXCLUDED.ovr_rating, team_data = EXCLUDED.team_data, updated_at = EXCLUDED.updated_at"
        else:
            query = "INSERT OR REPLACE INTO dream_teams (user_id, guild_id, pg, sg, sf, pf, c, total_cost, ovr_rating, team_data, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        await self.execute(query, str(user_id), str(guild_id) if guild_id else None, pg, sg, sf, pf, c, int(total_cost), float(ovr_rating), team_data, float(updated_at))
        return True

    async def get_dream_team(self, user_id: Any) -> Optional[Dict[str, Any]]:
        """Fetches a user's active Starting 5 lineup."""
        return await self.fetchrow("SELECT user_id, guild_id, pg, sg, sf, pf, c, total_cost, ovr_rating, team_data, updated_at FROM dream_teams WHERE user_id = ?", str(user_id))

    async def get_top_dream_teams(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetches the top Starting 5 teams ranked by OVR rating, excluding creator."""
        return await self.fetch("SELECT user_id, guild_id, pg, sg, sf, pf, c, total_cost, ovr_rating, updated_at FROM dream_teams WHERE user_id != '719932313919684670' ORDER BY ovr_rating DESC, updated_at ASC LIMIT ?", int(limit))

    async def delete_dream_team(self, user_id: Any) -> bool:
        """Deletes a user's Starting 5 lineup."""
        await self.execute("DELETE FROM dream_teams WHERE user_id = ?", str(user_id))
        return True

    async def reset_all_dream_teams(self) -> bool:
        """Deletes all saved Starting 5 lineups."""
        await self.execute("DELETE FROM dream_teams")
        return True

    # ── Team Battle Career Stats & Leaderboard ──────────────────────────────
    async def get_team_battle_stats(self, user_id: Any) -> Dict[str, Any]:
        """Fetches a member's career NBA team battle record, streak, achievements, and coaching DNA."""
        row = await self.fetchrow("SELECT user_id, wins, losses, ties, streak, best_streak, total_duels_won, total_points, daily_wins, last_daily_win_date, achievements, coaching_dna, updated_at FROM team_battle_stats WHERE user_id = ?", str(user_id))
        if row:
            try:
                achievements = json.loads(row.get("achievements") or "[]")
            except Exception:
                achievements = []
            try:
                coaching_dna = json.loads(row.get("coaching_dna") or "{}")
            except Exception:
                coaching_dna = {}
            coaching_dna.setdefault("three", 0)
            coaching_dna.setdefault("drive", 0)
            coaching_dna.setdefault("pnr", 0)
            coaching_dna.setdefault("defense", 0)
            coaching_dna.setdefault("iso", 0)
            coaching_dna.setdefault("timeouts", 0)
            coaching_dna.setdefault("total", 0)
            return {
                "wins": row.get("wins", 0),
                "losses": row.get("losses", 0),
                "ties": row.get("ties", 0),
                "streak": row.get("streak", 0),
                "best_streak": row.get("best_streak", 0),
                "total_duels_won": row.get("total_duels_won", 0),
                "total_points": row.get("total_points", 0),
                "daily_wins": row.get("daily_wins", 0),
                "last_daily_win_date": row.get("last_daily_win_date", ""),
                "achievements": achievements,
                "coaching_dna": coaching_dna
            }
        return {
            "wins": 0, "losses": 0, "ties": 0, "streak": 0, "best_streak": 0,
            "total_duels_won": 0, "total_points": 0, "daily_wins": 0, "last_daily_win_date": "", "achievements": [],
            "coaching_dna": {"three": 0, "drive": 0, "pnr": 0, "defense": 0, "iso": 0, "timeouts": 0, "total": 0}
        }

    async def update_team_battle_record(
        self,
        user_id: Any,
        won: bool,
        is_tie: bool,
        duels_won: int,
        points_scored: int,
        new_achievements: Optional[List[str]] = None,
        is_daily_win: bool = False,
        tactics_used: Optional[Dict[str, int]] = None,
        timeouts_used: int = 0
    ):
        """Updates career record, streaks, points, daily challenge wins, coaching DNA, and unlocks achievements."""
        stats = await self.get_team_battle_stats(user_id)
        wins = stats["wins"]
        losses = stats["losses"]
        ties = stats["ties"]
        streak = stats["streak"]
        best_streak = stats["best_streak"]
        total_duels = stats["total_duels_won"] + duels_won
        total_pts = stats["total_points"] + points_scored
        daily_wins = stats.get("daily_wins", 0)
        last_daily_win_date = stats.get("last_daily_win_date", "")
        achievements_set = set(stats["achievements"])
        dna = dict(stats.get("coaching_dna", {}))

        if is_daily_win:
            daily_wins += 1
            last_daily_win_date = datetime.now().strftime("%Y-%m-%d")

        if new_achievements:
            for ach in new_achievements:
                achievements_set.add(ach)

        if is_tie:
            ties += 1
            streak = 0
        elif won:
            wins += 1
            streak = streak + 1 if streak > 0 else 1
            if streak > best_streak:
                best_streak = streak
        else:
            losses += 1
            streak = streak - 1 if streak < 0 else -1

        if tactics_used:
            for k, count in tactics_used.items():
                dna[k] = dna.get(k, 0) + count
                dna["total"] = dna.get("total", 0) + count
        if timeouts_used:
            dna["timeouts"] = dna.get("timeouts", 0) + timeouts_used

        now = datetime.now().timestamp()
        ach_json = json.dumps(list(achievements_set))
        dna_json = json.dumps(dna)

        if self.is_postgres:
            query = """
                INSERT INTO team_battle_stats (user_id, wins, losses, ties, streak, best_streak, total_duels_won, total_points, daily_wins, last_daily_win_date, achievements, coaching_dna, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                    wins = EXCLUDED.wins, losses = EXCLUDED.losses, ties = EXCLUDED.ties,
                    streak = EXCLUDED.streak, best_streak = EXCLUDED.best_streak,
                    total_duels_won = EXCLUDED.total_duels_won, total_points = EXCLUDED.total_points,
                    daily_wins = EXCLUDED.daily_wins, last_daily_win_date = EXCLUDED.last_daily_win_date,
                    achievements = EXCLUDED.achievements, coaching_dna = EXCLUDED.coaching_dna, updated_at = EXCLUDED.updated_at
            """
        else:
            query = "INSERT OR REPLACE INTO team_battle_stats (user_id, wins, losses, ties, streak, best_streak, total_duels_won, total_points, daily_wins, last_daily_win_date, achievements, coaching_dna, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"

        await self.execute(query, str(user_id), wins, losses, ties, streak, best_streak, total_duels, total_pts, daily_wins, last_daily_win_date, ach_json, dna_json, now)

    async def get_nba_rivalry(self, user_a_id: Any, user_b_id: Any) -> Dict[str, Any]:
        """Fetches head-to-head rivalry history and match count between two users."""
        u1, u2 = str(user_a_id), str(user_b_id)
        p_a, p_b = (u1, u2) if u1 < u2 else (u2, u1)
        row = await self.fetchrow("SELECT player_a, player_b, wins_a, wins_b, ties, last_5 FROM nba_rivalries WHERE player_a = ? AND player_b = ?", p_a, p_b)
        if not row:
            return {
                "player_a": p_a, "player_b": p_b,
                "wins_a": 0, "wins_b": 0, "ties": 0,
                "user_a_wins": 0, "user_b_wins": 0,
                "total_matches": 0, "is_rivalry": False,
                "last_5": [], "streak": 0, "leader_id": None
            }
        w_a = row.get("wins_a", 0)
        w_b = row.get("wins_b", 0)
        ties = row.get("ties", 0)
        total = w_a + w_b + ties
        try:
            last_5 = json.loads(row.get("last_5") or "[]")
        except Exception:
            last_5 = []

        user_a_wins = w_a if u1 == p_a else w_b
        user_b_wins = w_b if u1 == p_a else w_a

        streak_winner = last_5[-1] if last_5 else None
        streak_count = 0
        if streak_winner and streak_winner != "tie":
            for winner in reversed(last_5):
                if winner == streak_winner:
                    streak_count += 1
                else:
                    break

        leader_id = None
        if user_a_wins > user_b_wins:
            leader_id = u1
        elif user_b_wins > user_a_wins:
            leader_id = u2

        return {
            "player_a": p_a, "player_b": p_b,
            "wins_a": w_a, "wins_b": w_b, "ties": ties,
            "user_a_wins": user_a_wins, "user_b_wins": user_b_wins,
            "total_matches": total,
            "is_rivalry": total >= 3,
            "last_5": last_5,
            "streak": streak_count,
            "streak_winner": streak_winner,
            "leader_id": leader_id
        }

    async def update_nba_rivalry(self, winner_id: Any, loser_id: Any, is_tie: bool = False) -> Dict[str, Any]:
        """Updates head-to-head match count and last-5 results for a rivalry matchup."""
        u1, u2 = str(winner_id), str(loser_id)
        p_a, p_b = (u1, u2) if u1 < u2 else (u2, u1)
        row = await self.fetchrow("SELECT player_a, player_b, wins_a, wins_b, ties, last_5 FROM nba_rivalries WHERE player_a = ? AND player_b = ?", p_a, p_b)
        w_a = row.get("wins_a", 0) if row else 0
        w_b = row.get("wins_b", 0) if row else 0
        ties = row.get("ties", 0) if row else 0
        try:
            last_5 = json.loads(row.get("last_5") or "[]") if row else []
        except Exception:
            last_5 = []

        if is_tie:
            ties += 1
            last_5.append("tie")
        elif u1 == p_a:
            w_a += 1
            last_5.append(u1)
        else:
            w_b += 1
            last_5.append(u1)

        last_5 = last_5[-5:]
        now = datetime.now().timestamp()
        last_5_json = json.dumps(last_5)

        if self.is_postgres:
            query = """
                INSERT INTO nba_rivalries (player_a, player_b, wins_a, wins_b, ties, last_5, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (player_a, player_b) DO UPDATE SET
                    wins_a = EXCLUDED.wins_a, wins_b = EXCLUDED.wins_b, ties = EXCLUDED.ties,
                    last_5 = EXCLUDED.last_5, updated_at = EXCLUDED.updated_at
            """
        else:
            query = "INSERT OR REPLACE INTO nba_rivalries (player_a, player_b, wins_a, wins_b, ties, last_5, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"

        await self.execute(query, p_a, p_b, w_a, w_b, ties, last_5_json, now)
        return await self.get_nba_rivalry(winner_id, loser_id)

    async def get_top_battle_records(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetches top coaches ranked by wins and win streak, excluding creator."""
        query = """
            SELECT user_id, wins, losses, ties, streak, best_streak, total_duels_won, total_points, daily_wins, last_daily_win_date, achievements, coaching_dna
            FROM team_battle_stats
            WHERE user_id != '719932313919684670'
            ORDER BY wins DESC, streak DESC, total_points DESC
            LIMIT ?
        """
        return await self.fetch(query, int(limit))

    async def record_user_snipe_event(
        self,
        message_id: Any,
        guild_id: Any,
        channel_id: Any,
        channel_name: str,
        user_id: Any,
        user_name: str,
        user_display_name: str,
        user_avatar: Optional[str],
        content: str,
        attachments_json: str = "[]",
        stickers_json: str = "[]",
        message_type: str = "deleted",
        before_content: Optional[str] = None,
        after_content: Optional[str] = None,
        created_at: Optional[float] = None,
        recorded_at: Optional[float] = None
    ) -> bool:
        """Stores a deleted or edited message in persistent database for up to 30-day user snipe history."""
        now = recorded_at or datetime.now().timestamp()
        c_at = created_at or now
        query = """
            INSERT INTO user_snipe_history (
                message_id, guild_id, channel_id, channel_name, user_id,
                user_name, user_display_name, user_avatar, content,
                attachments_json, stickers_json, message_type,
                before_content, after_content, created_at, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            await self.execute(
                query,
                str(message_id),
                str(guild_id),
                str(channel_id),
                str(channel_name),
                str(user_id),
                str(user_name),
                str(user_display_name),
                str(user_avatar or ""),
                str(content or ""),
                str(attachments_json or "[]"),
                str(stickers_json or "[]"),
                str(message_type),
                str(before_content or "") if before_content is not None else None,
                str(after_content or "") if after_content is not None else None,
                float(c_at),
                float(now)
            )
            return True
        except Exception as e:
            logger.error(f"Error recording user snipe event: {e}")
            return False

    async def get_user_snipe_history(
        self,
        guild_id: Any,
        user_id: Any,
        days: int = 30,
        message_type: Optional[str] = None,
        limit: int = 150
    ) -> List[Dict[str, Any]]:
        """Fetches deleted/edited message history for a specific user in a guild within the past X days (default 30)."""
        cutoff = datetime.now().timestamp() - (max(1, min(days, 30)) * 86400)
        if message_type:
            query = """
                SELECT * FROM user_snipe_history
                WHERE guild_id = ? AND user_id = ? AND message_type = ? AND recorded_at >= ?
                ORDER BY recorded_at DESC
                LIMIT ?
            """
            return await self.fetch(query, str(guild_id), str(user_id), str(message_type), cutoff, int(limit))
        else:
            query = """
                SELECT * FROM user_snipe_history
                WHERE guild_id = ? AND user_id = ? AND recorded_at >= ?
                ORDER BY recorded_at DESC
                LIMIT ?
            """
            return await self.fetch(query, str(guild_id), str(user_id), cutoff, int(limit))

    async def get_user_snipe_stats(
        self,
        guild_id: Any,
        user_id: Any,
        days: int = 30
    ) -> Dict[str, Any]:
        """Calculates 30-day deleted and edited message stats for a user."""
        cutoff = datetime.now().timestamp() - (max(1, min(days, 30)) * 86400)
        query = """
            SELECT 
                COUNT(*) as total_count,
                SUM(CASE WHEN message_type = 'deleted' THEN 1 ELSE 0 END) as deleted_count,
                SUM(CASE WHEN message_type = 'edited' THEN 1 ELSE 0 END) as edited_count
            FROM user_snipe_history
            WHERE guild_id = ? AND user_id = ? AND recorded_at >= ?
        """
        row = await self.fetchrow(query, str(guild_id), str(user_id), cutoff)
        if not row:
            return {"total_count": 0, "deleted_count": 0, "edited_count": 0}
        return {
            "total_count": row.get("total_count", 0) or 0,
            "deleted_count": row.get("deleted_count", 0) or 0,
            "edited_count": row.get("edited_count", 0) or 0
        }

    async def prune_old_snipe_history(self, days: int = 30) -> int:
        """Prunes snipe history older than specified days (default 30)."""
        cutoff = datetime.now().timestamp() - (max(1, days) * 86400)
        query = "DELETE FROM user_snipe_history WHERE recorded_at < ?"
        try:
            res = await self.execute(query, cutoff)
            return res if isinstance(res, int) else 0
        except Exception as e:
            logger.error(f"Error pruning old snipe history: {e}")
            return 0

    async def clear_user_snipe_history(self, guild_id: Any, user_id: Optional[Any] = None) -> int:
        """Clears persistent snipe history for a specific user or entire guild."""
        try:
            if user_id:
                query = "DELETE FROM user_snipe_history WHERE guild_id = ? AND user_id = ?"
                res = await self.execute(query, str(guild_id), str(user_id))
            else:
                query = "DELETE FROM user_snipe_history WHERE guild_id = ?"
                res = await self.execute(query, str(guild_id))
            return res if isinstance(res, int) else 0
        except Exception as e:
            logger.error(f"Error clearing user snipe history: {e}")
            return 0

    # ── Active Scheduled Mutes & Fallback System ──────────────────────────────
    async def add_active_mute(self, guild_id: Any, user_id: Any, unmute_at: float, role_id: Optional[Any] = None, reason: str = "") -> bool:
        """Saves an active 7-day role-based mute with auto-expiration timestamp."""
        now = time.time()
        if not self.is_postgres:
            query = """
            INSERT INTO active_mutes (guild_id, user_id, role_id, unmute_at, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                role_id = excluded.role_id,
                unmute_at = excluded.unmute_at,
                reason = excluded.reason,
                created_at = excluded.created_at
            """
        else:
            query = """
            INSERT INTO active_mutes (guild_id, user_id, role_id, unmute_at, reason, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                role_id = EXCLUDED.role_id,
                unmute_at = EXCLUDED.unmute_at,
                reason = EXCLUDED.reason,
                created_at = EXCLUDED.created_at
            """
        try:
            await self.execute(query, str(guild_id), str(user_id), str(role_id) if role_id else None, unmute_at, reason, now)
            return True
        except Exception as e:
            logger.error(f"Error adding active mute: {e}")
            return False

    async def get_active_mute(self, guild_id: Any, user_id: Any) -> Optional[Dict[str, Any]]:
        """Fetches active mute entry for a member (only if not expired)."""
        now = time.time()
        if not self.is_postgres:
            query = "SELECT * FROM active_mutes WHERE guild_id = ? AND user_id = ? AND unmute_at > ?"
            return await self.fetchrow(query, str(guild_id), str(user_id), now)
        else:
            query = "SELECT * FROM active_mutes WHERE guild_id = $1 AND user_id = $2 AND unmute_at > $3"
            return await self.fetchrow(query, str(guild_id), str(user_id), now)

    async def get_due_unmutes(self, current_time: float) -> List[Dict[str, Any]]:
        """Retrieves all active mutes whose expiration timestamp has passed."""
        if not self.is_postgres:
            query = "SELECT * FROM active_mutes WHERE unmute_at <= ?"
        else:
            query = "SELECT * FROM active_mutes WHERE unmute_at <= $1"
        return await self.fetch(query, current_time)

    async def remove_active_mute(self, guild_id: Any, user_id: Any) -> bool:
        """Deletes active mute record upon unmuting or appeal acceptance."""
        if not self.is_postgres:
            query = "DELETE FROM active_mutes WHERE guild_id = ? AND user_id = ?"
        else:
            query = "DELETE FROM active_mutes WHERE guild_id = $1 AND user_id = $2"
        try:
            await self.execute(query, str(guild_id), str(user_id))
            return True
        except Exception as e:
            logger.error(f"Error removing active mute: {e}")
            return False

    # ── Appeal Tickets System ─────────────────────────────────────────────────
    async def create_appeal_ticket(self, guild_id: Any, user_id: Any, channel_id: Any, reason: str, additional_info: str = "") -> bool:
        """Records a new open appeal ticket."""
        now = time.time()
        if not self.is_postgres:
            query = """
            INSERT INTO appeal_tickets (guild_id, user_id, channel_id, status, reason, additional_info, created_at)
            VALUES (?, ?, ?, 'open', ?, ?, ?)
            """
        else:
            query = """
            INSERT INTO appeal_tickets (guild_id, user_id, channel_id, status, reason, additional_info, created_at)
            VALUES ($1, $2, $3, 'open', $4, $5, $6)
            """
        try:
            await self.execute(query, str(guild_id), str(user_id), str(channel_id), reason, additional_info, now)
            return True
        except Exception as e:
            logger.error(f"Error creating appeal ticket in DB: {e}")
            return False

    async def get_appeal_ticket_by_channel(self, channel_id: Any) -> Optional[Dict[str, Any]]:
        """Fetches appeal ticket data for a specific channel."""
        if not self.is_postgres:
            query = "SELECT * FROM appeal_tickets WHERE channel_id = ?"
        else:
            query = "SELECT * FROM appeal_tickets WHERE channel_id = $1"
        return await self.fetchrow(query, str(channel_id))

    async def get_active_appeal_by_user(self, guild_id: Any, user_id: Any) -> Optional[Dict[str, Any]]:
        """Checks if a user already has an open appeal ticket in this guild."""
        if not self.is_postgres:
            query = "SELECT * FROM appeal_tickets WHERE guild_id = ? AND user_id = ? AND status = 'open' ORDER BY created_at DESC LIMIT 1"
        else:
            query = "SELECT * FROM appeal_tickets WHERE guild_id = $1 AND user_id = $2 AND status = 'open' ORDER BY created_at DESC LIMIT 1"
        return await self.fetchrow(query, str(guild_id), str(user_id))

    async def resolve_appeal_ticket(self, channel_id: Any, status: str, resolved_by: Any) -> bool:
        """Marks an appeal ticket as accepted or denied."""
        now = time.time()
        if not self.is_postgres:
            query = "UPDATE appeal_tickets SET status = ?, resolved_at = ?, resolved_by = ? WHERE channel_id = ?"
        else:
            query = "UPDATE appeal_tickets SET status = $1, resolved_at = $2, resolved_by = $3 WHERE channel_id = $4"
        try:
            await self.execute(query, status, now, str(resolved_by), str(channel_id))
            return True
        except Exception as e:
            logger.error(f"Error resolving appeal ticket in DB: {e}")
            return False

    # ── User Memory System (Persistent AI Memory) ─────────────────────────

    async def set_user_memory(self, user_id: Any, fact_key: str, fact_value: str, guild_id: Optional[Any] = None, source: str = "manual") -> bool:
        """Stores or updates a remembered fact about a user."""
        now = time.time()
        clean_key = str(fact_key).strip().lower().replace(" ", "_")[:50]
        clean_val = str(fact_value).strip()[:500]
        if not clean_key or not clean_val:
            return False

        gid_str = str(guild_id) if guild_id else None
        if not self.is_postgres:
            query = """
            INSERT INTO user_memories (user_id, guild_id, fact_key, fact_value, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, fact_key)
            DO UPDATE SET
                fact_value = excluded.fact_value,
                guild_id = COALESCE(excluded.guild_id, user_memories.guild_id),
                source = excluded.source,
                updated_at = excluded.updated_at;
            """
        else:
            query = """
            INSERT INTO user_memories (user_id, guild_id, fact_key, fact_value, source, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT(user_id, fact_key)
            DO UPDATE SET
                fact_value = EXCLUDED.fact_value,
                guild_id = COALESCE(EXCLUDED.guild_id, user_memories.guild_id),
                source = EXCLUDED.source,
                updated_at = EXCLUDED.updated_at;
            """
        try:
            await self.execute(query, str(user_id), gid_str, clean_key, clean_val, source, now, now)
            return True
        except Exception as e:
            logger.error(f"Error setting user memory in DB: {e}")
            return False

    async def get_user_memories(self, user_id: Any, limit: int = 25) -> List[Dict[str, Any]]:
        """Retrieves all stored facts/memories for a user."""
        if not self.is_postgres:
            query = "SELECT fact_key, fact_value, source, updated_at FROM user_memories WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?"
        else:
            query = "SELECT fact_key, fact_value, source, updated_at FROM user_memories WHERE user_id = $1 ORDER BY updated_at DESC LIMIT $2"
        return await self.fetch(query, str(user_id), limit)

    async def delete_user_memory(self, user_id: Any, fact_key: str) -> bool:
        """Deletes a specific remembered fact for a user."""
        clean_key = str(fact_key).strip().lower().replace(" ", "_")
        if not self.is_postgres:
            query = "DELETE FROM user_memories WHERE user_id = ? AND fact_key = ?"
        else:
            query = "DELETE FROM user_memories WHERE user_id = $1 AND fact_key = $2"
        try:
            await self.execute(query, str(user_id), clean_key)
            return True
        except Exception as e:
            logger.error(f"Error deleting user memory in DB: {e}")
            return False

    async def clear_user_memories(self, user_id: Any) -> bool:
        """Clears all stored memories for a user."""
        if not self.is_postgres:
            query = "DELETE FROM user_memories WHERE user_id = ?"
        else:
            query = "DELETE FROM user_memories WHERE user_id = $1"
        try:
            await self.execute(query, str(user_id))
            return True
        except Exception as e:
            logger.error(f"Error clearing user memories in DB: {e}")
            return False

    async def add_blacklist_user(self, user_id: Any, reason: str = "No reason provided", blacklisted_by: Any = None) -> bool:
        """Adds a user to the permanent global blacklist."""
        now = time.time()
        if not self.is_postgres:
            query = "INSERT OR REPLACE INTO blacklisted_users (user_id, reason, blacklisted_by, blacklisted_at) VALUES (?, ?, ?, ?)"
        else:
            query = """
            INSERT INTO blacklisted_users (user_id, reason, blacklisted_by, blacklisted_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE SET reason = EXCLUDED.reason, blacklisted_by = EXCLUDED.blacklisted_by, blacklisted_at = EXCLUDED.blacklisted_at;
            """
        try:
            await self.execute(query, str(user_id), str(reason)[:500], str(blacklisted_by) if blacklisted_by else None, now)
            return True
        except Exception as e:
            logger.error(f"Error adding user to blacklist in DB: {e}")
            return False

    async def remove_blacklist_user(self, user_id: Any) -> bool:
        """Removes a user from the global blacklist."""
        if not self.is_postgres:
            query = "DELETE FROM blacklisted_users WHERE user_id = ?"
        else:
            query = "DELETE FROM blacklisted_users WHERE user_id = $1"
        try:
            await self.execute(query, str(user_id))
            return True
        except Exception as e:
            logger.error(f"Error removing user from blacklist in DB: {e}")
            return False

    async def is_user_blacklisted(self, user_id: Any) -> bool:
        """Checks if a user is currently blacklisted."""
        if not self.is_postgres:
            query = "SELECT user_id FROM blacklisted_users WHERE user_id = ? LIMIT 1"
        else:
            query = "SELECT user_id FROM blacklisted_users WHERE user_id = $1 LIMIT 1"
        try:
            rows = await self.fetch(query, str(user_id))
            return len(rows) > 0
        except Exception as e:
            logger.error(f"Error checking blacklist status in DB: {e}")
            return False

    async def get_blacklisted_users(self) -> List[Dict[str, Any]]:
        """Returns all currently blacklisted users."""
        query = "SELECT * FROM blacklisted_users ORDER BY blacklisted_at DESC"
        try:
            return await self.fetch(query)
        except Exception as e:
            logger.error(f"Error fetching blacklisted users from DB: {e}")
            return []

    # ── NBA 2K Mobile Cards & Economy System ─────────────────────────────────

    async def add_user_nba_card(self, user_id: Any, card_id: str, source: str = "pack") -> bool:
        """Adds an NBA 2K card to a user's inventory."""
        now = time.time()
        query = "INSERT INTO user_nba_cards (user_id, card_id, obtained_at, source) VALUES (?, ?, ?, ?)"
        try:
            await self.execute(query, str(user_id), str(card_id), now, str(source))
            # Increment claimed/pulled stats in economy
            await self.execute(
                """
                INSERT INTO user_nba_economy (user_id, vc_balance, cards_claimed)
                VALUES (?, 1000, 1)
                ON CONFLICT(user_id) DO UPDATE SET cards_claimed = user_nba_economy.cards_claimed + 1
                """,
                str(user_id)
            )
            return True
        except Exception as e:
            logger.error(f"Error adding NBA card to user in DB: {e}")
            return False

    async def get_user_nba_cards(self, user_id: Any) -> List[Dict[str, Any]]:
        """Fetches all NBA 2K cards owned by a user."""
        query = "SELECT * FROM user_nba_cards WHERE user_id = ? ORDER BY obtained_at DESC"
        try:
            return await self.fetch(query, str(user_id))
        except Exception as e:
            logger.error(f"Error fetching user NBA cards from DB: {e}")
            return []

    async def remove_user_nba_card(self, user_id: Any, card_id: str) -> bool:
        """Removes a single copy of an NBA card from user inventory."""
        query = "DELETE FROM user_nba_cards WHERE id = (SELECT id FROM user_nba_cards WHERE user_id = ? AND card_id = ? LIMIT 1)"
        try:
            await self.execute(query, str(user_id), str(card_id))
            return True
        except Exception as e:
            logger.error(f"Error removing user NBA card from DB: {e}")
            return False

    async def transfer_user_nba_card(self, from_user_id: Any, to_user_id: Any, card_id: str) -> bool:
        """Transfers an NBA card from one user to another."""
        query = "UPDATE user_nba_cards SET user_id = ? WHERE id = (SELECT id FROM user_nba_cards WHERE user_id = ? AND card_id = ? LIMIT 1)"
        try:
            await self.execute(query, str(to_user_id), str(from_user_id), str(card_id))
            return True
        except Exception as e:
            logger.error(f"Error transferring NBA card in DB: {e}")
            return False

    async def gift_user_nba_card(self, from_user_id: Any, to_user_id: Any, card_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Transfers an NBA card from from_user_id to to_user_id cleanly."""
        u_from = str(from_user_id)
        u_to = str(to_user_id)
        cid = str(card_id).strip()

        if cid.lower().startswith("excl-") or cid.lower().startswith("exclusive"):
            return False, "Exclusive cards cannot be traded or gifted.", None

        try:
            row = await self.fetchrow("SELECT id, card_id, source FROM user_nba_cards WHERE user_id = ? AND LOWER(card_id) = LOWER(?) LIMIT 1", u_from, cid)
            if not row:
                return False, f"You do not own card `{cid}` in your collection binder.", None
            
            db_id = row["id"] if isinstance(row, dict) and "id" in row else row[0]
            # Preserve pack source so legitimate pack-pulled cards survive the abuse purge
            orig_source = row.get("source", "gift") if isinstance(row, dict) else "gift"
            new_source = orig_source if (orig_source and orig_source.startswith("pack")) else "gift"
            await self.execute("UPDATE user_nba_cards SET user_id = ?, source = ? WHERE id = ?", u_to, new_source, db_id)
            return True, "Card gifted successfully.", dict(row) if isinstance(row, dict) else {"id": db_id, "card_id": cid}
        except Exception as e:
            logger.error(f"Error gifting NBA card from {u_from} to {u_to}: {e}")
            return False, f"Database error during gift transfer: {e}", None

    async def execute_multi_card_trade(
        self,
        user_a_id: Any,
        user_b_id: Any,
        card_a_ids: List[str],
        card_b_ids: List[str],
        vc_a: int = 0,
        vc_b: int = 0
    ) -> Tuple[bool, str]:
        """Atomically swaps multiple cards and/or VC between user_a and user_b."""
        u_a = str(user_a_id)
        u_b = str(user_b_id)
        vc_a = max(0, int(vc_a or 0))
        vc_b = max(0, int(vc_b or 0))

        if not card_a_ids and not card_b_ids and vc_a <= 0 and vc_b <= 0:
            return False, "Cannot execute an empty trade."

        for c in (card_a_ids or []) + (card_b_ids or []):
            if str(c).lower().startswith("excl-") or str(c).lower().startswith("exclusive"):
                return False, "Exclusive cards cannot be traded or transferred."

        try:
            # Verify VC balances if VC is included in offer
            if vc_a > 0:
                bal_a = await self.get_user_vc(u_a)
                if bal_a < vc_a:
                    return False, f"<@{u_a}> has insufficient VC ({bal_a:,} < {vc_a:,} VC)."

            if vc_b > 0:
                bal_b = await self.get_user_vc(u_b)
                if bal_b < vc_b:
                    return False, f"<@{u_b}> has insufficient VC ({bal_b:,} < {vc_b:,} VC)."

            # Get all owned cards for user_a
            owned_a = await self.fetch("SELECT id, card_id FROM user_nba_cards WHERE user_id = ?", u_a)
            a_pool: Dict[str, List[int]] = {}
            for r in owned_a:
                cid = str(r.get("card_id", "")).lower()
                a_pool.setdefault(cid, []).append(r.get("id"))

            ids_to_transfer_to_b = []
            for requested in card_a_ids:
                req_lower = requested.lower()
                if not a_pool.get(req_lower):
                    return False, f"<@{u_a}> no longer owns card `{requested}` in their binder."
                ids_to_transfer_to_b.append(a_pool[req_lower].pop(0))

            # Get all owned cards for user_b
            owned_b = await self.fetch("SELECT id, card_id FROM user_nba_cards WHERE user_id = ?", u_b)
            b_pool: Dict[str, List[int]] = {}
            for r in owned_b:
                cid = str(r.get("card_id", "")).lower()
                b_pool.setdefault(cid, []).append(r.get("id"))

            ids_to_transfer_to_a = []
            for requested in card_b_ids:
                req_lower = requested.lower()
                if not b_pool.get(req_lower):
                    return False, f"<@{u_b}> no longer owns card `{requested}` in their binder."
                ids_to_transfer_to_a.append(b_pool[req_lower].pop(0))

            # Transfer cards
            for db_id in ids_to_transfer_to_b:
                # Preserve pack source so legitimate pack-pulled cards survive the abuse purge
                orig = await self.fetchrow("SELECT source FROM user_nba_cards WHERE id = ?", db_id)
                orig_source = orig["source"] if orig and orig.get("source") else "trade"
                new_source = orig_source if (orig_source and orig_source.startswith("pack")) else "trade"
                await self.execute("UPDATE user_nba_cards SET user_id = ?, source = ? WHERE id = ?", u_b, new_source, db_id)

            for db_id in ids_to_transfer_to_a:
                orig = await self.fetchrow("SELECT source FROM user_nba_cards WHERE id = ?", db_id)
                orig_source = orig["source"] if orig and orig.get("source") else "trade"
                new_source = orig_source if (orig_source and orig_source.startswith("pack")) else "trade"
                await self.execute("UPDATE user_nba_cards SET user_id = ?, source = ? WHERE id = ?", u_a, new_source, db_id)

            # Transfer VC
            if vc_a > 0:
                await self.deduct_user_vc(u_a, vc_a)
                await self.add_user_vc(u_b, vc_a)

            if vc_b > 0:
                await self.deduct_user_vc(u_b, vc_b)
                await self.add_user_vc(u_a, vc_b)

            return True, "Multi-card and VC trade completed successfully."
        except Exception as e:
            logger.error(f"Error executing multi-card trade between {u_a} and {u_b}: {e}")
            return False, f"Database error during multi-card trade: {e}"

    async def execute_card_trade(self, user_a_id: Any, user_b_id: Any, card_a_id: str, card_b_id: str, vc_a: int = 0, vc_b: int = 0) -> Tuple[bool, str]:
        """Safely and atomically swaps card_a/vc_a from user_a and card_b/vc_b from user_b."""
        cards_a = [card_a_id] if card_a_id else []
        cards_b = [card_b_id] if card_b_id else []
        return await self.execute_multi_card_trade(user_a_id, user_b_id, cards_a, cards_b, vc_a, vc_b)

    async def grant_bulk_nba_cards(self, user_id: Any, card_counts: Dict[str, int]) -> int:
        """Ensures user_id has at least the specified count for each card in card_counts."""
        u = str(user_id)
        now = time.time()
        
        try:
            owned = await self.fetch("SELECT card_id, COUNT(*) as cnt FROM user_nba_cards WHERE user_id = ? GROUP BY card_id", u)
            owned_map = {str(r.get("card_id", "")).lower(): int(r.get("cnt", 0)) for r in owned}

            inserts = []
            for cid, target_count in card_counts.items():
                cid_lower = cid.lower()
                current_count = owned_map.get(cid_lower, 0)
                needed = target_count - current_count
                if needed > 0:
                    for _ in range(needed):
                        inserts.append((u, cid, now, "creator_grant"))

            if not inserts:
                return 0

            # Execute in lightning-fast batches using executemany
            for i in range(0, len(inserts), 500):
                batch = inserts[i:i+500]
                await self.executemany("INSERT INTO user_nba_cards (user_id, card_id, obtained_at, source) VALUES (?, ?, ?, ?)", batch)

            return len(inserts)
        except Exception as e:
            logger.error(f"Error granting bulk NBA cards to {u}: {e}")
            return 0

    async def set_creator_godmode_stats(self, user_id: Any, achievements: Optional[List[str]] = None) -> None:
        """Grants Creator Supreme GM Battle mastery: 100W-0L, 100 win streak, and all achievements unlocked."""
        u = str(user_id)
        now = time.time()
        ach_list = achievements or [
            "first_champ", "budget_maestro", "the_clamps", "splash_dynasty",
            "hof_gm", "showtime_century", "streak_master"
        ]
        ach_json = json.dumps(ach_list)
        dna_json = json.dumps({"3pt": 50, "def": 50, "mid": 50, "rim": 50, "total": 200})

        if self.is_postgres:
            query = """
                INSERT INTO team_battle_stats (user_id, wins, losses, ties, streak, best_streak, total_duels_won, total_points, daily_wins, last_daily_win_date, achievements, coaching_dna, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                    wins = EXCLUDED.wins, losses = EXCLUDED.losses, ties = EXCLUDED.ties,
                    streak = EXCLUDED.streak, best_streak = EXCLUDED.best_streak,
                    total_duels_won = EXCLUDED.total_duels_won, total_points = EXCLUDED.total_points,
                    daily_wins = EXCLUDED.daily_wins, last_daily_win_date = EXCLUDED.last_daily_win_date,
                    achievements = EXCLUDED.achievements, coaching_dna = EXCLUDED.coaching_dna, updated_at = EXCLUDED.updated_at
            """
        else:
            query = """
                INSERT OR REPLACE INTO team_battle_stats (user_id, wins, losses, ties, streak, best_streak, total_duels_won, total_points, daily_wins, last_daily_win_date, achievements, coaching_dna, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        await self.execute(query, u, 100, 0, 0, 100, 100, 500, 10000, 10, datetime.now().strftime('%Y-%m-%d'), ach_json, dna_json, now)

    async def remove_abused_top_tier_cards(self, card_ids: List[str], exclude_user_id: Optional[Any] = None) -> int:
        """Removes only 97+ OVR cards that came from chat catches, command spawns, trades, or gifts (preserves genuine pack pulls & creator vault)."""
        if not card_ids:
            return 0
        try:
            placeholders = ", ".join(["?"] * len(card_ids))
            lower_ids = [str(cid).strip().lower() for cid in card_ids]
            
            if exclude_user_id:
                count_query = f"""
                    SELECT COUNT(*) as cnt FROM user_nba_cards 
                    WHERE LOWER(card_id) IN ({placeholders}) 
                    AND (source NOT LIKE 'pack%' OR source IS NULL OR source = 'trade' OR source = 'gift')
                    AND source != 'creator_grant'
                    AND user_id != ?
                """
                params = lower_ids + [str(exclude_user_id)]
                count_rows = await self.fetch(count_query, *params)
                total_count = count_rows[0]["cnt"] if count_rows and "cnt" in count_rows[0] else 0
                if total_count > 0:
                    delete_query = f"""
                        DELETE FROM user_nba_cards 
                        WHERE LOWER(card_id) IN ({placeholders}) 
                        AND (source NOT LIKE 'pack%' OR source IS NULL OR source = 'trade' OR source = 'gift')
                        AND source != 'creator_grant'
                        AND user_id != ?
                    """
                    await self.execute(delete_query, *params)
            else:
                count_query = f"""
                    SELECT COUNT(*) as cnt FROM user_nba_cards 
                    WHERE LOWER(card_id) IN ({placeholders}) 
                    AND (source NOT LIKE 'pack%' OR source IS NULL OR source = 'trade' OR source = 'gift')
                    AND source != 'creator_grant'
                """
                count_rows = await self.fetch(count_query, *lower_ids)
                total_count = count_rows[0]["cnt"] if count_rows and "cnt" in count_rows[0] else 0
                if total_count > 0:
                    delete_query = f"""
                        DELETE FROM user_nba_cards 
                        WHERE LOWER(card_id) IN ({placeholders}) 
                        AND (source NOT LIKE 'pack%' OR source IS NULL OR source = 'trade' OR source = 'gift')
                        AND source != 'creator_grant'
                    """
                    await self.execute(delete_query, *lower_ids)

            logger.info(f"[DB] remove_abused_top_tier_cards removed {total_count} non-pack abused/spawned records (pack pulls preserved).")
            return total_count
        except Exception as e:
            logger.error(f"[DB] Error in remove_abused_top_tier_cards: {e}", exc_info=True)
            return 0

    async def remove_cards_by_ids(self, card_ids: List[str], exclude_user_id: Optional[Any] = None) -> int:
        """Alias pointing to remove_abused_top_tier_cards."""
        return await self.remove_abused_top_tier_cards(card_ids, exclude_user_id)

    async def strip_exclusive_cards(
        self,
        target_user_id: Optional[Any] = None,
        exclude_creator_id: str = "719932313919684670",
        catalog_exclusive_ids: Optional[List[str]] = None
    ) -> Tuple[int, int]:
        """Strips/deletes all Exclusive-tier cards from a specific user or globally across all users (excluding creator).
        Also resets Starting 5 lineups containing exclusive cards.
        Returns (total_cards_deleted, affected_users_count).
        """
        try:
            excl_ids = catalog_exclusive_ids or []
            lower_ids = set(cid.lower().strip() for cid in excl_ids if cid)

            if target_user_id:
                t_user = str(target_user_id)
                query = "SELECT id, user_id, card_id, source FROM user_nba_cards WHERE user_id = ?"
                rows = await self.fetch(query, t_user)
            else:
                c_id = str(exclude_creator_id)
                query = "SELECT id, user_id, card_id, source FROM user_nba_cards WHERE user_id != ?"
                rows = await self.fetch(query, c_id)

            row_ids_to_delete = []
            affected_users = set()

            for r in rows:
                cid = str(r.get("card_id", "")).strip().lower()
                is_excl = (
                    cid.startswith("excl-") or
                    cid.startswith("excl_") or
                    cid.startswith("exclusive") or
                    cid in lower_ids or
                    r.get("source") == "creator_grant"
                )

                if is_excl:
                    row_ids_to_delete.append(r["id"])
                    affected_users.add(str(r["user_id"]))

            total_deleted = len(row_ids_to_delete)
            if total_deleted > 0:
                # Delete in batches of 500
                for i in range(0, total_deleted, 500):
                    batch = row_ids_to_delete[i:i+500]
                    placeholders = ", ".join(["?"] * len(batch))
                    await self.execute(f"DELETE FROM user_nba_cards WHERE id IN ({placeholders})", *batch)

                # Reset dream teams for affected users
                for u in affected_users:
                    dt = await self.get_dream_team(u)
                    if dt:
                        team_data_str = str(dt.get("team_data", ""))
                        if "exclusive" in team_data_str.lower() or "excl-" in team_data_str.lower():
                            await self.delete_dream_team(u)

            logger.info(f"[DB] strip_exclusive_cards purged {total_deleted} cards across {len(affected_users)} users.")
            return total_deleted, len(affected_users)
        except Exception as e:
            logger.error(f"[DB] Error in strip_exclusive_cards: {e}", exc_info=True)
            return 0, 0

    async def wipe_user_nba_data(self, user_id: Any) -> Dict[str, Any]:
        """Completely purges all NBA cards, dream team lineup, and resets economy for a specific user."""
        u = str(user_id)
        result = {"cards_deleted": 0, "dream_team_deleted": False, "vc_reset": 1000}
        try:
            # 1. Count & delete all cards
            cnt_row = await self.fetchrow("SELECT COUNT(*) as cnt FROM user_nba_cards WHERE user_id = ?", u)
            total_cards = int(cnt_row["cnt"]) if cnt_row and "cnt" in cnt_row else 0
            if total_cards > 0:
                await self.execute("DELETE FROM user_nba_cards WHERE user_id = ?", u)
            result["cards_deleted"] = total_cards

            # 2. Delete dream team starting 5
            await self.execute("DELETE FROM dream_teams WHERE user_id = ?", u)
            result["dream_team_deleted"] = True

            # 3. Reset VC & stats in user_nba_economy
            await self.execute(
                "UPDATE user_nba_economy SET vc_balance = 1000, cards_claimed = 0 WHERE user_id = ?",
                u
            )
            logger.info(f"[DB] wipe_user_nba_data successfully wiped {total_cards} cards and reset economy for user {u}.")
            return result
        except Exception as e:
            logger.error(f"[DB] Error in wipe_user_nba_data for user {u}: {e}", exc_info=True)
            return result

    async def migrate_legacy_nba_cards(self, legacy_map: Dict[str, str]) -> int:
        """Automatically updates legacy/duplicate card IDs in user_nba_cards to canonical IDs."""
        if not legacy_map:
            return 0
        total_migrated = 0
        try:
            for old_id, new_id in legacy_map.items():
                old_clean = str(old_id).strip().lower()
                new_clean = str(new_id).strip().lower()
                if old_clean != new_clean:
                    # Update base cards
                    await self.execute(
                        "UPDATE user_nba_cards SET card_id = ? WHERE LOWER(card_id) = ?",
                        new_clean, old_clean
                    )
                    # Update holo versions
                    await self.execute(
                        "UPDATE user_nba_cards SET card_id = ? WHERE LOWER(card_id) = ?",
                        f"holo_{new_clean}", f"holo_{old_clean}"
                    )
            logger.info("[DB] Legacy NBA card migration completed successfully.")
        except Exception as e:
            logger.error(f"[DB] Error in migrate_legacy_nba_cards: {e}", exc_info=True)
        return total_migrated

    async def fuse_nba_cards(self, user_id: Any, card_id: str, legacy_map: Optional[Dict[str, str]] = None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Combines 3 duplicate copies of a card to forge a Holo / Foil Edition (+5 OVR, +20% quicksell).
        Accepts canonical or legacy card IDs and matches all equivalent variants."""
        u = str(user_id)
        raw_cid = str(card_id).strip().lower().replace("holo_", "").replace("holo-", "")
        canonical_cid = (legacy_map.get(raw_cid, raw_cid) if legacy_map else raw_cid).lower()

        if canonical_cid.startswith("excl-") or canonical_cid.startswith("exclusive_") or canonical_cid.startswith("excl_"):
            return False, "Exclusive cards are uncraftable and cannot be fused!", None

        try:
            # Find all matching owned cards (non-holo copies)
            all_rows = await self.fetch(
                "SELECT id, card_id FROM user_nba_cards WHERE user_id = ? AND card_id NOT LIKE 'holo_%' AND card_id NOT LIKE 'holo-%'",
                u
            )
            matching_rows = []
            for r in all_rows:
                cid_in_db = str(r.get("card_id", "")).strip().lower()
                canon_in_db = (legacy_map.get(cid_in_db, cid_in_db) if legacy_map else cid_in_db).lower()
                if canon_in_db == canonical_cid:
                    matching_rows.append(r)

            if len(matching_rows) < 3:
                return False, f"You need **3 copies** of `{canonical_cid}` to fuse a Holo Foil Edition. You currently own **{len(matching_rows)}/3**.", None

            # Delete 3 copies atomically
            ids_to_consume = [r["id"] for r in matching_rows[:3]]
            placeholders = ", ".join(["?"] * len(ids_to_consume))
            await self.execute(f"DELETE FROM user_nba_cards WHERE id IN ({placeholders})", *ids_to_consume)

            # Insert 1 Holo version
            now = time.time()
            holo_cid = f"holo_{canonical_cid}"
            await self.execute(
                "INSERT INTO user_nba_cards (user_id, card_id, obtained_at, source) VALUES (?, ?, ?, 'fusion_holo')",
                u, holo_cid, now
            )
            return True, "Card fusion successful!", {"base_id": canonical_cid, "holo_id": holo_cid}
        except Exception as e:
            logger.error(f"Error in fuse_nba_cards for user {u}: {e}", exc_info=True)
            return False, f"Database error during card fusion: {e}", None



    async def get_user_vc(self, user_id: Any) -> int:
        """Gets user's current VC (Virtual Currency) balance."""
        query = "SELECT vc_balance FROM user_nba_economy WHERE user_id = ?"
        try:
            row = await self.fetchrow(query, str(user_id))
            if row and "vc_balance" in row:
                return int(row["vc_balance"])
            # Default new user balance is 1000 VC
            await self.execute("INSERT INTO user_nba_economy (user_id, vc_balance) VALUES (?, 1000) ON CONFLICT(user_id) DO NOTHING", str(user_id))
            return 1000
        except Exception as e:
            logger.error(f"Error fetching user VC balance from DB: {e}")
            return 1000

    async def add_user_vc(self, user_id: Any, amount: int) -> int:
        """Adds VC to a user's account."""
        query = """
        INSERT INTO user_nba_economy (user_id, vc_balance)
        VALUES (?, 1000 + ?)
        ON CONFLICT(user_id) DO UPDATE SET vc_balance = user_nba_economy.vc_balance + ?
        """
        try:
            await self.execute(query, str(user_id), int(amount), int(amount))
            return await self.get_user_vc(user_id)
        except Exception as e:
            logger.error(f"Error adding VC in DB: {e}")
            return 0

    async def deduct_user_vc(self, user_id: Any, amount: int) -> bool:
        """Deducts VC from a user if balance is sufficient."""
        balance = await self.get_user_vc(user_id)
        if balance < amount:
            return False
        query = "UPDATE user_nba_economy SET vc_balance = vc_balance - ? WHERE user_id = ?"
        try:
            await self.execute(query, int(amount), str(user_id))
            return True
        except Exception as e:
            logger.error(f"Error deducting VC in DB: {e}")
            return False

    async def claim_nba_daily(self, user_id: Any, amount: int = 1000) -> Tuple[bool, int, float]:
        """Claims daily NBA VC reward (24h cooldown). Returns (success, new_balance, time_remaining)."""
        now = time.time()
        query = "SELECT last_daily_claim, vc_balance FROM user_nba_economy WHERE user_id = ?"
        try:
            row = await self.fetchrow(query, str(user_id))
            last_claim = float(row.get("last_daily_claim", 0)) if row else 0.0
            
            if now - last_claim < 86400:
                remaining = 86400 - (now - last_claim)
                return False, int(row.get("vc_balance", 1000)) if row else 1000, remaining

            update_query = """
            INSERT INTO user_nba_economy (user_id, vc_balance, last_daily_claim)
            VALUES (?, 1000 + ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET vc_balance = user_nba_economy.vc_balance + ?, last_daily_claim = ?
            """
            await self.execute(update_query, str(user_id), int(amount), now, int(amount), now)
            new_bal = await self.get_user_vc(user_id)
            return True, new_bal, 0.0
        except Exception as e:
            logger.error(f"Error claiming NBA daily VC in DB: {e}")
            return False, 0, 0.0

    async def claim_nba_weekly(self, user_id: Any, amount: int = 5000) -> Tuple[bool, int, float]:
        """Claims weekly NBA VC reward (7-day cooldown = 604,800s). Returns (success, new_balance, time_remaining)."""
        now = time.time()
        query = "SELECT last_weekly_claim, vc_balance FROM user_nba_economy WHERE user_id = ?"
        try:
            row = await self.fetchrow(query, str(user_id))
            last_claim = float(row.get("last_weekly_claim", 0)) if row else 0.0
            
            if now - last_claim < 604800:
                remaining = 604800 - (now - last_claim)
                return False, int(row.get("vc_balance", 1000)) if row else 1000, remaining

            update_query = """
            INSERT INTO user_nba_economy (user_id, vc_balance, last_weekly_claim)
            VALUES (?, 1000 + ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET vc_balance = user_nba_economy.vc_balance + ?, last_weekly_claim = ?
            """
            await self.execute(update_query, str(user_id), int(amount), now, int(amount), now)
            new_bal = await self.get_user_vc(user_id)
            return True, new_bal, 0.0
        except Exception as e:
            logger.error(f"Error claiming NBA weekly VC in DB: {e}")
            return False, 0, 0.0

    async def claim_nba_monthly(self, user_id: Any, amount: int = 25000) -> Tuple[bool, int, float]:
        """Claims monthly NBA VC reward (30-day cooldown = 2,592,000s). Returns (success, new_balance, time_remaining)."""
        now = time.time()
        query = "SELECT last_monthly_claim, vc_balance FROM user_nba_economy WHERE user_id = ?"
        try:
            row = await self.fetchrow(query, str(user_id))
            last_claim = float(row.get("last_monthly_claim", 0)) if row else 0.0
            
            if now - last_claim < 2592000:
                remaining = 2592000 - (now - last_claim)
                return False, int(row.get("vc_balance", 1000)) if row else 1000, remaining

            update_query = """
            INSERT INTO user_nba_economy (user_id, vc_balance, last_monthly_claim)
            VALUES (?, 1000 + ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET vc_balance = user_nba_economy.vc_balance + ?, last_monthly_claim = ?
            """
            await self.execute(update_query, str(user_id), int(amount), now, int(amount), now)
            new_bal = await self.get_user_vc(user_id)
            return True, new_bal, 0.0
        except Exception as e:
            logger.error(f"Error claiming NBA monthly VC in DB: {e}")
            return False, 0, 0.0

    async def get_user_nba_economy_stats(self, user_id: Any) -> Dict[str, Any]:
        """Fetches full NBA economy stats for a user."""
        query = "SELECT * FROM user_nba_economy WHERE user_id = ?"
        try:
            row = await self.fetchrow(query, str(user_id))
            if row:
                return dict(row)
            return {"user_id": str(user_id), "vc_balance": 1000, "packs_opened": 0, "cards_claimed": 0, "is_private": 0}
        except Exception as e:
            logger.error(f"Error fetching user NBA economy stats from DB: {e}")
            return {"user_id": str(user_id), "vc_balance": 1000, "packs_opened": 0, "cards_claimed": 0, "is_private": 0}

    async def get_user_nba_privacy(self, user_id: Any) -> bool:
        """Returns True if user has set their NBA card binder/dex to Private, False otherwise."""
        try:
            row = await self.fetchrow("SELECT is_private FROM user_nba_economy WHERE user_id = ?", str(user_id))
            if row and "is_private" in row:
                return bool(row["is_private"])
            return False
        except Exception as e:
            logger.debug(f"Error checking NBA privacy for {user_id}: {e}")
            return False

    async def toggle_user_nba_privacy(self, user_id: Any) -> bool:
        """Toggles user's NBA binder/dex privacy (Public <-> Private) and returns the new state."""
        u = str(user_id)
        try:
            curr = await self.get_user_nba_privacy(u)
            new_val = 0 if curr else 1
            await self.execute("""
                INSERT INTO user_nba_economy (user_id, is_private)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET is_private = excluded.is_private
            """, u, new_val)
            return bool(new_val)
        except Exception as e:
            logger.error(f"Error toggling NBA privacy for {u}: {e}")
            return False

    async def save_shootout_score(self, user_id: Any, player_name: str, score: int, money_made: int = 0, starry_made: int = 0) -> bool:
        """Saves a 3-Point Shootout Contest run score."""
        try:
            now = time.time()
            query = """
            INSERT INTO nba_shootout_scores (user_id, player_name, score, money_made, starry_made, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            await self.execute(query, str(user_id), player_name, int(score), int(money_made), int(starry_made), now)
            return True
        except Exception as e:
            logger.error(f"Error saving shootout score in DB: {e}")
            return False

    async def get_shootout_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetches top 3-Point Shootout scores across all players, excluding creator."""
        query = f"""
        SELECT user_id, player_name, MAX(score) as best_score, MAX(money_made) as best_money, MAX(starry_made) as best_starry, MAX(created_at) as created_at
        FROM nba_shootout_scores
        WHERE user_id != '719932313919684670'
        GROUP BY user_id, player_name
        ORDER BY best_score DESC, best_starry DESC, best_money DESC
        LIMIT {int(limit)}
        """
        try:
            rows = await self.fetch(query)
            return [dict(r) for r in rows] if rows else []
        except Exception as e:
            logger.error(f"Error fetching shootout leaderboard: {e}")
            return []

    async def get_user_shootout_best(self, user_id: Any) -> Optional[Dict[str, Any]]:
        """Fetches a specific user's personal best 3-Point Shootout score."""
        query = """
        SELECT user_id, player_name, score, money_made, starry_made, created_at
        FROM nba_shootout_scores
        WHERE user_id = ?
        ORDER BY score DESC, created_at DESC
        LIMIT 1
        """
        try:
            row = await self.fetchrow(query, str(user_id))
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching user personal best shootout score: {e}")
    async def bulk_remove_user_nba_cards(self, user_id: Any, card_row_ids: List[int], vc_to_add: int) -> Tuple[bool, str, int]:
        """Atomically removes a list of card row IDs belonging to user_id and credits VC."""
        u = str(user_id)
        if not card_row_ids:
            return False, "No cards specified for deletion.", await self.get_user_vc(u)

        try:
            placeholders = ", ".join(["?"] * len(card_row_ids))
            # Verify all specified card row IDs currently belong to this user
            check_query = f"SELECT id FROM user_nba_cards WHERE user_id = ? AND id IN ({placeholders})"
            owned_rows = await self.fetch(check_query, u, *card_row_ids)
            owned_ids = {r["id"] if isinstance(r, dict) and "id" in r else r[0] for r in owned_rows}

            if len(owned_ids) != len(card_row_ids):
                return False, f"Ownership verification failed: You own {len(owned_ids)} of the {len(card_row_ids)} selected cards.", await self.get_user_vc(u)

            # Atomically delete cards and credit VC
            del_query = f"DELETE FROM user_nba_cards WHERE user_id = ? AND id IN ({placeholders})"
            await self.execute(del_query, u, *card_row_ids)

            new_bal = await self.add_user_vc(u, vc_to_add)
            logger.info(f"[DB] bulk_remove_user_nba_cards: User {u} sold {len(card_row_ids)} cards for {vc_to_add} VC. New bal: {new_bal}")
            return True, "Cards sold successfully.", new_bal
        except Exception as e:
            logger.error(f"[DB] Error in bulk_remove_user_nba_cards: {e}", exc_info=True)
            return False, f"Database error: {e}", await self.get_user_vc(u)

    async def create_nba_event(
        self,
        guild_id: Any,
        name: str,
        description: str,
        event_type: str = "custom",
        prize_card_id: str = "",
        prize_card_name: str = "",
        channel_id: Optional[Any] = None,
        duration_hours: float = 48.0,
        rules: str = "",
        boss_name: str = "",
        boss_hp: int = 0
    ) -> Optional[int]:
        """Creates an active NBA Event and stores it permanently in database."""
        now = time.time()
        ends_at = now + (duration_hours * 3600.0)
        query = """
        INSERT INTO nba_events (
            guild_id, name, description, event_type, prize_card_id,
            prize_card_name, channel_id, creator_id, created_at,
            ends_at, status, rules, boss_name, boss_hp, boss_max_hp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, '719932313919684670', ?, ?, 'active', ?, ?, ?, ?)
        """
        try:
            await self.execute(
                query,
                str(guild_id), name, description, event_type, prize_card_id,
                prize_card_name, str(channel_id or ""), now, ends_at,
                rules, boss_name, boss_hp, boss_hp
            )
            row = await self.fetchrow("SELECT id FROM nba_events WHERE guild_id = ? AND created_at = ? ORDER BY id DESC LIMIT 1", str(guild_id), now)
            return int(row["id"]) if row and "id" in row else None
        except Exception as e:
            logger.error(f"Error creating NBA event in DB: {e}", exc_info=True)
            return None

    async def get_active_nba_event(self, guild_id: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """Gets current active event for a server or globally."""
        if guild_id:
            query = "SELECT * FROM nba_events WHERE guild_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1"
            row = await self.fetchrow(query, str(guild_id))
        else:
            query = "SELECT * FROM nba_events WHERE status = 'active' ORDER BY created_at DESC LIMIT 1"
            row = await self.fetchrow(query)
        return dict(row) if row else None

    async def get_nba_event_by_id(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Gets event details by ID."""
        row = await self.fetchrow("SELECT * FROM nba_events WHERE id = ?", int(event_id))
        return dict(row) if row else None

    async def get_all_nba_events(self, guild_id: Optional[Any] = None, limit: int = 15) -> List[Dict[str, Any]]:
        """Gets history of all events."""
        if guild_id:
            query = f"SELECT * FROM nba_events WHERE guild_id = ? ORDER BY created_at DESC LIMIT {int(limit)}"
            rows = await self.fetch(query, str(guild_id))
        else:
            query = f"SELECT * FROM nba_events ORDER BY created_at DESC LIMIT {int(limit)}"
            rows = await self.fetch(query)
        return [dict(r) for r in rows] if rows else []

    async def end_nba_event(self, event_id: int) -> bool:
        """Marks an active event as ended."""
        try:
            await self.execute("UPDATE nba_events SET status = 'ended' WHERE id = ?", int(event_id))
            return True
        except Exception as e:
            logger.error(f"Error ending event {event_id}: {e}")
            return False

    async def cancel_nba_event(self, event_id: int) -> bool:
        """Cancels an active event."""
        try:
            await self.execute("UPDATE nba_events SET status = 'cancelled' WHERE id = ?", int(event_id))
            return True
        except Exception as e:
            logger.error(f"Error cancelling event {event_id}: {e}")
            return False

    async def reward_nba_event_winner(self, event_id: int, user_id: Any, card_id: str, card_name: str, count: int = 1, vc_amount: int = 0, rewarded_by: str = "719932313919684670") -> bool:
        """Records a winner and awards the custom cards and VC to their inventory."""
        u = str(user_id)
        now = time.time()
        try:
            # 1. Record winner in winners table
            await self.execute(
                "INSERT INTO nba_event_winners (event_id, user_id, card_id, card_name, rewarded_at, rewarded_by) VALUES (?, ?, ?, ?, ?, ?)",
                int(event_id), u, card_id, card_name, now, rewarded_by
            )
            # 2. Add custom count of cards to inventory
            count_to_grant = max(1, min(count, 50))
            for _ in range(count_to_grant):
                await self.add_user_nba_card(u, card_id, source="event_reward")
            # 3. Add VC if specified
            if vc_amount > 0:
                await self.add_user_vc(u, vc_amount)
            logger.info(f"👑 [EVENT REWARD] User {u} rewarded with {count_to_grant}x {card_id} and {vc_amount} VC for event {event_id}.")
            return True
        except Exception as e:
            logger.error(f"Error rewarding event winner: {e}", exc_info=True)
            return False

    async def get_nba_event_winners(self, event_id: int) -> List[Dict[str, Any]]:
        """Gets list of winners for a specific event."""
        rows = await self.fetch("SELECT * FROM nba_event_winners WHERE event_id = ? ORDER BY rewarded_at ASC", int(event_id))
        return [dict(r) for r in rows] if rows else []

    async def record_nba_raid_damage(self, event_id: int, user_id: Any, damage: int) -> Tuple[int, int]:
        """Records damage against a Raid Boss, updates remaining Boss HP, and returns (new_boss_hp, user_total_damage)."""
        u = str(user_id)
        now = time.time()
        dmg = max(1, int(damage))
        try:
            # Update boss HP
            event = await self.get_nba_event_by_id(event_id)
            if not event or event.get("status") != "active":
                return 0, 0
            cur_hp = int(event.get("boss_hp", 0))
            new_hp = max(0, cur_hp - dmg)
            await self.execute("UPDATE nba_events SET boss_hp = ? WHERE id = ?", new_hp, int(event_id))

            # Record damage
            query = """
            INSERT INTO nba_event_raid_damage (event_id, user_id, damage_dealt, last_attack_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(event_id, user_id) DO UPDATE SET damage_dealt = nba_event_raid_damage.damage_dealt + ?, last_attack_at = ?
            """
            await self.execute(query, int(event_id), u, dmg, now, dmg, now)

            user_row = await self.fetchrow("SELECT damage_dealt FROM nba_event_raid_damage WHERE event_id = ? AND user_id = ?", int(event_id), u)
            total_dmg = int(user_row["damage_dealt"]) if user_row and "damage_dealt" in user_row else dmg
            return new_hp, total_dmg
        except Exception as e:
            logger.error(f"Error recording raid damage: {e}", exc_info=True)
            return 0, 0

    async def get_nba_raid_leaderboard(self, event_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Gets top damage dealers for a Raid Boss."""
        query = f"SELECT user_id, damage_dealt, last_attack_at FROM nba_event_raid_damage WHERE event_id = ? ORDER BY damage_dealt DESC LIMIT {int(limit)}"
        rows = await self.fetch(query, int(event_id))
        return [dict(r) for r in rows] if rows else []

    async def set_nba_event_channel(self, guild_id: Any, channel_id: Any) -> bool:
        """Stores the designated event channel for a guild."""
        query = "INSERT INTO guild_configs (guild_id, key, value) VALUES (?, 'nba_event_channel', ?) ON CONFLICT(guild_id, key) DO UPDATE SET value = EXCLUDED.value"
        try:
            await self.execute(query, str(guild_id), str(channel_id))
            return True
        except Exception as e:
            logger.error(f"Error setting event channel: {e}")
            return False

    async def get_nba_event_channel(self, guild_id: Any) -> Optional[int]:
        """Gets designated event channel for a guild."""
        try:
            row = await self.fetchrow("SELECT value FROM guild_configs WHERE guild_id = ? AND key = 'nba_event_channel'", str(guild_id))
            if row and row.get("value") and str(row.get("value")).isdigit():
                return int(row["value"])
            return None
        except Exception as e:
            logger.error(f"Error getting event channel: {e}")
            return None

    async def close(self):
        """Closes all database connections."""
        if self.pg_pool:
            await self.pg_pool.close()
            logger.info("PostgreSQL pool closed.")
        if self.sqlite_conn:
            await self.sqlite_conn.close()
            logger.info("SQLite connection closed.")

db = DatabaseManager()
