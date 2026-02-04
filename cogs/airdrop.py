from datetime import datetime, timezone, timedelta
from decimal import Decimal
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from utils import mysql_module, parsing, checks

mysql = mysql_module.Mysql()
config = parsing.parse_json("config.json")
airdrop_cfg = config.get("airdrop", {})


class Airdrop(commands.Cog):
    """Scheduled MWC airdrops with management commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ───────── CREATE AIRDROP ─────────
    @app_commands.command(
        name="airdrop",
        description="Schedule a timed MWC airdrop"
    )
    @app_commands.checks.dynamic_check(lambda i: checks.in_server(i))
    async def airdrop(
        self,
        interaction: discord.Interaction,
        amount: float,
        minutes: int,
        role: Optional[discord.Role] = None,
        split: bool = True
    ):
        if amount <= 0 or minutes <= 0:
            await interaction.response.send_message(
                "⚠️ Amount and time must be greater than zero.", ephemeral=True
            )
            return

        guild = interaction.guild
        channel = interaction.channel
        if not guild or not channel:
            await interaction.response.send_message(
                "⚠️ This command can only be used in a server.", ephemeral=True
            )
            return

        # resolve members
        members = (
            [m for m in role.members if not m.bot]
            if role else [m for m in guild.members if not m.bot]
        )
        if not members:
            await interaction.response.send_message(
                "⚠️ No eligible users found for this airdrop.", ephemeral=True
            )
            return

        # safety check
        max_recipients = airdrop_cfg.get("max_recipients", 50)
        if airdrop_cfg.get("use_max_recipients", True) and len(members) > max_recipients:
            await interaction.response.send_message(
                f"⚠️ Too many recipients ({len(members)} / {max_recipients}).",
                ephemeral=True
            )
            return

        mysql.check_for_user(interaction.user.id)

        total_amount = Decimal(str(amount))
        per_user = total_amount / len(members) if split else total_amount
        total_required = total_amount if split else per_user * len(members)

        balance = mysql.get_balance(interaction.user.id, check_update=True)
        if balance < total_required:
            await interaction.response.send_message(
                f"⚠️ Insufficient balance. Required: **{total_required:.8f} MWC**",
                ephemeral=True
            )
            return

        execute_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        airdrop_id = mysql.create_airdrop(
            guild_id=guild.id,
            channel_id=channel.id,
            creator_id=interaction.user.id,
            amount=total_amount,
            split=split,
            role_id=role.id if role else None,
            execute_at=execute_at
        )

        target_label = role.mention if role else "everyone"
        await interaction.response.send_message(
            f"⏳ **Airdrop Scheduled!**\n"
            f"ID: `{airdrop_id}`\n"
            f"🎯 Target: {target_label}\n"
            f"👥 Recipients: **{len(members)}**\n"
            f"💰 Total: **{total_amount:.8f} MWC**\n"
            f"🔀 Mode: **{'Split' if split else 'Each'}**\n"
            f"⏱️ Executes in **{minutes} minutes**"
        )

    # ───────── LIST AIRDROPS ─────────
    @app_commands.command(
        name="airdrop_list",
        description="List your pending airdrops"
    )
    @app_commands.checks.dynamic_check(lambda i: checks.in_server(i))
    async def airdrop_list(self, interaction: discord.Interaction):
        drops = mysql.fetch_airdrops_by_creator(interaction.user.id, executed=False)
        if not drops:
            await interaction.response.send_message(
                "You have no pending airdrops.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Pending Airdrops",
            color=discord.Color.blurple()
        )
        for drop in drops:
            target_label = f"<@&{drop['role_id']}>" if drop['role_id'] else "everyone"
            execute_in = drop['execute_at'] - datetime.now(timezone.utc)
            minutes_left = int(execute_in.total_seconds() / 60)
            embed.add_field(
                name=f"ID {drop['id']}",
                value=(
                    f"Target: {target_label}\n"
                    f"Amount: {drop['amount']:.8f} MWC\n"
                    f"Split: {'Yes' if drop['split'] else 'No'}\n"
                    f"Executes in: {minutes_left} min"
                ),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ───────── CANCEL AIRDROP ─────────
    @app_commands.command(
        name="airdrop_cancel",
        description="Cancel a pending airdrop by ID"
    )
    @app_commands.checks.dynamic_check(lambda i: checks.in_server(i))
    async def airdrop_cancel(self, interaction: discord.Interaction, airdrop_id: int):
        drop = mysql.fetch_airdrop_by_id(airdrop_id)
        if not drop or drop["creator_id"] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Airdrop not found or you do not own it.", ephemeral=True
            )
            return

        if drop["executed"]:
            await interaction.response.send_message(
                "❌ This airdrop has already executed.", ephemeral=True
            )
            return

        mysql.mark_airdrop_executed(airdrop_id)
        await interaction.response.send_message(
            f"✅ Airdrop `{airdrop_id}` canceled.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Airdrop(bot))
