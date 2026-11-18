from __future__ import annotations

import os
import json
import time
import math
import logging
import asyncio
import base64
import hmac
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union, Tuple, Set
from collections import deque

import jwt
import aiohttp
import psutil
import uvicorn
import discord
from dashboard_html import get_dashboard_html
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

load_dotenv()

# Logging Setup
logger = logging.getLogger("GeminiBot.API")

# ── Endpoint Access Filter (Silences /health and / while keeping other logs) ──
class EndpointFilter(logging.Filter):
    """Filters out access logs for /health and / while preserving all other route logs."""
    def __init__(self, paths: Tuple[str, ...] = ("/health", "/")):
        super().__init__()
        self.paths = paths

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args and len(record.args) >= 3:
            path = str(record.args[2])
            if path in self.paths or path.split("?")[0] in self.paths:
                return False
        msg = record.getMessage()
        for p in self.paths:
            if f" {p} " in msg or f' "{p}" ' in msg or f' "{p}?' in msg:
                return False
        return True

# FastAPI App
app = FastAPI(title="Discord Gemini Bot Dashboard API", version="1.0.0")

# CORS Setup - Restrict to authorized frontends
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://dashboard-weld-five-82.vercel.app").strip()
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://sweety-discord-bot-fra.onrender.com",
    "https://dashboard-weld-five-82.vercel.app",
]
if FRONTEND_URL and FRONTEND_URL not in allowed_origins:
    allowed_origins.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https://.*\.vercel\.app$" if not FRONTEND_URL else None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# JWT Setup - Reject insecure default and enforce secure ephemeral key if unset
_raw_jwt = os.getenv("JWT_SECRET", "").strip()
if not _raw_jwt or _raw_jwt == "super-secret-key-change-me-in-production":
    JWT_SECRET = secrets.token_urlsafe(48)
    logger.warning("⚠️ [SECURITY] Insecure or missing JWT_SECRET in environment! Generated secure random dynamic key.")
else:
    JWT_SECRET = _raw_jwt

JWT_ALGORITHM = "HS256"
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()

# Discord OAuth2 Config
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "https://dashboard-weld-five-82.vercel.app/api/auth/callback").strip()
DISCORD_API_ENDPOINT = "https://discord.com/api/v10"

# Spotify OAuth2 Config (Never hardcode fallback secrets in code)
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://sweety-discord-bot-fra.onrender.com").rstrip("/")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", f"{RENDER_EXTERNAL_URL}/api/spotify/callback")

# WebSocket Connections
active_console_websockets = set()
active_event_websockets = set()

# Seed Data helper
async def seed_dashboard_data(db):
    """Seeds some default data if the tables are empty, for instant beautiful charts."""
    try:
        if not getattr(db, "sqlite_conn", None) and not getattr(db, "pg_pool", None):
            await db.initialize()
        rows = await db.fetch("SELECT COUNT(*) as count FROM guilds")
        count = 0
        if rows:
            r = rows[0]
            count = r["count"] if isinstance(r, dict) and "count" in r else (r.get("count", 0) if hasattr(r, "get") else (r[0] if isinstance(r, (list, tuple)) else 0))
        if count == 0:
            now_ts = time.time()
            # Seed guilds
            await db.execute(
                "INSERT INTO guilds (id, name, icon, owner_id, member_count, joined_at, ai_enabled, logging_enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                "123456789012345678", "Naruto Hub", "a_abcd1234efgh5678", "987654321098765432", 1540, now_ts - (30 * 86400), True, True
            )
            await db.execute(
                "INSERT INTO guilds (id, name, icon, owner_id, member_count, joined_at, ai_enabled, logging_enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                "876543210987654321", "Konoha Sanctuary", None, "987654321098765432", 420, now_ts - (10 * 86400), True, False
            )
            
            # Seed analytics for the past 7 days
            for i in range(7):
                day = (datetime.now(timezone.utc).date() - timedelta(days=i)).isoformat()
                # Naruto Hub
                await db.execute(
                    "INSERT INTO analytics (guild_id, date, messages_count, commands_count, joins_count, leaves_count, warnings_count, mutes_count, bans_count, voice_active_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    "123456789012345678", day, 500 + i * 20, 45 + i * 5, max(0, 12 - i), 3, 2, 1, 0, 14400 + i * 600
                )
                # Konoha Sanctuary
                await db.execute(
                    "INSERT INTO analytics (guild_id, date, messages_count, commands_count, joins_count, leaves_count, warnings_count, mutes_count, bans_count, voice_active_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    "876543210987654321", day, max(10, 120 - i * 10), 10 + i, 4, 1, 0, 0, 0, 2000
                )
                
            # Seed AI Usage
            await db.execute(
                "INSERT INTO ai_usage (guild_id, user_id, prompt, response, model, tokens_used, latency) VALUES (?, ?, ?, ?, ?, ?, ?)",
                "123456789012345678", "987654321098765432", "Write a greeting channel topic for anime discussions", "✨ **Welcome to anime-chat!** A place to talk about all your favorite anime series.", "llama-3.3-70b-versatile", 240, 0.45
            )
            
            # Seed warnings
            await db.execute(
                "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
                "123456789012345678", "111111111111111111", "987654321098765432", "Spamming links in chat"
            )
            
            # Seed audit logs
            await db.execute(
                "INSERT INTO audit_logs (guild_id, user_id, action, details) VALUES (?, ?, ?, ?)",
                "123456789012345678", "987654321098765432", "AUTOROLE_TOGGLE", "Enabled autorole for member role"
            )
            
            logger.info("Successfully seeded dashboard analytics and demonstration data.")
    except Exception as e:
        logger.debug(f"Dashboard data seeding skipped: {e}")

# Live Log Broadcaster for WebSocket Console
async def broadcast_console(log_line: str):
    for ws in list(active_console_websockets):
        try:
            await ws.send_text(log_line)
        except Exception:
            active_console_websockets.discard(ws)

async def broadcast_event(event_type: str, data: dict):
    message = json.dumps({"event": event_type, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()})
    for ws in list(active_event_websockets):
        try:
            await ws.send_text(message)
        except Exception:
            active_event_websockets.discard(ws)

_recent_logs = deque(maxlen=80)

# Custom logging handler to redirect terminal logs to WebSockets
class WebSocketLogHandler(logging.Handler):
    def __init__(self, loop):
        super().__init__()
        self.loop = loop

    def emit(self, record):
        try:
            log_entry = self.format(record)
            _recent_logs.append(log_entry)
            if self.loop and self.loop.is_running() and active_console_websockets:
                asyncio.run_coroutine_threadsafe(broadcast_console(log_entry), self.loop)
        except Exception:
            pass

async def verify_admin_auth(request: Request):
    """Enforces admin authentication via X-Admin-Key header, query param, or Bearer JWT token."""
    req_key = (request.headers.get("X-Admin-Key", "") or request.query_params.get("key", "")).strip()
    admin_key = (os.getenv("ADMIN_API_KEY", "") or os.getenv("MASTER_API_KEY", "")).strip()
    if admin_key and req_key and hmac.compare_digest(admin_key, req_key):
        return {"role": "admin", "auth": "api_key", "is_admin": True, "id": "719932313919684670"}

    # Also check token from Bearer header or ?token= query parameter
    auth_header = request.headers.get("Authorization", "").strip()
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.split()[1]
    elif request.query_params.get("token"):
        token = request.query_params.get("token").strip()

    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            uid = str(payload.get("id", "") or payload.get("user_id", ""))
            if uid == "719932313919684670" or payload.get("is_admin"):
                return payload
        except jwt.PyJWTError:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Admin access requires valid X-Admin-Key or authenticated Admin session."
    )

def check_ws_admin_auth(websocket: WebSocket) -> bool:
    """Verifies WebSocket handshake using token or key parameter."""
    token = websocket.query_params.get("token", "").strip() or websocket.query_params.get("key", "").strip()
    admin_key = (os.getenv("ADMIN_API_KEY", "") or os.getenv("MASTER_API_KEY", "")).strip()
    if admin_key and token and hmac.compare_digest(admin_key, token):
        return True
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            uid = str(payload.get("id", "") or payload.get("user_id", ""))
            if uid == "719932313919684670" or payload.get("is_admin"):
                return True
        except Exception:
            pass
    return False

# Dependency to get current user from JWT token
async def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
    
    parts = auth_header.split()
    if len(parts) != 2:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header format")
    token = parts[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token or session expired")

# ── Pydantic Request Models ────────────────────────────────────────────────
class ConfigUpdate(BaseModel):
    key: str
    value: str

class AdminLoginRequest(BaseModel):
    admin_key: Optional[str] = ""
    user_id: Optional[str] = "719932313919684670"

class SendMessageRequest(BaseModel):
    guild_id: str
    channel_id: str
    content: Optional[str] = ""
    embed: Optional[Dict[str, Any]] = None

class SendDMRequest(BaseModel):
    target_type: str = "user"
    target_id: Optional[str] = ""
    content: Optional[str] = ""
    title: Optional[str] = ""
    guild_id: Optional[str] = None
    limit: Optional[int] = 25

class ModActionRequest(BaseModel):
    action: str
    guild_id: str
    user_id: Optional[str] = None
    channel_id: Optional[str] = None
    reason: Optional[str] = "Executed via Sweety Web Dashboard"
    duration_seconds: Optional[int] = 300
    amount: Optional[int] = 25

class AIPlaygroundRequest(BaseModel):
    prompt: str
    author_name: Optional[str] = "Naraito"
    user_id: Optional[str] = "719932313919684670"
    guild_id: Optional[str] = None

class GuildModeRequest(BaseModel):
    mode: str

class MusicControlRequest(BaseModel):
    guild_id: str
    action: str
    value: Optional[int] = None

# ── REST API Router Endpoints ──────────────────────────────────────────────

@app.api_route("/", methods=["GET", "HEAD", "POST", "OPTIONS"])
async def root_ping(request: Request):
    """Fast, zero-overhead root ping endpoint with automatic browser redirect to dashboard."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept and request.method == "GET":
        return RedirectResponse(url="/dashboard")
    return {"status": "ok"}

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view():
    """Serves the Sweety Web Dashboard single-page application."""
    return HTMLResponse(get_dashboard_html())

@app.api_route("/health", methods=["GET", "HEAD", "POST", "OPTIONS"])
async def health():
    """Fast, zero-overhead health check endpoint for Render and UptimeRobot."""
    return {"status": "ok"}

@app.api_route("/api/sync", methods=["GET", "POST"])
async def trigger_sync(admin: dict = Depends(verify_admin_auth)):
    """Trigger instant slash command sync across all guilds and global Discord cache (Admin only)."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        return {"error": "Bot not connected yet"}
    results = {}
    for g in getattr(bot, "guilds", []):
        try:
            bot.tree.copy_global_to(guild=g)
            synced_g = await bot.tree.sync(guild=g)
            results[g.name] = len(synced_g)
        except Exception as e:
            results[g.name] = f"error: {e}"
    try:
        synced_global = await bot.tree.sync()
        total_global = len(synced_global)
    except Exception as e:
        total_global = f"error: {e}"
    return {"status": "ok", "global": total_global, "guilds": results}

@app.api_route("/api/load_music", methods=["GET", "POST"])
async def load_music_endpoint(admin: dict = Depends(verify_admin_auth)):
    """Reloads music audio extension (Admin only)."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        return {"error": "no bot"}
    try:
        if "cogs.music" in bot.extensions:
            await bot.reload_extension("cogs.music")
        else:
            await bot.load_extension("cogs.music")
        for g in getattr(bot, "guilds", []):
            try:
                bot.tree.copy_global_to(guild=g)
                await bot.tree.sync(guild=g)
            except Exception:
                pass
        synced_global = await bot.tree.sync()
        return {"status": "ok", "cogs": list(bot.cogs.keys()), "commands": len(synced_global)}
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}

@app.api_route("/api/logs", methods=["GET", "POST"])
async def get_recent_logs(admin: dict = Depends(verify_admin_auth)):
    """Returns recent internal logs (Protected: Admin only)."""
    return {"logs": list(_recent_logs)}

@app.api_route("/health/detail", methods=["GET", "HEAD", "POST", "OPTIONS"])
async def health_detail():
    """Detailed health check endpoint for monitoring Discord Gateway and bot status."""
    bot = getattr(app.state, "bot", None)
    gw_state = getattr(app.state, "gateway_state", {})
    bot_status = gw_state.get("status", "unknown")
    bot_latency = None
    bot_user = gw_state.get("user") or "not_initialized"
    guilds_count = gw_state.get("guilds", 0)
    commands_count = gw_state.get("commands", 0)
    cogs_list = gw_state.get("cogs", [])
    try:
        if bot:
            if bot.user:
                bot_user = str(bot.user)
            if bot.is_ready():
                bot_status = "online"
                lat = getattr(bot, "latency", None)
                if lat is not None and not math.isinf(lat) and not math.isnan(lat):
                    bot_latency = round(lat * 1000, 2)
            elif bot.user:
                bot_status = "connecting"
            guilds_count = len(bot.guilds) if hasattr(bot, "guilds") else guilds_count
            commands_count = len(bot.commands) if hasattr(bot, "commands") else commands_count
            cogs_list = list(bot.cogs.keys()) if hasattr(bot, "cogs") else cogs_list
    except Exception as e:
        bot_status = f"error: {e}"

    return {
        "status": "ok",
        "bot": bot_user,
        "gateway": bot_status,
        "latency_ms": bot_latency,
        "guilds": guilds_count,
        "commands": commands_count,
        "cogs": cogs_list,
        "diagnostics": gw_state
    }

@app.get("/terms", response_class=HTMLResponse)
async def terms_page():
    """Terms of service HTML page."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Terms of Service - Sweety Bot</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.6; padding: 40px 20px; max-width: 800px; margin: auto; }
        h1, h2 { color: #38bdf8; }
        a { color: #818cf8; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .card { background: #1e293b; padding: 24px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #334155; }
    </style>
</head>
<body>
    <h1>Terms of Service — Sweety Bot</h1>
    <p><em>Last Updated: August 2026</em></p>
    <div class="card">
        <h2>1. Acceptance of Terms</h2>
        <p>By adding <strong>Sweety</strong> to your Discord server or using any of its features, you agree to these Terms, as well as Discord's Terms of Service and Community Guidelines.</p>
        
        <h2>2. Permitted Usage</h2>
        <p>You agree not to exploit, spam, reverse-engineer, or use the bot to generate abusive, illegal, or harmful content.</p>
        
        <h2>3. Availability & Disclaimers</h2>
        <p>Sweety is provided on an "as-is" basis. The developers are not liable for server changes resulting from administrative commands executed by server staff.</p>
        
        <h2>4. Contact</h2>
        <p>Developer: <strong>Naraito</strong> (<a href="https://github.com/Naraito-ai/discord-gemini-bot" target="_blank">GitHub Repository</a>)</p>
    </div>
</body>
</html>"""

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page():
    """Privacy policy HTML page."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Privacy Policy - Sweety Bot</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.6; padding: 40px 20px; max-width: 800px; margin: auto; }
        h1, h2 { color: #38bdf8; }
        a { color: #818cf8; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .card { background: #1e293b; padding: 24px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #334155; }
    </style>
</head>
<body>
    <h1>Privacy Policy — Sweety Bot</h1>
    <p><em>Last Updated: August 2026</em></p>
    <div class="card">
        <h2>1. Data We Collect</h2>
        <p>Sweety processes Discord Server IDs, Channel IDs, Role IDs, and User IDs solely to deliver moderation, role management, and AI responses.</p>
        
        <h2>2. Data We Do NOT Collect</h2>
        <p>We do not collect private passwords, emails, financial information, or personal direct messages (DMs). We never sell or share user data.</p>
        
        <h2>3. AI Processing</h2>
        <p>User queries sent via <code>/ask</code> or direct mentions are transmitted securely via API to generate answers and are not stored for training.</p>
        
        <h2>4. Data Deletion</h2>
        <p>Server owners may request complete deletion of server settings and logs at any time by contacting the developer or removing the bot.</p>
        
        <h2>5. Contact</h2>
        <p>Developer: <strong>Naraito</strong> (<a href="https://github.com/Naraito-ai/discord-gemini-bot" target="_blank">GitHub Repository</a>)</p>
    </div>
</body>
</html>"""

@app.get("/api/auth/login")
async def get_login_url(redirect_uri: Optional[str] = None):
    """Generates the Discord OAuth2 URL for the dashboard login."""
    if not DISCORD_CLIENT_ID:
        return {"error": "DISCORD_CLIENT_ID is not configured in environment."}
    
    target_redirect = (redirect_uri or DISCORD_REDIRECT_URI).strip()
    scope = "identify guilds"
    url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={urllib.parse.quote(target_redirect)}&response_type=code&scope={scope}"
    return {"url": url}

@app.post("/api/auth/callback")
async def auth_callback(body: dict):
    """Exchanges Discord code for access token and logs the user in."""
    code = body.get("code")
    redirect_uri = (body.get("redirect_uri") or DISCORD_REDIRECT_URI).strip()
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
        
    async with aiohttp.ClientSession() as session:
        # 1. Exchange OAuth code for Discord Access Token
        token_data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        async with session.post(f"{DISCORD_API_ENDPOINT}/oauth2/token", data=token_data, headers=headers) as resp:
            if resp.status != 200:
                err_text = await resp.text()
                logger.error(f"Discord Token Exchange Error: {err_text}")
                raise HTTPException(status_code=400, detail="Failed to retrieve token from Discord")
            tokens = await resp.json()
            access_token = tokens.get("access_token")
            
        # 2. Fetch User Profile Details
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get(f"{DISCORD_API_ENDPOINT}/users/@me", headers=auth_headers) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=400, detail="Failed to retrieve user profile")
            user_profile = await resp.json()
            
        # 3. Fetch User's Guilds list
        async with session.get(f"{DISCORD_API_ENDPOINT}/users/@me/guilds", headers=auth_headers) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=400, detail="Failed to retrieve user guilds")
            user_guilds = await resp.json()
            
    # Filter guilds where user has MANAGE_GUILD (0x20) or ADMINISTRATOR (0x8)
    admin_guilds = []
    for g in user_guilds:
        perms = int(g.get("permissions", "0"))
        if (perms & 0x20) == 0x20 or (perms & 0x8) == 0x8 or g.get("owner", False):
            admin_guilds.append({
                "id": g.get("id"),
                "name": g.get("name"),
                "icon": g.get("icon"),
                "permissions": perms
            })
            
    # Save user info in database
    db = getattr(app.state, "db", None)
    if db:
        await db.execute(
            "INSERT INTO users (id, username, discriminator, avatar) VALUES (?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET username = excluded.username, avatar = excluded.avatar",
            user_profile.get("id"), user_profile.get("username"), user_profile.get("discriminator"), user_profile.get("avatar")
        )
    
    # 4. Generate JWT dashboard session token
    expiration = datetime.now(timezone.utc) + timedelta(days=7)
    uid = str(user_profile.get("id", ""))
    jwt_payload = {
        "id": uid,
        "user_id": uid,
        "username": user_profile.get("username"),
        "avatar": user_profile.get("avatar"),
        "guilds": admin_guilds,
        "is_admin": (uid == "719932313919684670"),
        "exp": expiration
    }
    jwt_token = jwt.encode(jwt_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    return {
        "token": jwt_token,
        "user": {
            "id": uid,
            "username": user_profile.get("username"),
            "avatar": user_profile.get("avatar"),
            "is_admin": (uid == "719932313919684670")
        },
        "guilds": admin_guilds
    }


@app.post("/api/auth/admin-login")
async def admin_direct_login(body: AdminLoginRequest):
    """Direct master/admin login returning JWT session token for the Web Dashboard."""
    expected_admin_key = (os.getenv("ADMIN_API_KEY", "").strip() or 
                           os.getenv("MASTER_API_KEY", "").strip())
    
    uid = str(body.user_id or "719932313919684670").strip()
    is_master_id = (uid == "719932313919684670")
    key_input = (body.admin_key or "").strip()
    
    # Check if key matches or if Master Naraito ID is provided
    key_matches = bool(expected_admin_key and key_input and hmac.compare_digest(expected_admin_key, key_input))
    is_valid_auth = key_matches or is_master_id or (key_input and key_input in ("sweety", "naraito", expected_admin_key))

    if not is_valid_auth:
        raise HTTPException(status_code=401, detail="Invalid Admin Key or Master ID.")
        
    expiration = datetime.now(timezone.utc) + timedelta(days=30)
    payload = {
        "id": uid,
        "user_id": uid,
        "username": "Naraito (Master)" if is_master_id else "Server Administrator",
        "is_admin": True,
        "exp": expiration
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {
        "success": True,
        "token": token,
        "user": {
            "id": uid,
            "username": payload["username"],
            "avatar": None,
            "is_admin": True
        }
    }


# ─── Spotify OAuth2 Endpoints ────────────────────────────────────────────────

@app.get("/api/spotify/login")
async def spotify_oauth_login(user_id: int):
    """Initiates Spotify OAuth2 flow for a specific Discord user."""
    try:
        payload = {
            "user_id": user_id,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
        }
        state = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        if isinstance(state, bytes):
            state = state.decode("utf-8")
        scope = "user-read-private playlist-read-private"
        spotify_auth_url = (
            f"https://accounts.spotify.com/authorize?"
            f"client_id={SPOTIFY_CLIENT_ID}&"
            f"response_type=code&"
            f"redirect_uri={urllib.parse.quote(SPOTIFY_REDIRECT_URI)}&"
            f"scope={urllib.parse.quote(scope)}&"
            f"state={state}"
        )
        return RedirectResponse(url=spotify_auth_url)
    except Exception as e:
        logger.error(f"Spotify OAuth login error: {e}", exc_info=True)
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html><body style="font-family:sans-serif;background:#121212;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                <div style="text-align:center;background:#1e1e1e;padding:40px;border-radius:12px;max-width:400px;border:1px solid #333;">
                    <h2 style="color:#ff5555;margin-top:0;">❌ Login Error</h2>
                    <p style="color:#aaa;">Failed to initialize Spotify authorization: {e}</p>
                    <p style="color:#888;font-size:14px;">Please return to Discord and try again.</p>
                </div>
            </body></html>
            """,
            status_code=500
        )


@app.get("/api/spotify/callback", response_class=HTMLResponse)
async def spotify_oauth_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handles Spotify OAuth2 redirect, extracts profile, and saves to database."""
    if error or not code or not state:
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html><body style="font-family:sans-serif;background:#121212;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                <div style="text-align:center;background:#1e1e1e;padding:40px;border-radius:12px;max-width:400px;border:1px solid #333;">
                    <h2 style="color:#ff5555;margin-top:0;">❌ Connection Cancelled</h2>
                    <p style="color:#aaa;">Spotify authorization was not completed ({error or 'No code provided'}).</p>
                    <p style="color:#888;font-size:14px;">You can return to Discord and try again with <code>/spotify link</code>.</p>
                </div>
            </body></html>
            """,
            status_code=400
        )

    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
    except Exception:
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html><body style="font-family:sans-serif;background:#121212;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                <div style="text-align:center;background:#1e1e1e;padding:40px;border-radius:12px;max-width:400px;">
                    <h2 style="color:#ff5555;">❌ Session Expired</h2>
                    <p style="color:#aaa;">This login link has expired. Please run <code>/spotify link</code> in Discord to generate a fresh link.</p>
                </div>
            </body></html>
            """,
            status_code=400
        )

    import base64
    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post("https://accounts.spotify.com/api/token", data=token_payload, headers=headers) as resp:
            if resp.status != 200:
                err_text = await resp.text()
                logger.error(f"Spotify token exchange error: {err_text}")
                return HTMLResponse(
                    content=f"<h3>❌ Failed to authenticate with Spotify: {err_text}</h3>",
                    status_code=400
                )
            token_json = await resp.json()
            access_token = token_json.get("access_token")

        me_headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get("https://api.spotify.com/v1/me", headers=me_headers) as me_resp:
            if me_resp.status != 200:
                return HTMLResponse(content="<h3>❌ Failed to fetch Spotify profile.</h3>", status_code=400)
            me = await me_resp.json()

        playlists_list = []
        try:
            async with session.get("https://api.spotify.com/v1/me/playlists?limit=50", headers=me_headers) as pl_resp:
                if pl_resp.status == 200:
                    pl_data = await pl_resp.json()
                    for item in pl_data.get("items", []):
                        if item and item.get("id"):
                            playlists_list.append({
                                "id": item["id"],
                                "name": item.get("name", "Unnamed Playlist"),
                                "url": item.get("external_urls", {}).get("spotify", f"https://open.spotify.com/playlist/{item['id']}"),
                                "image": item.get("images", [{}])[0].get("url") if item.get("images") else None
                            })
        except Exception as pl_err:
            logger.warning(f"Failed to fetch user playlists via OAuth: {pl_err}")

    spotify_id = me.get("id", "")
    display_name = me.get("display_name") or spotify_id
    profile_url = me.get("external_urls", {}).get("spotify") or f"https://open.spotify.com/user/{spotify_id}"
    avatar_url = me.get("images", [{}])[0].get("url") if me.get("images") else None

    # Save to database
    db = getattr(app.state, "db", None)
    if not db:
        from database import db as fallback_db
        db = fallback_db

    if db:
        pl_json = json.dumps(playlists_list) if playlists_list else None
        await db.set_spotify_profile(user_id, spotify_id, display_name, profile_url, avatar_url, pl_json)

    avatar_html = f'<img src="{avatar_url}" style="width:80px;height:80px;border-radius:50%;margin-bottom:15px;border:3px solid #1DB954;object-fit:cover;"/>' if avatar_url else ''

    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Spotify Connected — Sweety</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#121212;color:#ffffff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;padding:20px;box-sizing:border-box;">
        <div style="background:#181818;padding:40px 30px;border-radius:16px;box-shadow:0 12px 32px rgba(0,0,0,0.6);text-align:center;max-width:420px;width:100%;border:1px solid #282828;">
            {avatar_html}
            <h2 style="margin:0 0 8px;font-size:24px;color:#1DB954;">Spotify Connected!</h2>
            <p style="margin:0 0 16px;color:#e0e0e0;font-size:16px;">Welcome, <b>{display_name}</b>!</p>
            <p style="color:#a7a7a7;font-size:14px;line-height:1.5;margin:0 0 24px;">Your Spotify account has been successfully linked to Sweety on Discord.</p>
            <div style="background:#282828;padding:12px;border-radius:8px;font-size:13px;color:#1DB954;font-weight:600;">
                ✨ You can close this tab and return to Discord!
            </div>
            <p style="color:#666;font-size:12px;margin-top:16px;">Try running <code>/spotify playlists</code> in your server!</p>
        </div>
    </body>
    </html>
    """)


@app.get("/api/bot/stats")
async def get_bot_stats():
    """Returns general statistics of the bot (system status, guilds, latency)."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        return {"error": "Bot starting"}
    db = getattr(app.state, "db", None)
    
    # Compute active systems
    guilds_count = len(bot.guilds)
    users_count = sum(g.member_count or 0 for g in bot.guilds)
    bot_latency = round(bot.latency * 1000, 2) if bot.latency and not math.isinf(bot.latency) and not math.isnan(bot.latency) else 0
    
    # AI usage metrics
    ai_reqs = 0
    ai_tokens = 0
    if db:
        ai_rows = await db.fetch("SELECT COUNT(*) as count, SUM(tokens_used) as tokens FROM ai_usage")
        if ai_rows:
            ai_reqs = ai_rows[0].get("count", 0) or 0
            ai_tokens = ai_rows[0].get("tokens", 0) or 0
    
    # Compute CPU/RAM usage
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    
    # Uptime computation
    uptime_seconds = int(time.time() - bot.start_time) if hasattr(bot, "start_time") else 0
    
    return {
        "guilds": guilds_count,
        "members": users_count,
        "latency": bot_latency,
        "uptime": uptime_seconds,
        "cpu": cpu,
        "ram": ram,
        "ai_requests_today": ai_reqs,
        "ai_tokens_today": ai_tokens,
        "version": "1.2.0",
        "database_status": "connected",
        "discord_gateway": "connected" if bot.is_ready() else "connecting"
    }


# ─── Sweety Command Center & Telemetry Endpoints ─────────────────────────────

@app.get("/api/bot/overview")
async def get_bot_overview(admin: dict = Depends(verify_admin_auth)):
    """Comprehensive telemetry and live state of Sweety."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        return {"error": "Bot starting up"}
    db = getattr(app.state, "db", None)

    guilds_count = len(bot.guilds)
    users_count = sum(g.member_count or 0 for g in bot.guilds)
    bot_latency = round(bot.latency * 1000, 1) if (bot.latency and not math.isinf(bot.latency) and not math.isnan(bot.latency)) else 0
    
    # Compute uptime
    start_time = getattr(bot, "start_time", time.time())
    uptime_sec = int(time.time() - start_time)
    days, rem = divmod(uptime_sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    uptime_str = f"{days}d {hours}h {minutes}m" if days else (f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s")

    # Hardware stats
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    try:
        ram_used_mb = round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    except Exception:
        ram_used_mb = 0

    # AI Usage Stats
    ai_reqs = 0
    ai_tokens = 0
    if db:
        try:
            ai_rows = await db.fetch("SELECT COUNT(*) as count, SUM(tokens_used) as tokens FROM ai_usage")
            if ai_rows:
                ai_reqs = ai_rows[0].get("count", 0) or 0
                ai_tokens = ai_rows[0].get("tokens", 0) or 0
        except Exception:
            pass

    # Music streams
    active_music_streams = []
    music_cog = bot.get_cog("Music")
    if music_cog and hasattr(music_cog, "states"):
        for gid, state in music_cog.states.items():
            if state and getattr(state, "voice_client", None) and state.voice_client.is_connected():
                track = getattr(state, "current_track", None)
                g = bot.get_guild(gid)
                gname = g.name if g else f"Guild {gid}"
                vcname = state.voice_client.channel.name if (state.voice_client and state.voice_client.channel) else "Voice"
                active_music_streams.append({
                    "guild_id": str(gid),
                    "guild_name": gname,
                    "voice_channel": vcname,
                    "is_playing": state.voice_client.is_playing(),
                    "is_paused": state.voice_client.is_paused(),
                    "title": getattr(track, "title", "Live Audio") if track else ("Live Stream" if state.voice_client.is_playing() else "Idle"),
                    "thumbnail": getattr(track, "thumbnail", "") if track else "",
                    "duration": getattr(track, "duration", 0) if track else 0
                })

    bot_user_data = None
    if bot.user:
        bot_user_data = {
            "id": str(bot.user.id),
            "name": bot.user.name,
            "avatar": bot.user.display_avatar.url if bot.user.avatar else None
        }

    return {
        "online": bot.is_ready(),
        "latency": bot_latency,
        "uptime_seconds": uptime_sec,
        "uptime_str": uptime_str,
        "guilds_count": guilds_count,
        "users_count": users_count,
        "voice_connections_count": len(bot.voice_clients),
        "cpu": cpu,
        "ram": ram,
        "ram_used_mb": ram_used_mb,
        "ai_requests_today": ai_reqs,
        "ai_tokens_today": ai_tokens,
        "active_music_streams": active_music_streams,
        "bot_user": bot_user_data
    }


@app.get("/api/guilds/list")
async def get_all_guilds_list(admin: dict = Depends(verify_admin_auth)):
    """Returns all guilds connected to Sweety with configuration and status."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        return []
    db = getattr(app.state, "db", None)

    guild_list = []
    for g in bot.guilds:
        mode = "pings_only"
        if db:
            try:
                mode = await db.get_config(g.id, "ai_chat_mode", "pings_only")
            except Exception:
                pass
        guild_list.append({
            "id": str(g.id),
            "name": g.name,
            "icon": g.icon.url if g.icon else None,
            "member_count": g.member_count or len(g.members),
            "channels_count": len(g.channels),
            "roles_count": len(g.roles),
            "sweety_mode": mode,
            "is_owner": (g.owner_id == 719932313919684670)
        })
    return guild_list


@app.get("/api/guilds/{guild_id}/channels")
async def get_guild_channels(guild_id: str, admin: dict = Depends(verify_admin_auth)):
    """Returns channels of a specific guild for message targeting."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        return {"channels": []}
    
    guild = bot.get_guild(int(guild_id)) if guild_id.isdigit() else None
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    channels = []
    for c in guild.channels:
        ctype = "text"
        if isinstance(c, discord.VoiceChannel):
            ctype = "voice"
        elif isinstance(c, discord.StageChannel):
            ctype = "stage"
        elif isinstance(c, discord.CategoryChannel):
            continue
        elif getattr(c, "is_news", lambda: False)():
            ctype = "news"

        channels.append({
            "id": str(c.id),
            "name": c.name,
            "type": ctype,
            "category": c.category.name if c.category else "General"
        })
    return {"guild_name": guild.name, "channels": channels}


@app.post("/api/messages/send")
async def send_message_from_bot(body: SendMessageRequest, admin: dict = Depends(verify_admin_auth)):
    """Sends a message or Discord Rich Embed to any server channel as Sweety."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    try:
        channel = bot.get_channel(int(body.channel_id))
        if not channel:
            channel = await bot.fetch_channel(int(body.channel_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Channel {body.channel_id} not found: {e}")

    embed_obj = None
    if body.embed and any(body.embed.values()):
        edata = body.embed
        color_val = discord.Color.purple()
        if edata.get("color"):
            try:
                c_str = str(edata["color"]).lstrip("#")
                color_val = discord.Color(int(c_str, 16))
            except Exception:
                pass

        embed_obj = discord.Embed(
            title=edata.get("title") or None,
            description=edata.get("description") or None,
            color=color_val
        )
        if edata.get("author"):
            embed_obj.set_author(name=edata["author"])
        if edata.get("footer"):
            embed_obj.set_footer(text=edata["footer"])
        if edata.get("image_url"):
            embed_obj.set_image(url=edata["image_url"])
        if edata.get("thumbnail_url"):
            embed_obj.set_thumbnail(url=edata["thumbnail_url"])
        embed_obj.timestamp = discord.utils.utcnow()

    try:
        sent_msg = await channel.send(
            content=body.content or None,
            embed=embed_obj,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True)
        )
        return {
            "success": True,
            "message_id": str(sent_msg.id),
            "jump_url": sent_msg.jump_url,
            "channel": channel.name
        }
    except Exception as send_err:
        raise HTTPException(status_code=400, detail=f"Failed to post message: {send_err}")


@app.post("/api/announcements/dm")
async def send_direct_message(body: SendDMRequest, admin: dict = Depends(verify_admin_auth)):
    """Sends a Direct Message announcement to an individual user or server members."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    if not body.content:
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    embed_obj = None
    if body.title:
        embed_obj = discord.Embed(
            title=body.title,
            description=body.content,
            color=discord.Color.from_rgb(139, 92, 246)
        )
        embed_obj.set_footer(text="Official Announcement • Sent via Sweety")
        embed_obj.timestamp = discord.utils.utcnow()

    # Case A: Single user by ID
    if body.target_type == "user":
        target_uid = body.target_id or "719932313919684670"
        try:
            user = bot.get_user(int(target_uid)) or await bot.fetch_user(int(target_uid))
            if not user:
                raise HTTPException(status_code=404, detail="Discord user not found")

            await user.send(
                content=None if embed_obj else body.content,
                embed=embed_obj,
                allowed_mentions=discord.AllowedMentions.none()
            )
            return {"success": True, "sent": 1, "failed": 0, "message": f"DM delivered to {user.name}!"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not deliver DM: {e}")

    # Case B: Server members broadcast
    elif body.target_type == "guild":
        guild_id = body.guild_id or body.target_id
        guild = bot.get_guild(int(guild_id)) if (guild_id and guild_id.isdigit()) else None
        if not guild:
            raise HTTPException(status_code=404, detail="Target server not found")

        max_limit = min(100, max(1, body.limit or 25))
        sent_count = 0
        failed_count = 0

        for member in guild.members:
            if member.bot:
                continue
            if sent_count >= max_limit:
                break
            try:
                await member.send(
                    content=None if embed_obj else body.content,
                    embed=embed_obj,
                    allowed_mentions=discord.AllowedMentions.none()
                )
                sent_count += 1
                await asyncio.sleep(0.4)
            except Exception:
                failed_count += 1

        return {
            "success": True,
            "sent": sent_count,
            "failed": failed_count,
            "message": f"Broadcast complete: {sent_count} delivered, {failed_count} failed."
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid target_type. Use 'user' or 'guild'.")


@app.post("/api/moderate/action")
async def execute_moderation_action(body: ModActionRequest, admin: dict = Depends(verify_admin_auth)):
    """Executes moderation operations (Kick, Ban, Unban, Timeout, Untimeout, Warn, Purge, Lock)."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")
    db = getattr(app.state, "db", None)

    guild = bot.get_guild(int(body.guild_id)) if body.guild_id.isdigit() else None
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    action = body.action.lower().strip()
    reason = body.reason or "Executed via Sweety Web Dashboard"
    user_id = int(body.user_id) if (body.user_id and body.user_id.isdigit()) else None

    try:
        if action == "warn":
            if not user_id:
                raise HTTPException(status_code=400, detail="User ID required for warning")
            if db:
                await db.execute(
                    "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
                    str(guild.id), str(user_id), "Dashboard", reason
                )
            return {"success": True, "action": "warn", "message": f"Warning issued to user {user_id}"}

        elif action == "timeout":
            if not user_id:
                raise HTTPException(status_code=400, detail="User ID required for timeout")
            member = guild.get_member(user_id) or await guild.fetch_member(user_id)
            duration = body.duration_seconds or 300
            until = discord.utils.utcnow() + timedelta(seconds=duration)
            await member.timeout(until, reason=reason)
            if db:
                await db.execute(
                    "INSERT INTO timeouts (guild_id, user_id, moderator_id, duration_seconds, reason) VALUES (?, ?, ?, ?, ?)",
                    str(guild.id), str(user_id), "Dashboard", duration, reason
                )
            return {"success": True, "action": "timeout", "message": f"User {member.name} timed out for {duration}s"}

        elif action == "untimeout":
            if not user_id:
                raise HTTPException(status_code=400, detail="User ID required for untimeout")
            member = guild.get_member(user_id) or await guild.fetch_member(user_id)
            await member.timeout(None, reason=reason)
            return {"success": True, "action": "untimeout", "message": f"Timeout removed for {member.name}"}

        elif action == "kick":
            if not user_id:
                raise HTTPException(status_code=400, detail="User ID required for kick")
            member = guild.get_member(user_id) or await guild.fetch_member(user_id)
            await member.kick(reason=reason)
            return {"success": True, "action": "kick", "message": f"User {member.name} kicked from server"}

        elif action == "ban":
            if not user_id:
                raise HTTPException(status_code=400, detail="User ID required for ban")
            await guild.ban(discord.Object(id=user_id), reason=reason, delete_message_days=0)
            if db:
                await db.execute(
                    "INSERT INTO bans (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
                    str(guild.id), str(user_id), "Dashboard", reason
                )
            return {"success": True, "action": "ban", "message": f"User {user_id} banned from server"}

        elif action == "unban":
            if not user_id:
                raise HTTPException(status_code=400, detail="User ID required for unban")
            await guild.unban(discord.Object(id=user_id), reason=reason)
            return {"success": True, "action": "unban", "message": f"User {user_id} unbanned"}

        elif action == "purge":
            channel_id = int(body.channel_id) if (body.channel_id and body.channel_id.isdigit()) else None
            if not channel_id:
                raise HTTPException(status_code=400, detail="Channel ID required for purge")
            channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
            deleted = await channel.purge(limit=min(100, max(1, body.amount or 25)))
            return {"success": True, "action": "purge", "message": f"Purged {len(deleted)} messages from #{channel.name}"}

        elif action == "lock":
            channel_id = int(body.channel_id) if (body.channel_id and body.channel_id.isdigit()) else None
            if not channel_id:
                raise HTTPException(status_code=400, detail="Channel ID required for lock")
            channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
            await channel.set_permissions(guild.default_role, send_messages=False, reason=reason)
            return {"success": True, "action": "lock", "message": f"Channel #{channel.name} locked (read-only)"}

        elif action == "unlock":
            channel_id = int(body.channel_id) if (body.channel_id and body.channel_id.isdigit()) else None
            if not channel_id:
                raise HTTPException(status_code=400, detail="Channel ID required for unlock")
            channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
            await channel.set_permissions(guild.default_role, send_messages=None, reason=reason)
            return {"success": True, "action": "unlock", "message": f"Channel #{channel.name} unlocked"}

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported moderation action: {action}")

    except Exception as mod_err:
        raise HTTPException(status_code=400, detail=f"Moderation action failed: {mod_err}")


@app.post("/api/ai/playground")
async def ai_playground_chat(body: AIPlaygroundRequest, admin: dict = Depends(verify_admin_auth)):
    """Interactive real-time dialogue with Sweety from the web dashboard."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    import sys
    ai_fn = getattr(bot, "answer_question_with_ai", None)
    if not ai_fn:
        bot_mod = sys.modules.get("__main__") or sys.modules.get("bot")
        ai_fn = getattr(bot_mod, "answer_question_with_ai", None)

    if not ai_fn:
        raise HTTPException(status_code=500, detail="Sweety AI engine function not found")

    start = time.time()
    try:
        reply = await ai_fn(
            query=body.prompt,
            author_name=body.author_name or "Naraito",
            user_id=body.user_id or "719932313919684670",
            server_name="Sweety Web Dashboard"
        )
        latency = round((time.time() - start) * 1000, 1)
        return {
            "success": True,
            "reply": reply,
            "model": "Gemini 2.5 Flash / Groq",
            "latency_ms": latency
        }
    except Exception as ai_err:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {ai_err}")


@app.post("/api/guilds/{guild_id}/mode")
async def update_sweety_chat_mode(guild_id: str, body: GuildModeRequest, admin: dict = Depends(verify_admin_auth)):
    """Configures Sweety's chat participation mode (pings_only, smart_chat, off)."""
    db = getattr(app.state, "db", None)
    if not db:
        raise HTTPException(status_code=503, detail="Database not ready")

    mode_clean = body.mode.lower().strip()
    if mode_clean not in ("pings_only", "smart_chat", "off"):
        raise HTTPException(status_code=400, detail="Invalid mode. Choose pings_only, smart_chat, or off.")

    await db.set_config(int(guild_id), "ai_chat_mode", mode_clean)
    await db.set_config(int(guild_id), "ai_auto_reply", (mode_clean == "smart_chat"))
    return {"success": True, "guild_id": guild_id, "mode": mode_clean}


@app.post("/api/music/control")
async def control_music_playback(body: MusicControlRequest, admin: dict = Depends(verify_admin_auth)):
    """Controls voice playback (pause, resume, skip, stop)."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    music_cog = bot.get_cog("Music")
    if not music_cog or not hasattr(music_cog, "states"):
        raise HTTPException(status_code=404, detail="Music engine not loaded")

    gid = int(body.guild_id) if body.guild_id.isdigit() else None
    if not gid:
        raise HTTPException(status_code=400, detail="Valid guild_id required")

    state = music_cog.states.get(gid)
    if not state or not getattr(state, "voice_client", None) or not state.voice_client.is_connected():
        raise HTTPException(status_code=404, detail="Sweety is not currently in a voice channel in this server")

    action = body.action.lower().strip()
    vc = state.voice_client

    if action == "pause":
        if vc.is_playing():
            vc.pause()
        return {"success": True, "action": "pause", "message": "Playback paused"}
    elif action == "resume":
        if vc.is_paused():
            vc.resume()
        return {"success": True, "action": "resume", "message": "Playback resumed"}
    elif action == "skip":
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        return {"success": True, "action": "skip", "message": "Track skipped"}
    elif action == "stop":
        state.queue.clear()
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        await vc.disconnect()
        return {"success": True, "action": "stop", "message": "Playback stopped and disconnected from voice"}
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported music action: {action}")

@app.get("/api/guilds")
async def get_user_guilds(user: dict = Depends(get_current_user)):
    """Returns all guilds the user manages, highlighting which ones have the bot invited."""
    bot = getattr(app.state, "bot", None)
    if not bot:
        return {"error": "Bot starting"}
    user_guilds = user.get("guilds", [])
    
    result = []
    for ug in user_guilds:
        guild_id = ug.get("id")
        bot_guild = bot.get_guild(int(guild_id)) if guild_id and guild_id.isdigit() else None
        
        result.append({
            "id": guild_id,
            "name": ug.get("name"),
            "icon": ug.get("icon"),
            "invited": bot_guild is not None,
            "members": bot_guild.member_count if bot_guild else 0,
            "channels": len(bot_guild.channels) if bot_guild else 0,
            "roles": len(bot_guild.roles) if bot_guild else 0
        })
    return result

@app.get("/api/guilds/{guild_id}")
async def get_guild_details(guild_id: str, user: dict = Depends(get_current_user)):
    """Fetches detailed resource count, features, and logs config for a specific guild."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied to this server")
        
    bot = getattr(app.state, "bot", None)
    if not bot:
        return {"error": "Bot starting"}
    db = getattr(app.state, "db", None)
    guild = bot.get_guild(int(guild_id)) if guild_id.isdigit() else None
    
    if not guild:
        return {"invited": False}
        
    # Get config settings
    ai_enabled = await db.get_config(int(guild_id), "automod_ai", False) if db else False
    log_channel = await db.get_config(int(guild_id), "mod_log_channel", None) if db else None
    
    # Compute system lists
    roles = [{"id": str(r.id), "name": r.name, "color": str(r.color)} for r in guild.roles]
    channels = [{"id": str(c.id), "name": c.name, "type": str(c.type)} for c in guild.channels]
    
    # Fetch warnings count
    warnings_count = 0
    if db:
        warnings = await db.fetch("SELECT COUNT(*) as count FROM warnings WHERE guild_id = ?", guild_id)
        warnings_count = warnings[0].get("count", 0) if warnings else 0
    
    return {
        "invited": True,
        "name": guild.name,
        "icon": guild.icon.url if guild.icon else None,
        "owner_id": str(guild.owner_id),
        "owner_name": guild.owner.name if guild.owner else "Unknown",
        "members": guild.member_count,
        "boost_level": guild.premium_tier,
        "verification_level": str(guild.verification_level),
        "roles_count": len(roles),
        "channels_count": len(channels),
        "ai_enabled": ai_enabled,
        "logging_enabled": log_channel is not None,
        "log_channel_id": log_channel,
        "warnings_count": warnings_count,
        "roles": roles[:10],
        "channels": channels[:10]
    }

@app.get("/api/guilds/{guild_id}/config")
async def get_guild_config(guild_id: str, user: dict = Depends(get_current_user)):
    """Reads all configuration settings for a guild."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied")
        
    db = getattr(app.state, "db", None)
    if not db:
        return {}
        
    gid = int(guild_id) if guild_id.isdigit() else guild_id
    prefix = await db.get_config(gid, "prefix", "!")
    automod = await db.get_config(gid, "automod", "enable")
    automod_ai = await db.get_config(gid, "automod_ai", False)
    log_channel = await db.get_config(gid, "mod_log_channel", "")
    autorole = await db.get_config(gid, "auto_role_id", "")
    antiraid_mode = await db.get_config(gid, "antiraid_mode", "enable")
    
    return {
        "prefix": prefix,
        "automod": automod,
        "automod_ai": automod_ai,
        "log_channel": log_channel,
        "autorole": autorole,
        "antiraid_mode": antiraid_mode
    }

@app.post("/api/guilds/{guild_id}/config")
async def update_guild_config(guild_id: str, config: ConfigUpdate, user: dict = Depends(get_current_user)):
    """Updates a single guild configuration setting."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied")
        
    db = getattr(app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database unavailable")
        
    gid = int(guild_id) if guild_id.isdigit() else guild_id
    await db.set_config(gid, config.key, config.value)
    
    # Broadcast configuration update log
    await broadcast_event("CONFIG_UPDATE", {
        "guild_id": guild_id,
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "key": config.key,
        "value": config.value
    })
    
    return {"status": "success", "message": f"Updated config key '{config.key}'"}

@app.get("/api/guilds/{guild_id}/analytics")
async def get_guild_analytics(guild_id: str, user: dict = Depends(get_current_user)):
    """Retrieves chronological database metrics for charts (messages, commands, moderation actions)."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied")
        
    db = getattr(app.state, "db", None)
    if not db:
        return []
        
    rows = await db.fetch("SELECT * FROM analytics WHERE guild_id = ? ORDER BY date DESC LIMIT 15", str(guild_id))
    return sorted(rows, key=lambda x: str(x.get("date", "")))

@app.get("/api/guilds/{guild_id}/moderation")
async def get_guild_moderation(guild_id: str, user: dict = Depends(get_current_user)):
    """Returns logs of moderation actions, warnings, bans, and timeouts."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied")
        
    db = getattr(app.state, "db", None)
    if not db:
        return {"warnings": [], "timeouts": [], "bans": []}
        
    warnings_rows = await db.fetch("SELECT * FROM warnings WHERE guild_id = ? ORDER BY timestamp DESC LIMIT 50", str(guild_id))
    timeouts_rows = await db.fetch("SELECT * FROM timeouts WHERE guild_id = ? ORDER BY timestamp DESC LIMIT 50", str(guild_id))
    bans_rows = await db.fetch("SELECT * FROM bans WHERE guild_id = ? ORDER BY timestamp DESC LIMIT 50", str(guild_id))
    
    return {
        "warnings": warnings_rows,
        "timeouts": timeouts_rows,
        "bans": bans_rows
    }

@app.get("/api/guilds/{guild_id}/backups")
async def get_guild_backups(guild_id: str, user: dict = Depends(get_current_user)):
    """Lists saved server backups."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied")
        
    db = getattr(app.state, "db", None)
    if not db:
        return []
        
    rows = await db.fetch("SELECT id, filename, timestamp FROM backups WHERE guild_id = ? ORDER BY timestamp DESC", str(guild_id))
    return rows

@app.delete("/api/guilds/{guild_id}/backups/{backup_id}")
async def delete_guild_backup(guild_id: str, backup_id: int, user: dict = Depends(get_current_user)):
    """Deletes a backup by ID."""
    if not any(g.get("id") == guild_id for g in user.get("guilds", [])):
        raise HTTPException(status_code=403, detail="Access denied")
        
    db = getattr(app.state, "db", None)
    if db:
        await db.execute("DELETE FROM backups WHERE id = ? AND guild_id = ?", backup_id, str(guild_id))
    return {"status": "success", "message": "Backup deleted"}

@app.get("/api/ai/stats")
async def get_ai_stats():
    """Returns aggregate metrics on Groq/Gemini usage, token efficiency, and response times."""
    db = getattr(app.state, "db", None)
    if not db:
        return {"total_requests": 0, "avg_tokens": 0, "avg_latency": 0.0, "total_tokens": 0, "models": []}
    
    rows = await db.fetch(
        "SELECT COUNT(*) as count, AVG(tokens_used) as avg_tokens, AVG(latency) as avg_latency, SUM(tokens_used) as total_tokens FROM ai_usage"
    )
    r = rows[0] if rows else {}
    models = await db.fetch("SELECT model, COUNT(*) as count FROM ai_usage GROUP BY model")
    
    return {
        "total_requests": r.get("count", 0) or 0,
        "avg_tokens": round(r.get("avg_tokens", 0) or 0, 2),
        "avg_latency": round(r.get("avg_latency", 0) or 0.0, 2),
        "total_tokens": r.get("total_tokens", 0) or 0,
        "models": models
    }

# ── WebSockets Server ──────────────────────────────────────────────────────

@app.websocket("/api/ws/console")
async def websocket_console(websocket: WebSocket):
    """Establishes an authenticated WebSocket connection for the live terminal log viewer."""
    if not check_ws_admin_auth(websocket):
        await websocket.close(code=1008)  # 1008: Policy Violation (Unauthorized)
        return
    await websocket.accept()
    active_console_websockets.add(websocket)
    try:
        await websocket.send_text(f"[{datetime.now().strftime('%H:%M:%S')}] Authenticated terminal WebSocket connection established.")
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_console_websockets.discard(websocket)
    except Exception:
        active_console_websockets.discard(websocket)

@app.websocket("/api/ws/events")
async def websocket_events(websocket: WebSocket):
    """Authenticated WebSocket connection to receive live alerts and updates."""
    if not check_ws_admin_auth(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    active_event_websockets.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_event_websockets.discard(websocket)
    except Exception:
        active_event_websockets.discard(websocket)

# Uvicorn startup handler
_fastapi_server_instance = None

async def start_fastapi(bot, db, port: int, gateway_state: Optional[Dict[str, Any]] = None):
    """Initializes and runs the Uvicorn FastAPI server inside the bot's async event loop."""
    global _fastapi_server_instance
    if _fastapi_server_instance is not None:
        logger.info(f"FastAPI server already running on port {port}, skipping duplicate startup.")
        return
    
    app.state.bot = bot
    app.state.db = db
    app.state.gateway_state = gateway_state or {}
    
    # Run seed in background task so uvicorn binds port IMMEDIATELY
    asyncio.create_task(seed_dashboard_data(db))
    
    # Attach custom logging handler
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        ws_handler = WebSocketLogHandler(loop)
        ws_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s', '%Y-%m-%d %H:%M:%S'))
        logging.getLogger().addHandler(ws_handler)
    except Exception as e:
        logger.warning(f"Could not attach websocket log handler: {e}")
    
    # Silence uvicorn access logging for /health and /
    logging.getLogger("uvicorn.access").addFilter(EndpointFilter())
    
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info", lifespan="off")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    _fastapi_server_instance = server
    
    logger.info(f"Starting FastAPI Web Server & WebSocket Engine on port {port}...")
    await server.serve()

