import os
import json
import discord
from discord.ext import commands

# ── Config (set in your .env) ───────────────────────────────────
# INVITE_LOG_CHANNEL_ID  -> Discord channel ID where join/leave logs are posted
# IGNORE_BOTS_INVITE_LOG -> "true"/"false" (default true) - skip logging bot joins

LOG_CHANNEL_ID = int(os.getenv("INVITE_LOG_CHANNEL_ID", "0"))
IGNORE_BOTS = os.getenv("IGNORE_BOTS_INVITE_LOG", "true").lower() != "false"

DATA_FILE = "invite_tracker_data.json"

GREEN = 0x57F287
RED = 0xED4245


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


class InviteTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = _load_data()
        # in-memory cache: {guild_id: {code: {"uses":.., "inviter_id":.., "max_uses":.., "channel_id":.., "created_at":..}}}
        self.invite_cache: dict[int, dict[str, dict]] = {}
        self.vanity_cache: dict[int, int] = {}

        if not LOG_CHANNEL_ID:
            print("⚠️  Invite tracker: INVITE_LOG_CHANNEL_ID not set in .env — logging disabled")

    # ── helpers ──────────────────────────────────────────────

    def _guild_data(self, guild_id: int) -> dict:
        gid = str(guild_id)
        if gid not in self.data["guilds"]:
            self.data["guilds"][gid] = {"members": {}}
        return self.data["guilds"][gid]

    async def _cache_guild_invites(self, guild: discord.Guild):
        try:
            invites = await guild.invites()
        except discord.Forbidden:
            print(f"❌ Missing 'Manage Server' permission to fetch invites in {guild.name}")
            return
        except discord.HTTPException as e:
            print(f"❌ Failed to fetch invites for {guild.name}: {e}")
            return

        self.invite_cache[guild.id] = {
            inv.code: {
                "uses": inv.uses or 0,
                "inviter_id": inv.inviter.id if inv.inviter else None,
                "max_uses": inv.max_uses,
                "channel_id": inv.channel.id if inv.channel else None,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
            }
            for inv in invites
        }

        if "VANITY_URL" in guild.features:
            try:
                vanity = await guild.vanity_invite()
                self.vanity_cache[guild.id] = vanity.uses or 0
            except (discord.Forbidden, discord.HTTPException):
                pass

    def _inviter_stats(self, guild: discord.Guild, inviter_id: int) -> tuple[int, int]:
        """Returns (active, total) invited members for this inviter."""
        gdata = self._guild_data(guild.id)
        total = 0
        active = 0
        for uid_str, m in gdata["members"].items():
            if m.get("invited_by") == inviter_id:
                total += 1
                if guild.get_member(int(uid_str)) is not None:
                    active += 1
        return active, total

    async def _find_used_invite(self, guild: discord.Guild):
        """Compares cached invites to current invites; returns (code, info_dict) of the one used, or (None, None)."""
        before = self.invite_cache.get(guild.id, {})

        try:
            after_invites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return None, None

        after = {
            inv.code: {
                "uses": inv.uses or 0,
                "inviter_id": inv.inviter.id if inv.inviter else None,
                "max_uses": inv.max_uses,
                "channel_id": inv.channel.id if inv.channel else None,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
            }
            for inv in after_invites
        }

        used_code, used_info = None, None
        for code, info in after.items():
            prev_uses = before.get(code, {}).get("uses", 0)
            if info["uses"] > prev_uses:
                used_code, used_info = code, info
                break

        # Check vanity invite too
        if used_code is None and "VANITY_URL" in guild.features:
            try:
                vanity = await guild.vanity_invite()
                prev_vanity = self.vanity_cache.get(guild.id, 0)
                if (vanity.uses or 0) > prev_vanity:
                    used_code = vanity.code
                    used_info = {
                        "uses": vanity.uses or 0,
                        "inviter_id": None,
                        "max_uses": None,
                        "channel_id": None,
                        "created_at": None,
                        "vanity": True,
                    }
                self.vanity_cache[guild.id] = vanity.uses or 0
            except (discord.Forbidden, discord.HTTPException):
                pass

        # Refresh cache for next time
        self.invite_cache[guild.id] = after
        return used_code, used_info

    # ── event listeners ──────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self._cache_guild_invites(guild)
        print(f"📨 Invite tracker cached invites for {len(self.bot.guilds)} guild(s)")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self._cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        cache = self.invite_cache.setdefault(invite.guild.id, {})
        cache[invite.code] = {
            "uses": invite.uses or 0,
            "inviter_id": invite.inviter.id if invite.inviter else None,
            "max_uses": invite.max_uses,
            "channel_id": invite.channel.id if invite.channel else None,
            "created_at": invite.created_at.isoformat() if invite.created_at else None,
        }

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        cache = self.invite_cache.get(invite.guild.id, {})
        cache.pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if IGNORE_BOTS and member.bot:
            return

        guild = member.guild
        used_code, used_info = await self._find_used_invite(guild)

        gdata = self._guild_data(guild.id)
        uid = str(member.id)
        existing = gdata["members"].get(uid, {"join_history": []})
        times_before = len(existing.get("join_history", []))
        last_joined = existing["join_history"][-1] if times_before else None

        now_iso = discord.utils.utcnow().isoformat()
        existing["join_history"].append(now_iso)

        if used_code and used_info:
            invite_type = "Vanity URL" if used_info.get("vanity") else "Normal Invite"
            existing.update({
                "invited_by": used_info.get("inviter_id"),
                "invite_code": used_code,
                "invite_type": invite_type,
            })
        else:
            existing.update({
                "invited_by": None,
                "invite_code": None,
                "invite_type": "Unknown",
            })

        gdata["members"][uid] = existing
        _save_data(self.data)

        await self._post_join_log(member, used_code, used_info, times_before, last_joined)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if IGNORE_BOTS and member.bot:
            return

        guild = member.guild
        gdata = self._guild_data(guild.id)
        info = gdata["members"].get(str(member.id))

        await self._post_leave_log(member, info)

    # ── embed builders ───────────────────────────────────────

    async def _log_channel(self, guild: discord.Guild):
        if not LOG_CHANNEL_ID:
            return None
        channel = guild.get_channel(LOG_CHANNEL_ID) or self.bot.get_channel(LOG_CHANNEL_ID)
        return channel

    async def _post_join_log(self, member: discord.Member, code, info, times_before, last_joined):
        channel = await self._log_channel(member.guild)
        if channel is None:
            return

        embed = discord.Embed(title="📥 New member joined", color=GREEN, timestamp=discord.utils.utcnow())

        if times_before:
            last_dt = discord.utils.parse_time(last_joined) if last_joined else None
            ts = f"<t:{int(last_dt.timestamp())}:F>" if last_dt else "an earlier time"
            embed.description = (
                f"{member.mention} joined this server {times_before} time"
                f"{'s' if times_before != 1 else ''} before this, the last one was {ts}."
            )

        embed.add_field(name="Member", value=f"{member.mention} (`{member.id}`)", inline=True)

        if code and info:
            invite_type = "Vanity URL" if info.get("vanity") else "Normal Invite"
            embed.add_field(name="Invite-Type", value=invite_type, inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)

            invite_lines = [f"**Invite-Code:** [{code}](https://discord.gg/{code})"]
            if info.get("channel_id"):
                invite_lines.append(f"**Channel:** <#{info['channel_id']}>")
            if info.get("created_at"):
                created_dt = discord.utils.parse_time(info["created_at"])
                if created_dt:
                    invite_lines.append(f"**Created at:** <t:{int(created_dt.timestamp())}:F>")

            inviter_id = info.get("inviter_id")
            if inviter_id:
                active, total = self._inviter_stats(member.guild, inviter_id)
                invite_lines.append(f"**Invited by:** <@{inviter_id}> ({active}/{total} active invites)")

            invite_lines.append(f"**Uses:** {info.get('uses', 0)}")
            embed.add_field(name="Invite", value="\n".join(invite_lines), inline=False)
        else:
            embed.add_field(
                name="Invite-Type",
                value="Sorry, but I couldn't determine the invite this person used",
                inline=True,
            )

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Powered by {self.bot.user.name}", icon_url=self.bot.user.display_avatar.url)

        await channel.send(embed=embed)

    async def _post_leave_log(self, member: discord.Member, info: dict | None):
        channel = await self._log_channel(member.guild)
        if channel is None:
            return

        embed = discord.Embed(title="📤 Member left", color=RED, timestamp=discord.utils.utcnow())
        embed.add_field(name="Member", value=f"{member} (`{member.id}`)", inline=True)

        if info and info.get("invite_code"):
            embed.add_field(name="Invite-Type", value=info.get("invite_type", "Unknown"), inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)

            code = info["invite_code"]
            invite_lines = [f"**Invite-Code:** [{code}](https://discord.gg/{code})"]

            inviter_id = info.get("invited_by")
            if inviter_id:
                active, total = self._inviter_stats(member.guild, inviter_id)
                invite_lines.append(f"**Invited by:** <@{inviter_id}> ({active}/{total} active invites)")

            embed.add_field(name="Invite", value="\n".join(invite_lines), inline=False)
        else:
            embed.add_field(
                name="Invite-Type",
                value="Sorry, but I couldn't determine the invite this person used",
                inline=True,
            )

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Powered by {self.bot.user.name}", icon_url=self.bot.user.display_avatar.url)

        await channel.send(embed=embed)

    # ── bonus command ────────────────────────────────────────

    @commands.command(name="invites")
    async def invites(self, ctx: commands.Context, member: discord.Member = None):
        """Check how many active/total members someone has invited."""
        target = member or ctx.author
        active, total = self._inviter_stats(ctx.guild, target.id)
        await ctx.send(f"📨 {target.mention} has **{active}/{total}** active invites.")


async def setup(bot: commands.Bot):
    await bot.add_cog(InviteTracker(bot))