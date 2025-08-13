# ip.py
from discord.ext import commands
from discord import app_commands, Interaction, Embed, File

# ---- EDIT THESE THREE VALUES ----
JAVA_ADDRESS   = "paid.taitcloud.xyz:25575"  # Java address (domain:port)
BEDROCK_IP     = "paid.taitcloud.xyz"        # Bedrock IP
BEDROCK_PORT   = 25575                     # Bedrock port
BANNER_PATH    = "./assets/banner.gif"              # or "assets/banner.gif" if you put it in /assets
# ---------------------------------

class IP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ip", description="Show the server IP (Java & Bedrock)")
    async def ip(self, interaction: Interaction):
        embed = Embed(title="HERE IS THE IP AND PORT")
        embed.add_field(name="FOR JAVA", value=f"```{JAVA_ADDRESS}```", inline=False)
        embed.add_field(name="FOR BEDROCK\nIP", value=f"```{BEDROCK_IP}```", inline=False)
        embed.add_field(name="PORT", value=f"```{BEDROCK_PORT}```", inline=False)

        # Attach the banner and display it in the embed
        file = File(BANNER_PATH, filename="banner.gif")
        embed.set_image(url="attachment://banner.gif")

        await interaction.response.send_message(embed=embed, file=file)

async def setup(bot: commands.Bot):
    await bot.add_cog(IP(bot))
