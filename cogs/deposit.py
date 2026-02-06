import discord
from discord import app_commands
from discord.ext import commands
from enum import Enum
import qrcode
import io
from utils import parsing, mysql_module

mysql = mysql_module.Mysql()


# =========================
# DEPOSIT TYPES
# =========================
class DepositType(Enum):
    normal = "normal"
    mobile = "mobile"
    qr = "qr"
    history = "history"


class Deposit(commands.Cog):
    """Slash command for displaying deposit addresses"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="deposit", description="Get your MWC deposit information")
    @app_commands.describe(type="How you want the deposit info displayed")
    async def deposit(
        self,
        interaction: discord.Interaction,
        type: DepositType = DepositType.normal
    ):
        channel_name = interaction.channel.name
        allowed_channels = parsing.parse_json('config.json')['command_channels'].get("deposit", [])

        if allowed_channels and channel_name not in allowed_channels:
            await interaction.response.send_message(
                "This command cannot be used in this channel.",
                ephemeral=True
            )
            return

        snowflake = interaction.user.id
        mysql.check_for_user(snowflake)
        address = mysql.get_address(snowflake)

        # =========================
        # NORMAL EMBED
        # =========================
        if type == DepositType.normal:
            embed = discord.Embed(
                title="💰 Your MWC Deposit Address",
                description=f"`{address}`",
                color=0x2ecc71
            )
            embed.add_field(
                name="⚠️ Disclaimer",
                value=(
                    "Use `/balance` to check your balance — explorers may differ.\n\n"
                    "**BETA SOFTWARE**\n"
                    "Do not send large amounts of MWC.\n"
                    "The developers are not responsible for any lost funds."
                ),
                inline=False
            )

            embed.set_footer(text="MWC Tipper • Deposit Address")

            await interaction.response.send_message(embed=embed)
            return

        # =========================
        # MOBILE FRIENDLY
        # =========================
        if type == DepositType.mobile:
            embed = discord.Embed(
                title="📱 Mobile Deposit Address",
                description=(
                    "Tap and hold to copy:\n\n"
                    f"```\n{address}\n```"
                ),
                color=0x3498db
            )

            await interaction.response.send_message(embed=embed)
            return

        # =========================
        # QR CODE
        # =========================
        if type == DepositType.qr:
            qr = qrcode.make(address)
            buffer = io.BytesIO()
            qr.save(buffer, format="PNG")
            buffer.seek(0)

            file = discord.File(buffer, filename="deposit_qr.png")

            embed = discord.Embed(
                title="📷 Scan to Deposit MWC",
                description=f"`{address}`",
                color=0x9b59b6
            )
            embed.set_image(url="attachment://deposit_qr.png")

            await interaction.response.send_message(embed=embed, file=file)
            return

        # =========================
        # DEPOSIT HISTORY
        # =========================
        if type == DepositType.history:
            history = mysql.get_deposit_history(snowflake, limit=10)

            if not history:
                await interaction.response.send_message(
                    "📭 No deposits found yet.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="📜 Deposit History",
                color=0xf1c40f
            )

            for dep in history:
                embed.add_field(
                    name=f"{dep['amount']} MWC",
                    value=f"`{dep['txid']}`",
                    inline=False
                )

            embed.set_footer(text="Showing last 10 deposits")

            await interaction.response.send_message(embed=embed)
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Deposit(bot))
