import discord
from discord import app_commands
from discord.ext import commands
from utils import rpc_module, mysql_module, parsing, checks
import aiohttp

rpc = rpc_module.Rpc()
mysql = mysql_module.Mysql()
COINPAPRIKA_ID = "mwc-minersworldcoin"  # CoinPaprika ID

class Tip(commands.Cog):
    """Slash commands for tipping users"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def fetch_price_usd(self) -> float:
        """Fetch the current MWC price in USD from CoinPaprika"""
        url = f"https://api.coinpaprika.com/v1/tickers/{COINPAPRIKA_ID}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return float(data["quotes"]["USD"]["price"])

    @app_commands.command(name="tip", description="Tip another user MWC coins")
    @app_commands.checks.dynamic_check(lambda i: checks.in_server(i))
    async def tip(self, interaction: discord.Interaction, user: discord.Member, amount: float):
        # Restrict channels
        allowed_channels = parsing.parse_json('config.json')['command_channels']['tip']
        if interaction.channel.name not in allowed_channels:
            await interaction.response.send_message(
                "You cannot use this command in this channel!", ephemeral=True
            )
            return

        snowflake = interaction.user.id
        tip_user = user.id

        if snowflake == tip_user:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ You cannot tip yourself!", ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ Tip amount must be greater than 0!", ephemeral=True
            )
            return

        # Ensure users exist
        mysql.check_for_user(snowflake)
        mysql.check_for_user(tip_user)

        balance = mysql.get_balance(snowflake, check_update=True)
        if balance < amount:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ You cannot tip more MWC than you have!", ephemeral=True
            )
            return

        # Add tip
        mysql.add_tip(snowflake, tip_user, amount)

        # Fetch price
        price_usd = await self.fetch_price_usd()
        usd_value = amount * price_usd

        await interaction.response.send_message(
            f"{interaction.user.mention} tipped {user.mention} **{amount:.8f} MWC (~${usd_value:,.2f} USD)** <:MWC:1451276940236423189>"
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Tip(bot))
