import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
from utils import rpc_module, mysql_module

rpc = rpc_module.Rpc()
mysql = mysql_module.Mysql()

COINPAPRIKA_ID = "mwc-minersworldcoin"  # CoinPaprika ID for MWC

class Balance(commands.Cog):
    """Slash commands for viewing balances"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def fetch_price_usd(self) -> float:
        """Fetch the current MWC price in USD from CoinPaprika"""
        url = f"https://api.coinpaprika.com/v1/tickers/{COINPAPRIKA_ID}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return float(data["quotes"]["USD"]["price"])

    async def do_embed(self, user: discord.User, db_bal: float, db_bal_unconfirmed: float, price_usd: float) -> discord.Embed:
        # Ensure balances are float
        db_bal = float(db_bal)
        db_bal_unconfirmed = float(db_bal_unconfirmed)

        usd_balance = db_bal * price_usd
        embed = discord.Embed(colour=0xff0000)
        embed.add_field(name="User", value=user.mention)
        embed.add_field(
            name="Balance",
            value=f"{db_bal:.8f} MWC\n≈ ${usd_balance:,.6f} USD"
        )
        if db_bal_unconfirmed != 0.0:
            usd_unconfirmed = db_bal_unconfirmed * price_usd
            embed.add_field(
                name="Unconfirmed Deposits",
                value=f"{db_bal_unconfirmed:.8f} MWC\n≈ ${usd_unconfirmed:,.6f} USD"
            )
        return embed

    # ----------------- Slash Command -----------------
    @app_commands.command(name="balance", description="Display your MWC balance in coins and USD")
    async def balance(self, interaction: discord.Interaction):
        snowflake = interaction.user.id

        # Ensure user exists in DB
        mysql.check_for_user(snowflake)

        # Fetch balances and cast to float to avoid Decimal * float errors
        balance = float(mysql.get_balance(snowflake, check_update=True))
        balance_unconfirmed = float(mysql.get_balance(snowflake, check_unconfirmed=True))

        # Fetch USD price
        price_usd = await self.fetch_price_usd()

        embed = await self.do_embed(interaction.user, balance, balance_unconfirmed, price_usd)
        await interaction.response.send_message(embed=embed, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Balance(bot))
