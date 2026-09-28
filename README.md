# 💖 Sweety Bot (Discord AI & NBA 2K Mobile Game Engine)

[![Discord](https://img.shields.io/badge/Discord-Bot-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Gemini 2.5](https://img.shields.io/badge/Google%20Gemini-2.5%20Flash-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![Render](https://img.shields.io/badge/Render-Deployed-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

**Sweety Bot** is a high-performance, feature-packed Discord bot and full-scale **NBA 2K Mobile Card & Tactical Battle Game Engine** powered by **Google Gemini 2.5 Flash** (with **Groq** acceleration), dual SQLite/PostgreSQL persistence, and Pillow image rendering.

---

## 🌟 Table of Contents
- [🏀 NBA 2K Mobile Card Ecosystem](#-nba-2k-mobile-card-ecosystem)
- [⚔️ NBA Starting 5 Lineup Builder & Battles](#️-nba-starting-5-lineup-builder--battles)
- [🤖 Sweety AI Companion & Chat](#-sweety-ai-companion--chat)
- [🛡️ Enterprise Moderation, Sniping & Security](#️-enterprise-moderation-sniping--security)
- [🏗️ AI Server Architect & Tickets](#️-ai-server-architect--tickets)
- [📋 Complete Command Reference](#-complete-command-reference)
- [🛠️ Installation & Self-Hosting](#️-installation--self-hosting)
- [🚀 24/7 Deployment Guide (Render)](#-247-deployment-guide-render)

---

## 🏀 NBA 2K Mobile Card Ecosystem

Sweety features a card collection game inspired by **NBA 2K Mobile MyTEAM**:

* **🎴 68+ Authentic Player Cards across 6 Tiers**:
  * 🌌 **Dark Matter / G.O.A.T. (99 OVR)** — Michael Jordan, LeBron James, Stephen Curry, Kobe Bryant, Kevin Durant, Larry Bird, Giannis Antetokounmpo, Shaquille O'Neal, Magic Johnson, Victor Wembanyama.
  * ✨ **Galaxy Opal (97–98 OVR)** — Nikola Jokić, Luka Dončić, Tim Duncan, Tracy McGrady, Jayson Tatum, Joel Embiid, Anthony Davis, Kawhi Leonard, Jimmy Butler, Allen Iverson.
  * 💎 **Diamond (93–96 OVR)** — Kyrie Irving, Shai Gilgeous-Alexander, Anthony Edwards, Devin Booker, Donovan Mitchell, Damian Lillard, Tyrese Haliburton, Ja Morant, Dirk Nowitzki, Bam Adebayo, Hakeem Olajuwon.
  * 🔮 **Amethyst (88–92 OVR)** — Jalen Brunson, Jaylen Brown, Paolo Banchero, Zion Williamson, Karl-Anthony Towns, Domantas Sabonis, De'Aaron Fox, Trae Young, Jamal Murray, LaMelo Ball, Chet Holmgren.
  * 🔴 **Ruby (84–87 OVR)** — Derrick White, Jrue Holiday, Tyrese Maxey, Austin Reaves, Franz Wagner, Mikal Bridges, OG Anunoby, Aaron Gordon, Coby White, Rudy Gobert, Kristaps Porziņģis.
  * 🟡 **Gold (75–83 OVR)** — Alex Caruso, Naz Reid, Cam Thomas, Malik Monk, Herb Jones, Jaime Jaquez Jr., Payton Pritchard, Brandin Podziemski, Bobby Portis, Norman Powell, Dereck Lively II.
* **📸 Official Transparent Headshots**: Verified transparent player headshot cutouts from `cdn.nba.com` (`1040x760` with dual fallback to `260x190`).
* **💬 Wild Chat Spawns & 20-Min Periodic Drops**:
  * Spawns every **25 messages** in active channels and on a **20-minute periodic background timer**.
  * Displays dynamic silhouette card graphics with masked player name hints.
  * First to catch via `!catch <name>` or modal gets the card in their binder + **150 VC**.
* **📖 Interactive Binder & Dex (`/nbadex` / `!nbadex`)**:
  * Paginated card binder with tier filtering (Dark Matter, Galaxy Opal, Diamond, Amethyst, Ruby, Gold).
  * Card inspection view showing quick-sell VC values, attributes, and signature badges.
* **💰 Virtual Currency (VC) Economy & Card Packs (`/nbashop` / `!nbashop`)**:
  * Starter Packs, All-Star Packs, MVP Packs, and GOAT Packs with dynamic drop rates.
  * Quick-sell duplicates or claim daily VC rewards (`/nbadaily`).
* **🤝 Atomic Peer-to-Peer Trading (`/nbatrade` / `!nbatrade`)**:
  * Safe, atomic two-way card swapping inside a dedicated SQLite transaction (`BEGIN IMMEDIATE`) preventing duplicate trade glitches or race conditions.

---

## ⚔️ NBA Starting 5 Lineup Builder & Battles

* **🏀 Card Dex Lineup Builder (`/buildteam` / `!buildteam`)**:
  * Build your starting 5 lineup (**PG**, **SG**, **SF**, **PF**, **C**) directly from the cards owned in your binder.
  * Supports primary and secondary position eligibility.
  * **`[⚡ Auto-Equip Best Lineup]`**: Automatically equips your highest OVR cards without duplicate players.
  * **Complimentary Starter Pack**: Grants 5 starter cards to new players automatically.
* **🖼️ High-Definition Lineup Showcase (`/myteam` / `!myteam`)**:
  * Generates a 1600x960 2K MyTEAM court graphic featuring player cutout artwork, OVR ratings, tier ribbons, synergy badges, win streaks, and career records.
* **⚔️ 5-Round Tactical Team Battles (`/teambattle` / `!teambattle`)**:
  * Live positional duels (PG vs PG, SG vs SG, SF vs SF, PF vs PF, C vs C).
  * Real-time coaching tactical play calls: **Lockdown Clamp (🔒)**, **Mamba Iso (⚡)**, **Pick & Roll Maestro (🧠)**, **Fastbreak Rim Run (🏃)**, **Catch & Shoot 3PT (🎯)**, and **Coach Timeouts (⏱️)**.
  * Generates 1600x960 head-to-head matchup scouting graphics.
* **👑 Daily Boss Challenge (`/dailynba` / `!dailynba`)**:
  * Daily curated AI boss lineups with practice and ranked modes.
* **🏆 GM Leaderboards (`/teamtop` / `/nbaleaderboard`)**:
  * Server and global leaderboards tracking battle wins, win streaks, and binder collection sizes.

---

## 🤖 Sweety AI Companion & Chat

* **🧠 Powered by Gemini 2.5 Flash**: Fast, engaging conversational companion with witty, warm, and helpful personality.
* **💬 Natural Triggers**: Mention `@Sweety` in server text channels or chat directly in DMs.
* **💭 User Memory System**: Remembers user preferences, nicknames, and context across conversations.
* **🎭 Anime Social Roleplay Actions**: Rich animated GIF actions with interactive buttons:
  * `pat`, `hug`, `kiss`, `slap`, `cuddle`, `dance`, `cheers`, `bonk`, `poke`, `kill`, `feed`, `bite`, `wink`, `blush`, `wave`.

---

## 🛡️ Enterprise Moderation, Sniping & Security

* **🛡️ Multi-Tier Auto-Mod (`/automod`)**:
  * **Local Shield**: Zero-latency regex detection for slurs, toxicity, and phishing links.
  * **AI Scanner**: Dynamic semantic evaluation using Gemini safety filters.
* **⚠️ Warning & Strike Escalation (`/warn`, `/warnings`, `/strikes`)**:
  * Formal warning management with customizable strike thresholds and automatic timeout escalation.
  * DM strike appeal system (`!appeal`).
* **👻 Anti-Ghost-Ping Shield (`/antighostping`)**:
  * Instantly detects deleted or edited messages containing member pings and exposes the sender.
* **🎯 Advanced Snipe Engine**:
  * Inspect recently deleted messages (`/snipe`), edited messages (`/editsnipe`), or member-specific snipe history (`/usersnipe`).

---

## 🏗️ AI Server Architect & Tickets

* **🏗️ One-Click Server Builder (`/setup <prompt>`)**:
  * AI designs complete Discord server layouts with categories, emoji channels, permissions, and roles.
  * Preview layout with confirm/cancel buttons before applying changes.
* **🎟️ Persistent Ticket System (`/ticket`)**:
  * Spawns support ticket panels with buttons that create private support channels surviving bot restarts.
* **👋 Dynamic AI Welcome Greetings (`/welcome`)**:
  * Crafts contextual welcome messages for joining members.

---

## 📋 Complete Command Reference

### 🏀 NBA 2K Mobile & 3PT Shootout Commands
| Slash Command | Prefix Command | Description |
| :--- | :--- | :--- |
| `/shootout [bet]` | `!shootout` / `!3pt` | Play fast-paced NBA All-Star 3-Point Contest (5 racks, Money/Starry balls) |
| `/shootout duel @user [bet]` | `!shootout @user [bet]` | Challenge another user to a live 1v1 3-Point Shootout showdown |
| — | `!shootout lb` / `!3pt lb` | View global 3-Point Shootout high scores leaderboard |
| `/nbadex [user] [tier] [page]` | `!nbadex` | Open paginated card binder with tier filters & 🔒 Privacy Toggle |
| `/nbaprivacy` | `!nbaprivacy` | Toggle public/private visibility for your NBA card binder |
| `/giftcard @user <card_id>` | `!giftcard @user <id>` | Gift an owned NBA card from your binder to another member |
| `/buildteam` | `!buildteam` | Open interactive Lineup Builder to set Starting 5 from binder |
| `/myteam [user]` | `!myteam` | Generate high-res 1600x960 2K Starting 5 image card |
| `/teambattle <user>` | `!teambattle` | Challenge a member to a 5-round tactical NBA showdown |
| `/vcbet @user <amount>` | `!vcbet @user <amount>` | Wager VC on a 5v5 Starting 5 clash (winner takes pot) |
| `/teamqueue` | `!teamqueue` | Join auto-matchmaking queue for live NBA battles |
| `/dailynba` | `!dailynba` | Challenge today's featured daily NBA Boss squad |
| `/nbacard <id_or_name>` | `!nbacard` | Inspect full 2K card ratings, badges, and quick-sell value |
| `/openpack [tier]` | `!openpack [tier]` | Open Standard, Premium, Deluxe, Opal & End Game card packs |
| `/packodds` | `!packodds` | View transparent card pack drop rates and tier probabilities |
| `/nbasell <card_id>` | `!nbasell` | Quick-sell owned duplicate cards for VC |
| `/nbadaily` | `!nbadaily` | Claim daily VC salary reward |
| `/nbabal [user]` | `!nbabal` | Check your current VC balance and card count |
| `/nbatrade @user <card_id>` | `!nbatrade` | Propose secure atomic multi-card trade |
| `/teamtop [limit]` | `!teamtop` / `!teamlb` | View top GMs by battle wins and win streaks |
| `/nbatop [cards\|vc]` | `!nbatop [cards\|vc]` | View server leaderboard by card collection size or VC |
| `/spawndrop [tier]` | `!spawndrop` | Trigger wild player card drops |
| `/nbahint` | `!nbahint` | Reveal an additional letter hint for active wild drop |
| `/nbastatus` | `!nbastatus` | Check chat message drop counter and spawn status |
| `/nbaswitch` | `!nbaswitch` | Set default channel for wild NBA drops |

### 🤖 AI & Social Commands
| Command | Description |
| :--- | :--- |
| `@Sweety <message>` | Chat with Sweety AI powered by Gemini 2.5 Flash |
| `/ask <question>` | Ask Gemini AI a question with code formatting |
| `/remember <key> <fact>` | Store a personal memory for the bot to remember |
| `/memories` | View or manage your saved AI memories |
| `!pat`, `!hug`, `!kiss`, `!slap` | Interactive social anime roleplay actions with buttons |
| `/debate [channel]` | Roll an instant NBA basketball debate with live voting buttons |
| `/startbenchcut` | Play Start, Bench, Cut with 3 random NBA stars |

### 🛡️ Moderation & Server Utility
| Command | Permission | Description |
| :--- | :--- | :--- |
| `/warn <user> [reason]` | Moderate Members | Issue formal infraction warning |
| `/warnings [user]` | Everyone | View warning records and strike history |
| `/clearwarns <user>` | Moderate Members | Clear infraction records |
| `/antighostping <status>` | Manage Server | Toggle anti-ghost-ping detection |
| `/snipe [index]` | Everyone | Reveal recently deleted message in channel |
| `/editsnipe` | Everyone | Reveal original message before edit |
| `/usersnipe <user>` | Moderate Members | View deleted messages by specific member |
| `/setup <description>` | Manage Server | AI server architect layout generator |
| `/ticket` | Manage Server | Spawn persistent support ticket panel |
| `/welcome <style>` | Manage Server | Configure dynamic AI welcome greetings |
| `/lockdown <on/off>` | Manage Channels | Lock down text channels during emergency |
| `/purge <amount>` | Manage Messages | Bulk delete recent messages |

---

## 🛠️ Installation & Self-Hosting

### Prerequisites
* **Python 3.10+** (Python 3.12 recommended)
* **Discord Bot Token** from the [Discord Developer Portal](https://discord.com/developers/applications) (Enable Message Content, Server Members, and Presence Intents).
* **Google Gemini API Key** from [Google AI Studio](https://aistudio.google.com/).

### Setup Steps
```bash
# 1. Clone the repository
git clone https://github.com/Naraito-ai/Naraito-s-Disc-Swty.git
cd Naraito-s-Disc-Swty

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env configuration
cp .env.example .env
```

### Environment Variables (`.env`)
```env
DISCORD_TOKEN=your_discord_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
# Optional Groq fallback
GROQ_API_KEY=your_groq_api_key_here
# Optional PostgreSQL (Defaults to local SQLite bot_data.db if omitted)
DATABASE_URL=postgresql://user:password@host:port/dbname
```

### Run Bot
```bash
python bot.py
```

---

## 🚀 24/7 Deployment Guide (Render)

1. Create a **Web Service** or **Background Worker** on [Render.com](https://render.com).
2. Connect your GitHub repository (`Naraito-s-Disc-Swty`).
3. Configure settings:
   * **Runtime**: `Python`
   * **Build Command**: `pip install -r requirements.txt`
   * **Start Command**: `python bot.py`
4. Add environment variables under **Environment**:
   * `DISCORD_TOKEN`
   * `GEMINI_API_KEY`
   * `DATABASE_URL` (Supabase or Render PostgreSQL for cloud persistence)
5. Deploy service — Sweety Bot will be live 24/7 with automatic crash recovery.

---

## 📄 License
This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
