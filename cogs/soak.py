import math
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from enum import Enum
from utils import rpc_module, mysql_module, checks, parsing

rpc = rpc_module.Rpc()
mysql = mysql_module.Mysql()
COINPAPRIKA_ID = "mwc-minersworldcoin"


# =========================
# SOAK TYPES
# =========================
class SoakType(Enum):
    online = "online"
    role = "role"
    active = "active"


class Soak(commands.Cog):
    """Slash commands for soaking users"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        soak_config = parsing.parse_json('config.json')['soak']
        self.soak_max_recipients = soak_config["soak_max_recipients"]
        self.use_max_recipients = soak_config["use_max_recipients"]
        self.soak_min_received = soak_config["soak_min_received"]
        self.use_min_received = soak_config["use_min_received"]

    async def fetch_price_usd(self) -> float:
        url = f"https://api.coinpaprika.com/v1/tickers/{COINPAPRIKA_ID}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return float(data["quotes"]["USD"]["price"])

    # =========================
    # SOAK COMMAND
    # =========================
    @app_commands.command(name="soak", description="Soak users by online, role, or activity")
    @app_commands.check(checks.allow_soak)
    @app_commands.describe(
        type="Who should be soaked",
        amount="Total MWC amount to split",
        role="Role to soak (role type only)",
        timeframe="Activity window like 24h or 72h (active type only)"
    )
    async def soak(
        self,
        interaction: discord.Interaction,
        type: SoakType,
        amount: float,
        role: discord.Role | None = None,
        timeframe: str | None = None
    ):
        sender = interaction.user
        snowflake = sender.id

        mysql.check_for_user(snowflake)
        balance = mysql.get_balance(snowflake, update=True)

        if amount <= 0:
            await interaction.response.send_message(
                f"{sender.mention} ⚠️ Amount must be greater than 0!",
                ephemeral=True
            )
            return

        if balance < amount:
            await interaction.response.send_message(
                f"{sender.mention} ⚠️ Insufficient balance!",
                ephemeral=True
            )
            return

        recipients: list[discord.Member] = []

        # =========================
        # ONLINE SOAK
        # =========================
        if type == SoakType.online:
            recipients = [
                m for m in interaction.guild.members
                if m.status == discord.Status.online
                and not m.bot
                and m.id != snowflake
                and mysql.check_soakme(m.id)
            ]

        # =========================
        # ROLE SOAK
        # =========================
        elif type == SoakType.role:
            if not role:
                await interaction.response.send_message(
                    "⚠️ You must specify a role for role soak!",
                    ephemeral=True
                )
                return

            recipients = [
                m for m in role.members
                if not m.bot
                and m.id != snowflake
                and mysql.check_soakme(m.id)
            ]

        # =========================
        # ACTIVE SOAK
        # =========================
        elif type == SoakType.active:
            if not timeframe or not timeframe.endswith("h"):
                await interaction.response.send_message(
                    "⚠️ Timeframe must look like `24h` or `72h`",
                    ephemeral=True
                )
                return

            hours = int(timeframe.replace("h", ""))
            active_ids = mysql.get_active_users(hours)

            for uid in active_ids:
                member = interaction.guild.get_member(uid)
                if member and not member.bot and member.id != snowflake:
                    if mysql.check_soakme(member.id):
                        recipients.append(member)

        # =========================
        # VALIDATION
        # =========================
        if not recipients:
            await interaction.response.send_message(
                f"{sender.mention} ⚠️ No eligible users found!",
                ephemeral=True
            )
            return

        if self.use_max_recipients:
            recipients = recipients[: self.soak_max_recipients]

        count = len(recipients)

        if self.use_min_received and amount < self.soak_min_received:
            await interaction.response.send_message(
                f"{sender.mention} ⚠️ Amount below minimum soak ({self.soak_min_received})",
                ephemeral=True
            )
            return

        split_amount = math.floor(amount * 1e8 / count) / 1e8

        if split_amount <= 0:
            await interaction.response.send_message(
                f"{sender.mention} ⚠️ Amount too small to split!",
                ephemeral=True
            )
            return

        # =========================
        # EXECUTE SOAK
        # =========================
        for member in recipients:
            mysql.check_for_user(member.id)
            mysql.add_tip(snowflake, member.id, split_amount)

        price_usd = await self.fetch_price_usd()
        usd_each = split_amount * price_usd

        mentions = ", ".join(m.mention for m in recipients[:10])
        if len(recipients) > 10:
            mentions += f" +{len(recipients) - 10} more"

        await interaction.response.send_message(
            f"💦 {sender.mention} soaked **{count} users** ({type.value})\n"
            f"💰 **{split_amount:.8f} MWC each** (~${usd_each:,.6f})\n"
            f"👥 {mentions}\n"
            f"📦 Total: **{amount:.8f} MWC**"
        )

    # =========================
    # SOAK INFO
    # =========================
    @app_commands.command(name="soak_info", description="Display soak limits")
    async def soak_info(self, interaction: discord.Interaction):
        max_users = self.soak_max_recipients if self.use_max_recipients else "<disabled>"
        min_received = self.soak_min_received if self.use_min_received else "<disabled>"

        await interaction.response.send_message(
            f":information_source: Soak info\n"
            f"• Max recipients: {max_users}\n"
            f"• Min per user: {min_received}"
        )

    # =========================
    # SOAKME
    # =========================
    @app_commands.command(name="soakme", description="Allow/disallow being soaked")
    async def soakme(self, interaction: discord.Interaction, enable: bool):
        snowflake = interaction.user.id
        mysql.check_for_user(snowflake)
        mysql.set_soakme(snowflake, int(enable))

        await interaction.response.send_message(
            "✅ You will be soaked!" if enable else "❌ You will no longer be soaked!"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Soak(bot))
