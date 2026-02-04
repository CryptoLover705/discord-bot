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
                raw = await resp.read()
                data = json.loads(raw)

                # Try all possible keys to find MWC
                coin_data = None
                for key in ["yespowerMWC", "MWC", "minersworldcoin"]:
                    if key in data:
                        coin_data = data[key]
                        break

                if not coin_data:
                    return None

                # Extract data
                workers = coin_data.get("workers", 0)
                shares = coin_data.get("shares", 0)
                hashrate = coin_data.get("hashrate", 0)
                last_block = coin_data.get("lastblock", "?")
                blocks_24h = coin_data.get("blocks_24h", 0)
                time_since_last = coin_data.get("timesincelast", 0) / 60  # convert sec → min

                # Auto format hashrate
                hash_value, unit = self.format_hashrate(hashrate)

                embed = discord.Embed(colour=0x00FF00)
                embed.set_author(name="bMine Pool Information", icon_url="https://bmine.net/images/logo.png")
                embed.add_field(name="Workers", value=str(workers))
                embed.add_field(name="Pool Hashrate", value=f"{hash_value:.2f} {unit}")
                embed.add_field(name="Shares", value=str(shares))
                embed.add_field(name="24h Blocks", value=str(blocks_24h))
                embed.add_field(name="Last Block Found", value=str(last_block))
                embed.add_field(name="Time Since Last Block", value=f"{time_since_last:.2f} min")
                embed.set_footer(text="ccminer.exe -a yespower -o stratum+tcp://bmine.net:3333 -u <Wallet> -p <Rigname>")
                return embed

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
        # ---------------- Core chain info ----------------
        try:
            mining_info = self.rpc.getmininginfo()
            height = mining_info["blocks"]
            difficulty = mining_info["difficulty"]
            network_hashrate = mining_info["networkhashps"]

            hash_value, unit = self.format_hashrate(network_hashrate)

            embed_chain = discord.Embed(colour=0x00FF00)
            embed_chain.set_author(name='MWC Mining Information', icon_url="https://pbs.twimg.com/profile_images/2001665741133639680/oKsBqI8b_400x400.jpg")
            embed_chain.add_field(name="Current Height", value=str(height))
            embed_chain.add_field(name="Network Difficulty", value=f"{difficulty:.2f}")
            embed_chain.add_field(name="Network Hashrate", value=f"{hash_value:.2f} {unit}")

            await interaction.response.send_message(embed=embed_chain, ephemeral=False)
        except Exception as e:
            await interaction.response.send_message(f":warning: Error fetching chain info ({type(e).__name__}): {e}", ephemeral=True)
            return

        # ---------------- bMine pool info ----------------
        try:
            bmine_embed = await self.fetch_bmine_data()
            if bmine_embed:
                await interaction.followup.send(embed=bmine_embed, ephemeral=False)
            else:
                await interaction.followup.send(":warning: Could not fetch bMine pool info.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f":warning: Error fetching bMine pool info ({type(e).__name__}): {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Mining(bot))
