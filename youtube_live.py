import os
import json
import aiohttp
import discord
from discord.ext import commands, tasks

# ── Config (set these in your .env) ─────────────────────────────
# YOUTUBE_API_KEY        -> YouTube Data API v3 key (Google Cloud Console)
# YOUTUBE_CHANNEL_ID     -> the UC... channel ID to watch (NOT the @handle)
# YT_ANNOUNCE_CHANNEL_ID -> Discord channel ID to post the notification in
# YT_PING_ROLE_ID        -> Discord role ID to ping (optional; omit to skip ping)
# YT_CHECK_INTERVAL_MIN  -> minutes between checks (default 10)
#
# NOTE ON QUOTA: search.list costs 100 units/call, default daily quota is
# 10,000 units (~100 calls/day). At the default 10-min interval that's
# ~144 calls/day, which can exceed quota on a busy day. If you hit quota
# errors, either raise YT_CHECK_INTERVAL_MIN or request a quota increase
# in Google Cloud Console.

API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")
ANNOUNCE_CHANNEL_ID = int(os.getenv("YT_ANNOUNCE_CHANNEL_ID", "0"))
PING_ROLE_ID = int(os.getenv("YT_PING_ROLE_ID", "0"))
CHECK_INTERVAL_MIN = int(os.getenv("YT_CHECK_INTERVAL_MIN", "10"))

DATA_FILE = "youtube_live_data.json"
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def _load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_video_id": None, "is_live": False}


def _save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


class YouTubeLive(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = _load_data()
        self.session: aiohttp.ClientSession | None = None

        if not API_KEY or not CHANNEL_ID:
            print("⚠️  YouTube live notifications disabled: "
                  "YOUTUBE_API_KEY or YOUTUBE_CHANNEL_ID not set in .env")
            return

        if not ANNOUNCE_CHANNEL_ID:
            print("⚠️  YouTube live notifications disabled: "
                  "YT_ANNOUNCE_CHANNEL_ID not set in .env")
            return

        self.check_live.change_interval(minutes=CHECK_INTERVAL_MIN)
        self.check_live.start()

    def cog_unload(self):
        self.check_live.cancel()
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    @tasks.loop(minutes=10)  # overwritten by change_interval in __init__
    async def check_live(self):
        try:
            video = await self._get_current_live_video()
        except Exception as e:
            print(f"❌ YouTube live check failed: {e}")
            return

        if video is None:
            # Not live right now
            if self.data.get("is_live"):
                self.data["is_live"] = False
                _save_data(self.data)
            return

        video_id = video["id"]["videoId"]

        # Already announced this exact stream
        if self.data.get("is_live") and self.data.get("last_video_id") == video_id:
            return

        await self._announce(video)
        self.data["is_live"] = True
        self.data["last_video_id"] = video_id
        _save_data(self.data)

    @check_live.before_loop
    async def before_check_live(self):
        await self.bot.wait_until_ready()

    async def _get_current_live_video(self):
        """Returns the live video's search.list item dict, or None if not live."""
        params = {
            "key": API_KEY,
            "channelId": CHANNEL_ID,
            "part": "snippet",
            "eventType": "live",
            "type": "video",
            "maxResults": 1,
        }
        async with self.session.get(SEARCH_URL, params=params) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {body[:200]}")
            payload = await resp.json()

        items = payload.get("items", [])
        return items[0] if items else None

    async def _announce(self, video: dict):
        channel = self.bot.get_channel(ANNOUNCE_CHANNEL_ID)
        if channel is None:
            print(f"❌ Could not find announce channel {ANNOUNCE_CHANNEL_ID}")
            return

        video_id = video["id"]["videoId"]
        snippet = video["snippet"]
        title = snippet.get("title", "Live now!")
        channel_title = snippet.get("channelTitle", "")
        thumbnail = (
            snippet.get("thumbnails", {}).get("high", {}).get("url")
            or snippet.get("thumbnails", {}).get("default", {}).get("url")
        )
        url = f"https://www.youtube.com/watch?v={video_id}"

        embed = discord.Embed(
            title=title,
            url=url,
            description=f"{channel_title} is live on YouTube right now!",
            color=discord.Color.red(),
        )
        if thumbnail:
            embed.set_image(url=thumbnail)
        embed.set_footer(text="YouTube Live")

        content = None
        if PING_ROLE_ID:
            content = f"<@&{PING_ROLE_ID}>"

        await channel.send(content=content, embed=embed)
        print(f"📺 Announced live stream: {title}")

    @commands.command(name="ytcheck")
    @commands.has_permissions(administrator=True)
    async def ytcheck(self, ctx: commands.Context):
        """Manually trigger a live-status check (admin only)."""
        await ctx.send("🔍 Checking YouTube live status...")
        await self.check_live()
        await ctx.send("✅ Check complete.")


async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeLive(bot))