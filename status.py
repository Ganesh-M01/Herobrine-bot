from discord.ext import commands
from discord import app_commands, Interaction, Embed
from mcstatus import JavaServer

class Status(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="status", description="Check Minecraft server status")
    async def status(self, interaction: Interaction):
        try:
            # Replace with your actual IP and port
            server = JavaServer.lookup("like-titten.gl.joinmc.link:43700")
            status = server.status()

            embed = Embed(title="🟢 Server is Online", color=0x00ff00)
            embed.add_field(name="IP", value="like-titten.gl.joinmc.link:43700", inline=False)
            embed.add_field(name="Version", value="Paper 1.21.7", inline=False)
            embed.add_field(name="Players", value=f"{status.players.online}/{status.players.max}", inline=False)

            if status.players.sample:
                names = "\n".join(p.name for p in status.players.sample)
                embed.add_field(name="Online Players", value=names, inline=False)

            await interaction.response.send_message(embed=embed)

        except Exception:
            embed = Embed(title="🔴 Server under Maintenance", description="Just you wait! Server will be back online ASAP 😉", color=0xff0000)
            await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Status(bot))
