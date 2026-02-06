import math
import random
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from utils import rpc_module, mysql_module, checks, parsing

rpc = rpc_module.Rpc()
mysql = mysql_module.Mysql()
COINPAPRIKA_ID = "mwc-minersworldcoin"  # CoinPaprika ID

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
        """Fetch the current MWC price in USD from CoinPaprika"""
        url = f"https://api.coinpaprika.com/v1/tickers/{COINPAPRIKA_ID}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return float(data["quotes"]["USD"]["price"])

    @app_commands.command(name="soak", description="Tip all online users")
    @app_commands.check(checks.allow_soak)
    async def soak(self, interaction: discord.Interaction, amount: float):
        snowflake = interaction.user.id
        mysql.check_for_user(snowflake)
        balance = mysql.get_balance(snowflake, update=True)

        if float(balance) < amount:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ You cannot soak more than your balance!",
                ephemeral=True
            )
            return

        # Fetch online users
        online_users = [
            m for m in interaction.guild.members
            if m.status == discord.Status.online and not m.bot
        ]
        if interaction.user in online_users:
            online_users.remove(interaction.user)

        # Remove users who opted out
        online_users = [u for u in online_users if mysql.check_soakme(u.id)]

        # Apply max recipients
        len_receivers = len(online_users)
        if self.use_max_recipients:
            len_receivers = min(len_receivers, self.soak_max_recipients)

        # Apply min received
        if self.use_min_received:
            if amount < self.soak_min_received:
                await interaction.response.send_message(
                    f"{interaction.user.mention} ⚠️ {amount} is below the minimum soak ({self.soak_min_received})",
                    ephemeral=True
                )
                return
            len_receivers = min(len_receivers, amount / self.soak_min_received)

        if len_receivers == 0:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ No eligible users online to soak!",
                ephemeral=True
            )
            return

        # Calculate split
        amount_split = math.floor(amount * 1e8 / len_receivers) / 1e8
        if amount_split == 0:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ {amount} MWC is too small to split among {len_receivers} users!",
                ephemeral=True
            )
            return

        # Fetch price
        price_usd = await self.fetch_price_usd()
        usd_split = amount_split * price_usd

        # Perform soak
        receivers = []
        for _ in range(int(len_receivers)):
            user = random.choice(online_users)
            receivers.append(user)
            online_users.remove(user)
            mysql.check_for_user(user.id)
            mysql.add_tip(snowflake, user.id, amount_split)

        mentions = ', '.join([u.mention for u in receivers])
        msg = (
            f":moneybag: {interaction.user.mention} soaked **{amount_split:.8f} MWC (~${usd_split:,.2f} USD)** "
            f"to {mentions} [Total {amount} MWC] :moneybag:\n"
            "NOTE: Opt out of soak with `/soakme enable:false`"
        )

        await interaction.response.send_message(msg)

    @app_commands.command(name="soak_info", description="Display min soak amount and max recipients")
    async def soak_info(self, interaction: discord.Interaction):
        max_users = self.soak_max_recipients if self.use_max_recipients else "<disabled>"
        min_received = self.soak_min_received if self.use_min_received else "<disabled>"
        await interaction.response.send_message(
            f":information_source: Soak info: max recipients {max_users}, min amount receivable {min_received}"
        )

    @app_commands.command(name="checksoak", description="Check if soaking is enabled on this server")
    async def checksoak(self, interaction: discord.Interaction):
        result_set = mysql.check_soak(interaction.guild)
        if result_set:
            await interaction.response.send_message("Soaking is enabled! ✅")
        else:
            await interaction.response.send_message("Soaking is disabled! ❌")

    @app_commands.command(name="soakme", description="Allow/disallow others from soaking you")
    async def soakme(self, interaction: discord.Interaction, enable: bool):
        snowflake = interaction.user.id
        mysql.check_for_user(snowflake)
        mysql.set_soakme(snowflake, int(enable))
        if enable:
            await interaction.response.send_message("Ok! You will be soaked! ✅")
        else:
            await interaction.response.send_message("Ok! You will no longer be soaked! ❌")


async def setup(bot: commands.Bot):
    await bot.add_cog(Soak(bot))
