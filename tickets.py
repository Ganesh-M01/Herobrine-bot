"""
tickets.py — Ticket system cog for Herobrine-Bot

Features:
  • Panel with a dropdown of ticket topics (admin configurable)
  • Auto-creates a private ticket channel in a configured category
  • Sends the "New ticket #N" info embed (pinned) with Claim / Close buttons
  • Claim ticket (staff assigns themselves)
  • Add / remove a user from a ticket
  • Transcript generation on close, posted to a log channel
  • Fully persistent (buttons/select survive bot restarts)
  • Per-guild JSON config, no database required

Slash commands (all guild-scoped, most require Manage Server):
  /ticket-setup        category / log_channel / support_role
  /ticket-topic-add    name
  /ticket-topic-remove name
  /ticket-panel        [channel] [title] [description]
  /ticket-add          member   (run inside a ticket channel)
  /ticket-remove       member   (run inside a ticket channel)
  /ticket-close                 (run inside a ticket channel; same as the button)
"""

import asyncio
import io
import json
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticket_data.json")
DATA_LOCK = asyncio.Lock()

DEFAULT_GUILD_CONFIG = {
    "category_id": None,
    "log_channel_id": None,
    "support_role_id": None,
    "topics": ["General Support"],
    "ticket_counter": 0,
}

ACCENT_COLOR = discord.Color.from_str("#57F287")
FOOTER_TEXT = "🔷 Herobrine Ticket System"


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"guilds": {}, "tickets": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("guilds", {})
            data.setdefault("tickets", {})
            return data
    except (json.JSONDecodeError, OSError):
        return {"guilds": {}, "tickets": {}}


def _save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


class TicketStore:
    """JSON-backed store for guild config + open tickets."""

    def __init__(self):
        self.data = _load_data()

    async def save(self) -> None:
        async with DATA_LOCK:
            _save_data(self.data)

    def get_guild_config(self, guild_id: int) -> dict:
        gid = str(guild_id)
        if gid not in self.data["guilds"]:
            self.data["guilds"][gid] = dict(DEFAULT_GUILD_CONFIG)
            self.data["guilds"][gid]["topics"] = list(DEFAULT_GUILD_CONFIG["topics"])
        return self.data["guilds"][gid]

    def next_ticket_number(self, guild_id: int) -> int:
        cfg = self.get_guild_config(guild_id)
        cfg["ticket_counter"] += 1
        return cfg["ticket_counter"]

    def add_ticket(self, channel_id: int, info: dict) -> None:
        self.data["tickets"][str(channel_id)] = info

    def get_ticket(self, channel_id: int):
        return self.data["tickets"].get(str(channel_id))

    def remove_ticket(self, channel_id: int) -> None:
        self.data["tickets"].pop(str(channel_id), None)

    def find_open_ticket(self, guild_id: int, user_id: int):
        for cid, t in self.data["tickets"].items():
            if t["guild_id"] == guild_id and t["user_id"] == user_id:
                return int(cid), t
        return None, None


store = TicketStore()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_staff(member: discord.Member, cfg: dict) -> bool:
    if member.guild_permissions.manage_guild or member.guild_permissions.administrator:
        return True
    role_id = cfg.get("support_role_id")
    if role_id and any(r.id == role_id for r in member.roles):
        return True
    return False


async def generate_transcript(channel: discord.TextChannel) -> discord.File:
    lines = [f"Transcript for #{channel.name} — generated {datetime.now(timezone.utc).isoformat()}", "=" * 60]
    async for msg in channel.history(limit=None, oldest_first=True):
        ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        content = msg.content or ""
        if msg.attachments:
            content += " " + " ".join(a.url for a in msg.attachments)
        lines.append(f"[{ts}] {msg.author} ({msg.author.id}): {content}")
    buf = io.BytesIO("\n".join(lines).encode("utf-8"))
    return discord.File(buf, filename=f"{channel.name}-transcript.txt")


def build_ticket_embed(number: int, user: discord.abc.User, topic: str, claimed_by: discord.abc.User | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"📥 New ticket #{number}",
        color=ACCENT_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="👤 User", value=user.mention, inline=True)
    embed.add_field(name="🎫 Ticket-Topic", value=topic, inline=True)
    embed.add_field(
        name="ℹ️ Information",
        value="Your issue got solved? Click the button below. You can always find this message pinned.",
        inline=False,
    )
    if claimed_by:
        embed.add_field(name="🙋 Claimed by", value=claimed_by.mention, inline=False)
    embed.set_footer(text=FOOTER_TEXT)
    return embed


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class TicketPanelView(discord.ui.View):
    """Persistent view holding the topic-select dropdown."""

    def __init__(self, topics: list[str] | None = None):
        super().__init__(timeout=None)
        options = [discord.SelectOption(label=t[:100]) for t in (topics or [])] or [discord.SelectOption(label="placeholder")]
        select = discord.ui.Select(
            placeholder="🎫 Select a ticket topic...",
            options=options,
            custom_id="tickets:panel_select",
            min_values=1,
            max_values=1,
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        topic = interaction.data["values"][0]
        guild = interaction.guild
        cfg = store.get_guild_config(guild.id)

        existing_id, _ = store.find_open_ticket(guild.id, interaction.user.id)
        if existing_id:
            await interaction.response.send_message(
                f"⚠️ You already have an open ticket: <#{existing_id}>", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        category = guild.get_channel(cfg["category_id"]) if cfg["category_id"] else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True),
        }
        role_id = cfg.get("support_role_id")
        if role_id:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        number = store.next_ticket_number(guild.id)
        channel_name = f"ticket-{number:04d}"

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites,
                reason=f"Ticket opened by {interaction.user} ({interaction.user.id})",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to create channels here. Ask an admin to check my role permissions.",
                ephemeral=True,
            )
            return

        store.add_ticket(
            channel.id,
            {
                "guild_id": guild.id,
                "user_id": interaction.user.id,
                "topic": topic,
                "number": number,
                "claimed_by": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        await store.save()

        embed = build_ticket_embed(number, interaction.user, topic)
        msg = await channel.send(content=f"{interaction.user.mention}", embed=embed, view=TicketControlView())
        try:
            await msg.pin()
        except discord.HTTPException:
            pass

        await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)


class TicketControlView(discord.ui.View):
    """Persistent view attached to every ticket message (Claim / Close buttons)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim Ticket", emoji="🙋", style=discord.ButtonStyle.blurple, custom_id="tickets:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = store.get_ticket(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("This channel isn't a tracked ticket.", ephemeral=True)
            return
        cfg = store.get_guild_config(interaction.guild.id)
        if not is_staff(interaction.user, cfg):
            await interaction.response.send_message("Only support staff can claim tickets.", ephemeral=True)
            return
        if ticket.get("claimed_by"):
            claimer = interaction.guild.get_member(ticket["claimed_by"])
            await interaction.response.send_message(
                f"This ticket is already claimed by {claimer.mention if claimer else 'someone'}.", ephemeral=True
            )
            return

        ticket["claimed_by"] = interaction.user.id
        await store.save()

        opener = interaction.guild.get_member(ticket["user_id"])
        embed = build_ticket_embed(ticket["number"], opener or interaction.user, ticket["topic"], claimed_by=interaction.user)
        await interaction.response.edit_message(embed=embed)
        await interaction.followup.send(f"🙋 Claimed by {interaction.user.mention}", ephemeral=False)

    @discord.ui.button(label="Close Ticket", emoji="🔒", style=discord.ButtonStyle.red, custom_id="tickets:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = store.get_ticket(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("This channel isn't a tracked ticket.", ephemeral=True)
            return
        cfg = store.get_guild_config(interaction.guild.id)
        if not (is_staff(interaction.user, cfg) or interaction.user.id == ticket["user_id"]):
            await interaction.response.send_message("You don't have permission to close this ticket.", ephemeral=True)
            return

        await interaction.response.send_message(
            "Are you sure you want to close this ticket?", view=ConfirmCloseView(), ephemeral=True
        )


class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Confirm Close", style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="🔒 Closing ticket...", view=None)
        await close_ticket_channel(interaction.channel, interaction.user)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None)


async def close_ticket_channel(channel: discord.TextChannel, closer: discord.abc.User):
    ticket = store.get_ticket(channel.id)
    cfg = store.get_guild_config(channel.guild.id)

    transcript_file = await generate_transcript(channel)

    log_channel = channel.guild.get_channel(cfg["log_channel_id"]) if cfg.get("log_channel_id") else None
    if log_channel:
        opener = channel.guild.get_member(ticket["user_id"]) if ticket else None
        summary = discord.Embed(
            title=f"🔒 Ticket #{ticket['number'] if ticket else '?'} closed",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )
        summary.add_field(name="Opened by", value=(opener.mention if opener else "Unknown"), inline=True)
        summary.add_field(name="Closed by", value=closer.mention, inline=True)
        summary.add_field(name="Topic", value=(ticket["topic"] if ticket else "Unknown"), inline=True)
        try:
            await log_channel.send(embed=summary, file=transcript_file)
        except discord.HTTPException:
            pass

    store.remove_ticket(channel.id)
    await store.save()

    await channel.send("This ticket will be deleted in 5 seconds.")
    await asyncio.sleep(5)
    try:
        await channel.delete(reason=f"Ticket closed by {closer}")
    except discord.HTTPException:
        pass


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Re-register persistent views so buttons/selects work after a restart.
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketControlView())

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You need the **Manage Server** permission to do that.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Something went wrong: {error}", ephemeral=True)
            raise error

    def _require_ticket_channel(self, interaction: discord.Interaction):
        ticket = store.get_ticket(interaction.channel_id)
        if not ticket:
            raise app_commands.AppCommandError("This command can only be used inside a ticket channel.")
        return ticket

    # --- Admin setup ---------------------------------------------------

    @app_commands.command(name="ticket-setup", description="Configure the ticket system for this server.")
    @app_commands.describe(
        category="Category new ticket channels are created in",
        log_channel="Channel where closed-ticket transcripts are logged",
        support_role="Role that can see, claim, and close tickets",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel = None,
        log_channel: discord.TextChannel = None,
        support_role: discord.Role = None,
    ):
        cfg = store.get_guild_config(interaction.guild.id)
        if category:
            cfg["category_id"] = category.id
        if log_channel:
            cfg["log_channel_id"] = log_channel.id
        if support_role:
            cfg["support_role_id"] = support_role.id
        await store.save()

        embed = discord.Embed(title="✅ Ticket system configured", color=ACCENT_COLOR)
        embed.add_field(name="Category", value=(category.mention if category else "*(unchanged)*"), inline=False)
        embed.add_field(name="Log channel", value=(log_channel.mention if log_channel else "*(unchanged)*"), inline=False)
        embed.add_field(name="Support role", value=(support_role.mention if support_role else "*(unchanged)*"), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ticket-topic-add", description="Add a topic to the ticket panel dropdown.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_topic_add(self, interaction: discord.Interaction, name: str):
        cfg = store.get_guild_config(interaction.guild.id)
        if len(cfg["topics"]) >= 25:
            await interaction.response.send_message("❌ Discord allows a maximum of 25 dropdown options.", ephemeral=True)
            return
        if name in cfg["topics"]:
            await interaction.response.send_message("That topic already exists.", ephemeral=True)
            return
        cfg["topics"].append(name)
        await store.save()
        await interaction.response.send_message(f"✅ Added topic **{name}**. Re-run `/ticket-panel` to refresh the dropdown.", ephemeral=True)

    @app_commands.command(name="ticket-topic-remove", description="Remove a topic from the ticket panel dropdown.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_topic_remove(self, interaction: discord.Interaction, name: str):
        cfg = store.get_guild_config(interaction.guild.id)
        if name not in cfg["topics"]:
            await interaction.response.send_message("That topic doesn't exist.", ephemeral=True)
            return
        cfg["topics"].remove(name)
        await store.save()
        await interaction.response.send_message(f"✅ Removed topic **{name}**. Re-run `/ticket-panel` to refresh the dropdown.", ephemeral=True)

    @app_commands.command(name="ticket-panel", description="Post the ticket-opening panel in a channel.")
    @app_commands.describe(channel="Channel to post the panel in (defaults to this channel)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_panel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        cfg = store.get_guild_config(interaction.guild.id)
        target = channel or interaction.channel

        embed = discord.Embed(
            title="🎫 Need help?",
            description="Select a topic below to open a private support ticket.",
            color=ACCENT_COLOR,
        )
        embed.set_footer(text=FOOTER_TEXT)
        await target.send(embed=embed, view=TicketPanelView(cfg["topics"]))
        await interaction.response.send_message(f"✅ Panel posted in {target.mention}.", ephemeral=True)

    # --- Ticket-channel commands ----------------------------------------

    @app_commands.command(name="ticket-add", description="Add a member to the current ticket.")
    async def ticket_add(self, interaction: discord.Interaction, member: discord.Member):
        ticket = store.get_ticket(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("This command only works inside a ticket channel.", ephemeral=True)
            return
        cfg = store.get_guild_config(interaction.guild.id)
        if not is_staff(interaction.user, cfg):
            await interaction.response.send_message("Only support staff can add members to a ticket.", ephemeral=True)
            return
        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(f"✅ Added {member.mention} to the ticket.")

    @app_commands.command(name="ticket-remove", description="Remove a member from the current ticket.")
    async def ticket_remove(self, interaction: discord.Interaction, member: discord.Member):
        ticket = store.get_ticket(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("This command only works inside a ticket channel.", ephemeral=True)
            return
        cfg = store.get_guild_config(interaction.guild.id)
        if not is_staff(interaction.user, cfg):
            await interaction.response.send_message("Only support staff can remove members from a ticket.", ephemeral=True)
            return
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"✅ Removed {member.mention} from the ticket.")

    @app_commands.command(name="ticket-close", description="Close the current ticket.")
    async def ticket_close(self, interaction: discord.Interaction):
        ticket = store.get_ticket(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("This command only works inside a ticket channel.", ephemeral=True)
            return
        cfg = store.get_guild_config(interaction.guild.id)
        if not (is_staff(interaction.user, cfg) or interaction.user.id == ticket["user_id"]):
            await interaction.response.send_message("You don't have permission to close this ticket.", ephemeral=True)
            return
        await interaction.response.send_message("Are you sure you want to close this ticket?", view=ConfirmCloseView(), ephemeral=True)


async def setup(bot: commands.Bot):
    guild_id = int(os.getenv("GUILD_ID", "0"))
    if guild_id:
        # Matches the guild-scoped sync in main.py so these commands
        # actually show up without waiting on a global-sync propagation delay.
        await bot.add_cog(Tickets(bot), guild=discord.Object(id=guild_id))
    else:
        await bot.add_cog(Tickets(bot))