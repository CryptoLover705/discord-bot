import discord
from discord import app_commands
from discord.ext import commands
from typing import Union
from utils import rpc_module, mysql_module, parsing, checks
import aiohttp

rpc = rpc_module.Rpc()
mysql = mysql_module.Mysql()
COINPAPRIKA_ID = "mwc-minersworldcoin"

MAX_ROLE_MEMBERS = 50
MAX_MULTI_USERS = 10

class Tip(commands.Cog):
    """Slash commands for tipping users or roles"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def fetch_price_usd(self) -> float:
        url = f"https://api.coinpaprika.com/v1/tickers/{COINPAPRIKA_ID}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return float(data["quotes"]["USD"]["price"])

    @app_commands.command(name="tip", description="Tip users or roles MWC coins")
    @app_commands.check(checks.in_server)
    async def tip(
        self,
        interaction: discord.Interaction,
        target: Union[discord.Member, discord.Role],
        amount: float,
        split: bool = False,
        user2: discord.Member | None = None,
        user3: discord.Member | None = None,
        user4: discord.Member | None = None
    ):
        allowed_channels = parsing.parse_json('config.json')['command_channels']['tip']
        if interaction.channel.name not in allowed_channels:
            await interaction.response.send_message(
                "You cannot use this command in this channel!",
                ephemeral=False
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ Tip amount must be greater than 0!",
                ephemeral=False
            )
            return

        sender = interaction.user
        mysql.check_for_user(sender.id)

        recipients: list[discord.Member] = []

        # ───────── PRIMARY TARGET ─────────
        if isinstance(target, discord.Member):
            recipients.append(target)

        elif isinstance(target, discord.Role):
            role_members = [
                m for m in target.members
                if not m.bot and m.id != sender.id
            ]

            if not role_members:
                await interaction.response.send_message(
                    f"{sender.mention} ⚠️ No valid users found in that role!",
                    ephemeral=False
                )
                return

            if len(role_members) > MAX_ROLE_MEMBERS:
                await interaction.response.send_message(
                    f"{sender.mention} ⚠️ Role has **{len(role_members)} members** "
                    f"(max {MAX_ROLE_MEMBERS})",
                    ephemeral=False
                )
                return

            recipients.extend(role_members)

        # ───────── EXTRA USERS ─────────
        extras = [user2, user3, user4]
        for user in extras:
            if user and not user.bot:
                recipients.append(user)

        # ───────── CLEAN & DEDUPE ─────────
        recipients = list({
            m.id: m for m in recipients
            if m.id != sender.id
        }.values())

        if not recipients:
            await interaction.response.send_message(
                f"{sender.mention} ⚠️ No valid recipients!",
                ephemeral=False
            )
            return

        if len(recipients) > MAX_MULTI_USERS:
            await interaction.response.send_message(
                f"{sender.mention} ⚠️ Too many recipients "
                f"(**{len(recipients)}**, max {MAX_MULTI_USERS})",
                ephemeral=False
            )
            return

        # ───────── AMOUNT LOGIC ─────────
        if split:
            per_user_amount = amount / len(recipients)
            total_required = amount
        else:
            per_user_amount = amount
            total_required = amount * len(recipients)

        balance = mysql.get_balance(sender.id, check_update=True)
        if balance < total_required:
            await interaction.response.send_message(
                f"{sender.mention} ⚠️ You need **{total_required:.8f} MWC** to complete this tip!",
                ephemeral=False
            )
            return

        # ───────── PROCESS TIPS ─────────
        for member in recipients:
            mysql.check_for_user(member.id)
            mysql.add_tip(sender.id, member.id, per_user_amount)

        price_usd = await self.fetch_price_usd()
        usd_value = per_user_amount * price_usd

        mentions = ", ".join(m.mention for m in recipients[:5])
        if len(recipients) > 5:
            mentions += f" +{len(recipients) - 5} more"

        mode = "split" if split else "each"

        await interaction.response.send_message(
            f"{sender.mention} tipped **{len(recipients)} users** ({mode} mode)\n"
            f"👥 {mentions}\n"
            f"💰 **{per_user_amount:.8f} MWC per user**\n"
            f"💵 ~${usd_value:,.6f} USD each <:MWC:1451276940236423189>"
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Tip(bot))
