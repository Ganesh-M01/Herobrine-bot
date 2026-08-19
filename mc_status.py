import os
import io
import json
import base64
import asyncio

import discord
from discord.ext import commands, tasks
from mcstatus import JavaServer

# ── Config (set in your .env) ───────────────────────────────────
# MC_SERVER_ADDRESS       -> e.g. play.yourserver.com or play.yourserver.com:25565
# MC_SERVER_NAME          -> display name, e.g. "OG SMP"
# MC_STATUS_CHANNEL_ID    -> channel ID for the auto-refreshing live status message
# MC_STATUS_REFRESH_MIN   -> minutes between auto-refreshes (default 5)
# MC_OFFLINE_IMAGE_URL    -> optional image shown when server is offline

SERVER_ADDRESS = os.getenv("MC_SERVER_ADDRESS")
SERVER_NAME = os.getenv("MC_SERVER_NAME", "Minecraft Server")
STATUS_CHANNEL_ID = int(os.getenv("MC_STATUS_CHANNEL_ID", "0"))
REFRESH_MIN = int(os.getenv("MC_STATUS_REFRESH_MIN", "5"))
OFFLINE_IMAGE_URL = os.getenv("MC_OFFLINE_IMAGE_URL")

DATA_FILE = "mc_status_data.json"

GREEN = 0x57F287
RED = 0xED4245


def _load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"message_id": None, "channel_id": None}


def _save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


class MinecraftStatus(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = _load_data()

        if not SERVER_ADDRESS:
            print("⚠️  Minecraft status: MC_SERVER_ADDRESS not set in .env — disabled")
            return

        if STATUS_CHANNEL_ID:
            self.refresh_status.change_interval(minutes=REFRESH_MIN)
            self.refresh_status.start()

    def cog_unload(self):
        self.refresh_status.cancel()

    async def _query_server(self):
        """Returns mcstatus JavaStatusResponse, or None if unreachable."""
        try:
            server = await asyncio.to_thread(JavaServer.lookup, SERVER_ADDRESS)
            status = await asyncio.to_thread(server.status)
            return status
        except Exception as e:
            print(f"ℹ️  Minecraft status check failed (likely offline): {e}")
            return None

    def _motd_text(self, status) -> str:
        try:
            return status.motd.to_plain()
        except AttributeError:
            return str(status.description)

    def _build_embed_and_file(self, status):
        if status is None:
            embed = discord.Embed(
                title=f"⚠️ {SERVER_NAME} is currently offline",
                description=f"**{SERVER_NAME}** will be back soon ❤️",
                color=RED,
                timestamp=discord.utils.utcnow(),
            )
            file = None
            if OFFLINE_IMAGE_URL:
                embed.set_image(url=OFFLINE_IMAGE_URL)
            embed.set_footer(text=f"Powered by {self.bot.user.name}", icon_url=self.bot.user.display_avatar.url)
            return embed, file

        embed = discord.Embed(
            title=f"✅ {SERVER_NAME} is online!",
            color=GREEN,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Players", value=f"{status.players.online} / {status.players.max}", inline=True)
        embed.add_field(name="Version", value=status.version.name, inline=True)
        embed.add_field(name="Ping", value=f"{round(status.latency)} ms", inline=True)

        motd = self._motd_text(status)
        if motd:
            embed.add_field(name="MOTD", value=motd[:1024], inline=False)

        if status.players.sample:
            names = ", ".join(p.name for p in status.players.sample[:15])
            embed.add_field(name="Online Players", value=names[:1024], inline=False)

        file = None
        if status.icon:
            try:
                header, b64data = status.icon.split(",", 1)
                icon_bytes = base64.b64decode(b64data)
                file = discord.File(io.BytesIO(icon_bytes), filename="server-icon.png")
                embed.set_thumbnail(url="attachment://server-icon.png")
            except Exception:
                pass

        embed.set_footer(text=f"Powered by {self.bot.user.name}", icon_url=self.bot.user.display_avatar.url)
        return embed, file

    @tasks.loop(minutes=5)  # overwritten by change_interval
    async def refresh_status(self):
        channel = self.bot.get_channel(STATUS_CHANNEL_ID)
        if channel is None:
            print(f"❌ Could not find Minecraft status channel {STATUS_CHANNEL_ID}")
            return

        status = await self._query_server()
        embed, file = self._build_embed_and_file(status)

        message = None
        if self.data.get("message_id") and self.data.get("channel_id") == STATUS_CHANNEL_ID:
            try:
                message = await channel.fetch_message(self.data["message_id"])
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                message = None

        if message:
            if file:
                await message.edit(embed=embed, attachments=[file])
            else:
                await message.edit(embed=embed, attachments=[])
        else:
            sent = await channel.send(embed=embed, file=file) if file else await channel.send(embed=embed)
            self.data["message_id"] = sent.id
            self.data["channel_id"] = STATUS_CHANNEL_ID
            _save_data(self.data)

    @refresh_status.before_loop
    async def before_refresh_status(self):
        await self.bot.wait_until_ready()

    @commands.command(name="mcstatus")
    async def mcstatus(self, ctx: commands.Context):
        """Check the Minecraft server status on demand."""
        if not SERVER_ADDRESS:
            await ctx.send("⚠️ Minecraft server address isn't configured yet.")
            return

        msg = await ctx.send("🔍 Checking server status...")
        status = await self._query_server()
        embed, file = self._build_embed_and_file(status)

        await msg.delete()
        if file:
            await ctx.send(embed=embed, file=file)
        else:
            await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(MinecraftStatus(bot))