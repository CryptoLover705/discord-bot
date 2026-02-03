import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
from utils import parsing

COINPAPRIKA_ID = "mwc-minersworldcoin"  # CoinPaprika ID

class Stats(commands.Cog):
    """Slash commands for NORT stats"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def fetch_price_data(self) -> dict:
        """Fetch price info from CoinPaprika"""
        url = f"https://api.coinpaprika.com/v1/tickers/{COINPAPRIKA_ID}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return {
                    "price_usd": float(data["quotes"]["USD"]["price"]),
                    "market_cap_usd": float(data["quotes"]["USD"]["market_cap"]),
                    "circulating_supply": float(data["circulating_supply"]),
                    "rank": data.get("rank", "?"),
                    "volume_24h": float(data["quotes"]["USD"]["volume_24h"])
                }

    @app_commands.command(name="stats", description="Show NORT coin stats")
    async def stats(self, interaction: discord.Interaction):
        # Restrict channels
        allowed_channels = parsing.parse_json('config.json')['command_channels']['stats']
        if interaction.channel.name not in allowed_channels:
            await interaction.response.send_message(
                "You cannot use this command in this channel!", ephemeral=True
            )
            return

        try:
            data = await self.fetch_price_data()
            embed = discord.Embed(
                title="NORT Coin Stats",
                colour=0x00FF00,
                url="https://coinpaprika.com/coin/mwc-minersworldcoin"
            )
            embed.set_thumbnail(url="http://explorer.nort.network/images/logo.png")
            embed.add_field(name="Price (USD)", value=f"${data['price_usd']:.8f}", inline=True)
            embed.add_field(name="Market Cap", value=f"${data['market_cap_usd']:,}", inline=True)
            embed.add_field(name="Circulating Supply", value=f"{data['circulating_supply']:,} NORT", inline=True)
            embed.add_field(name="24h Volume", value=f"${data['volume_24h']:,}", inline=True)
            embed.add_field(name="Rank", value=f"#{data['rank']}", inline=True)

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f":warning: Error fetching NORT stats! ({type(e).__name__}: {e})", ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
