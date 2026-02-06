import math
import discord
from discord import app_commands
from discord.ext import commands
from utils import rpc_module, mysql_module, parsing
from decimal import Decimal, InvalidOperation
import traceback  # <-- for detailed error logging

rpc = rpc_module.Rpc()
mysql = mysql_module.Mysql()

class Withdraw(commands.Cog):
    """Slash command for withdrawing coins"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="withdraw", description="Withdraw MWC to any address")
    async def withdraw(self, interaction: discord.Interaction, address: str, amount: str):
        snowflake = interaction.user.id
        channel_name = interaction.channel.name
        allowed_channels = parsing.parse_json('config.json')['command_channels']['withdraw']

        if channel_name not in allowed_channels:
            await interaction.response.send_message(
                "You cannot use this command in this channel!",
                ephemeral=True
            )
            return

        # ---- Parse amount safely ----
        try:
            amount_dec = Decimal(amount)
        except InvalidOperation:
            await interaction.response.send_message(
                "⚠️ Invalid amount format!",
                ephemeral=True
            )
            return

        if amount_dec <= 0:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ You cannot withdraw <= 0!",
                ephemeral=True
            )
            return

        if amount_dec.as_tuple().exponent < -8:
            await interaction.response.send_message(
                "⚠️ Amount has too many decimal places!",
                ephemeral=True
            )
            return

        mysql.check_for_user(snowflake)

        # ---- Validate address ----
        conf = rpc.validateaddress(address)
        if not conf.get("isvalid"):
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ Invalid address!",
                ephemeral=True
            )
            return

        # ---- Prevent withdraw to bot-owned addresses ----
        for addr_info in rpc.listreceivedbyaddress(0, True):
            if addr_info.get("address") == address:
                await interaction.response.send_message(
                    f"{interaction.user.mention} ⚠️ You cannot withdraw to a bot-owned address. Use `/tip` instead.",
                    ephemeral=True
                )
                return

        # ---- Refresh deposits BEFORE balance check ----
        mysql.check_for_updated_balance(snowflake)

        balance = mysql.get_balance(snowflake, confirmed_only=True)
        txfee_decimal = Decimal(str(mysql.txfee))

        # ---- Check against txfee ----
        if amount_dec <= txfee_decimal:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ Withdrawal must be greater than the transaction fee ({txfee_decimal} MWC)!",
                ephemeral=True
            )
            return

        if balance < amount_dec:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ Insufficient confirmed balance!",
                ephemeral=True
            )
            return

        # ---- SINGLE SOURCE OF TRUTH FOR WITHDRAW WITH ERROR LOGGING ----
        try:
            txid = mysql.create_withdrawal(
                snowflake=snowflake,
                address=address,
                amount=amount_dec
            )

            if not txid:
                await interaction.response.send_message(
                    f"{interaction.user.mention} ❌ Withdrawal failed: insufficient balance or invalid amount.",
                    ephemeral=True
                )
                return

            explorer_url = f"https://miners-world-coin-mwc.github.io/explorer/#/transaction/{txid}"
            await interaction.response.send_message(
                f"{interaction.user.mention} ✅ Withdrew **{amount_dec} MWC** <:MWC:1451276940236423189>\n"
                f"Transaction ID: [{txid}]({explorer_url})",
                ephemeral=False
            )

        except Exception as e:
            # Print full traceback in console
            traceback.print_exc()

            # Show error in Discord for debugging
            await interaction.response.send_message(
                f"{interaction.user.mention} ❌ Withdrawal error:\n```{type(e).__name__}: {e}```",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Withdraw(bot))
