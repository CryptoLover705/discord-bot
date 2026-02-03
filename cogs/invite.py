import discord
from discord import app_commands
from discord.ext import commands
from utils import parsing


class Invite(commands.Cog):
    """Slash command to get the bot's invite link"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="invite", description="Get the bot's invite link")
    async def invite(self, interaction: discord.Interaction):
        # Optional: restrict to allowed channels
        channel_name = interaction.channel.name
        allowed_channels = parsing.parse_json('config.json')['command_channels'].get("invite", [])
        if allowed_channels and channel_name not in allowed_channels:
            await interaction.response.send_message(
                "This command cannot be used in this channel.", ephemeral=True
            )
            return

        invite_url = f"https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&permissions=2147862624&scope=bot%20applications.commands"
        await interaction.response.send_message(f":tada: {invite_url}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Invite(bot))
