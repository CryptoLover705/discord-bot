from datetime import datetime, timezone, timedelta
from decimal import Decimal
import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional

from utils import mysql_module, parsing, checks

mysql = mysql_module.Mysql()
config = parsing.parse_json("config.json")
airdrop_cfg = config.get("airdrop", {})


class Airdrop(commands.Cog):
    """Scheduled MWC airdrops with reaction opt-in and role restriction"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pending_airdrops: dict[int, dict] = {}  # airdrop_id -> info
        self.check_airdrops.start()

    # ───────── CREATE AIRDROP ─────────
    @app_commands.command(
        name="airdrop",
        description="Schedule a timed MWC airdrop"
    )
    @app_commands.check(checks.in_server)
    async def airdrop(
        self,
        interaction: discord.Interaction,
        amount: float,
        minutes: int,
        role: Optional[discord.Role] = None
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

        # safety check
        mysql.check_for_user(interaction.user.id)
        total_amount = Decimal(str(amount))
        balance = mysql.get_balance(interaction.user.id, update=True)
        if balance < total_amount:
            await interaction.response.send_message(
                f"⚠️ Insufficient balance. Required: **{total_amount:.8f} MWC**",
                ephemeral=True
            )
            return

        execute_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        airdrop_id = mysql.create_airdrop(
            guild_id=guild.id,
            channel_id=channel.id,
            creator_id=interaction.user.id,
            amount=total_amount,
            split=True,  # now only for claimed users
            role_id=role.id if role else None,
            execute_at=execute_at
        )

        # embed for announcement
        embed = discord.Embed(
            title="💸 MWC Airdrop Incoming!",
            color=discord.Color.green(),
            description=(
                f"**ID:** `{airdrop_id}`\n"
                f"**Creator:** {interaction.user.mention}\n"
                f"**Amount:** {total_amount:.8f} MWC\n"
                f"**Role restricted to:** {role.mention if role else 'everyone'}\n"
                f"**Time to claim:** {minutes} minutes\n\n"
                "React with 💸 to participate!"
            ),
            timestamp=execute_at
        )

        msg = await channel.send(embed=embed)
        await msg.add_reaction("💸")

        # store pending airdrop
        self.pending_airdrops[airdrop_id] = {
            "message_id": msg.id,
            "channel_id": channel.id,
            "guild_id": guild.id,
            "creator_id": interaction.user.id,
            "amount": total_amount,
            "role_id": role.id if role else None,
            "execute_at": execute_at
        }

        await interaction.response.send_message(
            f"✅ Airdrop `{airdrop_id}` scheduled and awaiting reactions!", ephemeral=True
        )

    # ───────── CHECK AIRDROPS ─────────
    @tasks.loop(seconds=30)
    async def check_airdrops(self):
        now = datetime.now(timezone.utc)
        to_remove = []

        for aid, info in list(self.pending_airdrops.items()):
            if info["execute_at"] <= now:
                guild = self.bot.get_guild(info["guild_id"])
                if not guild:
                    to_remove.append(aid)
                    continue

                channel = guild.get_channel(info["channel_id"])
                if not channel:
                    to_remove.append(aid)
                    continue

                try:
                    msg = await channel.fetch_message(info["message_id"])
                except discord.NotFound:
                    to_remove.append(aid)
                    continue

                try:
                    # collect eligible reactors
                    users = []
                    role_id = info["role_id"]
                    for reaction in msg.reactions:
                        if str(reaction.emoji) == "💸":
                            async for user in reaction.users():
                                if user.bot or user.id == info["creator_id"]:
                                    continue
                                member = guild.get_member(user.id)
                                if member and (not role_id or role_id in [r.id for r in member.roles]):
                                    users.append(user.id)

                    users = list(set(users))  # unique users

                    if not users:
                        await channel.send(
                            f"⚠️ No one claimed airdrop `{aid}`! Refunding **{info['amount']:.8f} MWC** to creator."
                        )
                        mysql.add_tip(None, info["creator_id"], info["amount"])
                        mysql.mark_airdrop_executed(aid)
                        to_remove.append(aid)
                        continue

                    # distribute MWC
                    per_user = info["amount"] / len(users)
                    for uid in users:
                        mysql.check_for_user(uid)
                        mysql.add_tip(info["creator_id"], uid, per_user)

                    await channel.send(
                        f"💸 Airdrop `{aid}` executed!\n"
                        f"**{len(users)} users** received **{per_user:.8f} MWC each**"
                    )

                    mysql.mark_airdrop_executed(aid)
                    to_remove.append(aid)

                except Exception as e:
                    await channel.send(
                        f"⚠️ Airdrop `{aid}` failed due to an error: {e}. Refunding creator."
                    )
                    mysql.add_tip(None, info["creator_id"], info["amount"])
                    mysql.mark_airdrop_executed(aid)
                    to_remove.append(aid)

        for aid in to_remove:
            self.pending_airdrops.pop(aid, None)

    @check_airdrops.before_loop
    async def before_check_airdrops(self):
        await self.bot.wait_until_ready()

    # ───────── LIST AIRDROPS ─────────
    @app_commands.command(name="airdrop_list", description="List pending airdrops")
    @app_commands.check(checks.in_server)
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
            minutes_left = max(int(execute_in.total_seconds() / 60), 0)
            embed.add_field(
                name=f"ID {drop['id']}",
                value=(
                    f"Target: {target_label}\n"
                    f"Amount: {drop['amount']:.8f} MWC\n"
                    f"Split: Yes (reaction-based)\n"
                    f"Executes in: {minutes_left} min"
                ),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=False)

    # ───────── CANCEL AIRDROP ─────────
    @app_commands.command(name="airdrop_cancel", description="Cancel a pending airdrop")
    @app_commands.check(checks.in_server)
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
        self.pending_airdrops.pop(airdrop_id, None)
        await interaction.response.send_message(
            f"✅ Airdrop `{airdrop_id}` canceled.", ephemeral=False
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Airdrop(bot))
