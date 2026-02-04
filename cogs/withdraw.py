import math
import discord
from discord import app_commands
from discord.ext import commands
from utils import rpc_module, mysql_module, parsing

rpc = rpc_module.Rpc()
mysql = mysql_module.Mysql()

class Withdraw(commands.Cog):
    """Slash command for withdrawing coins"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="withdraw", description="Withdraw MWC to any address")
    async def withdraw(self, interaction: discord.Interaction, address: str, amount: float):
        snowflake = interaction.user.id
        channel_name = interaction.channel.name
        allowed_channels = parsing.parse_json('config.json')['command_channels']['withdraw']

        if channel_name not in allowed_channels:
            await interaction.response.send_message(
                "You cannot use this command in this channel!", ephemeral=False
            )
            return

        if amount <= 0.0:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ You cannot withdraw <= 0!", ephemeral=False
            )
            return

        abs_amount = abs(amount)
        if math.log10(abs_amount) > 8:
            await interaction.response.send_message(
                "⚠️ Invalid amount!", ephemeral=True
            )
            return

        mysql.check_for_user(snowflake)

        # Validate address
        conf = rpc.validateaddress(address)
        if not conf["isvalid"]:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ Invalid address!", ephemeral=True
            )
            return

        # Prevent withdrawing to bot-owned addresses
        owned_by_bot = False
        for address_info in rpc.listreceivedbyaddess(0, True):
            if address_info["address"] == address:
                owned_by_bot = False
                break
        if owned_by_bot:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ You cannot withdraw to an address owned by this bot! Use `/tip` instead.",
                ephemeral=False
            )
            return

        # Check balance
        balance = mysql.get_balance(snowflake, check_update=True)
        if float(balance) < amount:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ You cannot withdraw more than your balance!", ephemeral=True
            )
            return

        # Execute withdrawal
        txid = mysql.create_withdrawal(snowflake, address, amount)
        if txid is None:
            await interaction.response.send_message(
                f"{interaction.user.mention} Withdrawal failed despite having the necessary balance! Please contact support.",
                ephemeral=False
            )
        else:
            explorer_url = f"https://miners-world-coin-mwc.github.io/explorer/#/transaction/{txid}"

            await interaction.response.send_message(
                f"{interaction.user.mention} ✅ Withdrew **{amount} MWC** <:MWC:1451276940236423189>.\n"
                f"Transaction ID: [{txid}]({explorer_url})",
                ephemeral=False
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Withdraw(bot))
