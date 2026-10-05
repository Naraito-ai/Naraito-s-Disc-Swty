import os
import asyncio
import time
import math
import random
import re
import logging
import datetime
from typing import Optional, Union, Tuple, List, Dict, Any, Set
import discord
from discord.ext import commands
from database import db

logger = logging.getLogger("SweetyBot.Utils")

TICKET_CHANNEL_ID = 1549080000328896583
_PURGE_BACKUP_TTL = 900  # 15 minutes
_purge_history_buffer: Dict[int, List[Dict[str, Any]]] = {}
_bot_deleted_message_ids: Set[int] = set()

async def ensure_muted_role(guild: discord.Guild) -> Optional[discord.Role]:
    """
    Finds or creates a @Muted role in the guild with channel overrides:
    - Ticket channels / ticket support: View Channel = True, Send Messages = True (so muted members can interact/appeal)
    - All other channels: Send Messages = False, Add Reactions = False, Speak = False
    """
    if not guild:
        return None
    muted_role = discord.utils.find(lambda r: r.name.lower() == "muted", guild.roles)
    if not muted_role:
        try:
            muted_role = await guild.create_role(
                name="Muted",
                color=discord.Color.dark_grey(),
                reason="Auto-created @Muted role for 7-day strike timeouts and moderation",
                permissions=discord.Permissions(send_messages=False, add_reactions=False, speak=False)
            )
            logger.info(f"Created @Muted role in guild {guild.name} ({guild.id})")
        except Exception as e:
            logger.warning(f"Could not create @Muted role in {guild.name}: {e}")
            return None

    # Apply category & channel overrides safely
    for category in guild.categories:
        try:
            is_ticket_cat = any(term in category.name.lower() for term in ["ticket", "appeal", "support", "staff"])
            if not is_ticket_cat:
                overwrite = category.overwrites_for(muted_role)
                if overwrite.send_messages is not False or overwrite.speak is not False:
                    overwrite.send_messages = False
                    overwrite.add_reactions = False
                    overwrite.create_public_threads = False
                    overwrite.create_private_threads = False
                    overwrite.send_messages_in_threads = False
                    overwrite.speak = False
                    overwrite.stream = False
                    await category.set_permissions(muted_role, overwrite=overwrite, reason="Apply @Muted category restrictions")
                    await asyncio.sleep(0.05)
        except Exception as ce:
            logger.debug(f"Could not apply @Muted override to category {category.name}: {ce}")

    for channel in guild.channels:
        try:
            is_ticket_channel = (
                channel.id == TICKET_CHANNEL_ID or 
                "ticket" in channel.name.lower() or 
                "appeal" in channel.name.lower()
            )
            if is_ticket_channel:
                if isinstance(channel, discord.TextChannel):
                    overwrite = channel.overwrites_for(muted_role)
                    if overwrite.view_channel is not True or overwrite.send_messages is not True:
                        overwrite.view_channel = True
                        overwrite.send_messages = True
                        overwrite.read_message_history = True
                        overwrite.attach_files = True
                        await channel.set_permissions(muted_role, overwrite=overwrite, reason="Allow muted users in ticket support")
                        await asyncio.sleep(0.05)
            else:
                if isinstance(channel, discord.TextChannel):
                    overwrite = channel.overwrites_for(muted_role)
                    if overwrite.send_messages is not False:
                        overwrite.send_messages = False
                        overwrite.add_reactions = False
                        overwrite.create_public_threads = False
                        overwrite.create_private_threads = False
                        overwrite.send_messages_in_threads = False
                        await channel.set_permissions(muted_role, overwrite=overwrite, reason="Apply @Muted restrictions")
                        await asyncio.sleep(0.05)
                elif isinstance(channel, discord.VoiceChannel):
                    overwrite = channel.overwrites_for(muted_role)
                    if overwrite.speak is not False:
                        overwrite.speak = False
                        overwrite.stream = False
                        await channel.set_permissions(muted_role, overwrite=overwrite, reason="Apply @Muted voice restrictions")
                        await asyncio.sleep(0.05)
        except Exception as ch_err:
            logger.debug(f"Could not apply @Muted override to channel {channel.name}: {ch_err}")

    return muted_role

BALLERS_ROLE_NAME = "Ballers"
BALLERS_ROLE_COLOR = 0xFF6B00

async def get_or_create_ballers_role(guild: discord.Guild) -> Optional[discord.Role]:
    """
    Finds or creates a @Ballers role in the guild with color 0xFF6B00 (orange).
    """
    if not guild:
        return None
    role = discord.utils.find(lambda r: r.name.lower() == "ballers", guild.roles)
    if not role:
        try:
            role = await guild.create_role(
                name=BALLERS_ROLE_NAME,
                color=discord.Color(BALLERS_ROLE_COLOR),
                reason="Auto-assigned NBA Ballers role"
            )
            logger.info(f"Created @Ballers role in guild '{guild.name}' ({guild.id})")
        except Exception as e:
            logger.debug(f"Could not create @Ballers role in {guild.name}: {e}")
            return None
    return role


async def assign_ballers_role(member: Union[discord.Member, discord.User], guild: Optional[discord.Guild] = None) -> None:
    """
    Silently checks if the user has the Ballers role, fetches/creates it, and assigns it in the background.
    """
    try:
        if not member:
            return
        actual_guild = guild or getattr(member, "guild", None)
        actual_member = member
        if not isinstance(actual_member, discord.Member) and actual_guild:
            actual_member = actual_guild.get_member(member.id)
            if not actual_member:
                try:
                    actual_member = await actual_guild.fetch_member(member.id)
                except Exception:
                    return
        if not isinstance(actual_member, discord.Member) or not actual_guild:
            return

        if any(r.name.lower() == "ballers" for r in actual_member.roles):
            return

        ballers_role = await get_or_create_ballers_role(actual_guild)
        if ballers_role and ballers_role not in actual_member.roles:
            await actual_member.add_roles(ballers_role, reason="Auto-assigned NBA Ballers role")
            logger.info(f"🏀 Auto-assigned @Ballers role to {actual_member.display_name} in '{actual_guild.name}'")
    except Exception as e:
        logger.debug(f"Failed to assign @Ballers role silently: {e}")


async def sync_all_ballers_roles(bot: commands.Bot, guild: Optional[discord.Guild] = None) -> Dict[str, Any]:
    """
    Scans the database for all users who own NBA cards or have cards claimed / VC activity,
    and retroactively assigns the @Ballers role across all guilds (or a specific guild).
    """
    synced_count = 0
    total_found = 0
    try:
        # Fetch all user IDs with NBA cards or non-zero claimed cards
        rows_cards = await db.fetch("SELECT DISTINCT user_id FROM user_nba_cards")
        rows_eco = await db.fetch("SELECT DISTINCT user_id FROM user_nba_economy WHERE cards_claimed > 0 OR vc_balance != 1000")

        user_ids: Set[int] = set()
        for r in (rows_cards or []):
            uid_val = r.get("user_id") if isinstance(r, dict) else r[0]
            try:
                user_ids.add(int(uid_val))
            except Exception:
                pass
        for r in (rows_eco or []):
            uid_val = r.get("user_id") if isinstance(r, dict) else r[0]
            try:
                user_ids.add(int(uid_val))
            except Exception:
                pass

        total_found = len(user_ids)
        logger.info(f"🏀 Found {total_found} unique NBA player accounts in DB for Ballers role sync.")

        target_guilds = [guild] if guild else list(bot.guilds)
        for g in target_guilds:
            if not g:
                continue
            role = await get_or_create_ballers_role(g)
            if not role:
                continue

            for uid in user_ids:
                try:
                    member = g.get_member(uid)
                    if not member:
                        try:
                            member = await g.fetch_member(uid)
                        except Exception:
                            member = None

                    if member and isinstance(member, discord.Member):
                        if role not in member.roles and not any(r.name.lower() == "ballers" for r in member.roles):
                            await member.add_roles(role, reason="Auto-assigned retroactive NBA Ballers role")
                            synced_count += 1
                            logger.info(f"🏀 Retroactively granted @Ballers to {member.display_name} in {g.name}")
                            await asyncio.sleep(0.05)  # Rate-limit safety
                except Exception as me:
                    logger.debug(f"Could not assign @Ballers to {uid} in {g.name}: {me}")

        logger.info(f"🏀 Ballers role sync complete. Assigned role to {synced_count} members across {len(target_guilds)} guild(s).")
    except Exception as e:
        logger.error(f"Error in sync_all_ballers_roles: {e}", exc_info=True)

    return {"total_nba_users": total_found, "synced_members": synced_count}


async def resolve_member_or_user(
    ctx_or_interaction: Union[commands.Context, discord.Interaction],
    argument: Optional[Union[discord.Member, discord.User, str]] = None
) -> Optional[Union[discord.Member, discord.User]]:
    """
    Robustly resolves a Discord Member or User from an argument:
    - Member or User object directly
    - User ID (<@123>, <@!123>, or raw digits)
    - Username, Nickname, or Display Name (case-insensitive, with or without leading @)
    - Defaults to the invoking user if argument is None
    """
    if argument is None:
        return ctx_or_interaction.author if isinstance(ctx_or_interaction, commands.Context) else ctx_or_interaction.user

    if isinstance(argument, (discord.Member, discord.User)):
        return argument

    raw = str(argument).strip()
    if not raw:
        return ctx_or_interaction.author if isinstance(ctx_or_interaction, commands.Context) else ctx_or_interaction.user

    guild = ctx_or_interaction.guild
    bot = ctx_or_interaction.bot if isinstance(ctx_or_interaction, commands.Context) else ctx_or_interaction.client

    # Check for mention syntax <@123456789> or raw numeric ID
    match = re.match(r"^<@!?(\d+)>$", raw)
    user_id = int(match.group(1)) if match else (int(raw) if raw.isdigit() else None)

    if user_id:
        if guild:
            m = guild.get_member(user_id)
            if m:
                return m
            try:
                m = await guild.fetch_member(user_id)
                if m:
                    return m
            except Exception:
                pass
        try:
            return await bot.fetch_user(user_id)
        except Exception:
            pass

    # Clean leading '@' if present (e.g. "@quit" -> "quit")
    clean_name = raw.lstrip("@").lower()

    if guild:
        # 1. Exact match on username, nickname, global_name, or display_name
        for m in guild.members:
            if (
                m.name.lower() == clean_name or
                m.display_name.lower() == clean_name or
                (getattr(m, "global_name", None) and m.global_name.lower() == clean_name)
            ):
                return m

        # 2. Substring match on guild members
        for m in guild.members:
            if clean_name in m.name.lower() or clean_name in m.display_name.lower():
                return m

    # 3. Search bot global user cache
    for u in getattr(bot, "users", []):
        if (
            u.name.lower() == clean_name or
            (getattr(u, "global_name", None) and u.global_name.lower() == clean_name) or
            u.display_name.lower() == clean_name
        ):
            return u

    return None


async def get_or_recover_appeal_ticket(interaction: discord.Interaction) -> Optional[Dict[str, Any]]:
    """
    Robustly retrieves the appeal ticket from the database.
    If the database record is missing, it reconstructs it from the channel context.
    """
    try:
        ticket = await db.get_appeal_ticket_by_channel(interaction.channel_id)
        if ticket:
            return ticket
    except Exception as e:
        logger.warning(f"Error querying appeal ticket by channel {interaction.channel_id}: {e}")

    channel = interaction.channel
    guild = interaction.guild
    if not channel or not guild:
        return None

    target_uid = None
    if getattr(channel, "topic", None):
        match = re.search(r'\((\d{17,20})\)', channel.topic)
        if match:
            target_uid = int(match.group(1))

    if not target_uid and hasattr(channel, "overwrites"):
        for target, ow in channel.overwrites.items():
            if isinstance(target, (discord.Member, discord.User)) and not getattr(target, "bot", False):
                if target.id != interaction.client.user.id and not is_protected(target):
                    target_uid = target.id
                    break

    if not target_uid and getattr(channel, "name", "").startswith("appeal-"):
        username_part = channel.name[len("appeal-"):].replace("-", "").lower()
        for m in guild.members:
            clean_m_name = re.sub(r'[^a-zA-Z0-9]', '', m.name.lower())
            if clean_m_name and (clean_m_name in username_part or username_part in clean_m_name):
                target_uid = m.id
                break

    if target_uid:
        logger.info(f"🔄 Auto-recovered missing appeal ticket for user {target_uid} in channel {channel.id}")
        await db.create_appeal_ticket(guild.id, target_uid, channel.id, "Auto-recovered appeal ticket", "Recovered by Sweety Auto-Recovery Engine")
        return await db.get_appeal_ticket_by_channel(channel.id) or {
            "guild_id": str(guild.id),
            "user_id": str(target_uid),
            "channel_id": str(channel.id),
            "status": "open",
            "reason": "Auto-recovered appeal ticket",
            "additional_info": ""
        }

    return None

async def restore_purged_messages(channel: discord.TextChannel) -> int:
    """Restores purged messages in chronological order using Webhook clone."""
    if not isinstance(channel, discord.TextChannel):
        return 0
    
    backup = _purge_history_buffer.pop(channel.id, None)
    if not backup:
        return 0
    
    first_msg_purged_at = backup[0].get("purged_at", 0) if backup else 0
    if time.time() - first_msg_purged_at > _PURGE_BACKUP_TTL:
        return 0

    restored_count = 0
    webhook = None
    try:
        if channel.permissions_for(channel.guild.me).manage_webhooks:
            try:
                webhooks = await channel.webhooks()
                for wh in webhooks:
                    if wh.token:
                        webhook = wh
                        break
                if not webhook:
                    webhook = await channel.create_webhook(name="Sweety Restore")
            except Exception as wh_err:
                logger.warning(f"Could not initialize webhook for restore: {wh_err}")
                webhook = None

        for msg_data in backup:
            author_name = msg_data.get("author_name") or "User"
            avatar_url = msg_data.get("author_avatar")
            content = msg_data.get("content") or ""
            embeds = [discord.Embed.from_dict(e) for e in msg_data.get("embeds", [])]
            
            if webhook:
                try:
                    await webhook.send(
                        content=content or None,
                        username=author_name,
                        avatar_url=avatar_url,
                        embeds=embeds if embeds else discord.utils.MISSING
                    )
                    restored_count += 1
                    await asyncio.sleep(0.3)
                    continue
                except Exception:
                    pass
            
            if content or embeds:
                restore_embed = discord.Embed(description=content, color=discord.Color.light_grey())
                restore_embed.set_author(name=author_name, icon_url=avatar_url)
                await channel.send(embed=restore_embed)
                restored_count += 1
                await asyncio.sleep(0.3)
    except Exception as e:
        logger.error(f"Error restoring purged messages: {e}")

    return restored_count

def is_creator(user: Union[discord.Member, discord.User, int, str, None]) -> bool:
    """Returns True if user is the Bot Creator/Owner (ID: 719932313919684670)."""
    if user is None:
        return False
    uid = getattr(user, "id", user)
    try:
        creator_env = os.getenv("BOT_CREATOR_ID", "719932313919684670").strip()
        allowed = {"719932313919684670"}
        if creator_env:
            allowed.add(creator_env)
        return str(uid) in allowed or int(uid) == 719932313919684670
    except (ValueError, TypeError):
        return False




def is_protected(member: Union[discord.Member, discord.User, int, None]) -> bool:
    """
    Sole authoritative gatekeeper for bot immunity and protection.
    Guarantees that User ID 719932313919684670 (Creator/Immune),
    Guild Owner, Administrators, and Staff/Moderators can NEVER be
    timed out, kicked, banned, warned, or penalized by automod/antiraid.
    """
    if member is None:
        return False
    
    # Numerical ID extraction
    mem_id = getattr(member, "id", member)
    try:
        mem_id = int(mem_id)
    except (ValueError, TypeError):
        mem_id = None

    # 1. Absolute Creator Immunity: User ID 719932313919684670
    if mem_id == 719932313919684670:
        return True

    # 2. Guild Owner Immunity
    guild = getattr(member, "guild", None)
    if guild and mem_id is not None and mem_id == getattr(guild, "owner_id", None):
        return True

    # 3. Staff Permissions Immunity
    perms = getattr(member, "guild_permissions", None)
    if perms and (
        perms.administrator or 
        perms.manage_guild or 
        perms.manage_channels or 
        perms.manage_messages or 
        perms.manage_roles or 
        perms.kick_members or 
        perms.ban_members or 
        perms.moderate_members
    ):
        return True

    # 4. Staff Role Name Substring Immunity
    staff_keywords = ["admin", "mod", "staff", "owner", "founder", "manager", "lead", "dev"]
    for role in getattr(member, "roles", []):
        r_name = getattr(role, "name", "").lower()
        if any(kw in r_name for kw in staff_keywords):
            return True

    return False



def parse_duration_string(time_str: str) -> Optional[int]:
    """
    Parses natural duration strings like '10m', '2h', '1d', '30s', '1h30m', '3 days', '4 hours', '15 mins', '1w'.
    Returns total duration in seconds, or None if invalid.
    """
    if not time_str:
        return None
    time_str = time_str.lower().strip().replace(",", "")
    
    if time_str.isdigit():
        return int(time_str) * 60

    if time_str in ["tomorrow", "1 day", "one day"]:
        return 86400
    if time_str in ["tonight"]:
        return 14400
    if time_str in ["1 hour", "one hour", "an hour"]:
        return 3600
    if time_str in ["1 week", "one week"]:
        return 604800

    pattern = re.compile(r'(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|wk|wks|week|weeks|mo|month|months|y|yr|yrs|year|years)?')
    matches = pattern.findall(time_str)
    
    if not matches:
        return None

    total_seconds = 0
    unit_multipliers = {
        's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1,
        'm': 60, 'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
        'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
        'd': 86400, 'day': 86400, 'days': 86400,
        'w': 604800, 'wk': 604800, 'wks': 604800, 'week': 604800, 'weeks': 604800,
        'mo': 2592000, 'month': 2592000, 'months': 2592000,
        'y': 31536000, 'yr': 31536000, 'yrs': 31536000, 'year': 31536000, 'years': 31536000
    }

    matched_any = False
    for amount_str, unit in matches:
        if not amount_str:
            continue
        amount = int(amount_str)
        unit = unit.lower() if unit else 'm'
        multiplier = unit_multipliers.get(unit, 60)
        total_seconds += amount * multiplier
        matched_any = True

    if not matched_any or total_seconds <= 0:
        return None

    return max(5, min(total_seconds, 31536000))



def format_time_elapsed(seconds: float) -> str:
    """Formats elapsed seconds into a clean human readable string like '14 minutes', '2 hours, 10 mins'."""
    sec = max(0, int(seconds))
    if sec < 60:
        return f"{sec} second{'s' if sec != 1 else ''}"
    minutes = sec // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = minutes // 60
    remaining_mins = minutes % 60
    if hours < 24:
        if remaining_mins > 0:
            return f"{hours} hr{'s' if hours != 1 else ''}, {remaining_mins} min{'s' if remaining_mins != 1 else ''}"
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = hours // 24
    remaining_hours = hours % 24
    if remaining_hours > 0:
        return f"{days} day{'s' if days != 1 else ''}, {remaining_hours} hr{'s' if remaining_hours != 1 else ''}"
    return f"{days} day{'s' if days != 1 else ''}"



async def get_mod_log_channel(guild: discord.Guild):
    """Retrieves the configured mod log channel or falls back to name-based detection."""
    channel_id = await db.get_config(guild.id, "mod_log_channel_id")
    if channel_id and str(channel_id) != "None":
        try:
            channel_id = int(channel_id)
            channel = guild.get_channel(channel_id)
            if not channel:
                channel = await guild.fetch_channel(channel_id)
            if channel:
                return channel
        except Exception as e:
            logger.warning(f"Failed to retrieve/fetch channel {channel_id}: {e}")
            
    return discord.utils.get(guild.text_channels, name="🚨-mod-logs") or \
           discord.utils.get(guild.text_channels, name="mod-logs") or \
           discord.utils.get(guild.text_channels, name="🚨-admin-chat")



async def log_mod_action(guild: Union[discord.Guild, int, str, None], moderator: Any, target: Any, action: str = "Mod Action", reason: str = "No reason provided", details: str = None):
    """Sends a detailed moderation action log embed to the configured logs channel and stores in database."""
    try:
        guild_id = getattr(guild, "id", guild)
        if not guild_id:
            return
        mod_id = getattr(moderator, "id", str(moderator))
        target_name = getattr(target, "name", str(target)) if target else "N/A"
        target_id = getattr(target, "id", str(target)) if target else "N/A"
        audit_text = f"Target: {target_name} ({target_id}) | Reason: {reason or 'No reason provided'}"
        if details:
            audit_text += f" | Details: {details}"
        await db.log_audit(guild_id, mod_id, action, audit_text)
    except Exception as db_err:
        logger.debug(f"Failed to record audit log to DB: {db_err}")

    # Dispatch Live Embed to configured mod log channel
    try:
        if isinstance(guild, discord.Guild):
            mod_log = await get_mod_log_channel(guild)
            if mod_log:
                embed = discord.Embed(title=f"🛡️ Mod Action: {action}", color=discord.Color.orange())
                embed.add_field(name="Moderator", value=f"{moderator} ({getattr(moderator, 'id', 'N/A')})", inline=True)
                embed.add_field(name="Target User", value=f"{target} ({getattr(target, 'id', 'N/A')})", inline=True)
                embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
                if details:
                    embed.add_field(name="Details", value=details, inline=False)
                embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
                await mod_log.send(embed=embed)
    except Exception as e:
        logger.error(f"Failed to send mod action log to channel: {e}")



def can_manage_kiss_role(guild: Optional[discord.Guild], user: Union[discord.Member, discord.User]) -> bool:
    """Checks if a user has authority to configure the kiss allowed role (Owner, Admins, Creator)."""
    if not guild:
        return False
    uid = getattr(user, "id", 0)
    if uid == 719932313919684670:
        return True
    if uid == getattr(guild, "owner_id", None):
        return True
    perms = getattr(user, "guild_permissions", None)
    if perms and perms.administrator:
        return True
    return False




async def can_use_kiss_command(guild: Optional[discord.Guild], user: Union[discord.Member, discord.User]) -> Tuple[bool, Optional[int]]:
    """
    Checks if a user is authorized to use the kiss command.
    Returns: (is_allowed: bool, configured_role_id: Optional[int])
    
    Rules:
    - Creator (719932313919684670) is always allowed.
    - Server Owner is always allowed.
    - Server Administrators are always allowed.
    - If a specific Kiss Role has been configured by Admins via /kissrole, members with that role are allowed.
    """
    if not guild:
        return True, None
    
    uid = getattr(user, "id", 0)
    if uid == 719932313919684670:
        return True, None
    if uid == getattr(guild, "owner_id", None):
        return True, None
    
    perms = getattr(user, "guild_permissions", None)
    if perms and perms.administrator:
        return True, None
    
    # Check if a custom role is configured
    allowed_role_id_raw = await db.get_config(guild.id, "kiss_allowed_role_id", None)
    allowed_role_id = None
    if allowed_role_id_raw and str(allowed_role_id_raw).lower() not in ("none", "null", "0", ""):
        try:
            allowed_role_id = int(allowed_role_id_raw)
        except (ValueError, TypeError):
            allowed_role_id = None
            
    if allowed_role_id and isinstance(user, discord.Member):
        if any(r.id == allowed_role_id for r in user.roles):
            return True, allowed_role_id
            
    return False, allowed_role_id




def create_action_embed(action_type: str, author: Union[discord.Member, discord.User], target: Union[discord.Member, discord.User], bot_user: Optional[Union[discord.Member, discord.User]] = None) -> discord.Embed:
    """Creates a clean OwO-style action embed featuring authentic anime video GIFs."""
    data = ACTION_METADATA.get(action_type.lower(), ACTION_METADATA["hug"])
    
    author_tag = f"**{getattr(author, 'display_name', str(author))}**"
    target_tag = f"**{getattr(target, 'display_name', str(target))}**"
    
    if author.id == target.id:
        desc = data["self_text"].format(author=author_tag)
        gif_url = random.choice(data["gifs"])
        color = data["color"]
    elif bot_user and target.id == bot_user.id:
        bot_texts = data.get("bot_text")
        if isinstance(bot_texts, list):
            desc = random.choice(bot_texts).format(author=author_tag)
        else:
            desc = bot_texts.format(author=author_tag)
            
        if "bot_gifs" in data:
            gif_url = random.choice(data["bot_gifs"])
            color = discord.Color.from_rgb(255, 60, 90)
        else:
            gif_url = random.choice(data["gifs"])
            color = data["color"]
    else:
        desc = f"{author_tag} {data['verb']} {target_tag}! {data['emoji']}"
        gif_url = random.choice(data["gifs"])
        color = data["color"]

    embed = discord.Embed(
        description=desc,
        color=color
    )
    embed.set_image(url=gif_url)
    return embed




parse_time_string = parse_duration_string

ACTION_METADATA = {
    "hug": {
        "color": discord.Color.from_rgb(255, 160, 180),
        "verb": "hugs",
        "emoji": "(つ >ω<)つ",
        "self_text": "{author} hugs themselves! (つ´∀｀)つ",
        "bot_text": "{author} hugs Sweety! (* >ω<) ❤️",
        "gifs": [
            "https://cdn.otakugifs.xyz/gifs/hug/df2aea0c15f3fd38.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/bc55980479c9473d.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/e68dd86d3f324c0b.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/2e058903bb17eff2.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/b726e6b16c163d04.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/9c04237bf0e04e75.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/1e74d56f2c2b6837.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/68ed8177a3a022d8.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/522c5565e52dc3c6.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/3d700909b0d33127.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/f544HNxZR0.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/923c84c09fdcb380.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/37876b8d388310f3.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/E0l7A2yayA.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/bf06f94d20fb33f3.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/8d3df8b9d154b613.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/acbFO8l7Hi.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/52144ce42c01a39c.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/c787d02e22435395.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/4b31f202610c5943.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/0d8f88e421d8b1eb.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/8a10a971e9f5a514.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/608e7397da18e9c7.gif",
            "https://cdn.otakugifs.xyz/gifs/hug/df0840a507aa481a.gif",
        ]
    },
    "pat": {
        "color": discord.Color.from_rgb(255, 200, 50),
        "verb": "pats",
        "emoji": "( ´ ▽ ` )ﾉ *pat pat*",
        "self_text": "{author} pats their own head! (*´▽`*)",
        "bot_text": "{author} pats Sweety! (´꒳`) ✨",
        "gifs": [
            "https://cdn.otakugifs.xyz/gifs/pat/7pUEkSbx3r.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/5c90b301ee64c14a.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/bafe48cd8212994b.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/c88e6bcc70232d91.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/fe34c159c9551319.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/d324b051f0bfe526.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/0d868f84caad8696.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/rzn5K09230.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/a2f5902d10f68ae5.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/19278030a3174e88.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/761c3fc2651263bc.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/XCNHCmIs1w.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/f738473258ae31f5.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/a9fdc8c531b4e66e.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/5cb16aa0e7fa5891.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/4de26d931b9eb6a3.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/519797f8714e4a5e.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/328e34427f543969.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/b827c8687dcd59e0.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/sXhIDsqPO6.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/87562e094ccfabb1.gif",
            "https://cdn.otakugifs.xyz/gifs/pat/61d8689da122b166.gif",
        ]
    },
    "kiss": {
        "color": discord.Color.from_rgb(255, 105, 180),
        "verb": "kisses",
        "emoji": "(づ￣ ³￣)づ ❤️ *kiss*",
        "self_text": "{author} blows a loving kiss into the air! (づ￣ ³￣)づ💋",
        "bot_text": "{author} kisses Sweety! (*ﾉωﾉ) 💖 *blushes deeply*",
        "gifs": [
            "https://cdn.otakugifs.xyz/gifs/kiss/147ef0fe59fcfbf0.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/55dce627608eb620.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/4f7bcadb7b30a094.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/e34493aac9970d50.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/736a111d8ed929b2.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/eba9a5d31d6e57a9.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/0e41d66ee4966bea.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/9cb66f2a86d8b3a3.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/5e1a1159b2d14a2c.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/f8c5edf9aa62b175.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/W2zxPFRkrd.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/cc21567435858305.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/6f908e301d1a1d5f.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/3f141e8d94dd07ca.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/e5ba4cf1044a70a5.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/99c6d80ba787d40a.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/a2cff2325e17c674.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/ec4530685e50980b.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/e8620e4b5d4907df.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/1467d223c890284c.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/2a924686c1c72fab.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/03b7558413fbedf8.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/NGLVWgfzrI.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/e344703a274d59e6.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/g95T4Gz6Jy.gif",
            "https://cdn.otakugifs.xyz/gifs/kiss/15a312f23dec92ab.gif",
            "https://cdn.otakugifs.xyz/gifs/airkiss/bd3a995ce96573ef.gif",
            "https://cdn.otakugifs.xyz/gifs/airkiss/NUqoApLJGg.gif",
            "https://cdn.otakugifs.xyz/gifs/airkiss/7b4d25f8de3942bc.gif",
            "https://cdn.otakugifs.xyz/gifs/airkiss/d600bf56401dbee5.gif",
            "https://cdn.otakugifs.xyz/gifs/airkiss/a840b9606d1fb6dd.gif",
            "https://cdn.otakugifs.xyz/gifs/airkiss/a446875d20d4d363.gif",
        ]
    },
    "highfive": {
        "color": discord.Color.from_rgb(255, 190, 60),
        "verb": "high-fives",
        "emoji": "✋⚡ ( ＾◡＾)",
        "self_text": "{author} high-fives themselves! 👏",
        "bot_text": "{author} high-fives Sweety! ✋🔥",
        "gifs": [
            "https://cdn.otakugifs.xyz/gifs/yay/kJl8Mm8hKW.gif",
            "https://cdn.otakugifs.xyz/gifs/yay/iMpFCFnCRCeM.gif",
            "https://cdn.otakugifs.xyz/gifs/yay/0j96SZyvZY.gif",
            "https://cdn.otakugifs.xyz/gifs/yay/5ee9bcd7353c17ba.gif",
            "https://cdn.otakugifs.xyz/gifs/yay/aXUiu8K4FPFi.gif",
            "https://cdn.otakugifs.xyz/gifs/yay/03c4ecf43db62486.gif",
            "https://cdn.otakugifs.xyz/gifs/yay/baced95d9eb113c0.gif",
            "https://cdn.otakugifs.xyz/gifs/yay/SeWA76dt7ZYN.gif",
            "https://cdn.otakugifs.xyz/gifs/yay/81d496fb29f6792b.gif",
            "https://cdn.otakugifs.xyz/gifs/yay/fc1459311d24273a.gif",
            "https://cdn.otakugifs.xyz/gifs/celebrate/6972def9c7c55de5.gif",
            "https://cdn.otakugifs.xyz/gifs/celebrate/2250bd2042d3a838.gif",
            "https://cdn.otakugifs.xyz/gifs/celebrate/d39e778bd0a7aa5c.gif",
            "https://cdn.otakugifs.xyz/gifs/celebrate/K4FAdzTq6ydJ.gif",
            "https://cdn.otakugifs.xyz/gifs/celebrate/124b84f058d8d6bc.gif",
            "https://cdn.otakugifs.xyz/gifs/celebrate/a4cee6028f5fec0e.gif",
            "https://cdn.otakugifs.xyz/gifs/celebrate/058ace7bf9412c28.gif",
            "https://cdn.otakugifs.xyz/gifs/cheers/c719a134dd76a24d.gif",
            "https://cdn.otakugifs.xyz/gifs/cheers/41b4954d25a2aa93.gif",
            "https://cdn.otakugifs.xyz/gifs/cheers/64bb946e4e8e6d1e.gif",
            "https://cdn.otakugifs.xyz/gifs/cheers/03d063c6eae43782.gif",
            "https://cdn.otakugifs.xyz/gifs/cheers/3412fc5930c6962f.gif",
            "https://cdn.otakugifs.xyz/gifs/cheers/c05873ab3b4d795d.gif",
            "https://cdn.otakugifs.xyz/gifs/brofist/47cdea3ee11ea46d.gif",
            "https://cdn.otakugifs.xyz/gifs/brofist/524bc07b24ce7392.gif",
            "https://cdn.otakugifs.xyz/gifs/brofist/5OdMjFhhAO.gif",
            "https://cdn.otakugifs.xyz/gifs/brofist/86ac6d7fcd6aa037.gif",
            "https://cdn.otakugifs.xyz/gifs/brofist/0qEaIcvowz.gif",
            "https://cdn.otakugifs.xyz/gifs/brofist/fe9bb21e05fabd1d.gif",
            "https://cdn.otakugifs.xyz/gifs/brofist/1fb59c43cca6c6d5.gif",
            "https://cdn.otakugifs.xyz/gifs/brofist/14f01db51999d44f.gif",
            "https://cdn.otakugifs.xyz/gifs/thumbsup/SLPQSVVKVQQm.gif",
            "https://cdn.otakugifs.xyz/gifs/thumbsup/96a5a4d278e37832.gif",
            "https://cdn.otakugifs.xyz/gifs/thumbsup/86c02b24f136e08f.gif",
            "https://cdn.otakugifs.xyz/gifs/thumbsup/6d802665ed2a176b.gif",
            "https://cdn.otakugifs.xyz/gifs/thumbsup/e1ecfd7c7569c53b.gif",
            "https://cdn.otakugifs.xyz/gifs/thumbsup/135a258d3a1a6c95.gif",
        ]
    },
    "wave": {
        "color": discord.Color.from_rgb(100, 200, 255),
        "verb": "waves at",
        "emoji": "( ´ ▽ ` )/ 🌸",
        "self_text": "{author} waves at their reflection! 👋✨",
        "bot_text": "{author} waves at Sweety! ( ´ ▽ ` )/ 💖",
        "gifs": [
            "https://cdn.otakugifs.xyz/gifs/wave/29801143d387184f.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/219054cc5ff6806d.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/7832e5c768ca70cb.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/7256dff418cace9f.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/3f6db91547ebde66.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/110af4a9b5c9107f.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/e2c97f5a33dcfe83.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/6183acb292d732e6.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/ca5f7fcafbfc9556.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/nruMcDv2tiFq.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/c431fefc7b33b594.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/2e565abe8764327d.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/vs1cQk1084.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/94af8e705ad3ecfc.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/c265105164e5f6ba.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/8b38064027efc84d.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/de5ac5daf0c3b4c5.gif",
            "https://cdn.otakugifs.xyz/gifs/wave/a9cd5027f2162c21.gif",
        ]
    },
    "slap": {
        "color": discord.Color.from_rgb(255, 75, 75),
        "verb": "slaps",
        "emoji": "( `Д´)ノ=3 *SMACK!*",
        "self_text": "{author} slaps themselves! ( >_< )",
        "bot_text": "{author} slaps Sweety! (ノ_<。) 💔",
        "gifs": [
            "https://cdn.otakugifs.xyz/gifs/slap/iycRe43Ygg.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/0vSCEWQ6ib.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/MEHoADoE1X.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/8Xg35eViSf.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/IGraVDzh5b.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/0d82850a623b04f6.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/bb9bdfcbd5c606f7.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/56d8426acc62f8fb.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/99d7a3247ec4bd51.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/8b4aad19774ed00c.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/21a5eb00bdd9bc78.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/728770007827600b.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/bec6d0d98bd68398.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/004ebed9b64b0581.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/a51d5c14f73d4c4f.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/7882244dc2ba254c.gif",
            "https://cdn.otakugifs.xyz/gifs/slap/756d7b12e16fbb1d.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/504b9994f7248a46.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/7537179b546d66db.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/Avh6ieJLzKeZ.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/Xhxvcdkcfx.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/df8232ef82800698.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/bd269a201834e64c.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/42f09810ba12345e.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/WWetybgH3D3g.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/78c956974f371f70.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/fa0c23b3a4fb3915.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/b281eb32b6bb3547.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/bc7b0879f90cf6f7.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/a3f546a9518843d7.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/fFLE6PqCbCvb.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/b2a96e2b92d86304.gif",
            "https://cdn.otakugifs.xyz/gifs/smack/f518f98959e91052.gif",
        ]
    },
    "punch": {
        "color": discord.Color.from_rgb(230, 50, 50),
        "verb": "punches",
        "emoji": "( ҂`з´) ᕤ *POW!*",
        "self_text": "{author} shadowboxes and punches themselves! 😵",
        "bot_text": "{author} punches Sweety! 🛡️ Energy shield deflected!",
        "gifs": [
            "https://cdn.otakugifs.xyz/gifs/punch/6Nl4IdAcfX.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/UAru8Vy4rnU5.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/8zgYvNjmtMnD.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/lQbYrpwHpz.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/120ad1827ee066b2.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/f55xAxN6kKHY.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/SAn5cOlzM5.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/6a071f4273b6c06d.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/05bc002e281ddd92.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/a68e34a1994c91f7.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/7iu27NtD3W57.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/2fd18184c78ec80d.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/f179131bd406f951.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/7895d749a1244483.gif",
            "https://cdn.otakugifs.xyz/gifs/punch/3a6417e6568b2e96.gif",
        ]
    },
}



def roll_pack_card(pack_id: str = "starter", user_id: Optional[int] = None) -> Dict[str, Any]:
    """Rolls an authentic card from NBA_2K_MOBILE_CARDS using transparent pack odds."""
    pack_data = NBA_PACK_TYPES.get(pack_id.lower().strip(), NBA_PACK_TYPES["starter"])
    odds = pack_data.get("odds", {"gold": 1.0})
    tiers = list(odds.keys())
    weights = list(odds.values())

    chosen_tier = random.choices(tiers, weights=weights, k=1)[0]
    matching = [
        c for c in NBA_2K_MOBILE_CARDS
        if c.get("tier") == chosen_tier and not c.get("is_exclusive") and not c.get("is_holo")
    ]
    if not matching:
        matching = [c for c in NBA_2K_MOBILE_CARDS if c.get("tier") == chosen_tier]
    if not matching:
        matching = NBA_2K_MOBILE_CARDS
    return random.choice(matching)

