import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))  # set in .env for dev-guild sync

# Intents
intents = discord.Intents.default()
intents.message_content = True  # your /announce flow uses wait_for on messages

# Bot setup
bot = commands.Bot(command_prefix="!", intents=intents)
EXTENSIONS = ["ip", "status", "announce"]

@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user} ({bot.user.id})")

async def load_extensions():
    for ext in EXTENSIONS:
        try:
            await bot.load_extension(ext)
            print(f"📂 Loaded extension: {ext}")
        except Exception as e:
            print(f"❌ Failed to load extension {ext}: {e}")

async def sync_commands():
    # Guild-scoped sync for instant iteration
    if GUILD_ID:
        guild_obj = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild_obj)
        print(f"✅ Synced {len(synced)} command(s) to guild {GUILD_ID}")
    else:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} global command(s)")

@bot.event
async def setup_hook():
    # Called before on_ready; safe place to load extensions and sync
    await load_extensions()
    await sync_commands()

def main():
    if not TOKEN:
        raise RuntimeError("TOKEN not set in environment")
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
