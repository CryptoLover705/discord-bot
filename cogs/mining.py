import discord
from discord import app_commands
from discord.ext import commands
from utils import rpc_module as rpc, parsing
from aiohttp import ClientSession
import json

class Mining(commands.Cog):
    """Slash commands to display MWC mining information"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rpc = rpc.Rpc()

    async def fetch_pool_data(self, url: str, pool_name: str, icon_url: str = None):
        headers = {"user-agent": "Mozilla/5.0"}
        try:
            async with ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    raw = await resp.read()
                    data = json.loads(raw)["NORT"]

                    workers = data["workers"]
                    shares = data["shares"]
                    hashrate_Ghs = data["hashrate"] / 1e9
                    lastblock = data["lastblock"]
                    blocks24h = data["24h_blocks"]
                    timesincelast = data["timesincelast"] / 60  # minutes

                    embed = discord.Embed(colour=0x00FF00)
                    embed.set_author(name=f"{pool_name} Pool Information", icon_url=icon_url)
                    embed.add_field(name="Workers", value=str(workers))
                    embed.add_field(name="Pool Hashrate", value=f"{hashrate_Ghs:.2f} GH/s")
                    embed.add_field(name="Shares", value=str(shares))
                    embed.add_field(name="24hr Blocks", value=str(blocks24h))
                    embed.add_field(name="Last Block Found", value=str(lastblock))
                    embed.add_field(name="Time Since Last Block", value=f"{timesincelast:.2f} min")
                    return embed
        except Exception:
            return None

    @app_commands.command(name="mining", description="Show MWC mining stats and pool info")
    async def mining(self, interaction: discord.Interaction):
        # Fetch core chain info
        mining_info = self.rpc.getmininginfo()
        height = mining_info["blocks"]
        difficulty = mining_info["difficulty"]
        network_hashrate_Ghs = mining_info["networkhashps"] / 1e9

        embed_chain = discord.Embed(colour=0x00FF00)
        embed_chain.set_author(name='MWC Mining Information', icon_url="http://explorer.nort.network/images/logo.png")
        embed_chain.add_field(name="Current Height", value=str(height))
        embed_chain.add_field(name="Network Difficulty", value=f"{difficulty:.2f}")
        embed_chain.add_field(name="Network Hashrate", value=f"{network_hashrate_Ghs:.2f} GH/s")

        await interaction.response.send_message(embed=embed_chain, ephemeral=True)

        # Fetch BSOD pool info
        bsod_embed = await self.fetch_pool_data(
            "http://api.bsod.pw/api/currencies",
            "BSOD",
            "https://pbs.twimg.com/profile_images/947108830495854593/XFrI4e8G_400x400.jpg"
        )
        if bsod_embed:
            bsod_embed.set_footer(text="ccminer.exe -a lyra2v2 -o stratum+tcp://pool.bsod.pw:1982 -u <Wallet>.<Rigname> -p c=NORT -R 5")
            await interaction.followup.send(embed=bsod_embed, ephemeral=True)
        else:
            await interaction.followup.send(":warning: Error fetching BSOD pool info!", ephemeral=True)

        # Fetch Erstweal pool info
        erst_embed = await self.fetch_pool_data(
            "https://erstweal.com/api/currencies",
            "Erstweal"
        )
        if erst_embed:
            erst_embed.set_footer(text="ccminer.exe -a lyra2v2 -o stratum+tcp://erstweal.com:4531 -u <Wallet> -p <Rigname> c=ORE")
            await interaction.followup.send(embed=erst_embed, ephemeral=True)
        else:
            await interaction.followup.send(":warning: Error fetching Erstweal pool info!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Mining(bot))
