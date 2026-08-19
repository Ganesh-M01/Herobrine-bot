import os
import json
import aiohttp
import discord
from discord.ext import commands, tasks

# ── Config (set these in your .env) ─────────────────────────────
# YOUTUBE_API_KEY        -> YouTube Data API v3 key (Google Cloud Console)
# YOUTUBE_CHANNEL_IDS    -> comma-separated list of UC... channel IDs to watch
#                           (e.g. "UCxxxxxxxx,UCyyyyyyyy"). For a single
#                           channel, YOUTUBE_CHANNEL_ID (singular) still works.
# YT_ANNOUNCE_CHANNEL_ID -> Discord channel ID to post notifications in (shared)
# YT_PING_ROLE_ID        -> Discord role ID to ping (optional; omit to skip ping)
# YT_CHECK_INTERVAL_MIN  -> minutes between checks (default 10)
#
# NOTE ON QUOTA: search.list costs 100 units/call, PER CHANNEL WATCHED.
# Default daily quota is 10,000 units. With N channels watched, max checks/day
# = 10000 / (100 * N). For 2 channels that's ~50 checks/day, i.e. an interval
# of at least ~29 minutes to stay under quota. The default below (10 min) is
# safe for 1 channel but will exceed quota with 2+ channels — raise
# YT_CHECK_INTERVAL_MIN accordingly, or request a quota increase in Google
# Cloud Console.

API_KEY = os.getenv("YOUTUBE_API_KEY")

_raw_ids = os.getenv("YOUTUBE_CHANNEL_IDS") or os.getenv("YOUTUBE_CHANNEL_ID", "")
CHANNEL_IDS = [c.strip() for c in _raw_ids.split(",") if c.strip()]

ANNOUNCE_CHANNEL_ID = int(os.getenv("YT_ANNOUNCE_CHANNEL_ID", "0"))
PING_ROLE_ID = int(os.getenv("YT_PING_ROLE_ID", "0"))
CHECK_INTERVAL_MIN = int(os.getenv("YT_CHECK_INTERVAL_MIN", "10"))

DATA_FILE = "youtube_live_data.json"
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def _load_data():
    default = {"channels": {}}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            return default

        # Migrate old single-channel format: {"last_video_id":.., "is_live":..}
        if "channels" not in raw and "last_video_id" in raw and CHANNEL_IDS:
            return {
                "channels": {
                    CHANNEL_IDS[0]: {
                        "last_video_id": raw.get("last_video_id"),
                        "is_live": raw.get("is_live", False),
                    }
                }
            }
        return raw
    return default


def _save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


class YouTubeLive(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = _load_data()
        self.session: aiohttp.ClientSession | None = None

        if not API_KEY or not CHANNEL_IDS:
            print("⚠️  YouTube live notifications disabled: "
                  "YOUTUBE_API_KEY or YOUTUBE_CHANNEL_IDS not set in .env")
            return

        if not ANNOUNCE_CHANNEL_ID:
            print("⚠️  YouTube live notifications disabled: "
                  "YT_ANNOUNCE_CHANNEL_ID not set in .env")
            return

        for cid in CHANNEL_IDS:
            self.data["channels"].setdefault(cid, {"last_video_id": None, "is_live": False})
        _save_data(self.data)

        self.check_live.change_interval(minutes=CHECK_INTERVAL_MIN)
        self.check_live.start()
        print(f"📺 Watching {len(CHANNEL_IDS)} YouTube channel(s) for live streams")

    def cog_unload(self):
        self.check_live.cancel()
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    @tasks.loop(minutes=10)  # overwritten by change_interval in __init__
    async def check_live(self):
        for cid in CHANNEL_IDS:
            try:
                await self._check_one_channel(cid)
            except Exception as e:
                print(f"❌ YouTube live check failed for {cid}: {e}")

    async def _check_one_channel(self, channel_id: str):
        video = await self._get_current_live_video(channel_id)
        state = self.data["channels"].setdefault(channel_id, {"last_video_id": None, "is_live": False})

        if video is None:
            if state.get("is_live"):
                state["is_live"] = False
                _save_data(self.data)
            return

        video_id = video["id"]["videoId"]

        # Already announced this exact stream
        if state.get("is_live") and state.get("last_video_id") == video_id:
            return

        await self._announce(video)
        state["is_live"] = True
        state["last_video_id"] = video_id
        _save_data(self.data)

    @check_live.before_loop
    async def before_check_live(self):
        await self.bot.wait_until_ready()

    async def _get_current_live_video(self, channel_id: str):
        """Returns the live video's search.list item dict, or None if not live."""
        params = {
            "key": API_KEY,
            "channelId": channel_id,
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
        print(f"📺 Announced live stream: {title} ({channel_title})")

    @commands.command(name="ytcheck")
    @commands.has_permissions(administrator=True)
    async def ytcheck(self, ctx: commands.Context):
        """Manually trigger a live-status check for all watched channels (admin only)."""
        await ctx.send(f"🔍 Checking YouTube live status for {len(CHANNEL_IDS)} channel(s)...")
        await self.check_live()
        await ctx.send("✅ Check complete.")


async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeLive(bot))