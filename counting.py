import os
import json
import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

# ── Config (set in your .env) ───────────────────────────────────
# COUNTING_CHANNEL_ID -> the channel ID where counting happens

COUNTING_CHANNEL_ID = int(os.getenv("COUNTING_CHANNEL_ID", "0"))

DATA_FILE = "counting_data.json"
COOLDOWN = timedelta(hours=12)


def _load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"guilds": {}}


def _save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


class Counting(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = _load_data()

        if not COUNTING_CHANNEL_ID:
            print("⚠️  Counting game: COUNTING_CHANNEL_ID not set in .env — disabled")

    def _guild_data(self, guild_id: int) -> dict:
        gid = str(guild_id)
        if gid not in self.data["guilds"]:
            self.data["guilds"][gid] = {
                "current_count": 0,
                "last_counter_id": None,
                "best_count": 0,
                "user_last_count": {},  # user_id -> iso timestamp of their last SUCCESSFUL count
            }
        return self.data["guilds"][gid]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not COUNTING_CHANNEL_ID or message.author.bot:
            return
        if message.channel.id != COUNTING_CHANNEL_ID:
            return

        content = message.content.strip()
        if not content.isdigit():
            return  # not a counting attempt, leave it alone

        gdata = self._guild_data(message.guild.id)
        expected = gdata["current_count"] + 1
        submitted = int(content)
        uid = str(message.author.id)
        now = datetime.now(timezone.utc)

        # Wrong number entirely -> just react, no state change
        if submitted != expected:
            await message.add_reaction("❌")
            return

        # Correct number, but check cooldown
        last_str = gdata["user_last_count"].get(uid)
        if last_str:
            last_time = datetime.fromisoformat(last_str)
            elapsed = now - last_time
            if elapsed < COOLDOWN:
                await message.add_reaction("❌")
                remaining = COOLDOWN - elapsed
                hrs = int(remaining.total_seconds() // 3600)
                mins = int((remaining.total_seconds() % 3600) // 60)
                warning = await message.reply(
                    f"⏳ You need to wait **{hrs}h {mins}m** before counting again.",
                    mention_author=False,
                )
                await asyncio.sleep(6)
                try:
                    await warning.delete()
                except discord.HTTPException:
                    pass
                return

        # Valid count!
        gdata["current_count"] = submitted
        gdata["last_counter_id"] = message.author.id
        gdata["user_last_count"][uid] = now.isoformat()
        await message.add_reaction("✅")

        # New record?
        if submitted > gdata["best_count"]:
            previous_best = gdata["best_count"]
            gdata["best_count"] = submitted
            _save_data(self.data)

            embed = discord.Embed(
                title="🎉 New Counting Record!",
                description=(
                    f"{message.author.mention} just pushed the count to **{submitted}**, "
                    f"beating the previous record of **{previous_best}**!"
                ),
                color=discord.Color.gold(),
            )
            await message.channel.send(embed=embed)
        else:
            _save_data(self.data)

    @commands.command(name="countinfo")
    async def countinfo(self, ctx: commands.Context):
        """Show the current count and all-time record."""
        gdata = self._guild_data(ctx.guild.id)
        embed = discord.Embed(title="🔢 Counting Game", color=discord.Color.blurple())
        embed.add_field(name="Current Count", value=str(gdata["current_count"]), inline=True)
        embed.add_field(name="All-Time Record", value=str(gdata["best_count"]), inline=True)
        if gdata["last_counter_id"]:
            embed.add_field(name="Last Counted By", value=f"<@{gdata['last_counter_id']}>", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="setcount")
    @commands.has_permissions(administrator=True)
    async def setcount(self, ctx: commands.Context, number: int):
        """Manually set the current count (admin only, e.g. to recover from an issue)."""
        gdata = self._guild_data(ctx.guild.id)
        gdata["current_count"] = number
        gdata["last_counter_id"] = None
        _save_data(self.data)
        await ctx.send(f"✅ Count manually set to **{number}**. Next number should be **{number + 1}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Counting(bot))