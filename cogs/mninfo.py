import discord
from discord import app_commands
from discord.ext import commands
from utils import rpc_module as rpc, parsing
import math
import aiohttp
import json

class Masternodes(commands.Cog):
    """Slash commands to display masternode info"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rpc = rpc.Rpc()

    async def get_price_usd(self):
        """Fetch current MWC price in USD from CoinPaprika"""
        url = "https://api.coinpaprika.com/v1/tickers/mwc-minersworldcoin"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    return float(data["quotes"]["USD"]["price"])
        except Exception:
            return None

    @app_commands.command(name="mninfo", description="Show NORT masternode statistics")
    async def mninfo(self, interaction: discord.Interaction):
        mn_info = self.rpc.listmasternodes()
        total_mn = len(mn_info)
        active_mn = sum(1 for mn in mn_info if mn["status"] in ["ENABLED", "WATCHDOG_EXPIRED"])

        curr_block_reward = 3.75
        curr_mn_reward_percent = 0.85
        mn_collateral = 2500

        daily_reward = (1 / max(active_mn, 1)) * curr_block_reward * 1440 * curr_mn_reward_percent
        weekly_reward = daily_reward * 7
        monthly_reward = daily_reward * 30
        yearly_reward = daily_reward * 365

        # Reward frequency
        avg_reward_freq_hr = 0
        avg_reward_freq_min = 0
        avg_reward_freq_sec = 0
        if active_mn > 0:
            avg_reward_freq = (active_mn * 1) / 60  # min per masternode
            avg_reward_freq_hr = math.floor(avg_reward_freq)
            avg_reward_freq_min = math.floor((avg_reward_freq - avg_reward_freq_hr) * 60)
            avg_reward_freq_sec = math.floor((avg_reward_freq - avg_reward_freq_hr - (avg_reward_freq_min/60)) * 3600)

        roi_days = mn_collateral / daily_reward if daily_reward > 0 else 0
        roi_yearly_percent = ((daily_reward * 365) / mn_collateral) * 100 if daily_reward > 0 else 0
        coins_locked = total_mn * mn_collateral

        # Fetch USD price
        price_usd = await self.get_price_usd()

        embed = discord.Embed(colour=0x00FF00)
        embed.set_author(name="NORT Masternode Information", icon_url="http://explorer.nort.network/images/logo.png")
        embed.add_field(name="Total Masternodes", value=str(total_mn))
        embed.add_field(name="Active Masternodes", value=str(active_mn))
        embed.add_field(name="\u200b", value="\u200b")
        embed.add_field(name="Daily Income", value=f"{daily_reward:.4f} NORT" + (f" (${daily_reward*price_usd:.2f})" if price_usd else ""))
        embed.add_field(name="Monthly Income", value=f"{monthly_reward:.4f} NORT" + (f" (${monthly_reward*price_usd:.2f})" if price_usd else ""))
        embed.add_field(name="Yearly Income", value=f"{yearly_reward:.4f} NORT" + (f" (${yearly_reward*price_usd:.2f})" if price_usd else ""))
        embed.add_field(name="Reward Frequency", value=f"{avg_reward_freq_hr:02}:{avg_reward_freq_min:02}:{avg_reward_freq_sec:02}")
        embed.add_field(name="Days to ROI", value=f"{roi_days:.0f} days")
        embed.add_field(name="Annual ROI", value=f"{roi_yearly_percent:.2f}%")
        embed.set_footer(text=f"Coins Locked in MNs: {coins_locked} NORT")

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Masternodes(bot))
