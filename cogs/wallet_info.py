import discord
from discord import app_commands
from discord.ext import commands

from utils import rpc_module


class WalletInfo(commands.Cog):
    """Admin wallet info commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rpc = rpc_module.Rpc()

    @app_commands.command(
        name="wallet",
        description="Show daemon wallet info [ADMIN ONLY]"
    )
    @app_commands.checks.is_owner()
    async def wallet(self, interaction: discord.Interaction):
        """Show wallet info"""
        try:
            info = self.rpc.getinfo()
            wallet_balance = float(info.get("balance", 0))
            block_height = info.get("blocks", "N/A")
            connection_count = self.rpc.getconnectioncount()

            embed = discord.Embed(
                title="🧾 Wallet Info",
                colour=discord.Colour.red()
            )
            embed.add_field(
                name="Balance",
                value=f"{wallet_balance:.8f} MWC",
                inline=False
            )
            embed.add_field(
                name="Connections",
                value=connection_count,
                inline=True
            )
            embed.add_field(
                name="Block Height",
                value=block_height,
                inline=True
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            await interaction.response.send_message(
                f"⚠️ Failed to fetch wallet info:\n`{type(e).__name__}: {e}`",
                ephemeral=False
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(WalletInfo(bot))
