import discord
from discord import app_commands
from discord.ext import commands
from utils import checks, parsing


class Help(commands.Cog):
    """Slash command for displaying a list of bot commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Display a list of commands")
    async def help(self, interaction: discord.Interaction):
        # Optional: restrict to allowed channels
        channel_name = interaction.channel.name
        allowed_channels = parsing.parse_json('config.json')['command_channels'].get("help", [])
        if allowed_channels and channel_name not in allowed_channels:
            await interaction.response.send_message(
                "This command cannot be used in this channel.", ephemeral=True
            )
            return

        desc = ""
        for command in self.bot.tree.get_commands():  # app commands
            # Skip hidden commands unless user is owner
            if getattr(command, "hidden", False) and not checks.is_owner(interaction.user):
                continue

            # Build description with aliases if any
            aliases = getattr(command, "aliases", [])
            if aliases:
                desc += f"/{command.name} - {command.description}\nAliases: {', '.join(aliases)}\n\n"
            else:
                desc += f"/{command.name} - {command.description}\n\n"

        embed = discord.Embed(description=desc)
        embed.set_author(icon_url=self.bot.user.display_avatar.url, name="MWC TipBot Commands")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
