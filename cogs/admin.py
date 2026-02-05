import discord
import os
from discord import app_commands
from discord.ext import commands
from utils import output, parsing, mysql_module, g

mysql = mysql_module.Mysql()
config = parsing.parse_json('config.json')["logging"]

# ---------------------- OWNER CHECK ----------------------
def is_owner():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id != 1157581316175437884:  # Replace with your Discord ID
            raise app_commands.CheckFailure("You are not allowed to use this command.")
        return True
    return app_commands.check(predicate)


class Server(commands.Cog):
    """Admin commands for the bot"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ----------------- Shutdown / Restart -----------------
    @app_commands.command(name="shutdown", description="Shut down the bot [ADMIN ONLY]")
    @is_owner()
    async def shutdown(self, interaction: discord.Interaction):
        author = str(interaction.user)
        try:
            await interaction.response.send_message("Shutting down...")
            output.info(f"{author} has shut down the bot...")
            await self.bot.close()
        except Exception as e:
            output.error(f"{author} attempted shutdown but got: {type(e).__name__}: {e}")

    @app_commands.command(name="restart", description="Restart the bot [ADMIN ONLY]")
    @is_owner()
    async def restart(self, interaction: discord.Interaction):
        author = str(interaction.user)
        try:
            await interaction.response.send_message("Restarting...")
            output.info(f"{author} has restarted the bot...")
            await self.bot.close()
            os.system('sh restart.sh')
        except Exception as e:
            output.error(f"{author} attempted restart but got: {type(e).__name__}: {e}")

    # ----------------- Load / Unload / Loaded -----------------
    @app_commands.command(name="load", description="Load a cog [ADMIN ONLY]")
    @is_owner()
    @app_commands.describe(module="Name of the module to load")
    async def load(self, interaction: discord.Interaction, module: str):
        module = module.strip()
        author = str(interaction.user)
        try:
            self.bot.load_extension(f"cogs.{module}")
            g.loaded_extensions.append(module)
            output.info(f"{author} loaded module: {module}")
            await interaction.response.send_message(f"Successfully loaded `{module}.py`")
        except Exception as e:
            output.error(f"{author} failed loading {module}: {type(e).__name__}: {e}")
            await interaction.response.send_message(f"Failed to load `{module}`\n-> {type(e).__name__}: {e}")

    @app_commands.command(name="unload", description="Unload a cog [ADMIN ONLY]")
    @is_owner()
    @app_commands.describe(module="Name of the module to unload")
    async def unload(self, interaction: discord.Interaction, module: str):
        module = module.strip()
        author = str(interaction.user)
        try:
            self.bot.unload_extension(f"cogs.{module}")
            g.loaded_extensions.remove(module)
            output.info(f"{author} unloaded module: {module}")
            await interaction.response.send_message(f"Successfully unloaded `{module}.py`")
        except Exception as e:
            output.error(f"{author} failed unloading {module}: {type(e).__name__}: {e}")
            await interaction.response.send_message(f"Failed to unload `{module}`\n-> {type(e).__name__}: {e}")

    @app_commands.command(name="loaded", description="List all loaded cogs [ADMIN ONLY]")
    @is_owner()
    async def loaded(self, interaction: discord.Interaction):
        modules = "\n".join(g.loaded_extensions) or "No extensions loaded."
        await interaction.response.send_message(f"Currently loaded extensions:\n```{modules}```")

    # ----------------- Soak -----------------
    @app_commands.command(
        name="allowsoak", 
        description="Enable/disable the soak feature [ADMIN ONLY]"
    )
    @is_owner()
    @app_commands.describe(enable="Enable or disable soak (True/False)")
    async def allowsoak(self, interaction: discord.Interaction, enable: bool):
        guild_id = interaction.guild.id  # <--- only the numeric ID
        mysql.set_soak(guild_id, int(enable))
        msg = "Soaking is now enabled! ✅" if enable else "Soaking is now disabled! ❌"
        await interaction.response.send_message(msg)

    # ----------------- Git Pull -----------------
    @app_commands.command(name="pull", description="Update the bot from git [ADMIN ONLY]")
    @is_owner()
    async def pull(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pulling...")
        try:
            returned = os.system("git pull")
            await interaction.followup.send(f":+1: Returned code {returned}")
        except Exception as e:
            output.error(f"{interaction.user} attempted git pull but got: {type(e).__name__}: {e}")

    # ----------------- Log -----------------
    @app_commands.command(name="log", description="Display the last few lines of the log [ADMIN ONLY]")
    @is_owner()
    @app_commands.describe(num_lines="Number of lines to display")
    async def log(self, interaction: discord.Interaction, num_lines: int = 5):
        with open(config["file"], "r") as f:
            text = f.readlines()
        num_lines = max(1, min(num_lines, len(text)))
        last_lines = "".join(text[-num_lines:])
        await interaction.response.send_message(f"```{last_lines}```")


async def setup(bot: commands.Bot):
    await bot.add_cog(Server(bot))
