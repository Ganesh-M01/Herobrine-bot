import discord
from discord.ext import commands, tasks
from discord import app_commands
from mcstatus import JavaServer, BedrockServer
import asyncio
import datetime
import os
import base64

GUILD_ID = int(os.getenv("GUILD_ID", "0"))  # dev/test guild ID from .env

class ServerStatus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = {}  # guild_id -> {ip, port, type, channel_id, message_id}
        self.update_status.start()

    def cog_unload(self):
        self.update_status.cancel()

    # ----------------- Slash Command ----------------- #
    @app_commands.command(name="setup", description="Setup the Minecraft server status monitor")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "⚙️ Let's set up your server status! Please answer the following:", ephemeral=True
        )

        def check(m: discord.Message):
            return m.author.id == interaction.user.id and m.channel == interaction.channel

        # Step 1: IP
        await interaction.followup.send(
            "🌍 Step 1: Please provide the **server IP** (e.g., `play.example.com`):", ephemeral=True
        )
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            ip = msg.content.strip()
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Setup cancelled (timeout).", ephemeral=True)
            return

        # Step 2: Port
        await interaction.followup.send(
            "🔌 Step 2: Provide the **server port** (e.g., `25565`):", ephemeral=True
        )
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            port = int(msg.content.strip())
        except (asyncio.TimeoutError, ValueError):
            await interaction.followup.send("⏰ Setup cancelled (invalid or timeout).", ephemeral=True)
            return

        # Step 3: Type
        await interaction.followup.send(
            "🎮 Step 3: Is this a **Java** or **Bedrock** server? (type exactly `java` or `bedrock`)",
            ephemeral=True
        )
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            srv_type = msg.content.lower().strip()
            if srv_type not in ("java", "bedrock"):
                raise ValueError
        except (asyncio.TimeoutError, ValueError):
            await interaction.followup.send("❌ Setup cancelled (invalid type).", ephemeral=True)
            return

        # Step 4: Channel
        await interaction.followup.send(
            "📢 Step 4: Do you want the status here or mention another channel? (type `here` or mention #channel)",
            ephemeral=True
        )
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            if msg.content.lower().strip() == "here":
                channel = interaction.channel
            elif msg.channel_mentions:
                channel = msg.channel_mentions[0]
            else:
                raise ValueError
        except (asyncio.TimeoutError, ValueError):
            await interaction.followup.send("❌ Setup cancelled (invalid channel).", ephemeral=True)
            return

        # Save config
        self.config[interaction.guild.id] = {
            "ip": ip,
            "port": port,
            "type": srv_type,
            "channel_id": channel.id,
            "message_id": None
        }

        await interaction.followup.send(f"✅ Setup complete! Status will be posted in {channel.mention}", ephemeral=True)

        # Immediately send status
        await self.post_or_update_status(interaction.guild.id)

    # ----------------- Status Update ----------------- #
    async def fetch_status(self, ip, port, srv_type):
        try:
            if srv_type == "java":
                server = JavaServer.lookup(f"{ip}:{port}")
                status = server.status()
                sample = status.players.sample or []
                players = "\n".join([f"{i+1}. {p.name}" for i, p in enumerate(sample)]) if sample else "No players online"

                favicon_data = None
                if status.favicon:
                    # keep the base64 favicon as a data URI for Discord embed
                    favicon_data = status.favicon

                return {
                    "online": True,
                    "ip": ip,
                    "version": status.version.name,
                    "players_online": status.players.online,
                    "players_max": status.players.max,
                    "players_list": players,
                    "favicon": favicon_data
                }
            else:
                server = BedrockServer.lookup(f"{ip}:{port}")
                status = server.status()
                return {
                    "online": True,
                    "ip": ip,
                    "version": status.version.brand,
                    "players_online": status.players_online,
                    "players_max": status.players_max,
                    "players_list": "Not available for Bedrock"
                }
        except Exception:
            return {"online": False}

    async def post_or_update_status(self, guild_id):
        cfg = self.config.get(guild_id)
        if not cfg:
            return

        channel = self.bot.get_channel(cfg["channel_id"])
        if not channel:
            return

        data = await self.fetch_status(cfg["ip"], cfg["port"], cfg["type"])
        embed = discord.Embed(
            title="📊 Minecraft Server Status",
            color=discord.Color.green() if data["online"] else discord.Color.red()
        )

        if data["online"]:
            embed.add_field(name="IP", value=data["ip"], inline=False)
            embed.add_field(name="Type", value=cfg["type"].capitalize(), inline=True)
            embed.add_field(name="Version", value=data["version"], inline=True)
            embed.add_field(name="Players", value=f"{data['players_online']}/{data['players_max']}", inline=False)
            embed.add_field(name="Player List", value=data["players_list"], inline=False)

            # Add Java server banner if available
            if cfg["type"] == "java" and "favicon" in data and data["favicon"]:
                embed.set_image(url=data["favicon"])

        else:
            embed.add_field(name="Status", value="❌ Server Offline", inline=False)

        embed.set_footer(text=f"Last updated • {datetime.datetime.now().strftime('%d-%m-%Y %I:%M %p')}")

        try:
            if cfg["message_id"]:
                msg = await channel.fetch_message(cfg["message_id"])
                await msg.edit(embed=embed)
            else:
                msg = await channel.send(embed=embed)
                cfg["message_id"] = msg.id
        except discord.Forbidden:
            print("❌ Bot missing permissions to send/edit messages.")

    @tasks.loop(minutes=2)
    async def update_status(self):
        for guild_id in self.config.keys():
            await self.post_or_update_status(guild_id)

# ----------------- Cog Setup ----------------- #
async def setup(bot):
    cog = ServerStatus(bot)
    await bot.add_cog(cog)
    # Register setup command in dev/test guild for instant availability
    if GUILD_ID:
        bot.tree.add_command(cog.setup, guild=discord.Object(id=GUILD_ID))
