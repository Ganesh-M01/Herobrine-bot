
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
from flask import Flask
import threading

# -------------------- Flask server (for Render port) --------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Hello, Render!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))  # Render provides this
    app.run(host="0.0.0.0", port=port)

# Start Flask in a separate thread
threading.Thread(target=run_flask, daemon=True).start()

# -------------------- Discord Bot --------------------
TOKEN = os.environ['TOKEN']
GUILD_ID = 1272252145508421632  # Replace with your server's guild ID

ADMIN_ROLE_ID = 1335986334673932378  # Replace with your admin role ID
MOD_ROLE_ID = 1335986334673932378    # Replace with your mod role ID

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------- Announcement Modal --------------------
class AnnouncementModal(discord.ui.Modal, title="📢 Send Announcement"):
    message = discord.ui.TextInput(
        label="Announcement Message",
        placeholder="Type the announcement here...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000,
    )

    channel_id = discord.ui.TextInput(
        label="Target Channel ID",
        placeholder="123456789012345678",
        style=discord.TextStyle.short,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel = bot.get_channel(int(self.channel_id.value))
            if not channel:
                await interaction.response.send_message("❌ Invalid channel ID.", ephemeral=True)
                return

            embed = discord.Embed(
                title="📢 Announcement",
                description=self.message.value,
                color=discord.Color.red()
            )

            await channel.send(embed=embed)
            await interaction.response.send_message("✅ Announcement sent!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

# -------------------- Herobrine Panel Slash Command --------------------
@bot.tree.command(name="herobrinepanel", description="Herobrine Control Panel")
@app_commands.checks.has_any_role(ADMIN_ROLE_ID, MOD_ROLE_ID)
async def herobrinepanel(interaction: discord.Interaction):
    view = discord.ui.View(timeout=60)
    options = [discord.SelectOption(label="Announcement", description="Send a server-wide announcement", emoji="📢")]
    select = discord.ui.Select(placeholder="Select a moderator function...", options=options)

    async def select_callback(select_interaction: discord.Interaction):
        if select.values[0] == "Announcement":
            await select_interaction.response.send_modal(AnnouncementModal())

    select.callback = select_callback
    view.add_item(select)
    await interaction.response.send_message("Herobrine Functions", view=view, ephemeral=True)

# -------------------- Global Error Handling --------------------
@bot.tree.error
async def global_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingAnyRole):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)

# -------------------- on_ready Event --------------------
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    print(f"✅ Logged in as {bot.user}. Slash commands synced to guild {GUILD_ID}.")

# -------------------- Start Bot --------------------
asyncio.run(bot.start(TOKEN))
