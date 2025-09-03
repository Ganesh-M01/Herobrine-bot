from discord.ext import commands
from discord import app_commands, Interaction, Embed, File, Color, AllowedMentions

# ---- EDIT THESE VALUES ----
JAVA_ADDRESS = "play.ogsmp.me:25575"
BEDROCK_IP = "play.ogsmp.me"
BEDROCK_PORT = 25575
BANNER_PATH = "./assets/banner.gif"

ADMIN_ROLE_ID = 1335986334673932378
MOD_ROLE_ID = 1335986334673932378
SMP_ROLE_ID = 1336559018591653889   # replace with real ID
MINECRAFT_ROLE_ID = 1303738832683925524   # replace with real ID
# ---------------------------

class IP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ip", description="Get the server IP and port for Java & Bedrock")
    @app_commands.checks.has_any_role(ADMIN_ROLE_ID, MOD_ROLE_ID)
    async def ip(self, interaction: Interaction):
        embed = Embed(
            title="🌐 Here is the IP and Port",
            color=Color.green()
        )
        embed.add_field(name="💻 For Java", value=f"```{JAVA_ADDRESS}```", inline=False)
        embed.add_field(
            name="📱 For Bedrock",
            value=f"**IP:** ```{BEDROCK_IP}```\n**Port:** ```{BEDROCK_PORT}```",
            inline=False
        )

        try:
            file = File(BANNER_PATH, filename="banner.gif")
            embed.set_image(url="attachment://banner.gif")
        except Exception as e:
            print(f"Banner file error: {e}")
            file = None

        # Explicit role mentions
        content = f"<@&{SMP_ROLE_ID}> <@&{MINECRAFT_ROLE_ID}>"

        await interaction.response.send_message(
            content=content,
            embed=embed,
            file=file if file else None,
            allowed_mentions=AllowedMentions(roles=True)  # ✅ allow role pings
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(IP(bot))
