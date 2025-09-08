import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

# Intents
intents = discord.Intents.default()

# Bot setup
bot = commands.Bot(command_prefix="!", intents=intents)

# -------- Events -------- #
@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}")


# -------- Startup -------- #
async def main():
    # Load all cogs
    for ext in ["ip", "status", "announce"]:
        try:
            await bot.load_extension(ext)
            print(f"📂 Loaded extension: {ext}")
        except Exception as e:
            print(f"❌ Failed to load extension {ext}: {e}")

    # Sync commands AFTER loading cogs
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"✅ Synced {len(synced)} command(s) to guild {GUILD_ID}")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

    # Start bot
    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
