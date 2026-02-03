import discord
from discord.ext import commands
from discord import app_commands

from utils import output, parsing, mysql_module, g
import os
import traceback
import database

# =========================
# CONFIG
# =========================
config = parsing.parse_json("config.json")

# =========================
# INTENTS (REQUIRED)
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = False
intents.messages = False  # not needed for slash commands

# =========================
# BOT INITIALIZATION
# =========================
class MinerBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=None,  # slash commands only
            description=config["description"],
            intents=intents
        )

    async def setup_hook(self):
        """Runs before the bot connects to Discord"""
        output.info(f"Loading {len(g.startup_extensions)} extension(s)...")

        for extension in g.startup_extensions:
            try:
                await self.load_extension(f"cogs.{extension}")
                g.loaded_extensions.append(extension)
            except Exception:
                output.error(
                    f"Failed to load extension {extension}\n{traceback.format_exc()}"
                )

        await self.tree.sync()
        output.success(
            f"Successfully loaded: {', '.join(g.loaded_extensions)}"
        )
        output.success("Slash commands synced successfully.")

bot = MinerBot()
Mysql = mysql_module.Mysql()

# =========================
# CLEAN LOG FILE
# =========================
try:
    os.remove("log.txt")
except FileNotFoundError:
    pass

if "__pycache__" in g.startup_extensions:
    g.startup_extensions.remove("__pycache__")
g.startup_extensions = [ext.replace(".py", "") for ext in g.startup_extensions]

# =========================
# EVENTS
# =========================
@bot.event
async def on_ready():
    output.success(f"Logged in as {bot.user} ({bot.user.id})")
    output.info(
        f"Invite URL: https://discord.com/oauth2/authorize"
        f"?client_id={bot.user.id}&permissions=0&scope=bot%20applications.commands"
    )

@bot.event
async def on_guild_join(guild: discord.Guild):
    output.info(f"Added to {guild.name}")
    Mysql.add_server(guild)
    for channel in guild.channels:
        Mysql.add_channel(channel)

@bot.event
async def on_guild_remove(guild: discord.Guild):
    Mysql.remove_server(guild)
    output.info(f"Removed from {guild.name}")

@bot.event
async def on_guild_channel_create(channel):
    if isinstance(channel, discord.DMChannel):
        return
    Mysql.add_channel(channel)
    output.info(f"Channel {channel.name} added to {channel.guild.name}")

@bot.event
async def on_guild_channel_delete(channel):
    Mysql.remove_channel(channel)
    output.info(f"Channel {channel.name} deleted from {channel.guild.name}")

# =========================
# GLOBAL SLASH ERROR HANDLER
# =========================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    output.error(f"Slash command error: {error}")

    if interaction.response.is_done():
        await interaction.followup.send(
            "❌ An unexpected error occurred. Please try again later.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "❌ An unexpected error occurred. Please try again later.",
            ephemeral=True
        )

# =========================
# STARTUP
# =========================
database.run()
bot.run(config["discord"]["token"])
