from discord.ext import commands
from discord import app_commands, Interaction, Embed, File, Color

# ---- EDIT THESE THREE VALUES ----
JAVA_ADDRESS = "paid.taitcloud.xyz:25575"
BEDROCK_IP = "paid.taitcloud.xyz"
BEDROCK_PORT = 25575
BANNER_PATH = "./assets/banner.gif"
ADMIN_ROLE_ID = 1335986334673932378
MOD_ROLE_ID = 1335986334673932378
# ---------------------------------

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

        # Attach banner.gif to embed
        file = File(BANNER_PATH, filename="banner.gif")
        embed.set_image(url="attachment://banner.gif")

        # Add mentions in the message content
        content = "<@&1272255683516960850> <@&1303738832683925524>"

        await interaction.response.send_message(content=content, embed=embed, file=file)

async def setup(bot: commands.Bot):
    await bot.add_cog(IP(bot))
