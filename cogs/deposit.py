import discord
from discord import app_commands
from discord.ext import commands
from utils import parsing, mysql_module

mysql = mysql_module.Mysql()


class Deposit(commands.Cog):
    """Slash command for displaying deposit addresses"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="deposit", description="Get your public deposit address for MWC")
    async def deposit(self, interaction: discord.Interaction):
        # Optional: restrict to allowed channels from config
        channel_name = interaction.channel.name
        allowed_channels = parsing.parse_json('config.json')['command_channels'].get("deposit", [])
        if allowed_channels and channel_name not in allowed_channels:
            await interaction.response.send_message(
                "This command cannot be used in this channel.", ephemeral=True
            )
            return

        # Ensure user exists in DB
        snowflake = interaction.user.id
        mysql.check_for_user(snowflake)
        user_address = mysql.get_address(snowflake)

        message = (
            f"{interaction.user.mention}'s Deposit Address: `{user_address}`\n\n"
            "Remember to use `/balance` to check your balance and not an explorer. "
            "The address balance and your actual balance are not always the same!\n\n"
            ":warning: DISCLAIMER: This is BETA software! Do not send large amounts of MWC! "
            "The developers are not responsible for any lost funds! :warning:"
        )

        await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Deposit(bot))
