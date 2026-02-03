import discord
import time
import datetime
from discord import app_commands
from discord.ext import commands
from utils import parsing

start_time = time.time()

class Uptime(commands.Cog):
    """Slash command for bot uptime"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="uptime", description="Show how long the bot has been online")
    async def uptime(self, interaction: discord.Interaction):
        # Restrict channels
        allowed_channels = parsing.parse_json('config.json')['command_channels']['uptime']
        if interaction.channel.name not in allowed_channels:
            await interaction.response.send_message(
                "You cannot use this command in this channel!", ephemeral=True
            )
            return

        current_time = time.time()
        difference = int(round(current_time - start_time))
        uptime_text = str(datetime.timedelta(seconds=difference))

        embed = discord.Embed(colour=0xFF0000)
        embed.add_field(name="Uptime", value=uptime_text)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Uptime(bot))
