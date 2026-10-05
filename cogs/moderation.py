import os
import asyncio
import time
import math
import random
import re
import logging
import datetime
from typing import Optional, Union, Tuple, List, Dict, Any
import discord
from discord.ext import commands
from discord import app_commands
from database import db
from utils import (
    is_creator, is_protected, log_mod_action, get_mod_log_channel,
    parse_duration_string, parse_time_string, format_time_elapsed,
    create_action_embed, ACTION_METADATA, ensure_muted_role,
    get_or_recover_appeal_ticket, restore_purged_messages,
    _purge_history_buffer, _bot_deleted_message_ids, TICKET_CHANNEL_ID
)

logger = logging.getLogger("SweetyBot.Moderation")

async def issue_warning_logic(guild: discord.Guild, member: discord.Member, moderator: discord.Member, reason: str) -> tuple[int, str]:
    """
    Issues a formal warning / strike, tracks strike count, and enforces strike policies:
    - 3 Strikes: 7-Day Server Timeout (Appeal via DM button, !appeal, or ticket)
    - 6 Strikes: Permanent Server Ban
    """
    clean_reason = discord.utils.escape_mentions(reason[:500])
    await db.add_warning(guild.id, member.id, moderator.id, clean_reason)
    
    warnings = await db.get_warnings(guild.id, member.id)
    total_warns = len(warnings)
    
    escalation_action = ""
    if total_warns == 3:
        try:
            if not is_protected(member):
                await member.timeout(datetime.timedelta(days=7), reason=f"Auto-Escalation: 3 Strikes Reached ({clean_reason})")
                muted_role = await ensure_muted_role(guild)
                if muted_role:
                    await member.add_roles(muted_role, reason="Auto-Escalation: 3 Strikes Reached (7-day role mute)")
                await db.add_active_mute(guild.id, member.id, time.time() + (7 * 86400))

            escalation_action = (
                "\n\n🛑 **Auto-Escalation: 7-Day Timeout Applied**\n"
                "• **Penalty:** Muted for **7 full days** (Reached 3 Strikes).\n"
                "• **Appeal Options (3 Ways):**\n"
                "  1. 📩 Click the **Submit Strike Appeal** button attached in DM.\n"
                "  2. 💬 Reply with `!appeal <reason>` directly in DM to Sweety.\n"
                "  3. 🎫 Open a ticket in <#1549080000328896583>.\n"
                "• **Warning:** Accumulating 3 more strikes (6 total) will result in a **permanent ban**."
            )
        except Exception as e:
            logger.warning(f"Failed to timeout member {member.id} for 7 days: {e}")
    elif total_warns >= 6:
        try:
            if not is_protected(member):
                await member.ban(reason=f"Auto-Escalation: 6 Strikes Reached - Permanent Server Ban ({clean_reason})", delete_message_days=0)
            escalation_action = (
                "\n\n⛔ **Auto-Escalation: Permanent Ban Applied**\n"
                "• **Penalty:** **Permanently banned** from the server (Accumulated 6 Strikes)."
            )
        except Exception as e:
            logger.warning(f"Failed to ban member {member.id} for 6 strikes: {e}")
    elif total_warns > 3:
        remaining = 6 - total_warns
        escalation_action = f"\n\n⚠️ **Critical Notice:** Member has **{total_warns}/6 strikes** ({remaining} more strike{'s' if remaining != 1 else ''} will result in a **permanent ban**)."
    else:
        remaining = 3 - total_warns
        escalation_action = f"\n\n🟡 **Notice:** Member has **{total_warns}/3 strikes** before a 7-day timeout ({remaining} strike{'s' if remaining != 1 else ''} remaining)."

    try:
        dm_color = discord.Color.red() if total_warns >= 3 else discord.Color.gold()
        dm_embed = discord.Embed(
            title=f"⚠️ Warning / Strike Issued in {guild.name}",
            description=f"You have been formally issued a strike by **{moderator.display_name}**.",
            color=dm_color
        )
        dm_embed.add_field(name="Reason", value=clean_reason, inline=False)
        dm_embed.add_field(name="Total Strikes on Record", value=f"`{total_warns}` / 6 strikes", inline=True)
        
        if total_warns == 3:
            dm_embed.add_field(
                name="🛑 Penalty Applied: 7-Day Mute",
                value=(
                    "You have reached **3 strikes** and have been **muted for 7 full days**.\n\n"
                    "📌 **How to Appeal (Choose Any Method):**\n"
                    "1️⃣ **In-DM Button:** Click the **📩 Submit Strike Appeal** button below.\n"
                    "2️⃣ **DM Command:** Reply to this DM with `!appeal <your reason here>`\n"
                    "3️⃣ **Ticket Support:** Open a ticket in <#1549080000328896583> in the server.\n\n"
                    "⚠️ *Note: Accumulating 3 more strikes (6 total) results in a permanent ban.*"
                ),
                inline=False
            )
        elif total_warns >= 6:
            dm_embed.add_field(
                name="⛔ Penalty Applied: Permanent Ban",
                value="You have accumulated **6 strikes** and have been **permanently banned** from the server.",
                inline=False
            )
        elif total_warns > 3:
            dm_embed.add_field(
                name="🚨 High Risk Notice",
                value=f"You currently have **{total_warns}/6 strikes**. Reaching 6 strikes results in an immediate permanent ban.",
                inline=False
            )
        else:
            dm_embed.add_field(
                name="📌 How to Appeal This Warning",
                value="If you believe this warning was issued in error, click the button below or reply `!appeal <reason>`.",
                inline=False
            )

        dm_embed.add_field(
            name="📜 Server Strike Rules",
            value=(
                "• **3 Strikes:** Muted for 7 full days (Appeal via in-DM button, `!appeal`, or <#1549080000328896583>)\n"
                "• **6 Strikes:** Permanent ban from the server"
            ),
            inline=False
        )
        dm_embed.set_footer(text="Please keep the community friendly and adhere to server rules.")
        
        dm_view = DMAppealLauncherView()
        await member.send(embed=dm_embed, view=dm_view)
    except Exception:
        pass

    await log_mod_action(guild, moderator, member, "Warning Issued", clean_reason, f"Total Strikes: {total_warns}{escalation_action}")
    return total_warns, escalation_action

class ModerationCog(commands.Cog, name="Moderation"):
    """Moderation, server management, warning system, and appeal tickets."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="appeal", description="Submit an official appeal for your active warnings, strikes, or timeout")
    @app_commands.describe(reason="Reason for your appeal (optional if opening interactive modal)")
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.guild_only()
    async def appeal_slash_cmd(self, interaction: discord.Interaction, reason: Optional[str] = None):
        try:
            warns = await db.get_warnings(interaction.guild.id, interaction.user.id)
            active_mute = await db.get_active_mute(interaction.guild.id, interaction.user.id)

            if not warns and not active_mute:
                return await interaction.response.send_message(
                    "ℹ️ **You have a clean record!** You currently have 0 active warnings, strikes, or timeouts in this server.",
                    ephemeral=True
                )

            active_ticket = await db.get_active_appeal_by_user(interaction.guild.id, interaction.user.id)
            if active_ticket:
                channel_id_raw = active_ticket.get("channel_id")
                chan = None
                try:
                    if channel_id_raw:
                        chan = interaction.guild.get_channel(int(channel_id_raw))
                        if not chan:
                            try:
                                chan = await self.bot.fetch_channel(int(channel_id_raw))
                            except Exception:
                                chan = None
                except Exception:
                    chan = None

                if not chan:
                    # Ghost ticket! Channel was deleted from Discord. Close it in DB so user can appeal again
                    await db.close_appeal_ticket(interaction.guild.id, int(channel_id_raw) if channel_id_raw else 0, "Channel deleted", interaction.user.id)
                else:
                    chan_mention = chan.mention
                    return await interaction.response.send_message(
                        f"ℹ️ You already have an open appeal ticket pending review: {chan_mention}.",
                        ephemeral=True
                    )

            if reason:
                await interaction.response.defer(ephemeral=True)
                ticket_chan = await create_appeal_ticket_channel(interaction.guild, interaction.user, reason, "Submitted via /appeal slash command")
                if ticket_chan:
                    chan_link = f"https://discord.com/channels/{interaction.guild.id}/{ticket_chan.id}"
                    await interaction.followup.send(
                        f"✅ **Your appeal ticket has been opened in {interaction.guild.name}: [{ticket_chan.name}]({chan_link}) ({ticket_chan.mention})!**\n"
                        f"You have been granted permission to talk directly with the moderation team in your appeal channel. Staff has been notified to review your appeal.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send("❌ Failed to create appeal ticket. Please contact a moderator directly.", ephemeral=True)
            else:
                await interaction.response.send_modal(StrikeAppealModal())
        except Exception as e:
            logger.error(f"Error in /appeal: {e}")
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ An error occurred while opening appeal ticket: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ An error occurred while opening appeal ticket: {e}", ephemeral=True)



    @app_commands.command(name="appealrole", description="Configure which staff role gets pinged when a user opens an appeal ticket")
    @app_commands.describe(
        action="Choose action: set a role, view current role, or reset to default",
        role="The staff/moderator role to ping on new appeal tickets (required for 'set')"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="⚙️ Set Role (Ping a specific role)", value="set"),
            app_commands.Choice(name="🔄 Remove / Reset (Ping all staff & admin roles)", value="remove"),
            app_commands.Choice(name="📋 View Current Setting", value="view")
        ]
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.guild_only()
    async def appealrole_slash_cmd(self, interaction: discord.Interaction, action: str = "view", role: Optional[discord.Role] = None):
        try:
            if not is_protected(interaction.user) and not interaction.permissions.administrator:
                return await interaction.response.send_message("❌ Only Server Administrators can configure appeal ping roles.", ephemeral=True)

            guild = interaction.guild
            if action == "set":
                if not role:
                    return await interaction.response.send_message("❌ Please specify a role: `/appealrole set role:@Role`", ephemeral=True)
                await db.set_config(guild.id, "appeal_ping_role_id", role.id)
                embed = discord.Embed(
                    title="📩 Appeal Ping Role Updated",
                    description=f"When a member submits a strike/warning appeal, {role.mention} will now be pinged and given access to the appeal ticket channel.",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Configured by {interaction.user.display_name}")
                await interaction.response.send_message(embed=embed)
            elif action == "remove":
                await db.set_config(guild.id, "appeal_ping_role_id", "None")
                embed = discord.Embed(
                    title="🔄 Appeal Ping Role Reset",
                    description="Reset to default: All Server Administrators and Moderator roles will be pinged on new appeal tickets.",
                    color=discord.Color.blue()
                )
                embed.set_footer(text=f"Configured by {interaction.user.display_name}")
                await interaction.response.send_message(embed=embed)
            else:  # view
                role_id_raw = await db.get_config(guild.id, "appeal_ping_role_id", None)
                role_obj = None
                if role_id_raw and str(role_id_raw).lower() not in ("none", "null", "0", ""):
                    try:
                        role_obj = guild.get_role(int(role_id_raw))
                    except (ValueError, TypeError):
                        role_obj = None
            
                embed = discord.Embed(
                    title=f"📩 Appeal Ticket Notification Settings — {guild.name}",
                    color=discord.Color.gold()
                )
                if role_obj:
                    embed.add_field(name="🎭 Configured Ping Role", value=f"✅ {role_obj.mention} (`{role_obj.id}`)", inline=False)
                    embed.add_field(name="ℹ️ Behavior", value="Only members with this role will be pinged when an appeal ticket opens.", inline=False)
                else:
                    embed.add_field(name="🎭 Configured Ping Role", value="*Default: All staff and admin roles*", inline=False)
                    embed.add_field(name="ℹ️ Behavior", value="The bot automatically pings all moderator and administrator roles.", inline=False)
                embed.set_footer(text="Use /appealrole set @Role to customize, or /appealrole remove to reset.")
                await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"Error in /appealrole: {e}")
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Error configuring appeal role: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Error configuring appeal role: {e}", ephemeral=True)



    @app_commands.command(name="appealpanel", description="Post the official interactive strike appeal button panel in a channel")
    @app_commands.describe(channel="The channel to post the appeal panel in (defaults to current channel)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.guild_only()
    async def appealpanel_slash_cmd(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        try:
            if not is_protected(interaction.user) and not interaction.permissions.administrator:
                return await interaction.response.send_message("❌ Only Server Administrators can post the appeal panel.", ephemeral=True)

            target_channel = channel or interaction.channel
            guild = interaction.guild

            embed = discord.Embed(
                title=f"🛡️ {guild.name} • Official Strike Appeal Center",
                description=(
                    "Welcome to the official Strike & Moderation Appeal Portal.\n\n"
                    "If you have received a formal warning strike or a 7-day timeout and believe it was issued in error or you have proper justification, you can open an official appeal ticket here for staff review.\n\n"
                    "📌 **How It Works:**\n"
                    "1️⃣ Click the **`📩 Submit Strike Appeal`** button below.\n"
                    "2️⃣ Provide your reason and any relevant context in the popup form.\n"
                    "3️⃣ A private ticket channel (`#appeal-username`) will be created where you can speak directly with the moderation team.\n\n"
                    "🔇 **Muted / Timed-Out Members:**\n"
                    "• *Discord's client disables button clicks inside server channels during an active timeout.*\n"
                    "• **To appeal while timed out:**\n"
                    "  👉 Check your **Direct Message (DM) from Sweety** to click the appeal button, OR\n"
                    "  👉 Send `!appeal <your reason>` directly in **DM to Sweety**!"
                ),
                color=discord.Color.blue(),
                timestamp=datetime.datetime.utcnow()
            )
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            embed.set_footer(text="Sweety Strike Appeal Shield • Click below or DM !appeal <reason> to appeal")

            view = DMAppealLauncherView()
            try:
                await target_channel.send(embed=embed, view=view)
                await interaction.response.send_message(
                    f"✅ **Appeal Panel posted successfully in {target_channel.mention}!**\nMembers can click the button, and timed-out members can appeal via DM or `!appeal`.",
                    ephemeral=True
                )
            except Exception as e:
                logger.error(f"Failed to post appeal panel in {target_channel.id}: {e}")
                await interaction.response.send_message(f"❌ Failed to post appeal panel in {target_channel.mention}: {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /appealpanel: {e}")
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)



    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="The member to kick", reason="The reason for kicking")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def kick_command(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        try:
            if member is None:
                return await interaction.response.send_message("❌ That member is not in this server or has already left.", ephemeral=True)
            if not interaction.guild.me.guild_permissions.kick_members:
                return await interaction.response.send_message("❌ I lack the `Kick Members` permission in this server.", ephemeral=True)

            if is_protected(member):
                await interaction.response.send_message("❌ This member is staff/immune and cannot be kicked.", ephemeral=True)
                return
            
            if member.id == interaction.guild.owner_id:
                await interaction.response.send_message("❌ You cannot kick the Server Owner!", ephemeral=True)
                return
            
            if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
                await interaction.response.send_message("❌ You cannot kick this member because they have a higher or equal role than you.", ephemeral=True)
                return
            if member.top_role >= interaction.guild.me.top_role:
                await interaction.response.send_message("❌ I cannot kick this member because they have a higher or equal role than me.", ephemeral=True)
                return
            
            clean_reason = discord.utils.escape_mentions(reason[:500])
            try:
                await member.kick(reason=clean_reason)
                await interaction.response.send_message(f"✅ **{member.display_name}** has been kicked from the server. (Reason: {clean_reason})")
                await log_mod_action(interaction.guild, interaction.user, member, "Kick", clean_reason)
            except Exception as e:
                logger.error(f"Kick command failed: {e}", exc_info=True)
                await interaction.response.send_message("❌ Failed to kick member due to an internal error.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /kick: {e}", exc_info=True)
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)



    @app_commands.command(name="ban", description="Ban a user from the server")
    @app_commands.describe(
        member="The member/user to ban", 
        reason="The reason for the ban", 
        delete_message_days="Number of days of messages to delete (0-7)"
    )
    @app_commands.choices(
        delete_message_days=[
            app_commands.Choice(name="Don't delete any", value=0),
            app_commands.Choice(name="Previous 24 hours", value=1),
            app_commands.Choice(name="Previous 7 days", value=7)
        ]
    )
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def ban_command(self, interaction: discord.Interaction, member: discord.User, reason: str = "No reason provided", delete_message_days: int = 0):
        try:
            if not interaction.guild.me.guild_permissions.ban_members:
                return await interaction.response.send_message("❌ I lack the `Ban Members` permission in this server.", ephemeral=True)

            guild_member = interaction.guild.get_member(member.id)
            if is_protected(guild_member or member):
                await interaction.response.send_message("❌ This user is staff/immune and cannot be banned.", ephemeral=True)
                return
            
            if member.id == interaction.guild.owner_id:
                await interaction.response.send_message("❌ You cannot ban the Server Owner!", ephemeral=True)
                return
            
            if guild_member:
                if guild_member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
                    await interaction.response.send_message("❌ You cannot ban this member because they have a higher or equal role than you.", ephemeral=True)
                    return
                if guild_member.top_role >= interaction.guild.me.top_role:
                    await interaction.response.send_message("❌ I cannot ban this member because they have a higher or equal role than me.", ephemeral=True)
                    return
                
            clean_reason = discord.utils.escape_mentions(reason[:500])
            try:
                seconds = delete_message_days * 86400
                await interaction.guild.ban(member, reason=clean_reason, delete_message_seconds=seconds)
                await interaction.response.send_message(f"✅ **{member.display_name}** has been banned from the server. (Reason: {clean_reason})")
                await log_mod_action(interaction.guild, interaction.user, member, "Ban", clean_reason, f"Deleted messages history: {delete_message_days} days")
            except Exception as e:
                logger.error(f"Ban command failed: {e}", exc_info=True)
                await interaction.response.send_message("❌ Failed to ban user due to an internal error.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /ban: {e}", exc_info=True)
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)



    @app_commands.command(name="unban", description="Unban a user from the server")
    @app_commands.describe(user_id="The Discord ID of the user to unban", reason="The reason for unbanning")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def unban_command(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        try:
            if not interaction.guild.me.guild_permissions.ban_members:
                return await interaction.response.send_message("❌ I lack the `Ban Members` permission to unban users in this server.", ephemeral=True)
            clean_reason = discord.utils.escape_mentions(reason[:500])
            try:
                uid = int(user_id)
                user = await self.bot.fetch_user(uid)
                await interaction.guild.unban(user, reason=clean_reason)
                await interaction.response.send_message(f"✅ **{user.display_name}** (ID: {user_id}) has been unbanned. (Reason: {clean_reason})")
                await log_mod_action(interaction.guild, interaction.user, user, "Unban", clean_reason)
            except ValueError:
                await interaction.response.send_message("❌ Please provide a valid numerical User ID.", ephemeral=True)
            except discord.NotFound:
                await interaction.response.send_message("❌ That user was not found or is not banned.", ephemeral=True)
            except Exception as e:
                logger.error(f"Unban command failed: {e}", exc_info=True)
                await interaction.response.send_message("❌ Failed to unban user due to an internal error.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /unban: {e}", exc_info=True)
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


    # ── Formal Warning & Auto-Escalation System ──────────────────────────────────

    TICKET_CHANNEL_ID = 1549080000328896583


    @app_commands.command(name="mute", description="Timeout (mute) a member in the server")
    @app_commands.describe(
        member="The member to mute", 
        duration_minutes="Mute duration in minutes (max 40320 - 28 days)", 
        reason="The reason for muting"
    )
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def mute_command(self, interaction: discord.Interaction, member: discord.Member, duration_minutes: int, reason: str = "No reason provided"):
        if member is None:
            return await interaction.response.send_message("❌ That member is not in this server or has already left.", ephemeral=True)
        if not interaction.guild.me.guild_permissions.moderate_members:
            return await interaction.response.send_message("❌ I lack the `Moderate Members (Timeout)` permission in this server.", ephemeral=True)

        if is_protected(member):
            await interaction.response.send_message("❌ This member is staff/immune and cannot be muted.", ephemeral=True)
            return
        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You cannot mute this member because they have a higher or equal role than you.", ephemeral=True)
            return
        if member.top_role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ I cannot mute this member because they have a higher or equal role than me.", ephemeral=True)
            return

        if duration_minutes <= 0 or duration_minutes > 40320:
            await interaction.response.send_message("❌ Mute duration must be between 1 and 40,320 minutes (28 days).", ephemeral=True)
            return
        
        duration = datetime.timedelta(minutes=duration_minutes)
        clean_reason = discord.utils.escape_mentions(reason[:500])
        try:
            await member.timeout(duration, reason=clean_reason)
            await interaction.response.send_message(f"✅ **{member.display_name}** has been timed out for `{duration_minutes}` minutes. (Reason: {clean_reason})")
            await log_mod_action(interaction.guild, interaction.user, member, "Timeout (Mute)", clean_reason, f"Duration: {duration_minutes} minutes")
        except Exception as e:
            logger.error(f"Mute command failed: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to mute member due to an internal error.", ephemeral=True)



    @app_commands.command(name="unmute", description="Remove timeout (unmute) from a member in the server")
    @app_commands.describe(member="The member to unmute", reason="The reason for unmuting")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def unmute_command(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if member is None:
            return await interaction.response.send_message("❌ That member is not in this server or has already left.", ephemeral=True)
        if not interaction.guild.me.guild_permissions.moderate_members:
            return await interaction.response.send_message("❌ I lack the `Moderate Members (Timeout)` permission in this server.", ephemeral=True)

        if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("❌ You cannot unmute this member because they have a higher or equal role than you.", ephemeral=True)
            return
        if member.top_role >= interaction.guild.me.top_role:
            await interaction.response.send_message("❌ I cannot unmute this member because they have a higher or equal role than me.", ephemeral=True)
            return
        
        has_timeout = member.is_timed_out()
        muted_role = discord.utils.find(lambda r: r.name.lower() == "muted", interaction.guild.roles)
        has_role = muted_role and muted_role in member.roles
        active_mute = await db.get_active_mute(interaction.guild.id, member.id)

        if not has_timeout and not has_role and not active_mute:
            await interaction.response.send_message(f"ℹ️ **{member.display_name}** is not timed out or muted.", ephemeral=True)
            return
        
        clean_reason = discord.utils.escape_mentions(reason[:500])
        try:
            if has_timeout:
                await member.timeout(None, reason=clean_reason)
            if has_role:
                try:
                    await member.remove_roles(muted_role, reason=clean_reason)
                except Exception:
                    pass
            await db.remove_active_mute(interaction.guild.id, member.id)
            await interaction.response.send_message(f"✅ **{member.display_name}** is no longer timed out or muted. (Reason: {clean_reason})")
            await log_mod_action(interaction.guild, interaction.user, member, "Unmute", clean_reason)
        except Exception as e:
            logger.error(f"Unmute command failed: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to unmute member due to an internal error.", ephemeral=True)



    @app_commands.command(name="purge", description="Quickly delete a specified number of messages from this channel with undo support")
    @app_commands.describe(amount="Number of messages to delete (max 100)")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
    async def purge_command(self, interaction: discord.Interaction, amount: int):
        try:
            amount = max(1, min(amount, 100))
            await interaction.response.defer(ephemeral=True)
            try:
                deleted = await interaction.channel.purge(limit=amount)
                for msg in deleted:
                    _bot_deleted_message_ids.add(msg.id)
            
                # Serialize deleted messages in chronological order (oldest -> newest)
                serialized_backup = []
                for msg in reversed(deleted):
                    serialized_backup.append({
                        "id": msg.id,
                        "author_name": msg.author.display_name,
                        "author_avatar": msg.author.display_avatar.url if msg.author.display_avatar else None,
                        "content": msg.content,
                        "embeds": [e.to_dict() for e in msg.embeds],
                        "attachments": [a.url for a in msg.attachments],
                        "timestamp": msg.created_at.timestamp() if msg.created_at else time.time(),
                        "purged_at": time.time(),
                        "purged_by": interaction.user.id
                    })
            
                _purge_history_buffer[interaction.channel.id] = serialized_backup

                embed = discord.Embed(
                    title="🧹 Messages Purged",
                    description=(
                        f"Successfully purged `{len(deleted)}` messages from {interaction.channel.mention}.\n\n"
                        f"💡 **Made a mistake?** Click **`↩️ Undo Purge`** below (or run `/unpurge`) within **15 minutes** to restore these messages!"
                    ),
                    color=discord.Color.gold(),
                    timestamp=discord.utils.utcnow()
                )
                view = UndoPurgeView(interaction.channel.id, interaction.user.id, len(deleted))
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            except Exception as e:
                logger.error(f"Purge failed: {e}", exc_info=True)
                await interaction.followup.send("❌ Purge failed due to an internal error.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /purge: {e}")
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)



    @app_commands.command(name="unpurge", description="Undo the last purge in this channel and restore the messages")
    @app_commands.describe(channel="Channel to restore purged messages in (defaults to current channel)")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
    async def unpurge_slash_cmd(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        try:
            target_chan = channel or interaction.channel
            if not isinstance(target_chan, discord.TextChannel):
                return await interaction.response.send_message("❌ Please specify a valid text channel.", ephemeral=True)
        
            if not interaction.user.guild_permissions.manage_messages and not is_protected(interaction.user):
                return await interaction.response.send_message("❌ You need **Manage Messages** permission to undo a purge.", ephemeral=True)
        
            if target_chan.id not in _purge_history_buffer:
                return await interaction.response.send_message(f"ℹ️ No recent purge backup found for {target_chan.mention} (backups expire after 15 minutes).", ephemeral=True)
        
            await interaction.response.defer(ephemeral=True)
            restored = await restore_purged_messages(target_chan)
            if restored > 0:
                await interaction.followup.send(f"✅ **Purge Reverted!** Successfully restored `{restored}` messages in {target_chan.mention}.", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Failed to restore messages or backup expired.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /unpurge: {e}")
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


    @app_commands.command(name="setnick", description="Set or change a server member's nickname so it appears to everyone")
    @app_commands.describe(
        member="The user whose nickname you want to set",
        nickname="The new nickname to set (leave blank or type 'reset' to clear back to original username)"
    )
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def setnick_slash_cmd(self, interaction: discord.Interaction, member: discord.Member, nickname: Optional[str] = None):
        """Slash command to set or reset a member's server nickname visible to everyone."""
        try:
            if not interaction.user.guild_permissions.manage_nicknames and not is_protected(interaction.user):
                return await interaction.response.send_message("❌ You need the **Manage Nicknames** permission to set nicknames.", ephemeral=True)

            if not interaction.guild.me.guild_permissions.manage_nicknames:
                return await interaction.response.send_message("❌ I do not have the **Manage Nicknames** permission in this server.", ephemeral=True)

            if member.id == interaction.guild.owner_id and interaction.user.id != interaction.guild.owner_id:
                return await interaction.response.send_message("❌ You cannot change the Server Owner's nickname.", ephemeral=True)

            if interaction.user.id != interaction.guild.owner_id and not is_creator(interaction.user):
                if interaction.user.top_role <= member.top_role:
                    return await interaction.response.send_message("❌ You cannot change the nickname of a member with an equal or higher role than yourself.", ephemeral=True)

            if interaction.guild.me.top_role <= member.top_role and member.id != interaction.guild.me.id:
                return await interaction.response.send_message("❌ I cannot change this member's nickname because their role is higher than or equal to my highest role.", ephemeral=True)

            old_nick = member.display_name
            clean_nick = nickname.strip() if nickname else ""

            if not clean_nick or clean_nick.lower() in ["reset", "clear", "none", "off"]:
                new_nick = None
                action_text = f"Reset nickname for **{member.name}** back to original username."
            else:
                if len(clean_nick) > 32:
                    return await interaction.response.send_message("❌ Nicknames must be **32 characters or fewer** in length.", ephemeral=True)
                new_nick = clean_nick
                action_text = f"Changed nickname for **{member.name}** to **{new_nick}**."

            await member.edit(nick=new_nick, reason=f"Nickname changed by {interaction.user} ({interaction.user.id})")

            embed = discord.Embed(
                title="🏷️ Server Nickname Updated",
                description=f"✅ {action_text}\nThis name is now visible to everyone in **{interaction.guild.name}**!",
                color=discord.Color.blue()
            )
            embed.add_field(name="User", value=member.mention, inline=True)
            embed.add_field(name="Old Name", value=f"`{old_nick}`", inline=True)
            embed.add_field(name="New Name", value=f"`{new_nick or member.name}`", inline=True)
            embed.set_footer(text=f"Updated by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
            embed.timestamp = discord.utils.utcnow()

            await interaction.response.send_message(embed=embed)
            await log_mod_action(interaction.guild, interaction.user, member, "Set Nickname", f"New nick: {new_nick or '[RESET]'}")
        except discord.Forbidden:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Failed to set nickname. Missing permission or target member has a higher role hierarchy than the bot.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /setnick: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error setting nickname: {e}", ephemeral=True)



    @app_commands.command(name="lockdown", description="Freeze or unfreeze public chat channels in an emergency")
    @app_commands.describe(status="Lock or unlock the channels")
    @app_commands.choices(
        status=[
            app_commands.Choice(name="Lock (Freeze)", value="on"),
            app_commands.Choice(name="Unlock (Unfreeze)", value="off")
        ]
    )
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
    @app_commands.guild_only()
    async def lockdown_command(self, interaction: discord.Interaction, status: str):
        try:
            await interaction.response.defer(thinking=True)
            guild = interaction.guild
            if status == "on":
                locked = 0
                for chan in guild.text_channels:
                    # Skip if regular members already cannot send messages
                    overwrites = chan.overwrites_for(guild.default_role)
                    if overwrites.send_messages is False:
                        continue
                    
                    try:
                        await chan.set_permissions(guild.default_role, send_messages=False, reason="Emergency Lockdown")
                        await db.add_resource(guild.id, "locked_channels", chan.id)
                        locked += 1
                        await asyncio.sleep(0.2)  # Avoid rate limiting
                    except Exception:
                        pass
                await interaction.followup.send(f"🚨 **EMERGENCY LOCKDOWN INITIATED!** 🚨\nLocked `{locked}` public text channels. Regular members cannot type until unlocked.")
            else:
                unlocked = 0
                locked_resources = await db.get_resources(guild.id, "locked_channels")
                locked_ids = {r["resource_id"] for r in locked_resources}
            
                for chan in guild.text_channels:
                    if chan.id in locked_ids:
                        try:
                            await chan.set_permissions(guild.default_role, send_messages=None, reason="Lockdown Lifted")
                            unlocked += 1
                            await asyncio.sleep(0.2)  # Avoid rate limiting
                        except Exception:
                            pass
                await db.delete_resources_by_type(guild.id, "locked_channels")
                await interaction.followup.send(f"🔓 **LOCKDOWN LIFTED!** Unlocked `{unlocked}` channels. Public chat is reopened.")
        except Exception as e:
            logger.error(f"Error in /lockdown: {e}")
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Lockdown error: {e}")
            else:
                await interaction.response.send_message(f"❌ Lockdown error: {e}", ephemeral=True)


    # ── Purge & Undo-Purge Restoration Subsystem ─────────────────────────────────
    _purge_history_buffer: dict[int, list[dict]] = {}
    _PURGE_BACKUP_TTL = 900  # 15 minutes



    @app_commands.command(name="slowmode", description="Set chat slowmode to throttle raid spam")
    @app_commands.describe(seconds="Slowmode delay in seconds (0 to turn off, max 21600)", channel="Optional target channel")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def slowmode_command(self, interaction: discord.Interaction, seconds: int, channel: discord.TextChannel = None):
        try:
            target = channel or interaction.channel
            seconds = max(0, min(seconds, 21600))
            await target.edit(slowmode_delay=seconds, reason=f"Slowmode set by {interaction.user}")
            if seconds == 0:
                await interaction.response.send_message(f"🔓 Slowmode disabled in {target.mention}.")
            else:
                await interaction.response.send_message(f"⏱️ Slowmode in {target.mention} set to **{seconds} seconds**.")
        except Exception as e:
            logger.error(f"Error in /slowmode: {e}")
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Failed to update slowmode: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Failed to update slowmode: {e}", ephemeral=True)



    @app_commands.command(name="autorole", description="Configure a role to be automatically assigned to new members on join")
    @app_commands.describe(
        status="Enable or disable auto-role",
        role="The role to assign (required when enabling)"
    )
    @app_commands.choices(
        status=[
            app_commands.Choice(name="Enable", value="on"),
            app_commands.Choice(name="Disable", value="off")
        ]
    )
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
    async def autorole_command(self, interaction: discord.Interaction, status: str, role: discord.Role = None):
        try:
            if status == "on":
                if not role:
                    await interaction.response.send_message("❌ Please specify the `role` you want to assign automatically.", ephemeral=True)
                    return
                
                if role.position >= interaction.user.top_role.position and interaction.user.id != interaction.guild.owner_id:
                    await interaction.response.send_message("❌ You cannot configure an auto-role that is higher than or equal to your own top role.", ephemeral=True)
                    return
                
                if role.position >= interaction.guild.me.top_role.position:
                    await interaction.response.send_message("❌ I cannot assign this role because it is higher than my bot role. Please drag my bot role higher in server settings.", ephemeral=True)
                    return
                
                await db.set_config(interaction.guild_id, "auto_role_id", role.id)
                await interaction.response.send_message(f"✅ **Auto-Role enabled!** New members will automatically be assigned the **{role.name}** role.")
            else:
                await db.set_config(interaction.guild_id, "auto_role_id", None)
                await interaction.response.send_message("⚙️ **Auto-Role disabled.**")
        except Exception as e:
            logger.error(f"Error in autorole command: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Failed to configure auto-role due to an internal error.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Failed to configure auto-role due to an internal error.", ephemeral=True)



    @app_commands.command(name="addrole", description="Assign a role to a member")
    @app_commands.describe(member="The member to assign the role to", role="The role to assign")
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def addrole_command(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if role.managed:
            await interaction.followup.send("❌ This is a managed/integration role and cannot be manually assigned.", ephemeral=True)
            return
        
        if role.position >= interaction.user.top_role.position and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send("❌ You cannot assign a role that is higher than or equal to your own top role.", ephemeral=True)
            return
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.followup.send("❌ I cannot assign this role because it is higher than my bot role. Please drag my bot role higher in server settings.", ephemeral=True)
            return
        
        try:
            await member.add_roles(role, reason=f"Assigned by {interaction.user.display_name}")
            await interaction.followup.send(f"✅ Successfully added role **{role.name}** to **{member.display_name}**.", ephemeral=True)
        except Exception as e:
            logger.error(f"Addrole command failed: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to assign role due to an internal error.", ephemeral=True)



    @app_commands.command(name="removerole", description="Remove a role from a member")
    @app_commands.describe(member="The member to remove the role from", role="The role to remove")
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def removerole_command(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if role.managed:
            await interaction.followup.send("❌ This is a managed/integration role and cannot be manually removed.", ephemeral=True)
            return
        
        if role.position >= interaction.user.top_role.position and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send("❌ You cannot remove a role that is higher than or equal to your own top role.", ephemeral=True)
            return
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.followup.send("❌ I cannot remove this role because it is higher than my bot role. Please drag my bot role higher in server settings.", ephemeral=True)
            return
        
        try:
            await member.remove_roles(role, reason=f"Removed by {interaction.user.display_name}")
            await interaction.followup.send(f"✅ Successfully removed role **{role.name}** from **{member.display_name}**.", ephemeral=True)
        except Exception as e:
            logger.error(f"Removerole command failed: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to remove role due to an internal error.", ephemeral=True)



    @app_commands.command(name="warn", description="Issue a formal warning to a member with auto-escalation")
    @app_commands.describe(member="The member to warn", reason="Reason for the warning")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def warn_command(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        try:
            if member is None:
                return await interaction.response.send_message("❌ That member is not in this server or has already left.", ephemeral=True)
            if not interaction.guild.me.guild_permissions.moderate_members:
                return await interaction.response.send_message("❌ I lack the `Moderate Members (Timeout)` permission in this server.", ephemeral=True)

            if is_protected(member):
                await interaction.response.send_message("❌ This member is staff/immune and cannot be warned.", ephemeral=True)
                return
            if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
                await interaction.response.send_message("❌ You cannot warn this member because they have a higher or equal role than you.", ephemeral=True)
                return
            if member.id == interaction.guild.owner_id:
                await interaction.response.send_message("❌ You cannot warn the Server Owner!", ephemeral=True)
                return

            await interaction.response.defer()
            clean_reason = discord.utils.escape_mentions(reason[:500])
            total_warns, escalation = await issue_warning_logic(interaction.guild, member, interaction.user, clean_reason)
        
            embed = discord.Embed(
                title="⚠️ Member Formally Warned",
                description=f"**{member.mention}** has been issued a warning.{escalation}",
                color=discord.Color.gold()
            )
            embed.add_field(name="User", value=f"{member.name} (`{member.id}`)", inline=True)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
            embed.add_field(name="Total Warnings", value=f"`{total_warns}`", inline=True)
            embed.add_field(name="Reason", value=clean_reason, inline=False)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in /warn: {e}", exc_info=True)
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Failed to warn member: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Failed to warn member: {e}", ephemeral=True)





    # ── Interactive Warning Management UI ──────────────────────────────────────────


    @app_commands.command(name="warnings", description="View all active warnings and infraction history for a member")
    @app_commands.describe(member="The member to check (defaults to yourself)")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
    async def warnings_command(self, interaction: discord.Interaction, member: discord.Member = None):
        try:
            target = member or interaction.user
            await interaction.response.defer()
        
            warns = await db.get_warnings(interaction.guild.id, target.id)
            if not warns:
                embed = discord.Embed(
                    title=f"📜 Warning History — {target.display_name}",
                    description=f"✅ **{target.mention} has a clean record with 0 warnings!**",
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=target.display_avatar.url)
                await interaction.followup.send(embed=embed)
                return

            embed = discord.Embed(
                title=f"⚠️ Infraction Record — {target.display_name}",
                description=f"Total Warnings on file: **`{len(warns)}`**",
                color=discord.Color.orange()
            )
            embed.set_thumbnail(url=target.display_avatar.url)
        
            for idx, w in enumerate(warns[:10], 1):
                warn_id = w.get("id") if isinstance(w, dict) else w[0]
                mod_id = w.get("moderator_id") if isinstance(w, dict) else w[1]
                reason = w.get("reason") if isinstance(w, dict) else w[2]
                ts = w.get("timestamp") if isinstance(w, dict) else w[3]
                embed.add_field(
                    name=f"Warning #{idx} (ID: `{warn_id}`) • {ts or 'Recently'}",
                    value=f"• **Reason:** {reason}\n• **Moderator:** <@{mod_id}>",
                    inline=False
                )
            if len(warns) > 10:
                embed.set_footer(text=f"Showing top 10 of {len(warns)} total warnings. Use /clearwarns or /delwarn to manage.")
            else:
                embed.set_footer(text="Sweety Moderation Shield • Use /clearwarns or /delwarn to manage")
            
            # Attach interactive action view if viewer is moderator/staff, or appeal button if user checking their own warnings
            view = None
            if is_protected(interaction.user):
                view = WarningActionView(interaction.guild.id, target, interaction.user.id)
            elif target.id == interaction.user.id and len(warns) > 0:
                view = DMAppealLauncherView()

            await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error in /warnings: {e}", exc_info=True)
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Failed to fetch warnings: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Failed to fetch warnings: {e}", ephemeral=True)



    @app_commands.command(name="clearwarns", description="Clear warnings for a member (all or a specific amount)")
    @app_commands.describe(
        member="The member whose warnings will be cleared",
        amount="Number of warnings to remove (Select from dropdown or leave empty to clear all)"
    )
    @app_commands.choices(amount=[
        app_commands.Choice(name="1 Warning", value=1),
        app_commands.Choice(name="2 Warnings", value=2),
        app_commands.Choice(name="3 Warnings", value=3),
        app_commands.Choice(name="5 Warnings", value=5),
        app_commands.Choice(name="10 Warnings", value=10),
        app_commands.Choice(name="All Warnings", value=0)
    ])
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def clearwarns_command(self, interaction: discord.Interaction, member: discord.Member, amount: Optional[int] = None):
        try:
            # Staff / Mod Permission Check
            if not is_protected(interaction.user):
                await interaction.response.send_message("❌ You do not have permission to clear warnings.", ephemeral=True)
                return

            # Role Hierarchy Check (Creator/Owner/Admins bypass)
            is_admin = interaction.user.guild_permissions.administrator or interaction.user.id == interaction.guild.owner_id or interaction.user.id == 719932313919684670
            if not is_admin and is_protected(member) and member.top_role >= interaction.user.top_role:
                await interaction.response.send_message("❌ You cannot modify warnings for another staff member with a higher or equal role.", ephemeral=True)
                return

            amt = amount if (amount is not None and amount > 0) else None
            await interaction.response.defer()
            count = await db.clear_warnings(interaction.guild.id, member.id, amount=amt)
            if count == 0:
                await interaction.followup.send(f"ℹ️ **{member.mention}** currently has no warnings on record.", ephemeral=True)
                return

            if amt is not None:
                desc = f"Successfully removed **`{count}`** recent warning(s) for **{member.mention}**."
            else:
                desc = f"Successfully cleared all **`{count}`** warning(s) for **{member.mention}**.\nTheir record has been reset to clean."

            embed = discord.Embed(
                title="🧹 Warnings Cleared",
                description=desc,
                color=discord.Color.green()
            )
            embed.add_field(name="Member", value=f"{member.name} (`{member.id}`)", inline=True)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
            embed.add_field(name="Warnings Removed", value=f"`{count}`", inline=True)
            await interaction.followup.send(embed=embed)
            await log_mod_action(interaction.guild, interaction.user, member, "Warnings Cleared", f"Cleared {count} warnings")
        except Exception as e:
            logger.error(f"Error in /clearwarns: {e}", exc_info=True)
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Failed to clear warnings: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Failed to clear warnings: {e}", ephemeral=True)



    @app_commands.command(name="delwarn", description="Delete a single warning by its specific Warning ID")
    @app_commands.describe(warn_id="The ID of the warning to delete (found using /warnings)")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def delwarn_command(self, interaction: discord.Interaction, warn_id: int):
        try:
            if not is_protected(interaction.user):
                await interaction.response.send_message("❌ You do not have permission to delete warnings.", ephemeral=True)
                return

            await interaction.response.defer()
            success = await db.delete_warning_by_id(interaction.guild.id, warn_id)
            if success:
                embed = discord.Embed(
                    title="🗑️ Warning Deleted",
                    description=f"Successfully deleted warning with ID **`{warn_id}`**.",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Action by {interaction.user.display_name}")
                await interaction.followup.send(embed=embed)
                await log_mod_action(interaction.guild, interaction.user, None, "Warning Deleted", f"Deleted warning ID {warn_id}")
            else:
                await interaction.followup.send(f"❌ Warning with ID **`{warn_id}`** was not found in this server.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /delwarn: {e}", exc_info=True)
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Failed to delete warning: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Failed to delete warning: {e}", ephemeral=True)



    @app_commands.command(name="warnleaderboard", description="Display the server leaderboard of members with the most warnings")
    @app_commands.describe(limit="Number of top warned users to display (5 to 25, default 10)")
    @app_commands.choices(limit=[
        app_commands.Choice(name="Top 5", value=5),
        app_commands.Choice(name="Top 10", value=10),
        app_commands.Choice(name="Top 15", value=15),
        app_commands.Choice(name="Top 20", value=20),
        app_commands.Choice(name="Top 25", value=25),
    ])
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 5.0, key=lambda i: (i.guild_id, i.user.id))
    async def warnleaderboard_command(self, interaction: discord.Interaction, limit: Optional[int] = 10):
        try:
            await interaction.response.defer()
            limit = max(1, min(limit or 10, 25))
            rows = await db.get_warnings_leaderboard(interaction.guild.id, limit=limit)
        
            if not rows:
                embed = discord.Embed(
                    title=f"🏆 Warnings Leaderboard — {interaction.guild.name}",
                    description="✅ **No warnings recorded in this server! The record is completely clean.**",
                    color=discord.Color.green()
                )
                if interaction.guild.icon:
                    embed.set_thumbnail(url=interaction.guild.icon.url)
                await interaction.followup.send(embed=embed)
                return

            embed = discord.Embed(
                title=f"⚠️ Warnings Leaderboard — {interaction.guild.name}",
                description=f"Showing top **{len(rows)}** members with active infractions on file.\n",
                color=discord.Color.orange()
            )
            if interaction.guild.icon:
                embed.set_thumbnail(url=interaction.guild.icon.url)

            rank_emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            lines = []
            for idx, r in enumerate(rows, 1):
                uid = r["user_id"] if isinstance(r, dict) and "user_id" in r else r[0]
                cnt = int(r["warn_count"] if isinstance(r, dict) and "warn_count" in r else r[1])
            
                if cnt >= 6:
                    risk = f"⛔ **{cnt} Strikes** `(Permanent Ban Applied)`"
                elif cnt >= 3:
                    remaining = 6 - cnt
                    risk = f"🛑 **{cnt} Strikes** `(7-Day Mute / {remaining} from Ban)`"
                else:
                    remaining = 3 - cnt
                    risk = f"🟡 **{cnt} Strike{'s' if cnt != 1 else ''}** `({remaining} from 7-Day Mute)`"

                medal = rank_emojis[idx-1] if idx <= len(rank_emojis) else f"`#{idx}`"
                lines.append(f"{medal} <@{uid}> — {risk}")

            embed.description = "\n\n".join(lines)
            embed.set_footer(text="Sweety Moderation Shield • Use /warnings <user> or /clearwarns to manage")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in /warnleaderboard: {e}", exc_info=True)
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Failed to fetch warning leaderboard: {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Failed to fetch warning leaderboard: {e}", ephemeral=True)










    @commands.command(name="kick")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def kick_prefix_cmd(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = "No reason provided"):
        """Kick a member from the server: !kick @user [reason]"""
        try:
            if is_protected(member) or member.id == ctx.guild.owner_id:
                return await ctx.send("❌ This member is staff/immune and cannot be kicked.")
            if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
                return await ctx.send("❌ You cannot kick this member because they have a higher or equal role.")
            if member.top_role >= ctx.guild.me.top_role:
                return await ctx.send("❌ I cannot kick this member because their role is higher than mine.")
            clean_reason = discord.utils.escape_mentions(reason[:500])
            await member.kick(reason=clean_reason)
            await ctx.send(f"✅ **{member.display_name}** has been kicked. (Reason: {clean_reason})")
            await log_mod_action(ctx.guild, ctx.author, member, "Kick", clean_reason)
        except Exception as e:
            logger.error(f"Error in !kick: {e}")
            await ctx.send(f"❌ Error: {e}")



    @commands.command(name="ban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def ban_prefix_cmd(self, ctx: commands.Context, member: discord.User, *, reason: Optional[str] = "No reason provided"):
        """Ban a user from the server: !ban @user [reason]"""
        try:
            guild_member = ctx.guild.get_member(member.id)
            if guild_member and (is_protected(guild_member) or member.id == ctx.guild.owner_id):
                return await ctx.send("❌ This user is staff/immune and cannot be banned.")
            if guild_member and guild_member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
                return await ctx.send("❌ You cannot ban this member because they have a higher or equal role.")
            clean_reason = discord.utils.escape_mentions(reason[:500])
            await ctx.guild.ban(member, reason=clean_reason, delete_message_days=0)
            await ctx.send(f"✅ **{member.name}** has been banned from the server. (Reason: {clean_reason})")
            await log_mod_action(ctx.guild, ctx.author, member, "Ban", clean_reason)
        except Exception as e:
            logger.error(f"Error in !ban: {e}")
            await ctx.send(f"❌ Error: {e}")



    @commands.command(name="unban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def unban_prefix_cmd(self, ctx: commands.Context, user_id: int, *, reason: Optional[str] = "No reason provided"):
        """Unban a user by their user ID: !unban <user_id> [reason]"""
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=reason)
            await ctx.send(f"✅ **{user.name}** (`{user.id}`) has been unbanned.")
            await log_mod_action(ctx.guild, ctx.author, user, "Unban", reason)
        except Exception as e:
            logger.error(f"Error in !unban: {e}")
            await ctx.send(f"❌ Error: {e}")



    @commands.command(name="mute", aliases=["timeout"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def mute_prefix_cmd(self, ctx: commands.Context, member: discord.Member, duration: str = "10m", *, reason: Optional[str] = "No reason provided"):
        """Timeout (mute) a member: !mute @user [duration e.g. 10m, 1h, 1d] [reason]"""
        try:
            if is_protected(member) or member.id == ctx.guild.owner_id:
                return await ctx.send("❌ This member is staff/immune and cannot be timed out.")
            if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
                return await ctx.send("❌ You cannot mute this member because they have a higher or equal role.")
            seconds = parse_time_string(duration)
            if not seconds or seconds < 10 or seconds > 2419200:
                return await ctx.send("❌ Invalid duration. Please provide a time between 10 seconds and 28 days (e.g. `10m`, `2h`, `1d`).")
            until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
            await member.timeout(until, reason=reason)
            await ctx.send(f"🔇 **{member.display_name}** has been timed out for **{duration}**. (Reason: {reason})")
            await log_mod_action(ctx.guild, ctx.author, member, f"Timeout ({duration})", reason)
        except Exception as e:
            logger.error(f"Error in !mute: {e}")
            await ctx.send(f"❌ Error: {e}")



    @commands.command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def unmute_prefix_cmd(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Remove timeout and @Muted role from a member: !unmute @member [reason]"""
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send("❌ You cannot unmute this member because they have a higher or equal role than you.")
            return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send("❌ I cannot unmute this member because they have a higher or equal role than me.")
            return

        has_timeout = member.is_timed_out()
        muted_role = discord.utils.find(lambda r: r.name.lower() == "muted", ctx.guild.roles)
        has_role = muted_role and muted_role in member.roles
        active_mute = await db.get_active_mute(ctx.guild.id, member.id)

        if not has_timeout and not has_role and not active_mute:
            await ctx.send(f"ℹ️ **{member.display_name}** is not timed out or muted.")
            return

        try:
            if has_timeout:
                await member.timeout(None, reason=reason)
            if has_role:
                try:
                    await member.remove_roles(muted_role, reason=reason)
                except Exception:
                    pass
            await db.remove_active_mute(ctx.guild.id, member.id)
            await ctx.send(f"✅ **{member.display_name}** is no longer timed out or muted. (Reason: {reason})")
            await log_mod_action(ctx.guild, ctx.author, member, "Unmute", reason)
        except Exception as e:
            logger.error(f"Prefix unmute command failed: {e}", exc_info=True)
            await ctx.send("❌ Failed to unmute member due to an internal error.")



    @commands.command(name="purge", aliases=["clear", "clean"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def purge_prefix_cmd(self, ctx: commands.Context, amount: int = 10):
        """Purge recent messages from channel: !purge [amount max 100]"""
        try:
            amt = min(max(amount, 1), 100)
            deleted = await ctx.channel.purge(limit=amt + 1)
            msg = await ctx.send(f"🧹 Successfully purged **{len(deleted)-1}** messages.")
            await asyncio.sleep(4)
            try:
                await msg.delete()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error in !purge: {e}")
            await ctx.send(f"❌ Error: {e}")



    @commands.command(name="unpurge", aliases=["undopurge"])
    @commands.guild_only()
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def unpurge_prefix_cmd(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Undo the last purge in a channel and restore messages: !unpurge [#channel]"""
        try:
            target_chan = channel or ctx.channel
            if not isinstance(target_chan, discord.TextChannel):
                return await ctx.reply("❌ Please specify a valid text channel.")
        
            if not ctx.author.guild_permissions.manage_messages and not is_protected(ctx.author):
                return await ctx.reply("❌ You need **Manage Messages** permission to undo a purge.")
        
            if target_chan.id not in _purge_history_buffer:
                return await ctx.reply(f"ℹ️ No recent purge backup found for {target_chan.mention} (backups expire after 15 minutes).")
        
            status_msg = await ctx.reply(f"⏳ **Restoring purged messages in {target_chan.mention}...**")
            restored = await restore_purged_messages(target_chan)
            if restored > 0:
                await status_msg.edit(content=f"✅ **Purge Reverted!** Successfully restored `{restored}` messages in {target_chan.mention} via Webhook clone.")
            else:
                await status_msg.edit(content=f"❌ Failed to restore messages or backup expired.")
        except Exception as e:
            logger.error(f"Error in !unpurge: {e}")
            await ctx.reply(f"❌ Error: {e}")



    @commands.command(name="lockdown", aliases=["lock"])
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def lockdown_prefix_cmd(self, ctx: commands.Context, status: Optional[str] = "lock"):
        """Lock or unlock the current channel: !lockdown [lock|unlock]"""
        try:
            is_lock = (status.lower() != "unlock")
            overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = False if is_lock else None
            await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
            state_str = "🔒 **LOCKED** (Members can no longer send messages)" if is_lock else "🔓 **UNLOCKED** (Members can now chat)"
            await ctx.send(f"{state_str} in {ctx.channel.mention}.")
        except Exception as e:
            logger.error(f"Error in !lockdown: {e}")
            await ctx.send(f"❌ Error: {e}")



    @commands.command(name="slowmode", aliases=["slow"])
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def slowmode_prefix_cmd(self, ctx: commands.Context, seconds: int = 0):
        """Set slowmode for current channel: !slowmode <seconds> (0 to disable)"""
        try:
            sec = min(max(seconds, 0), 21600)
            await ctx.channel.edit(slowmode_delay=sec)
            status_str = f"⏱️ Slowmode set to **{sec} seconds**." if sec > 0 else "⏱️ Slowmode has been **disabled**."
            await ctx.send(status_str)
        except Exception as e:
            logger.error(f"Error in !slowmode: {e}")
            await ctx.send(f"❌ Error: {e}")



    @commands.command(name="autorole")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def autorole_prefix_cmd(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Set or disable automatic role for new members: !autorole [@role]"""
        try:
            if role:
                await db.set_autorole(ctx.guild.id, role.id)
                await ctx.send(f"✅ Auto-role enabled! New members will receive {role.mention}.")
            else:
                await db.set_autorole(ctx.guild.id, None)
                await ctx.send("✅ Auto-role has been disabled.")
        except Exception as e:
            logger.error(f"Error in !autorole: {e}")
            await ctx.send(f"❌ Error: {e}")



    @commands.command(name="addrole")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def addrole_prefix_cmd(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        """Assign a role to a member: !addrole @user @role"""
        try:
            if role >= ctx.guild.me.top_role:
                return await ctx.send("❌ I cannot assign this role because it is higher than my highest role.")
            await member.add_roles(role)
            await ctx.send(f"✅ Added {role.mention} to **{member.display_name}**.")
        except Exception as e:
            logger.error(f"Error in !addrole: {e}")
            await ctx.send(f"❌ Error: {e}")



    @commands.command(name="removerole")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def removerole_prefix_cmd(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        """Remove a role from a member: !removerole @user @role"""
        try:
            if role >= ctx.guild.me.top_role:
                return await ctx.send("❌ I cannot remove this role because it is higher than my highest role.")
            await member.remove_roles(role)
            await ctx.send(f"✅ Removed {role.mention} from **{member.display_name}**.")
        except Exception as e:
            logger.error(f"Error in !removerole: {e}")
            await ctx.send(f"❌ Error: {e}")



    @commands.command(name="setnick", aliases=["setname", "nickname", "nick", "rename", "changenick"])
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def setnick_prefix_cmd(self, ctx: commands.Context, member: discord.Member, *, nickname: Optional[str] = None):
        """Set or change a server member's nickname visible to everyone: !setnick @user [new_nickname]"""
        try:
            if not ctx.guild.me.guild_permissions.manage_nicknames:
                return await ctx.send("❌ I do not have the **Manage Nicknames** permission in this server.")

            if member.id == ctx.guild.owner_id and ctx.author.id != ctx.guild.owner_id:
                return await ctx.send("❌ You cannot change the Server Owner's nickname.")

            if ctx.author.id != ctx.guild.owner_id and not is_creator(ctx.author):
                if ctx.author.top_role <= member.top_role:
                    return await ctx.send("❌ You cannot change the nickname of a member with an equal or higher role than yourself.")

            if ctx.guild.me.top_role <= member.top_role and member.id != ctx.guild.me.id:
                return await ctx.send("❌ I cannot change this member's nickname because their role is higher than or equal to my highest role.")

            old_nick = member.display_name
            clean_nick = nickname.strip() if nickname else ""

            if not clean_nick or clean_nick.lower() in ["reset", "clear", "none", "off"]:
                new_nick = None
                action_text = f"Reset nickname for **{member.name}** back to original username."
            else:
                if len(clean_nick) > 32:
                    return await ctx.send("❌ Nicknames must be **32 characters or fewer** in length.")
                new_nick = clean_nick
                action_text = f"Changed nickname for **{member.name}** to **{new_nick}**."

            await member.edit(nick=new_nick, reason=f"Nickname changed by {ctx.author} ({ctx.author.id})")

            embed = discord.Embed(
                title="🏷️ Server Nickname Updated",
                description=f"✅ {action_text}\nThis name is now visible to everyone in **{ctx.guild.name}**!",
                color=discord.Color.blue()
            )
            embed.add_field(name="User", value=member.mention, inline=True)
            embed.add_field(name="Old Name", value=f"`{old_nick}`", inline=True)
            embed.add_field(name="New Name", value=f"`{new_nick or member.name}`", inline=True)
            embed.set_footer(text=f"Updated by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            embed.timestamp = discord.utils.utcnow()

            await ctx.send(embed=embed)
            await log_mod_action(ctx.guild, ctx.author, member, "Set Nickname", f"New nick: {new_nick or '[RESET]'}")
        except discord.Forbidden:
            await ctx.send("❌ Failed to set nickname. Missing permission or target member has a higher role hierarchy than the bot.")
        except Exception as e:
            logger.error(f"Error in !setnick: {e}")
            await ctx.send(f"❌ Error setting nickname: {e}")



    @commands.command(name="warn", aliases=["strike", "strikemember"])
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def warn_prefix_cmd(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Issue a warning or strike to a member: !warn @member [reason] or !strike @member [reason]"""
        try:
            if is_protected(member):
                await ctx.send("❌ This member is staff/immune and cannot be warned.")
                return
            if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
                await ctx.send("❌ You cannot warn this member because they have a higher or equal role than you.")
                return
            if member.id == ctx.guild.owner_id:
                await ctx.send("❌ You cannot warn the Server Owner!")
                return

            total_warns, escalation = await issue_warning_logic(ctx.guild, member, ctx.author, reason)
            embed = discord.Embed(
                title="⚠️ Member Formally Warned",
                description=f"**{member.mention}** has been issued a warning.{escalation}",
                color=discord.Color.gold()
            )
            embed.add_field(name="User", value=f"{member.name} (`{member.id}`)", inline=True)
            embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
            embed.add_field(name="Total Warnings", value=f"`{total_warns}`", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in !warn: {e}", exc_info=True)
            await ctx.send(f"❌ Failed to warn member: {e}")



    @commands.command(name="warnings", aliases=["warns"])
    @commands.guild_only()
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def warnings_prefix_cmd(self, ctx: commands.Context, member: discord.Member = None):
        """Check active warnings for a member: !warnings [@member]"""
        try:
            target = member or ctx.author
            warns = await db.get_warnings(ctx.guild.id, target.id)
            if not warns:
                await ctx.send(f"✅ **{target.mention} has a clean record with 0 warnings!**")
                return

            embed = discord.Embed(
                title=f"⚠️ Infraction Record — {target.display_name}",
                description=f"Total Warnings on file: **`{len(warns)}`**",
                color=discord.Color.orange()
            )
            for idx, w in enumerate(warns[:10], 1):
                warn_id = w.get("id") if isinstance(w, dict) else w[0]
                mod_id = w.get("moderator_id") if isinstance(w, dict) else w[1]
                reason = w.get("reason") if isinstance(w, dict) else w[2]
                ts = w.get("timestamp") if isinstance(w, dict) else w[3]
                embed.add_field(
                    name=f"Warning #{idx} (ID: `{warn_id}`) • {ts or 'Recently'}",
                    value=f"• **Reason:** {reason}\n• **Moderator:** <@{mod_id}>",
                    inline=False
                )
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in !warnings: {e}", exc_info=True)
            await ctx.send(f"❌ Failed to fetch warnings: {e}")



    @commands.command(name="clearwarns", aliases=["clearwarnings", "removewarn"])
    @commands.guild_only()
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def clearwarns_prefix_cmd(self, ctx: commands.Context, member: discord.Member, amount: Optional[int] = None):
        """Clear warnings for a member: !clearwarns @member [amount]"""
        try:
            if not is_protected(ctx.author):
                await ctx.send("❌ You do not have permission to clear warnings.")
                return

            is_admin = ctx.author.guild_permissions.administrator or ctx.author.id == ctx.guild.owner_id or ctx.author.id == 719932313919684670
            if not is_admin and is_protected(member) and member.top_role >= ctx.author.top_role:
                await ctx.send("❌ You cannot modify warnings for another staff member with a higher or equal role.")
                return

            if amount is not None and amount <= 0:
                await ctx.send("❌ Amount must be at least 1.")
                return

            count = await db.clear_warnings(ctx.guild.id, member.id, amount=amount)
            if count == 0:
                await ctx.send(f"ℹ️ **{member.mention}** has no warnings on record.")
                return

            if amount is not None:
                await ctx.send(f"🧹 Successfully removed **`{count}`** recent warning(s) for **{member.mention}**!")
            else:
                await ctx.send(f"🧹 Successfully cleared all **`{count}`** warnings for **{member.mention}**!")
            await log_mod_action(ctx.guild, ctx.author, member, "Warnings Cleared", f"Cleared {count} warnings")
        except Exception as e:
            logger.error(f"Error in !clearwarns: {e}", exc_info=True)
            await ctx.send(f"❌ Failed to clear warnings: {e}")



    @commands.command(name="delwarn")
    @commands.guild_only()
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def delwarn_prefix_cmd(self, ctx: commands.Context, warn_id: int):
        """Delete a specific warning by ID: !delwarn <id>"""
        try:
            if not is_protected(ctx.author):
                await ctx.send("❌ You do not have permission to delete warnings.")
                return

            success = await db.delete_warning_by_id(ctx.guild.id, warn_id)
            if success:
                await ctx.send(f"🗑️ Successfully deleted warning with ID **`{warn_id}`**!")
                await log_mod_action(ctx.guild, ctx.author, None, "Warning Deleted", f"Deleted warning ID {warn_id}")
            else:
                await ctx.send(f"❌ Warning with ID **`{warn_id}`** was not found in this server.")
        except Exception as e:
            logger.error(f"Error in !delwarn: {e}", exc_info=True)
            await ctx.send(f"❌ Failed to delete warning: {e}")



    @commands.command(name="warnleaderboard", aliases=["warnlb", "warnslb", "warningslb", "warningsleaderboard"])
    @commands.guild_only()
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def warnleaderboard_prefix_cmd(self, ctx: commands.Context, limit: Optional[int] = 10):
        """View the server warnings leaderboard: !warnlb [limit]"""
        try:
            limit = max(1, min(limit or 10, 25))
            rows = await db.get_warnings_leaderboard(ctx.guild.id, limit=limit)
            if not rows:
                embed = discord.Embed(
                    title=f"🏆 Warnings Leaderboard — {ctx.guild.name}",
                    description="✅ **No warnings recorded in this server! The record is completely clean.**",
                    color=discord.Color.green()
                )
                if ctx.guild.icon:
                    embed.set_thumbnail(url=ctx.guild.icon.url)
                await ctx.send(embed=embed)
                return

            embed = discord.Embed(
                title=f"⚠️ Warnings Leaderboard — {ctx.guild.name}",
                description=f"Showing top **{len(rows)}** members with active infractions on file.\n",
                color=discord.Color.orange()
            )
            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            rank_emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            lines = []
            for idx, r in enumerate(rows, 1):
                uid = r["user_id"] if isinstance(r, dict) and "user_id" in r else r[0]
                cnt = int(r["warn_count"] if isinstance(r, dict) and "warn_count" in r else r[1])
            
                if cnt >= 6:
                    risk = f"⛔ **{cnt} Strikes** `(Permanent Ban Applied)`"
                elif cnt >= 3:
                    remaining = 6 - cnt
                    risk = f"🛑 **{cnt} Strikes** `(7-Day Mute / {remaining} from Ban)`"
                else:
                    remaining = 3 - cnt
                    risk = f"🟡 **{cnt} Strike{'s' if cnt != 1 else ''}** `({remaining} from 7-Day Mute)`"

                medal = rank_emojis[idx-1] if idx <= len(rank_emojis) else f"`#{idx}`"
                lines.append(f"{medal} <@{uid}> — {risk}")

            embed.description = "\n\n".join(lines)
            embed.set_footer(text="Sweety Moderation Shield • Use !warnings <user> or !clearwarns to manage")
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in !warnleaderboard: {e}", exc_info=True)
            await ctx.send(f"❌ Failed to fetch warning leaderboard: {e}")



    @commands.command(name="appeal", aliases=["submitappeal", "strikeappeal"])
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def appeal_prefix_cmd(self, ctx: commands.Context, *, reason: Optional[str] = None):
        """Submit an official appeal for your active warnings, strikes, or timeout: !appeal <reason>"""
        try:
            user = ctx.author
            guild = ctx.guild

            # If launched in DM, locate target guild where user has active strikes or timeout
            if not guild:
                for g in ctx.bot.guilds:
                    if g.get_member(user.id):
                        active_mute = await db.get_active_mute(g.id, user.id)
                        warnings = await db.get_warnings(g.id, user.id)
                        if active_mute or len(warnings) >= 1:
                            guild = g
                            break
                if not guild and ctx.bot.guilds:
                    for g in ctx.bot.guilds:
                        if g.get_member(user.id):
                            guild = g
                            break

            if not guild:
                return await ctx.send("❌ Could not find a server where you have active strikes, warnings, or timeouts to appeal.")

            warns = await db.get_warnings(guild.id, user.id)
            active_mute = await db.get_active_mute(guild.id, user.id)

            if not warns and not active_mute:
                return await ctx.send(f"ℹ️ **You have a clean record in {guild.name}!** You currently have 0 active warnings, strikes, or timeouts.")

            active_ticket = await db.get_active_appeal_by_user(guild.id, user.id)
            if active_ticket:
                channel_id_raw = active_ticket.get("channel_id")
                chan = None
                try:
                    if channel_id_raw:
                        chan = guild.get_channel(int(channel_id_raw))
                        if not chan:
                            try:
                                chan = await self.bot.fetch_channel(int(channel_id_raw))
                            except Exception:
                                chan = None
                except Exception:
                    chan = None

                if not chan:
                    # Ghost ticket: close in DB
                    await db.close_appeal_ticket(guild.id, int(channel_id_raw) if channel_id_raw else 0, "Channel deleted", user.id)
                else:
                    chan_link = f"https://discord.com/channels/{guild.id}/{channel_id_raw}"
                    chan_mention = f"[{chan.name}]({chan_link})"
                    return await ctx.send(f"ℹ️ You already have an open appeal ticket pending review by staff in **{guild.name}**: {chan_mention}.")

            if not reason:
                embed = discord.Embed(
                    title="📩 Submit a Strike / Timeout Appeal",
                    description=(
                        f"Please provide a reason with your appeal command for **{guild.name}**:\n\n"
                        "**Usage:** `!appeal <your explanation / reason here>`\n"
                        "**Example:** `!appeal I believe the strike was a misunderstanding because...`\n\n"
                        "Or click the button below to open the interactive appeal form!"
                    ),
                    color=discord.Color.blue()
                )
                view = DMAppealLauncherView()
                return await ctx.send(embed=embed, view=view)

            member = guild.get_member(user.id) or user
            ticket_chan = await create_appeal_ticket_channel(guild, member, reason, f"Submitted via !appeal command by {user.name}")
            if ticket_chan:
                chan_link = f"https://discord.com/channels/{guild.id}/{ticket_chan.id}"
                embed = discord.Embed(
                    title="✅ Strike Appeal Ticket Created",
                    description=(
                        f"Your official appeal ticket has been opened in **{guild.name}**: [{ticket_chan.name}]({chan_link}) ({ticket_chan.mention})!\n\n"
                        f"• **Status:** Staff and admins have been notified.\n"
                        f"• **Access:** You can now view and chat directly in your private appeal channel [{ticket_chan.name}]({chan_link})."
                    ),
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"❌ Failed to create appeal ticket channel in **{guild.name}**. Please contact staff directly.")
        except Exception as e:
            logger.error(f"Error in !appeal: {e}")
            await ctx.send(f"❌ Error creating appeal ticket: {e}")



    @commands.command(name="appealrole", aliases=["setappealrole", "appealping", "setappealping"])
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    @commands.guild_only()
    async def appealrole_prefix_cmd(self, ctx: commands.Context, action: Optional[str] = "view", role: Optional[discord.Role] = None):
        """Configure which role is pinged for appeal tickets: !appealrole set @Role | !appealrole remove | !appealrole view"""
        try:
            guild = ctx.guild
            act = (action or "view").lower()
            if act in ("set", "add", "enable"):
                target_role = role
                if not target_role and ctx.message.role_mentions:
                    target_role = ctx.message.role_mentions[0]
                if not target_role:
                    return await ctx.send("❌ Please specify or mention a role: `!appealrole set @Role`")
                await db.set_config(guild.id, "appeal_ping_role_id", target_role.id)
                embed = discord.Embed(
                    title="📩 Appeal Ping Role Updated",
                    description=f"When a member submits a strike/warning appeal, {target_role.mention} will now be pinged and given access to the appeal ticket channel.",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Configured by {ctx.author.display_name}")
                await ctx.send(embed=embed)
            elif act in ("remove", "reset", "clear", "delete", "disable"):
                await db.set_config(guild.id, "appeal_ping_role_id", "None")
                embed = discord.Embed(
                    title="🔄 Appeal Ping Role Reset",
                    description="Reset to default: All Server Administrators and Moderator roles will be pinged on new appeal tickets.",
                    color=discord.Color.blue()
                )
                embed.set_footer(text=f"Configured by {ctx.author.display_name}")
                await ctx.send(embed=embed)
            else:  # view
                role_id_raw = await db.get_config(guild.id, "appeal_ping_role_id", None)
                role_obj = None
                if role_id_raw and str(role_id_raw).lower() not in ("none", "null", "0", ""):
                    try:
                        role_obj = guild.get_role(int(role_id_raw))
                    except (ValueError, TypeError):
                        role_obj = None
                embed = discord.Embed(
                    title=f"📩 Appeal Ticket Notification Settings — {guild.name}",
                    color=discord.Color.gold()
                )
                if role_obj:
                    embed.add_field(name="🎭 Configured Ping Role", value=f"✅ {role_obj.mention} (`{role_obj.id}`)", inline=False)
                    embed.add_field(name="ℹ️ Behavior", value="Only members with this role will be pinged when an appeal ticket opens.", inline=False)
                else:
                    embed.add_field(name="🎭 Configured Ping Role", value="*Default: All staff and admin roles*", inline=False)
                    embed.add_field(name="ℹ️ Behavior", value="The bot automatically pings all moderator and administrator roles.", inline=False)
                embed.set_footer(text="Use !appealrole set @Role to customize, or !appealrole remove to reset.")
                await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in !appealrole: {e}")
            await ctx.send(f"❌ Error configuring appeal role: {e}")



    @commands.command(name="appealpanel", aliases=["setappealpanel", "postappealpanel", "ticketpanel"])
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    @commands.guild_only()
    async def appealpanel_prefix_cmd(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Post the official appeal button panel: !appealpanel [#channel]"""
        try:
            target_channel = channel or ctx.channel
            guild = ctx.guild

            embed = discord.Embed(
                title=f"🛡️ {guild.name} • Official Strike Appeal Center",
                description=(
                    "Welcome to the official Strike & Moderation Appeal Portal.\n\n"
                    "If you have received a formal warning strike or a 7-day timeout and believe it was issued in error or you have proper justification, you can open an official appeal ticket here for staff review.\n\n"
                    "📌 **How It Works:**\n"
                    "1️⃣ Click the **`📩 Submit Strike Appeal`** button below.\n"
                    "2️⃣ Provide your reason and any relevant context in the popup form.\n"
                    "3️⃣ A private ticket channel (`#appeal-username`) will be created where you can speak directly with the moderation team.\n\n"
                    "🔇 **Muted / Timed-Out Members:**\n"
                    "• *Discord's client disables button clicks inside server channels during an active timeout.*\n"
                    "• **To appeal while timed out:**\n"
                    "  👉 Check your **Direct Message (DM) from Sweety** to click the appeal button, OR\n"
                    "  👉 Send `!appeal <your reason>` directly in **DM to Sweety**!"
                ),
                color=discord.Color.blue(),
                timestamp=datetime.datetime.utcnow()
            )
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
            embed.set_footer(text="Sweety Strike Appeal Shield • Click below or DM !appeal <reason> to appeal")

            view = DMAppealLauncherView()
            try:
                await target_channel.send(embed=embed, view=view)
                if target_channel.id != ctx.channel.id:
                    await ctx.send(f"✅ **Appeal Panel posted successfully in {target_channel.mention}!**")
            except Exception as e:
                logger.error(f"Failed to post appeal panel: {e}")
                await ctx.send(f"❌ Failed to post appeal panel: {e}")
        except Exception as e:
            logger.error(f"Error in !appealpanel: {e}")
            await ctx.send(f"❌ Error: {e}")


    # ── AI User Profile Memory Commands ──────────────────────────────────────────


    @commands.command(name="servers", aliases=["guilds", "guildlist"])
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def servers_prefix_cmd(self, ctx: commands.Context):
        """Creator-only command to list all servers: !servers"""
        try:
            if not is_creator(ctx.author):
                return

            guilds = list(self.bot.guilds)
            total_members = sum(g.member_count or 0 for g in guilds)
            guilds_sorted = sorted(guilds, key=lambda g: g.member_count or 0, reverse=True)

            embed = discord.Embed(
                title=f"🌐 Sweety Guild Network ({len(guilds)} Servers • {total_members:,} Members)",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            lines = []
            for idx, g in enumerate(guilds_sorted[:25], 1):
                lines.append(f"`{idx}.` **{g.name}** (`{g.id}`) — `{g.member_count:,}` members")

            embed.description = "\n".join(lines)[:4000]
            embed.set_footer(text="Use !leaveserver <id> to make Sweety leave a server")
            await ctx.reply(embed=embed, mention_author=False)
        except Exception as e:
            logger.error(f"Error in !servers: {e}")
            await ctx.reply(f"❌ Error listing servers: {e}", mention_author=False)



    @commands.command(name="leaveserver", aliases=["leaveguild", "forceleave"])
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def leaveserver_prefix_cmd(self, ctx: commands.Context, guild_id: str):
        """Creator-only command to remotely leave a server: !leaveserver <guild_id>"""
        try:
            if not is_creator(ctx.author):
                return

            try:
                gid = int(guild_id.strip())
            except ValueError:
                return await ctx.reply("❌ Invalid numerical Guild ID.", mention_author=False)

            guild = self.bot.get_guild(gid)
            if not guild:
                return await ctx.reply(f"❌ Server `{gid}` not found.", mention_author=False)

            guild_name = guild.name
            try:
                await guild.leave()
                await ctx.reply(f"✅ Left server **{guild_name}** (`{gid}`).", mention_author=False)
            except Exception as e:
                await ctx.reply(f"❌ Error leaving server: {e}", mention_author=False)
        except Exception as e:
            logger.error(f"Error in !leaveserver: {e}")
            await ctx.reply(f"❌ Error: {e}", mention_author=False)





class StrikeAppealModal(discord.ui.Modal, title="Submit Strike / Warning Appeal"):
    reason_input = discord.ui.TextInput(
        label="Reason for appeal",
        style=discord.TextStyle.paragraph,
        placeholder="Explain why this warning or strike should be appealed...",
        required=True,
        min_length=10,
        max_length=1000
    )
    extra_input = discord.ui.TextInput(
        label="Anything else to add?",
        style=discord.TextStyle.paragraph,
        placeholder="Any additional context, details, or explanation (optional)...",
        required=False,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        guild = interaction.guild

        # If launched from DM, locate the target guild
        if not guild:
            for g in interaction.client.guilds:
                if g.get_member(user.id):
                    active_mute = await db.get_active_mute(g.id, user.id)
                    warnings = await db.get_warnings(g.id, user.id)
                    if active_mute or len(warnings) >= 1:
                        guild = g
                        break
            if not guild and interaction.client.guilds:
                for g in interaction.client.guilds:
                    if g.get_member(user.id):
                        guild = g
                        break

        if not guild:
            await interaction.followup.send("❌ Could not find a server with active strikes or warnings to submit your appeal.", ephemeral=True)
            return

        # Check existing active ticket
        active_ticket = await db.get_active_appeal_by_user(guild.id, user.id)
        if active_ticket:
            await interaction.followup.send(f"ℹ️ You already have an open appeal ticket pending review in **{guild.name}**.", ephemeral=True)
            return

        member = guild.get_member(user.id) or user
        ticket_chan = await create_appeal_ticket_channel(guild, member, self.reason_input.value, self.extra_input.value)
        if ticket_chan:
            chan_link = f"https://discord.com/channels/{guild.id}/{ticket_chan.id}"
            await interaction.followup.send(
                f"✅ **Your appeal ticket has been opened in {guild.name}: [{ticket_chan.name}]({chan_link}) ({ticket_chan.mention})!**\n"
                f"You have been granted access to view and chat directly with staff in your appeal channel. Admins and moderators have been pinged to review your appeal.",
                ephemeral=True
            )
        else:
            await interaction.followup.send("❌ Failed to create appeal ticket. Please contact a moderator directly.", ephemeral=True)




async def create_appeal_ticket_channel(
    guild: discord.Guild,
    user: Union[discord.Member, discord.User],
    reason: str,
    additional_info: str = ""
) -> Optional[discord.TextChannel]:
    """Creates a private appeal ticket channel, grants the user talk permissions, and pings moderators/admins."""
    clean_name = re.sub(r'[^a-zA-Z0-9]', '', user.name.lower())[:15] or f"user-{user.id}"
    channel_name = f"appeal-{clean_name}"

    # Find or select Staff / Tickets category
    target_category = None
    for cat in guild.categories:
        c_name = cat.name.lower()
        if any(term in c_name for term in ["ticket", "staff", "appeal", "mod", "admin"]):
            target_category = cat
            break
            
    # Check ticket channel's parent category
    if not target_category and TICKET_CHANNEL_ID:
        ticket_chan = guild.get_channel(TICKET_CHANNEL_ID)
        if ticket_chan and ticket_chan.category:
            target_category = ticket_chan.category

    # Build Overwrites: visible to bot, staff/admins, and the appealing user
    target_member = guild.get_member(user.id) or user
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            embed_links=True,
            attach_files=True,
            manage_channels=True,
            manage_messages=True
        )
    }

    # Grant appealing member full talk & view permissions in their private appeal ticket
    if isinstance(target_member, (discord.Member, discord.User)):
        overwrites[target_member] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            embed_links=True,
            attach_files=True
        )

    def is_bot_or_excluded_role(r: discord.Role) -> bool:
        """Filters out bot roles, integration roles, and excluded honorary roles."""
        if r.is_default() or r.managed:
            return True
        if hasattr(r, 'tags') and r.tags and (r.tags.bot_id or r.tags.is_bot_managed()):
            return True
        r_name = r.name.lower()
        if any(b in r_name for b in ["bot", "sapphire", "ticket king", "jockie", "tourney", "invite tracker", "mee6", "dyno", "carl", "honorary", "buildmaster"]):
            return True
        if r.members and all(m.bot for m in r.members):
            return True
        return False

    # Check if a custom appeal ping role has been configured via /appealrole
    custom_role_id_raw = await db.get_config(guild.id, "appeal_ping_role_id", None)
    custom_ping_role = None
    if custom_role_id_raw and str(custom_role_id_raw).lower() not in ("none", "null", "0", ""):
        try:
            custom_ping_role = guild.get_role(int(custom_role_id_raw))
        except (ValueError, TypeError):
            custom_ping_role = None

    if custom_ping_role:
        overwrites[custom_ping_role] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            embed_links=True,
            attach_files=True
        )
        staff_ping_str = custom_ping_role.mention

        # Also grant access to true human Administrator roles
        for role in guild.roles:
            if is_bot_or_excluded_role(role):
                continue
            if (role.permissions.administrator or role.name.lower() in ["admin", "administrator", "space admins"]) and role.id != custom_ping_role.id:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    embed_links=True,
                    attach_files=True
                )
    else:
        # Fallback: grant access ONLY to human Administrator / Space Admins roles
        admin_roles = [
            r for r in guild.roles 
            if not is_bot_or_excluded_role(r) and (r.permissions.administrator or r.name.lower() in ["admin", "administrator", "space admins"])
        ]
        for role in admin_roles:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                embed_links=True,
                attach_files=True
            )
        staff_ping_str = " ".join([r.mention for r in admin_roles[:3]]) if admin_roles else "🛡️ **Admins**"

    # Lift native Discord timeout ONLY for users who are currently timed out so Discord platform allows them to talk in appeal ticket
    if isinstance(target_member, discord.Member):
        try:
            warnings = await db.get_warnings(guild.id, target_member.id)
            strike_count = len(warnings) if warnings else 0
            if target_member.is_timed_out() or strike_count >= 3:
                muted_role = await ensure_muted_role(guild)
                if muted_role and muted_role not in target_member.roles:
                    await target_member.add_roles(muted_role, reason="Enforcing @Muted role during strike appeal discussion")
                if target_member.is_timed_out():
                    await target_member.timeout(None, reason="Lifted native timeout to allow communication in appeal ticket channel")
            elif strike_count < 3:
                # Ensure members with < 3 strikes NEVER have @Muted role
                muted_role = discord.utils.find(lambda r: r.name.lower() == "muted", guild.roles)
                if muted_role and muted_role in target_member.roles:
                    await target_member.remove_roles(muted_role, reason="Removed @Muted role on appeal ticket creation (strike count < 3)")
        except Exception as te:
            logger.warning(f"Could not adjust native timeout for {target_member.id}: {te}")

    try:
        channel = await guild.create_text_channel(
            name=channel_name,
            category=target_category,
            overwrites=overwrites,
            topic=f"Strike Appeal Ticket for {user.name} ({user.id}) | Auto-generated by Sweety"
        )
    except Exception as e:
        logger.error(f"Failed to create appeal channel in {guild.name}: {e}")
        return None

    # Save to database
    await db.create_appeal_ticket(guild.id, user.id, channel.id, reason, additional_info)

    # Fetch user's strike history
    warnings = await db.get_warnings(guild.id, user.id)
    history_lines = []
    if warnings:
        for idx, w in enumerate(warnings, 1):
            w_reason = w.get("reason", "No reason") if isinstance(w, dict) else (w[4] if len(w) > 4 else "No reason")
            w_time = w.get("timestamp", "") if isinstance(w, dict) else (w[5] if len(w) > 5 else "")
            history_lines.append(f"**#{idx}** • {w_reason} *({w_time})*")
    else:
        history_lines.append("• No prior logged warnings found in database.")

    strike_history_text = "\n".join(history_lines[:10])
    if len(warnings) > 10:
        strike_history_text += f"\n*...and {len(warnings)-10} more*"

    embed = discord.Embed(
        title=f"📩 Strike Appeal Ticket — {user.name}",
        description="A member has submitted an official strike / warning appeal for staff review.",
        color=discord.Color.gold(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="👤 User Information", value=f"• **Username:** {user.name} (`{user.id}`)\n• **Mention:** {user.mention}\n• **Account Created:** <t:{int(user.created_at.timestamp())}:R>", inline=False)
    embed.add_field(name="📜 Full Strike History", value=strike_history_text, inline=False)
    embed.add_field(name="📝 Reason for Appeal", value=reason, inline=False)
    if additional_info:
        embed.add_field(name="ℹ️ Additional Context", value=additional_info, inline=False)
    embed.set_footer(text="Sweety Strike Appeal System • Staff can use buttons below to resolve")

    view = AppealReviewView()
    await channel.send(
        content=f"🔔 **Staff Alert:** {staff_ping_str}\n👋 {user.mention}, your private appeal ticket has been opened! You have permission to explain your appeal and discuss directly with the moderation team here.",
        embed=embed,
        view=view
    )
    return channel


# ── AI User Profile Memory UI Components ─────────────────────────────────────



class DMAppealLauncherView(discord.ui.View):
    """Persistent view attached to warning/strike DMs and server appeal panels."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 Submit Strike Appeal", style=discord.ButtonStyle.primary, custom_id="btn_submit_dm_appeal")
    async def open_appeal_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(StrikeAppealModal())

    @discord.ui.button(label="📜 Check My Infractions", style=discord.ButtonStyle.secondary, custom_id="btn_appeal_check_status")
    async def check_my_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        if not guild:
            for g in interaction.client.guilds:
                if g.get_member(user.id):
                    warns = await db.get_warnings(g.id, user.id)
                    mute = await db.get_active_mute(g.id, user.id)
                    if warns or mute:
                        guild = g
                        break
        if not guild:
            await interaction.response.send_message("ℹ️ No active infraction record found for you.", ephemeral=True)
            return

        warns = await db.get_warnings(guild.id, user.id)
        mute = await db.get_active_mute(guild.id, user.id)
        strike_count = len(warns) if warns else 0

        embed = discord.Embed(
            title=f"📜 Infraction Status — {user.display_name}",
            color=discord.Color.gold() if (warns or mute) else discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.add_field(name="⚠️ Total Warning Strikes", value=f"**`{strike_count}/6`** Strikes", inline=True)
        
        if mute:
            unmute_at = int(float(mute.get("unmute_at", 0)))
            embed.add_field(name="🔇 7-Day Timeout Status", value=f"**Active** (Expires <t:{unmute_at}:R>)", inline=True)
        else:
            embed.add_field(name="🔇 7-Day Timeout Status", value="*None active*", inline=True)

        if warns:
            lines = []
            for idx, w in enumerate(warns[:5], 1):
                reason = w.get("reason", "No reason") if isinstance(w, dict) else (w[4] if len(w) > 4 else "No reason")
                ts = w.get("timestamp", "") if isinstance(w, dict) else (w[5] if len(w) > 5 else "")
                lines.append(f"• **#{idx}:** {reason} *({ts})*")
            embed.add_field(name="Recent Warnings", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="Record", value="✅ You currently have a clean record with 0 warnings.", inline=False)

        embed.set_footer(text="Click 'Submit Strike Appeal' if you wish to appeal a strike or timeout.")
        await interaction.response.send_message(embed=embed, ephemeral=True)




class AppealReviewView(discord.ui.View):
    """Persistent view attached to staff appeal tickets with Accept, Deny, and Close buttons."""
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_protected(interaction.user):
            await interaction.response.send_message("❌ You must be a moderator or administrator to review appeals.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accept Appeal", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_appeal_accept")
    async def accept_appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ticket = await get_or_recover_appeal_ticket(interaction)
        if not ticket:
            await interaction.followup.send("⚠️ Could not find or recover ticket record for this channel.", ephemeral=True)
            return
        if ticket.get("status") not in ("open", None):
            await interaction.followup.send(f"ℹ️ This appeal ticket has already been marked as **{ticket.get('status')}**.", ephemeral=True)
            return

        guild = interaction.guild
        target_uid = int(ticket["user_id"])
        member = None
        if guild:
            member = guild.get_member(target_uid)
            if not member:
                try:
                    member = await guild.fetch_member(target_uid)
                except Exception:
                    member = None

        # Unmute member if muted: remove native timeout + @Muted role
        if member:
            try:
                if member.is_timed_out():
                    await member.timeout(None, reason=f"Strike appeal accepted by {interaction.user.display_name}")
            except Exception as te:
                logger.warning(f"Could not remove native timeout for {target_uid}: {te}")
            try:
                muted_role = discord.utils.find(lambda r: r.name.lower() == "muted", guild.roles)
                if muted_role and muted_role in member.roles:
                    await member.remove_roles(muted_role, reason=f"Strike appeal accepted by {interaction.user.display_name}")
            except Exception as re:
                logger.warning(f"Could not remove @Muted role for {target_uid}: {re}")

            # Send DM to user
            try:
                accept_embed = discord.Embed(
                    title="✅ Warning / Strike Appeal Accepted",
                    description=(
                        f"Your appeal in **{guild.name}** has been **accepted** by moderator **{interaction.user.display_name}**!\n\n"
                        "• **Action Taken:** Warning / strike penalty has been reviewed and cleared by staff.\n"
                        "• **Status:** Any active timeouts or mutes have been completely removed.\n\n"
                        "Please continue to adhere to server rules to maintain a clean record."
                    ),
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.utcnow()
                )
                accept_embed.set_footer(text="Your appeal was accepted by staff.")
                await member.send(content="Your appeal was accepted by staff.", embed=accept_embed)
            except Exception as dme:
                logger.debug(f"Could not DM user {target_uid} on appeal acceptance: {dme}")

        # Update DB: remove active mute and clear 1 recent warning
        if guild:
            try:
                await db.remove_active_mute(guild.id, target_uid)
                await db.clear_warnings(guild.id, target_uid, amount=1)
            except Exception as dbe:
                logger.error(f"Error clearing warnings/mutes for user {target_uid}: {dbe}")

        try:
            await db.resolve_appeal_ticket(interaction.channel_id, "accepted", interaction.user.id)
        except Exception as res_err:
            logger.error(f"Error resolving appeal ticket in DB: {res_err}")

        # Update review buttons
        for item in self.children:
            if getattr(item, "custom_id", "") in ("btn_appeal_accept", "btn_appeal_deny"):
                item.disabled = True
        
        status_embed = discord.Embed(
            title="✅ Appeal Accepted & Record Updated",
            description=(
                f"• **Reviewed by:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"• **Target User:** <@{target_uid}> (`{target_uid}`)\n"
                f"• **Action Taken:** 1 Warning/strike cleared from DB, timeout/mute removed if active, and DM confirmation sent.\n"
                f"• **Timestamp:** <t:{int(time.time())}:F>"
            ),
            color=discord.Color.green()
        )
        try:
            if interaction.message:
                await interaction.message.edit(view=self)
        except Exception as edit_err:
            logger.debug(f"Could not edit appeal message buttons: {edit_err}")

        await interaction.channel.send(embed=status_embed)
        if guild:
            asyncio.create_task(log_mod_action(guild, interaction.user, member or target_uid, "Strike Appeal Accepted", f"Accepted appeal for user ID {target_uid} (1 strike cleared)"))

    @discord.ui.button(label="Deny Appeal", style=discord.ButtonStyle.danger, emoji="❌", custom_id="btn_appeal_deny")
    async def deny_appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ticket = await get_or_recover_appeal_ticket(interaction)
        if not ticket:
            await interaction.followup.send("⚠️ Could not find or recover ticket record for this channel.", ephemeral=True)
            return
        if ticket.get("status") not in ("open", None):
            await interaction.followup.send(f"ℹ️ This appeal ticket has already been marked as **{ticket.get('status')}**.", ephemeral=True)
            return

        guild = interaction.guild
        target_uid = int(ticket["user_id"])
        member = None
        if guild:
            member = guild.get_member(target_uid)
            if not member:
                try:
                    member = await guild.fetch_member(target_uid)
                except Exception:
                    member = None

        now = time.time()
        
        # Check strike count & active mute status
        warnings = await db.get_warnings(guild.id, target_uid) if guild else []
        strike_count = len(warnings) if warnings else 0
        active_mute = await db.get_active_mute(guild.id, target_uid) if guild else None

        # Verify active mute validity: only valid if strike_count >= 3 and unmute_at > now
        has_valid_mute = False
        unmute_at = None
        if active_mute:
            unmute_at = float(active_mute.get("unmute_at", 0))
            if unmute_at > now and strike_count >= 3:
                has_valid_mute = True
            else:
                # Stale or invalid active mute entry
                if guild:
                    await db.remove_active_mute(guild.id, target_uid)
                active_mute = None

        # If user has fewer than 3 strikes, ensure any accidental Discord timeout or @Muted role is cleared
        if member and strike_count < 3:
            try:
                if member.is_timed_out():
                    await member.timeout(None, reason="Untimed out on appeal resolution (strike count < 3)")
            except Exception as te:
                logger.warning(f"Could not clear timeout for member {target_uid}: {te}")
            try:
                muted_role = discord.utils.find(lambda r: r.name.lower() == "muted", guild.roles)
                if muted_role and muted_role in member.roles:
                    await member.remove_roles(muted_role, reason="Removed @Muted role (strike count < 3)")
            except Exception as re:
                logger.warning(f"Could not remove @Muted role for {target_uid}: {re}")

        # Send DM to user
        try:
            target_user = interaction.client.get_user(target_uid) or await interaction.client.fetch_user(target_uid)
            if target_user:
                if has_valid_mute and unmute_at:
                    dm_desc = (
                        f"Your appeal in **{guild.name if guild else 'the server'}** was reviewed and **denied** by the moderation team.\n\n"
                        f"Your 7-day timeout remains in effect until <t:{int(unmute_at)}:F> (<t:{int(unmute_at)}:R>)."
                    )
                else:
                    dm_desc = (
                        f"Your strike appeal in **{guild.name if guild else 'the server'}** was reviewed and **denied** by the moderation team.\n\n"
                        f"Your warning strike remains on record ({strike_count}/6 total strikes)."
                    )
                deny_embed = discord.Embed(
                    title="❌ Strike Appeal Denied",
                    description=dm_desc,
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.utcnow()
                )
                deny_embed.set_footer(text="Your appeal was reviewed and denied.")
                await target_user.send(content="Your appeal was reviewed and denied.", embed=deny_embed)
        except Exception as dme:
            logger.debug(f"Could not DM user {target_uid} on appeal denial: {dme}")

        # Re-apply native timeout ONLY IF user had an active, valid 3-strike mute
        if guild and member and has_valid_mute and unmute_at:
            try:
                remaining_secs = max(60, int(unmute_at - now))
                await member.timeout(datetime.timedelta(seconds=remaining_secs), reason="Strike appeal denied by staff (3-strike timeout restored)")
                muted_role = await ensure_muted_role(guild)
                if muted_role and muted_role not in member.roles:
                    await member.add_roles(muted_role, reason="Re-enforcing @Muted role after appeal denial")
            except Exception as te:
                logger.warning(f"Could not re-apply timeout for {target_uid} on appeal denial: {te}")

        # Update DB
        try:
            await db.resolve_appeal_ticket(interaction.channel_id, "denied", interaction.user.id)
        except Exception as res_err:
            logger.error(f"Error resolving appeal ticket in DB: {res_err}")

        # Update review buttons
        for item in self.children:
            if getattr(item, "custom_id", "") in ("btn_appeal_accept", "btn_appeal_deny"):
                item.disabled = True

        status_action = (
            f"Appeal denied, 7-day timeout remains active (until <t:{int(unmute_at)}:R>), DM notification sent."
            if has_valid_mute and unmute_at
            else f"Appeal denied, warning strike remains on record ({strike_count}/6 strikes), DM notification sent."
        )
        status_embed = discord.Embed(
            title="❌ Appeal Denied",
            description=(
                f"• **Reviewed by:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"• **Target User:** <@{target_uid}> (`{target_uid}`)\n"
                f"• **Action Taken:** {status_action}\n"
                f"• **Timestamp:** <t:{int(time.time())}:F>"
            ),
            color=discord.Color.red()
        )
        try:
            if interaction.message:
                await interaction.message.edit(view=self)
        except Exception as edit_err:
            logger.debug(f"Could not edit appeal message buttons: {edit_err}")

        await interaction.channel.send(embed=status_embed)
        if guild:
            asyncio.create_task(log_mod_action(guild, interaction.user, target_uid, "Strike Appeal Denied", f"Denied strike appeal for user ID {target_uid}"))

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.secondary, emoji="🔒", custom_id="btn_appeal_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 **Closing and archiving appeal ticket channel in 5 seconds...**")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Appeal ticket closed by {interaction.user.display_name}")
        except Exception as e:
            logger.warning(f"Failed to delete appeal ticket channel {interaction.channel_id}: {e}")




class UndoPurgeView(discord.ui.View):
    """Interactive Undo button allowing moderators to restore purged messages via Webhook clone."""
    def __init__(self, channel_id: int, user_id: int, count: int):
        super().__init__(timeout=300.0)  # 5 minutes active button
        self.channel_id = channel_id
        self.user_id = user_id
        self.count = count

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id and not interaction.user.guild_permissions.manage_messages and not is_protected(interaction.user):
            await interaction.response.send_message("❌ You need **Manage Messages** permission to undo this purge.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Undo Purge", style=discord.ButtonStyle.danger, emoji="↩️")
    async def undo_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(content="⏳ **Restoring purged messages...** Please wait.", view=self)
            
            restored = await restore_purged_messages(interaction.channel)
            if restored > 0:
                await interaction.edit_original_response(
                    content=f"✅ **Purge Reverted!** Successfully restored `{restored}` messages via Webhook clone.",
                    view=None
                )
            else:
                await interaction.edit_original_response(
                    content="❌ Could not restore messages (backup was missing or expired).",
                    view=None
                )
        except Exception as e:
            logger.error(f"Error in UndoPurgeView button: {e}")
            try:
                await interaction.edit_original_response(content=f"❌ Failed to restore: {e}", view=None)
            except Exception:
                pass




class WarningActionView(discord.ui.View):
    def __init__(self, guild_id: int, target_member: discord.Member, author_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.target_member = target_member
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not is_protected(interaction.user):
            await interaction.response.send_message("❌ You must be a moderator or administrator to use warning controls.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Clear 1 Warn", style=discord.ButtonStyle.primary, emoji="1️⃣")
    async def clear_one(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        count = await db.clear_warnings(self.guild_id, self.target_member.id, amount=1)
        if count > 0:
            await interaction.followup.send(f"✅ Successfully removed **1** recent warning for {self.target_member.mention}.", ephemeral=True)
            await log_mod_action(interaction.guild, interaction.user, self.target_member, "Warning Cleared", "Cleared 1 warning via interactive UI")
        else:
            await interaction.followup.send(f"ℹ️ {self.target_member.mention} currently has no warnings.", ephemeral=True)

    @discord.ui.button(label="Clear All Warns", style=discord.ButtonStyle.danger, emoji="🧹")
    async def clear_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        count = await db.clear_warnings(self.guild_id, self.target_member.id)
        if count > 0:
            await interaction.followup.send(f"✅ Successfully cleared **all {count}** warnings for {self.target_member.mention}.", ephemeral=True)
            await log_mod_action(interaction.guild, interaction.user, self.target_member, "Warnings Cleared", f"Cleared all {count} warnings via interactive UI")
        else:
            await interaction.followup.send(f"ℹ️ {self.target_member.mention} currently has no warnings.", ephemeral=True)





async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
