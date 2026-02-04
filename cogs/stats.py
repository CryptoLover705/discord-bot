import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
from decimal import Decimal
from utils import parsing

COINPAPRIKA_ID = "mwc-minersworldcoin"
CHAIN_INFO_URL = "https://api.minersworld.org/info"
SATOSHIS = Decimal("100000000")


class Stats(commands.Cog):
    """Slash commands for MWC stats"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def fetch_price_data(self) -> dict:
        url = f"https://api.coinpaprika.com/v1/tickers/{COINPAPRIKA_ID}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                data = await resp.json()
                usd = data["quotes"]["USD"]
                return {
                    "price_usd": Decimal(str(usd["price"])),
                    "market_cap_usd": Decimal(str(usd["market_cap"])),
                    "volume_24h": Decimal(str(usd["volume_24h"])),
                    "rank": data.get("rank", "?")
                }

    async def fetch_chain_supply(self) -> Decimal:
        async with aiohttp.ClientSession() as session:
            async with session.get(CHAIN_INFO_URL, timeout=10) as resp:
                data = await resp.json()
                sat_supply = Decimal(str(data["result"]["supply"]))
                return sat_supply / SATOSHIS

    @app_commands.command(
        name="stats",
        description="Show Miners World Coin (MWC) stats"
    )
    async def stats(self, interaction: discord.Interaction):
        # Channel restriction
        allowed_channels = parsing.parse_json("config.json")["command_channels"]["stats"]
        if interaction.channel.name not in allowed_channels:
            await interaction.response.send_message(
                "🚫 You cannot use this command in this channel.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            price_data, supply = await asyncio.gather(
                self.fetch_price_data(),
                self.fetch_chain_supply()
            )

            embed = discord.Embed(
                title="⛏️ Miners World Coin (MWC) Stats",
                colour=0x00FF00,
                url="https://coinpaprika.com/coin/mwc-minersworldcoin"
            )

            embed.set_thumbnail(
                url="https://pbs.twimg.com/profile_images/2001665741133639680/oKsBqI8b_400x400.jpg"
            )

            embed.add_field(
                name="Price (USD)",
                value=f"${price_data['price_usd']:.8f}",
                inline=True
            )

            embed.add_field(
                name="Market Cap",
                value=f"${price_data['market_cap_usd']:,}",
                inline=True
            )

            embed.add_field(
                name="Circulating Supply",
                value=f"{supply:,.8f} MWC",
                inline=True
            )

            embed.add_field(
                name="24h Volume",
                value=f"${price_data['volume_24h']:,}",
                inline=True
            )

            embed.add_field(
                name="Rank",
                value=f"#{price_data['rank']}",
                inline=True
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(
                f"⚠️ Error fetching MWC stats:\n`{type(e).__name__}: {e}`",
                ephemeral=False
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
