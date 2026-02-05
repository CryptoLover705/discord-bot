import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
from decimal import Decimal
from utils import rpc_module, mysql_module

rpc = rpc_module.Rpc()
mysql = mysql_module.Mysql()

COINPAPRIKA_ID = "mwc-minersworldcoin"


class Balance(commands.Cog):
    """Slash commands for viewing balances"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def fetch_price_usd(self) -> Decimal:
        url = f"https://api.coinpaprika.com/v1/tickers/{COINPAPRIKA_ID}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return Decimal(str(data["quotes"]["USD"]["price"]))

    def build_embed(
        self,
        user: discord.User,
        confirmed: Decimal,
        unconfirmed: Decimal,
        price_usd: Decimal
    ) -> discord.Embed:

        confirmed_usd = confirmed * price_usd

        embed = discord.Embed(
            title="💰 MWC Balance",
            colour=0xff0000
        )

        embed.add_field(
            name="User",
            value=user.mention,
            inline=False
        )

        embed.add_field(
            name="Balance",
            value=f"{confirmed:.8f} MWC\n≈ ${confirmed_usd:,.6f} USD",
            inline=True
        )

        if unconfirmed > 0:
            unconfirmed_usd = unconfirmed * price_usd
            embed.add_field(
                name="Unconfirmed Deposits",
                value=f"{unconfirmed:.8f} MWC\n≈ ${unconfirmed_usd:,.6f} USD",
                inline=True
            )

        return embed

    # ---------------- SLASH COMMAND ----------------

    @app_commands.command(
        name="balance",
        description="Display your MWC balance"
    )
    async def balance(self, interaction: discord.Interaction):

        snowflake = interaction.user.id

        # Ensure user exists
        mysql.check_for_user(snowflake)

        # ✅ NEW BALANCE CALLS
        confirmed = mysql.get_confirmed_balance(snowflake)
        unconfirmed = mysql.get_unconfirmed_balance(snowflake)

        price_usd = await self.fetch_price_usd()

        embed = self.build_embed(
            interaction.user,
            confirmed,
            unconfirmed,
            price_usd
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=False
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Balance(bot))
