import discord
from discord.ext import commands
from discord import app_commands
import asyncio

ADMIN_ROLE_ID = 1335986334673932378
MOD_ROLE_ID = 1335986334673932378

class Announce(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="announce", description="Create a guided server announcement")
    @app_commands.checks.has_any_role(ADMIN_ROLE_ID, MOD_ROLE_ID)
    async def announce(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "📢 **Starting Announcement Creation**\n\n"
            "**Step 1:** Mention or provide the channel (`#general`, ID, or link).",
            ephemeral=True
        )

        def check(m):
            return m.author.id == interaction.user.id and m.channel == interaction.channel

        # ---- Step 1: Channel ----
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            channel = None
            if msg.channel_mentions:
                channel = msg.channel_mentions[0]
            elif msg.content.isdigit():
                channel = self.bot.get_channel(int(msg.content))
            elif "discord.com/channels/" in msg.content:
                channel_id = int(msg.content.split("/")[-1])
                channel = self.bot.get_channel(channel_id)

            if not channel:
                await interaction.followup.send("❌ Could not find that channel.", ephemeral=True)
                return
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timeout! You didn’t respond in time.", ephemeral=True)
            return

        # ---- Step 2: Title ----
        await interaction.followup.send("✅ Channel set! Now provide the **title**.", ephemeral=True)
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            title = msg.content
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timeout on title step.", ephemeral=True)
            return

        # ---- Step 3: Content ----
        await interaction.followup.send("✅ Title set! Now send the **main content**.", ephemeral=True)
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=300)
            content = msg.content
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timeout on content step.", ephemeral=True)
            return

        # ---- Step 4: Mentions ----
        await interaction.followup.send(
            "✅ Content set! Send any **role/user mentions** (or `skip`).",
            ephemeral=True
        )
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            mentions = "" if msg.content.lower() in ["skip", "no"] else msg.content
        except asyncio.TimeoutError:
            mentions = ""

        # ---- Step 5: Image ----
        await interaction.followup.send(
            "✅ Mentions set! Send an **image URL** (or `skip`).",
            ephemeral=True
        )
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            image_url = None if msg.content.lower() in ["skip", "no"] else msg.content
        except asyncio.TimeoutError:
            image_url = None

        # ---- Preview ----
        embed = discord.Embed(title=title, description=content, color=discord.Color.red())
        if image_url:
            embed.set_image(url=image_url)

        preview_text = (
            f"📢 **Announcement Preview**\n\n"
            f"**Channel:** {channel.mention}\n"
            f"**Mentions:** {mentions if mentions else 'None'}\n"
            f"**Image:** {'Yes' if image_url else 'No'}"
        )

        await interaction.followup.send(preview_text, embed=embed, ephemeral=True)
        await interaction.followup.send("Reply `yes` to send or `no` to cancel.", ephemeral=True)

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            if msg.content.lower() in ["yes", "confirm", "send"]:
                await channel.send(content=mentions, embed=embed)
                await interaction.followup.send(f"✅ Announcement sent to {channel.mention}!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Announcement cancelled.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timeout at confirmation step.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Announce(bot))
