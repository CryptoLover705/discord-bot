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

        # --- In-memory activity tracker for active soak ---
        self.active_users: dict[int, float] = {}  # snowflake -> last seen timestamp

    async def fetch_price_usd(self) -> float:
        url = f"https://api.coinpaprika.com/v1/tickers/{COINPAPRIKA_ID}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return float(data["quotes"]["USD"]["price"])

    # =========================
    # MESSAGE SPLITTER
    # =========================
    async def send_long_message(self, channel, content, **kwargs):
        # Discord max message length is 2000 chars
        for i in range(0, len(content), 2000):
            await channel.send(content[i:i+2000], **kwargs)

    # =========================
    # SOAK COMMAND
    # =========================
    @app_commands.command(name="soak", description="Soak users by online, role, or activity")
    @app_commands.check(checks.allow_soak)
    @app_commands.describe(
        type="Who should be soaked",
        amount="Total MWC amount to split",
        role="Role to soak (role type only)",
        timeframe="Activity window like 10m, 1h, 24h (active type only)"
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

        # ------------------------
        # DEFER TO AVOID TIMEOUT
        # ------------------------
        await interaction.response.defer(ephemeral=False)

        mysql.check_for_user(snowflake)
        balance = mysql.get_balance(snowflake, update=True)

        if amount <= 0:
            await interaction.followup.send(f"{sender.mention} ⚠️ Amount must be greater than 0!", ephemeral=True)
            return

        if balance < amount:
            await interaction.followup.send(f"{sender.mention} ⚠️ Insufficient balance!", ephemeral=True)
            return

        recipients: list[discord.Member] = []

        # =========================
        # ONLINE SOAK
        # =========================
        if type == SoakType.online:
            recipients = [
                m for m in interaction.guild.members
                if not m.bot and m.id != snowflake and m.status != discord.Status.offline
            ]

        # =========================
        # ROLE SOAK
        # =========================
        elif type == SoakType.role:
            if not role:
                await interaction.followup.send("⚠️ You must specify a role for role soak!", ephemeral=True)
                return
            recipients = [
                m for m in role.members
                if not m.bot and m.id != snowflake
            ]

        # =========================
        # ACTIVE SOAK (since bot startup)
        # =========================
        elif type == SoakType.active:
            if not timeframe:
                await interaction.followup.send(
                    "⚠️ You must provide a timeframe like `10m`, `1h`, or `24h`",
                    ephemeral=True
                )
                return

            try:
                duration_seconds = parsing.parse_duration(timeframe)
            except ValueError:
                await interaction.followup.send(
                    "⚠️ Invalid timeframe format.\nUse `30s`, `1m`, `10m`, `1h`, `24h`, `7d`",
                    ephemeral=True
                )
                return

            # Optional safety limits
            if duration_seconds < 60 or duration_seconds > 86400:
                await interaction.followup.send(
                    "⚠️ Timeframe must be between **1 minute and 24 hours**",
                    ephemeral=True
                )
                return

            cutoff = discord.utils.utcnow().timestamp() - duration_seconds

            active_ids = [
                uid for uid, ts in self.active_users.items()
                if ts >= cutoff
            ]

            for uid in active_ids:
                member = interaction.guild.get_member(uid)
                if member and not member.bot and member.id != snowflake:
                    recipients.append(member)

        # =========================
        # VALIDATION
        # =========================
        if not recipients:
            await interaction.followup.send(f"{sender.mention} ⚠️ No eligible users found!", ephemeral=True)
            return

        if self.use_max_recipients:
            recipients = recipients[: self.soak_max_recipients]

        count = len(recipients)

        if self.use_min_received and amount < self.soak_min_received:
            await interaction.followup.send(
                f"{sender.mention} ⚠️ Amount below minimum soak ({self.soak_min_received})",
                ephemeral=True
            )
            return

        split_amount = math.floor(amount * 1e8 / count) / 1e8
        if split_amount <= 0:
            await interaction.followup.send(f"{sender.mention} ⚠️ Amount too small to split!", ephemeral=True)
            return

        # =========================
        # EXECUTE SOAK
        # =========================
        for member in recipients:
            mysql.check_for_user(member.id)
            mysql.add_tip(snowflake, member.id, split_amount)

        price_usd = await self.fetch_price_usd()
        usd_each = split_amount * price_usd

        # =========================
        # BUILD MENTIONS WITH SPLIT MESSAGES
        # =========================
        chunk_size = 50
        mentions_chunks = [
            ", ".join(m.mention for m in recipients[i:i+chunk_size])
            for i in range(0, len(recipients), chunk_size)
        ]

        # First chunk uses followup.send to resolve the defer
        first_chunk = mentions_chunks.pop(0)
        msg = (
            f"💦 {sender.mention} soaked **{count} users** ({type.value})\n"
            f"💰 **{split_amount:.8f} MWC each** (~${usd_each:,.6f})\n"
            f"👥 {first_chunk}\n"
            f"📦 Total: **{amount:.8f} MWC**"
        )
        await interaction.followup.send(msg)

        # Remaining chunks sent normally
        for chunk in mentions_chunks:
            extra_msg = (
                f"💦 {sender.mention} soaked **{count} users** ({type.value})\n"
                f"💰 **{split_amount:.8f} MWC each** (~${usd_each:,.6f})\n"
                f"👥 {chunk}\n"
                f"📦 Total: **{amount:.8f} MWC**"
            )
            await self.send_long_message(interaction.channel, extra_msg)

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

    # =========================
    # MESSAGE ACTIVITY HOOK
    # =========================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        self.active_users[message.author.id] = message.created_at.timestamp()


async def setup(bot: commands.Bot):
    await bot.add_cog(Soak(bot))
