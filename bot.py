import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands

from utils import output, parsing, mysql_module, g
import os
import traceback
import database

from datetime import datetime, timezone
from decimal import Decimal

from utils.mysql_module import MIN_CONFIRMATIONS_FOR_DEPOSIT, Mysql

mysql = Mysql()

# =========================
# CONFIG
# =========================
config = parsing.parse_json("config.json")
airdrop_cfg = config.get("airdrop", {})

# =========================
# INTENTS
# =========================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True   # REQUIRED for airdrops
intents.presences = True
intents.messages = True

# =========================
# BOT INITIALIZATION
# =========================
class MinerBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=["!", "?"],
            description=config["description"],
            intents=intents
        )

    async def setup_hook(self):
        """Runs before the bot connects to Discord"""
        output.info(f"Loading {len(g.startup_extensions)} extension(s)...")

        for extension in g.startup_extensions:
            try:
                await self.load_extension(f"cogs.{extension}")
                g.loaded_extensions.append(extension)
            except Exception:
                output.error(
                    f"Failed to load extension {extension}\n{traceback.format_exc()}"
                )

        await self.tree.sync()
        output.success(
            f"Successfully loaded: {', '.join(g.loaded_extensions)}"
        )
        output.success("Slash commands synced successfully.")

        # Start airdrop loop only if enabled
        if airdrop_cfg.get("enabled", True):
            self.airdrop_loop.start()
            output.info("Airdrop background loop started")

    # =========================
    # AIRDROP BACKGROUND LOOP
    # =========================
    @tasks.loop(seconds=airdrop_cfg.get("loop_interval_seconds", 30))
    async def airdrop_loop(self):
        now = datetime.now(timezone.utc)
        pending = Mysql.fetch_pending_airdrops(now)

        for drop in pending:
            try:
                await self.execute_airdrop(drop)
            except Exception:
                output.error(f"Airdrop execution error:\n{traceback.format_exc()}")

    async def execute_airdrop(self, drop: dict):
        # Safety: disabled
        if not airdrop_cfg.get("enabled", True):
            Mysql.mark_airdrop_executed(drop["id"])
            return

        guild = self.get_guild(int(drop["guild_id"]))
        if not guild:
            Mysql.mark_airdrop_executed(drop["id"])
            return

        channel = guild.get_channel(int(drop["channel_id"]))
        if not channel:
            Mysql.mark_airdrop_executed(drop["id"])
            return

        role = guild.get_role(int(drop["role_id"])) if drop["role_id"] else None

        # Safety: guild-wide airdrops
        if role is None and not airdrop_cfg.get("allow_guild_wide", False):
            await channel.send("⚠️ Guild-wide airdrops are disabled.")
            Mysql.mark_airdrop_executed(drop["id"])
            return

        members = [
            m for m in (role.members if role else guild.members)
            if not m.bot
        ]

        if not members:
            Mysql.mark_airdrop_executed(drop["id"])
            return

        # Safety: max recipients
        if (
            airdrop_cfg.get("use_max_recipients", True)
            and len(members) > airdrop_cfg.get("max_recipients", 50)
        ):
            await channel.send(
                f"⚠️ Airdrop cancelled: too many recipients "
                f"({len(members)} / {airdrop_cfg['max_recipients']})"
            )
            Mysql.mark_airdrop_executed(drop["id"])
            return

        split = bool(drop["split"])
        total_amount = Decimal(drop["amount"])

        per_user_amount = (
            total_amount / len(members)
            if split
            else total_amount
        )

        total_required = (
            total_amount
            if split
            else per_user_amount * len(members)
        )

        Mysql.check_for_user(drop["creator_id"])
        balance = Mysql.get_balance(drop["creator_id"], check_update=True)

        if balance < total_required:
            await channel.send("⚠️ **Airdrop failed:** insufficient balance.")
            Mysql.mark_airdrop_executed(drop["id"])
            return

        for member in members:
            Mysql.check_for_user(member.id)
            Mysql.add_tip(drop["creator_id"], member.id, per_user_amount)

        Mysql.mark_airdrop_executed(drop["id"])

        await channel.send(
            f"🎉 **Airdrop Complete!**\n"
            f"👥 {len(members)} users received "
            f"**{per_user_amount:.8f} MWC** <:MWC:1451276940236423189>"
        )


# =========================
# BOT INSTANCE
# =========================
bot = MinerBot()
Mysql = mysql_module.Mysql()

# =========================
# CLEAN LOG FILE
# =========================
try:
    os.remove("log.txt")
except FileNotFoundError:
    pass

if "__pycache__" in g.startup_extensions:
    g.startup_extensions.remove("__pycache__")
g.startup_extensions = [ext.replace(".py", "") for ext in g.startup_extensions]

# =========================
# EVENTS
# =========================
@bot.event
async def on_ready():
    output.success(f"Logged in as {bot.user} ({bot.user.id})")
    output.info(
        f"Invite URL: https://discord.com/oauth2/authorize"
        f"?client_id={bot.user.id}&permissions=0&scope=bot%20applications.commands"
    )

@bot.event
async def on_ready():
    async def deposit_notify(snowflake, amount: Decimal, txid: str, confirmed: bool):
        user = await bot.fetch_user(int(snowflake))
        if not user:
            return

        status = "CONFIRMED ✅" if confirmed else "UNCONFIRMED ⏳"

        await user.send(
            f"💰 **MWC Deposit Received**\n\n"
            f"Amount: `{amount:.8f} MWC`\n"
            f"Status: **{status}**\n"
            f"TXID: `{txid}`\n\n"
            f"{'Funds are now spendable.' if confirmed else f'Funds will be credited after {MIN_CONFIRMATIONS_FOR_DEPOSIT} confirmations.'}"
        )

    # bind callback
    mysql.set_deposit_callback(
        lambda *args: asyncio.create_task(deposit_notify(*args))
    )

    print("✅ Deposit notifications enabled")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    mysql.recover_missed_deposits()

@bot.event
async def on_guild_join(guild: discord.Guild):
    output.info(f"Added to {guild.name}")
    Mysql.add_server(guild)
    for channel in guild.channels:
        Mysql.add_channel(channel)

@bot.event
async def on_guild_remove(guild: discord.Guild):
    Mysql.remove_server(guild)
    output.info(f"Removed from {guild.name}")

@bot.event
async def on_guild_channel_create(channel):
    if isinstance(channel, discord.DMChannel):
        return
    Mysql.add_channel(channel)
    output.info(f"Channel {channel.name} added to {channel.guild.name}")

@bot.event
async def on_guild_channel_delete(channel):
    Mysql.remove_channel(channel)
    output.info(f"Channel {channel.name} deleted from {channel.guild.name}")

# =========================
# GLOBAL SLASH ERROR HANDLER
# =========================
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    output.error(f"Slash command error: {error}")

    if interaction.response.is_done():
        await interaction.followup.send(
            "❌ An unexpected error occurred. Please try again later.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "❌ An unexpected error occurred. Please try again later.",
            ephemeral=True
        )

# =========================
# STARTUP
# =========================
database.run()
bot.run(config["discord"]["token"])
