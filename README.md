<h1 align="center">⚡ Herobrine Bot ⚡</h1>
<p align="center">
  <img src="./assets/banner2.gif" alt="Herobrine Banner" width="600">
</p>
<p align="center">
  A custom <b>Discord Bot</b> built with <code>discord.py</code> to power the <b>Only Gamers</b> community.<br>
  ✨ Announcements, tickets, invite tracking, YouTube live alerts, a counting game, Minecraft server status, and a stylish control panel for moderators.
</p>

---

## 🚀 Features

- 📢 **Announcements**
  ➝ Send server-wide announcements via a modal with channel selection.
  ➝ Only Admins & Moderators can access.

- ⚙️ **Herobrine Control Panel (`/herobrinepanel`)**
  ➝ Dropdown UI for moderator tools.
  ➝ Currently includes announcement sending (more coming soon).

- 🌍 **Server IP Command (`/ip`)**
  ➝ Shows both **Java** & **Bedrock** IP + Port.
  ➝ Displays your custom `banner.gif` below the embed.
  ➝ Restricted to Admins & Moderators.

- 🎟️ **Ticket System**
  ➝ Users can open support tickets, staff can manage and close them.
  ➝ Ticket state persisted so nothing is lost on restart.

- 📺 **YouTube Live Notifications**
  ➝ Watches one or more YouTube channels via the YouTube Data API v3.
  ➝ Posts an embed + role ping in Discord the moment a watched channel goes live.
  ➝ Tracks last-announced stream so it never double-pings the same broadcast.
  ➝ `!ytcheck` — manually trigger a live-status check (admin only).

- 📨 **Invite Tracker**
  ➝ Logs member joins and leaves with full invite attribution (who invited them, invite code, channel, uses).
  ➝ Shows "X joined this server N times before" for returning members.
  ➝ Tracks each inviter's **active/total** invite stats (how many of their invites are still in the server).
  ➝ `!invites @user` — check anyone's invite stats on demand.

- 🔢 **Counting Game**
  ➝ A dedicated channel where members count up together.
  ➝ ✅ correct number advances the count, ❌ wrong number just gets flagged (count stays put).
  ➝ 12-hour per-user cooldown to keep it fair.
  ➝ Announces a new all-time record when the count is broken.
  ➝ `!countinfo` — view current count & record. `!setcount` — admin override.

- 🟩 **Minecraft Server Status**
  ➝ Live-updating embed showing online/offline status, player count, version, ping, and MOTD.
  ➝ Displays the server's real favicon and a list of online players (when available).
  ➝ Auto-refreshes on a timer *and* supports on-demand checks via `!mcstatus`.

---

## 📦 Installation

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/your-username/herobrine-bot.git
cd herobrine-bot
```

### 2️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 3️⃣ Configure Environment Variables
Create a `.env` file in the project root:

```env
# Core
TOKEN=your_discord_bot_token
GUILD_ID=your_guild_id_for_dev_sync

# YouTube Live Notifications
YOUTUBE_API_KEY=your_youtube_data_api_key
YOUTUBE_CHANNEL_IDS=UCxxxxxxxxxxxxxxxxxxxxxx,UCyyyyyyyyyyyyyyyyyyyyyy
YT_ANNOUNCE_CHANNEL_ID=discord_channel_id
YT_PING_ROLE_ID=discord_role_id
YT_CHECK_INTERVAL_MIN=30

# Invite Tracker
INVITE_LOG_CHANNEL_ID=discord_channel_id
IGNORE_BOTS_INVITE_LOG=true

# Counting Game
COUNTING_CHANNEL_ID=discord_channel_id

# Minecraft Server Status
MC_SERVER_ADDRESS=play.yourserver.com
MC_SERVER_NAME=OG SMP
MC_STATUS_CHANNEL_ID=discord_channel_id
MC_STATUS_REFRESH_MIN=5
MC_OFFLINE_IMAGE_URL=https://your-image-link.png
```

### 4️⃣ Run the Bot
```bash
python main.py
```

---

## 🧩 Tech Stack

- [discord.py](https://discordpy.readthedocs.io/) — Discord bot framework (cogs/extensions architecture)
- [mcstatus](https://pypi.org/project/mcstatus/) — Minecraft Java server status queries
- [aiohttp](https://docs.aiohttp.org/) — async HTTP requests to the YouTube Data API
- JSON-based persistence per feature (tickets, invites, counting, YouTube state, MC status)

---

## 🗂️ Project Structure

```
Herobrine-Bot/
├── main.py               # Bot entrypoint, extension loader, command sync
├── announce.py            # Announcement modal + channel selection
├── ip.py                  # /ip command
├── status.py               # Control panel
├── tickets.py              # Ticket system
├── youtube_live.py         # YouTube live notifications (multi-channel)
├── invite_tracker.py       # Invite tracking & join/leave logs
├── counting.py             # Counting game
├── mc_status.py            # Minecraft server status
├── keep_alive.py           # Keeps the bot alive on hosting platforms
├── assets/                 # Banners, icons, images
└── *_data.json             # Per-feature persisted state
```

---

<p align="center">Built with ❤️ for the <b>Only Gamers</b> community.</p>
