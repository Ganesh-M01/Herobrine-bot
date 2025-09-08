import asyncio
import discord
from discord.ext import commands
from discord import app_commands

ADMIN_ROLE_ID = 1335986334673932378
MOD_ROLE_ID = 1335986334673932378

class Announce(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="announce", description="Create a guided server announcement")
    @app_commands.checks.has_any_role(ADMIN_ROLE_ID, MOD_ROLE_ID)
    async def announce(self, interaction: discord.Interaction):
        # Defer ephemerally so all followups are hidden for the author
        await interaction.response.defer(ephemeral=True)  # ensures subsequent followups are ephemeral [13][12]

        def check(m: discord.Message):
            return m.author.id == interaction.user.id and m.channel == interaction.channel  # gate inputs to the initiator [20]

        # Step 1: Channel
        await interaction.followup.send("📢 Starting Announcement Creation\n\nStep 1: Mention or provide the channel (#general, ID, or link).")  # ephemeral due to defer [13][12]
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)  # wait for user input [20]
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timeout! No channel provided in time.")
            return

        channel: discord.abc.Messageable | None = None
        try:
            if msg.channel_mentions:
                channel = msg.channel_mentions
            elif msg.content.isdigit():
                channel = self.bot.get_channel(int(msg.content))
            elif "discord.com/channels/" in msg.content:
                parts = msg.content.strip().split("/")
                channel_id = int(parts[-1])
                channel = self.bot.get_channel(channel_id)
        except Exception:
            channel = None

        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
            await interaction.followup.send("❌ Could not find that channel or it’s not a text-capable channel.")
            return

        # Step 2: Title
        await interaction.followup.send("✅ Channel set! Now provide the title.")
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            title = msg.content.strip()
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timeout on title step.")
            return

        if not title:
            await interaction.followup.send("❌ Title cannot be empty.")
            return

        # Step 3: Content
        await interaction.followup.send("✅ Title set! Now send the main content.")
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=300)
            content = msg.content.strip()
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timeout on content step.")
            return

        if not content:
            await interaction.followup.send("❌ Content cannot be empty.")
            return

        # Step 4: Mentions (optional)
        await interaction.followup.send("✅ Content set! Send any role/user mentions (or type `skip`).")
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            mentions = "" if msg.content.lower().strip() in ("skip", "no") else msg.content
        except asyncio.TimeoutError:
            mentions = ""

        # Step 5: Image (optional)
        await interaction.followup.send("✅ Mentions set! Send an image URL (or type `skip`).")
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
            image_url = None if msg.content.lower().strip() in ("skip", "no") else msg.content.strip()
        except asyncio.TimeoutError:
            image_url = None

        # Build preview
        embed = discord.Embed(title=title, description=content, color=discord.Color.red())
        if image_url:
            embed.set_image(url=image_url)

        preview_text = (
            f"📢 Announcement Preview\n\n"
            f"Channel: {getattr(channel, 'mention', str(channel))}\n"
            f"Mentions: {mentions if mentions else 'None'}\n"
            f"Image: {'Yes' if image_url else 'No'}"
        )
        await interaction.followup.send(preview_text, embed=embed)
        await interaction.followup.send("Reply `yes` to send or `no` to cancel.")

        # Confirmation
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Timeout at confirmation step.")
            return

        if msg.content.lower().strip() in ("yes", "confirm", "send"):
            # Attempt to send in the chosen channel
            try:
                await channel.send(content=mentions if mentions else None, embed=embed)  # actual public post [4]
                await interaction.followup.send(f"✅ Announcement sent to {channel.mention}!")
            except discord.Forbidden:
                await interaction.followup.send("❌ Missing permissions to send messages or embeds in the target channel.")
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to send announcement: {e}")
        else:
            await interaction.followup.send("❌ Announcement cancelled.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Announce(bot))
