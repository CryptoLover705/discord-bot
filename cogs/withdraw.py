import discord
from discord import app_commands
from discord.ext import commands
from utils import rpc_module, mysql_module, parsing
from decimal import Decimal, InvalidOperation
import traceback
from datetime import datetime

rpc = rpc_module.Rpc()
mysql = mysql_module.Mysql()

EXPLORER_TX_URL = "https://miners-world-coin-mwc.github.io/explorer/#/transaction/{}"


class Withdraw(commands.Cog):
    """Withdraw MWC and view withdrawal history"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    withdraw = app_commands.Group(
        name="withdraw",
        description="Withdraw MWC or view withdrawal history"
    )

    # =========================
    # /withdraw send
    # =========================
    @withdraw.command(name="send", description="Withdraw MWC to an external address")
    async def withdraw_send(
        self,
        interaction: discord.Interaction,
        address: str,
        amount: str
    ):
        snowflake = interaction.user.id
        allowed_channels = parsing.parse_json("config.json")["command_channels"].get("withdraw", [])

        if allowed_channels and interaction.channel.name not in allowed_channels:
            await interaction.response.send_message(
                "❌ You cannot use this command in this channel.",
                ephemeral=True
            )
            return

        # ---- Parse amount ----
        try:
            amount_dec = Decimal(amount)
        except InvalidOperation:
            await interaction.response.send_message("⚠️ Invalid amount format.", ephemeral=True)
            return

        if amount_dec <= 0:
            await interaction.response.send_message(
                "⚠️ Withdrawal amount must be greater than 0.",
                ephemeral=True
            )
            return

        if amount_dec.as_tuple().exponent < -8:
            await interaction.response.send_message(
                "⚠️ Amount has too many decimal places (max 8).",
                ephemeral=True
            )
            return

        mysql.check_for_user(snowflake)

        # ---- Validate address ----
        addr_info = rpc.validateaddress(address)
        if not addr_info.get("isvalid"):
            await interaction.response.send_message(
                "⚠️ Invalid withdrawal address.",
                ephemeral=True
            )
            return

        # ---- Prevent withdrawing to bot-owned addresses ----
        for addr in rpc.listreceivedbyaddress(0, True):
            if addr.get("address") == address:
                await interaction.response.send_message(
                    "⚠️ You cannot withdraw to a bot-owned address. Use `/tip` instead.",
                    ephemeral=True
                )
                return

        # ---- Update balance ----
        mysql.check_for_updated_balance(snowflake)

        balance = mysql.get_balance(snowflake, confirmed_only=True)
        txfee = Decimal(str(mysql.txfee))

        if amount_dec <= txfee:
            await interaction.response.send_message(
                f"⚠️ Amount must be greater than the tx fee ({txfee} MWC).",
                ephemeral=True
            )
            return

        if balance < amount_dec:
            await interaction.response.send_message(
                "⚠️ Insufficient confirmed balance.",
                ephemeral=True
            )
            return

        # ---- Execute withdrawal ----
        try:
            txid = mysql.create_withdrawal(
                snowflake=snowflake,
                address=address,
                amount=amount_dec
            )

            if not txid:
                await interaction.response.send_message(
                    "❌ Withdrawal failed. Please contact support.",
                    ephemeral=True
                )
                return

            explorer_link = EXPLORER_TX_URL.format(txid)

            embed = discord.Embed(
                title="✅ Withdrawal Successful",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Amount", value=f"{amount_dec:.8f} MWC", inline=False)
            embed.add_field(name="To Address", value=f"`{address}`", inline=False)
            embed.add_field(
                name="Transaction ID",
                value=f"[{txid}]({explorer_link})",
                inline=False
            )
            embed.set_footer(
                text="⚠️ Tx fee paid by sender • Use /balance to verify"
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            traceback.print_exc()
            await interaction.response.send_message(
                f"❌ Withdrawal error:\n```{type(e).__name__}: {e}```",
                ephemeral=True
            )

    # =========================
    # /withdraw history
    # =========================
    @withdraw.command(name="history", description="View your withdrawal history")
    async def withdraw_history(self, interaction: discord.Interaction):
        snowflake = interaction.user.id
        mysql.check_for_user(snowflake)

        withdrawals = mysql.get_withdrawal_history(snowflake)

        if not withdrawals:
            await interaction.response.send_message(
                "📭 You have no withdrawal history.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📜 Withdrawal History",
            color=discord.Color.blurple()
        )

        for w in withdrawals[:10]:
            explorer_link = EXPLORER_TX_URL.format(w["txid"])

            embed.add_field(
                name=f"{w['amount']:.8f} MWC",
                value=f"[View Transaction]({explorer_link})",
                inline=False
            )

        embed.set_footer(text="Showing last 10 withdrawals")

        await interaction.response.send_message(embed=embed, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Withdraw(bot))
