import discord
from discord import app_commands
from discord.ext import commands
from utils import rpc_module as rpc
from aiohttp import ClientSession
import json

class Mining(commands.Cog):
    """Slash commands to display MWC mining information"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rpc = rpc.Rpc()

    async def fetch_bmine_data(self):
        url = "https://bmine.net/api/stats"
        headers = {"user-agent": "Mozilla/5.0"}

        async with ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()

                pools = data.get("pools", {})
                mwc = pools.get("minersworldcoin")

                if not mwc:
                    return None

                pool_stats = mwc.get("poolStats", {})
                blocks = mwc.get("blocks", {})

                return {
                    "workers": mwc.get("workerCount", 0),
                    "hashrate": mwc.get("hashrate", 0),
                    "shares": pool_stats.get("validShares", 0),
                    "blocks_24h": blocks.get("confirmed", 0),
                    "last_block": pool_stats.get("networkBlocks", "?"),
                    "time_since_last": mwc.get("maxRoundTime", 0) / 60
                }

    @staticmethod
    def format_hashrate(hashrate: float):
        """Auto-detect units for hashrate"""
        units = ["H/s", "kH/s", "MH/s", "GH/s", "TH/s", "PH/s"]
        idx = 0
        while hashrate >= 1000 and idx < len(units) - 1:
            hashrate /= 1000
            idx += 1
        return hashrate, units[idx]

    @app_commands.command(name="mining", description="Show MWC mining stats and pool info")
    async def mining(self, interaction: discord.Interaction):
        try:
            # ---------------- Core chain info ----------------
            mining_info = self.rpc.getmininginfo()
            height = mining_info["blocks"]
            difficulty = mining_info["difficulty"]
            network_hashrate = mining_info["networkhashps"]
            hash_value, unit = self.format_hashrate(network_hashrate)

            # ---------------- bMine pool info ----------------
            pool_data = await self.fetch_bmine_data()

            embed = discord.Embed(colour=0x00FF00)
            embed.set_author(name="MWC Mining & Pool Info", icon_url="https://pbs.twimg.com/profile_images/2001665741133639680/oKsBqI8b_400x400.jpg")

            # Chain fields
            embed.add_field(name="Current Height", value=str(height), inline=True)
            embed.add_field(name="Network Difficulty", value=f"{difficulty:.4f}", inline=True)
            embed.add_field(name="Network Hashrate", value=f"{hash_value:.4f} {unit}", inline=True)

            # Pool fields
            if pool_data:
                phash, punits = self.format_hashrate(pool_data["hashrate"])
                embed.add_field(name="Pool Workers", value=str(pool_data["workers"]), inline=True)
                embed.add_field(name="Pool Hashrate", value=f"{phash:.2f} {punits}", inline=True)
                embed.add_field(name="Pool Shares", value=str(pool_data["shares"]), inline=True)
                embed.add_field(name="24h Blocks", value=str(pool_data["blocks_24h"]), inline=True)
                embed.add_field(name="Last Block Found", value=str(pool_data["last_block"]), inline=True)
                embed.add_field(name="Time Since Last Block", value=f"{pool_data['time_since_last']:.2f} min", inline=True)
                embed.set_footer(text="ccminer.exe -a yespower -o stratum+tcp://bmine.net:3333 -u <Wallet>.<RigName> -p <Anything>")
            else:
                embed.add_field(name="Pool Info", value="Could not fetch bMine pool info", inline=False)

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f":warning: Error fetching mining info ({type(e).__name__}): {e}",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Mining(bot))
