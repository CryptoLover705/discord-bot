import discord
from discord import app_commands
from discord.ext import commands
from typing import Union
from utils import rpc_module, mysql_module, parsing, checks
import aiohttp
import re

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

    @app_commands.command(
        name="tip",
        description="Tip users or roles MWC coins"
    )
    @app_commands.check(checks.in_server)
    async def tip(
        self,
        interaction: discord.Interaction,
        amount: float,
        user: discord.Member | None = None,
        users: str | None = None,  # comma-separated user mentions
        role: discord.Role | None = None
    ):
        allowed_channels = parsing.parse_json('config.json')['command_channels']['tip']
        if interaction.channel.name not in allowed_channels:
            await interaction.response.send_message(
                "You cannot use this command in this channel!",
                ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                f"{interaction.user.mention} ⚠️ Tip amount must be greater than 0!",
                ephemeral=True
            )
            return

        sender = interaction.user
        mysql.check_for_user(sender.id)

        recipients: list[discord.Member] = []

        # ----- SINGLE USER -----
        if user:
            recipients.append(user)

        # ----- MULTI USERS -----
        if users:
            user_ids = [int(re.sub(r"[<@!>]", "", u.strip())) for u in users.split(",") if u.strip()]
            for uid in user_ids:
                member = interaction.guild.get_member(uid)
                if member and not member.bot and member.id != sender.id:
                    recipients.append(member)

        # ----- ROLE -----
        if role:
            role_members = [m for m in role.members if not m.bot and m.id != sender.id]
            if len(role_members) > MAX_ROLE_MEMBERS:
                await interaction.response.send_message(
                    f"{sender.mention} ⚠️ Role has **{len(role_members)} members** "
                    f"(max {MAX_ROLE_MEMBERS})",
                    ephemeral=True
                )
                return
            recipients.extend(role_members)

        # ----- CLEAN & DEDUPE -----
        recipients = list({m.id: m for m in recipients}.values())

        if not recipients:
            await interaction.response.send_message(
                f"{sender.mention} ⚠️ No valid recipients!",
                ephemeral=True
            )
            return

        if len(recipients) > MAX_MULTI_USERS:
            await interaction.response.send_message(
                f"{sender.mention} ⚠️ Too many recipients "
                f"(**{len(recipients)}**, max {MAX_MULTI_USERS})",
                ephemeral=True
            )
            return

        # ----- SPLIT LOGIC -----
        if len(recipients) > 1:
            per_user_amount = amount / len(recipients)
            total_required = amount
        else:
            per_user_amount = amount
            total_required = amount

        # ----- CHECK SENDER BALANCE -----
        balance = mysql.get_balance(sender.id, update=True)
        if balance < total_required:
            await interaction.response.send_message(
                f"{sender.mention} ⚠️ You need **{total_required:.8f} MWC** to complete this tip!",
                ephemeral=True
            )
            return

        # ----- PROCESS TIPS -----
        for member in recipients:
            mysql.check_for_user(member.id)
            mysql.add_tip(sender.id, member.id, per_user_amount)

        price_usd = await self.fetch_price_usd()
        usd_value = per_user_amount * price_usd

        mentions = ", ".join(m.mention for m in recipients[:5])
        if len(recipients) > 5:
            mentions += f" +{len(recipients) - 5} more"

        mode = "split" if len(recipients) > 1 else "single"

        await interaction.response.send_message(
            f"{sender.mention} tipped **{len(recipients)} users** ({mode} mode)\n"
            f"👥 {mentions}\n"
            f"💰 **{per_user_amount:.8f} MWC per user**\n"
            f"💵 ~${usd_value:,.6f} USD each <:MWC:1451276940236423189>"
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Tip(bot))
