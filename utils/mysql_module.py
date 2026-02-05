import pymysql.cursors
import discord
from discord.abc import GuildChannel
from utils import parsing, rpc_module
from decimal import Decimal
import asyncio
from typing import Optional, Union
from datetime import datetime, timezone

rpc = rpc_module.Rpc()
MIN_CONFIRMATIONS_FOR_DEPOSIT = 30


class Mysql:
    """
    Singleton helper for complex database methods
    """
    instance = None

    def __init__(self):
        if not Mysql.instance:
            Mysql.instance = Mysql.__Mysql()

    def __getattr__(self, name):
        return getattr(self.instance, name)

    class __Mysql:
        def __init__(self):
            config = parsing.parse_json('config.json')["mysql"]
            self.__host = config["db_host"]
            self.__port = int(config.get("db_port", 3306))
            self.__db_user = config["db_user"]
            self.__db_pass = config["db_pass"]
            self.__db = config["db"]
            self.txfee = parsing.parse_json('config.json')["txfee"]
            self.deposit_callback = None  # callback for deposit notifications
            self.__setup_connection()

        def __setup_connection(self):
            self.__connection = pymysql.connect(
                host=self.__host,
                port=self.__port,
                user=self.__db_user,
                password=self.__db_pass,
                db=self.__db,
                autocommit=True
            )

        def __setup_cursor(self):
            self.__connection.ping(reconnect=True)
            return self.__connection.cursor(pymysql.cursors.DictCursor)

        # -------------------- USER --------------------
        def make_user(self, snowflake: int, address: str):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (snowflake_pk, balance, balance_unconfirmed, address, allow_soak) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (str(snowflake), '0', '0', address, 1)
                )

        def check_for_user(self, snowflake: int):
            """Ensure user exists; if not, create + new address."""
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT snowflake_pk FROM users WHERE snowflake_pk = %s",
                    (str(snowflake),)
                )
                result = cursor.fetchone()

            if not result:
                address = rpc.getnewaddress(str(snowflake))
                self.make_user(snowflake, address)

        def get_user(self, snowflake: int) -> Optional[dict]:
            """Return full user row for a snowflake."""
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT snowflake_pk, address, balance, balance_unconfirmed, allow_soak "
                    "FROM users WHERE snowflake_pk = %s",
                    (str(snowflake),)
                )
                return cursor.fetchone()

        def get_user_by_address(self, address: str) -> Optional[dict]:
            """Return user row by wallet address."""
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT snowflake_pk, balance, balance_unconfirmed, address, allow_soak "
                    "FROM users WHERE address = %s",
                    (address,)
                )
                return cursor.fetchone()

        def get_address(self, snowflake: int) -> Optional[str]:
            """Get (and ensure) address for user."""
            self.check_for_user(snowflake)
            user = self.get_user(snowflake)
            return user["address"] if user else None

        def set_deposit_callback(self, callback):
            """Register callback for new deposit notifications."""
            self.deposit_callback = callback

        def deposit_callback(self, snowflake, amount, txid, confirmed):
            user = self.bot.get_user(int(snowflake))
            if not user:
                return

            status = "CONFIRMED" if confirmed else "UNCONFIRMED"
            msg = f"💰 Deposit {status}\nAmount: {amount} MWC\nTXID: `{txid}`"
            self.bot.loop.create_task(user.send(msg))

        # -------------------- SERVERS/CHANNELS --------------------
        def check_guild(self, guild_id: int):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT server_id FROM server WHERE server_id = %s",
                    (str(guild_id),)
                )
                result = cursor.fetchone()

            if not result:
                with self.__setup_cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO server (server_id, enable_soak) VALUES (%s, %s)",
                        (str(guild_id), 1)
                    )

        def add_guild(self, guild: discord.Guild):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO server (server_id, enable_soak) VALUES (%s, %s)",
                    (str(guild.id), 1)
                )

        def remove_guild(self, guild: discord.Guild):
            with self.__setup_cursor() as cursor:
                cursor.execute("DELETE FROM server WHERE server_id = %s", (str(guild.id),))
                cursor.execute("DELETE FROM channel WHERE server_id = %s", (str(guild.id),))

        def add_channel(self, channel: GuildChannel):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO channel(channel_id, server_id, enabled) VALUES (%s, %s, 1)",
                    (str(channel.id), str(channel.guild.id))
                )

        def remove_channel(self, channel: GuildChannel):
            with self.__setup_cursor() as cursor:
                cursor.execute("DELETE FROM channel WHERE channel_id = %s", (str(channel.id),))

        # -------------------- BALANCE --------------------
        def set_balance(self, snowflake: int, amount: Decimal, is_unconfirmed=False):
            field = "balance_unconfirmed" if is_unconfirmed else "balance"
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    f"UPDATE users SET {field} = %s WHERE snowflake_pk = %s",
                    (str(amount), str(snowflake))
                )

        def get_confirmed_balance(self, snowflake: int) -> Decimal:
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT balance FROM users WHERE snowflake_pk = %s",
                    (str(snowflake),)
                )
                row = cursor.fetchone()
            return Decimal(row["balance"] or 0) if row else Decimal("0")

        def get_unconfirmed_balance(self, snowflake: int) -> Decimal:
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT balance_unconfirmed FROM users WHERE snowflake_pk = %s",
                    (str(snowflake),)
                )
                row = cursor.fetchone()
            return Decimal(row["balance_unconfirmed"] or 0) if row else Decimal("0")

        def add_to_balance(self, snowflake: int, amount: Decimal):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET balance = balance + %s WHERE snowflake_pk = %s",
                    (str(amount), str(snowflake))
                )

        def remove_from_balance(self, snowflake: int, amount: Decimal):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET balance = balance - %s WHERE snowflake_pk = %s",
                    (str(amount), str(snowflake))
                )

        def add_to_balance_unconfirmed(self, snowflake: int, amount: Decimal):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET balance_unconfirmed = balance_unconfirmed + %s WHERE snowflake_pk = %s",
                    (str(amount), str(snowflake))
                )

        def remove_from_balance_unconfirmed(self, snowflake: int, amount: Decimal):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE users
                    SET balance_unconfirmed = GREATEST(balance_unconfirmed - %s, 0)
                    WHERE snowflake_pk = %s
                    """,
                    (str(amount), str(snowflake))
                )

        # -------------------- DEPOSIT TRACKING --------------------
        async def check_for_updated_balance_async(self):
            """
            Async wrapper: scans all users for deposits without needing a specific snowflake.
            """
            await asyncio.to_thread(self.check_for_updated_balance)

        def check_for_updated_balance(self):
            """
            Scan wallet using listreceivedbyaddress and update balances.
            Handles:
            - Missed deposits on startup
            - Multi-output transactions
            - Auto-confirmation
            - Calls deposit_callback when new deposits are found
            """
            # Fetch all users from DB
            with self.__setup_cursor() as cursor:
                cursor.execute("SELECT snowflake_pk, address FROM users")
                users = cursor.fetchall()
            address_to_snowflake = {u["address"]: u["snowflake_pk"] for u in users}

            try:
                received_list = rpc.listreceivedbyaddress(
                    minconf=0,
                    include_empty=True,
                    include_watch_only=True
                )
            except Exception as e:
                print(f"[RECOVERY] RPC error fetching received list: {e}")
                return

            # Map user addresses to snowflake
            with self.__setup_cursor() as cursor:
                cursor.execute("SELECT snowflake_pk, address FROM users")
                users = cursor.fetchall()
            address_to_snowflake = {u["address"]: u["snowflake_pk"] for u in users}

            for entry in received_list:
                address = entry.get("address")
                txids = entry.get("txids", [])
                if not address or address not in address_to_snowflake or not txids:
                    continue

                snowflake = address_to_snowflake[address]

                for txid in txids:
                    status = self.get_transaction_status_by_txid(txid)
                    if status == "CONFIRMED":
                        continue

                    try:
                        tx = rpc.gettransaction(txid)
                    except Exception as e:
                        print(f"[RECOVERY] Failed to fetch tx {txid}: {e}")
                        continue

                    confirmations = tx.get("confirmations", 0)

                    # Sum amounts for this address (multi-output TX)
                    amount = Decimal("0")
                    for detail in tx.get("details", []):
                        if detail.get("category") == "receive" and detail.get("address") == address:
                            amount += Decimal(detail.get("amount", 0))

                    if amount <= 0:
                        continue

                    # 🟡 New unconfirmed deposit
                    if status == "DOESNT_EXIST" and confirmations < MIN_CONFIRMATIONS_FOR_DEPOSIT:
                        self.add_deposit(snowflake, amount, txid, "UNCONFIRMED")
                        self.add_to_balance_unconfirmed(snowflake, amount)
                        if self.deposit_callback:
                            self.deposit_callback(snowflake, amount, txid, False)

                    # 🟢 New confirmed deposit
                    elif status == "DOESNT_EXIST" and confirmations >= MIN_CONFIRMATIONS_FOR_DEPOSIT:
                        self.add_deposit(snowflake, amount, txid, "CONFIRMED")
                        self.add_to_balance(snowflake, amount)
                        if self.deposit_callback:
                            self.deposit_callback(snowflake, amount, txid, True)

                    # 🔁 Previously unconfirmed, now confirmed
                    elif status == "UNCONFIRMED" and confirmations >= MIN_CONFIRMATIONS_FOR_DEPOSIT:
                        self.confirm_deposit(txid)

                        # 🔄 MOVE funds from unconfirmed → confirmed
                        self.remove_from_balance_unconfirmed(snowflake, amount)
                        self.add_to_balance(snowflake, amount)

                        if self.deposit_callback:
                            self.deposit_callback(snowflake, amount, txid, True)

        def get_transaction_status_by_txid(self, txid: str) -> str:
            with self.__setup_cursor() as cursor:
                cursor.execute("SELECT status FROM deposit WHERE txid = %s", (txid,))
                result = cursor.fetchone()
            return result["status"] if result else "DOESNT_EXIST"

        # -------------------- Deposit/Withdraw/Tip/Soak --------------------
        def add_deposit(self, snowflake: int, amount: Decimal, txid: str, status: str):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO deposit(snowflake_fk, amount, txid, status) VALUES (%s, %s, %s, %s)",
                    (str(snowflake), str(amount), txid, status)
                )

        def confirm_deposit(self, txid: str):
            with self.__setup_cursor() as cursor:
                cursor.execute("UPDATE deposit SET status = %s WHERE txid = %s", ('CONFIRMED', txid))

        def create_withdrawal(self, snowflake: int, address: str, amount: Decimal) -> Optional[str]:
            if not rpc.settxfee(self.txfee):
                return None
            txid = rpc.sendtoaddress(address, float(amount - self.txfee))
            if not txid:
                return None
            self.remove_from_balance(snowflake, amount)
            return self.add_withdrawal(snowflake, amount, txid)

        def add_withdrawal(self, snowflake: int, amount: Decimal, txid: str) -> str:
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO withdrawal(snowflake_fk, amount, txid) VALUES (%s, %s, %s)",
                    (str(snowflake), str(amount), txid)
                )
            return txid

        def add_tip(self, from_snowflake: int, to_snowflake: int, amount: Decimal):
            self.remove_from_balance(from_snowflake, amount)
            self.add_to_balance(to_snowflake, amount)
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO tip(snowflake_from_fk, snowflake_to_fk, amount) VALUES (%s, %s, %s)",
                    (str(from_snowflake), str(to_snowflake), str(amount))
                )

        def check_soak(self, guild_id: int) -> bool:
            self.check_guild(guild_id)
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT enable_soak FROM server WHERE server_id = %s",
                    (str(guild_id),)
                )
                result = cursor.fetchone()

            return bool(result["enable_soak"]) if result else False

        def set_soak(self, guild_id: int, enable: bool):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "UPDATE server SET enable_soak = %s WHERE server_id = %s",
                    (int(enable), str(guild_id))
                )

        def set_soakme(self, snowflake: int, enable: bool):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET allow_soak = %s WHERE snowflake_pk = %s",
                    (int(enable), str(snowflake))
                )

        def check_soakme(self, snowflake: int) -> bool:
            with self.__setup_cursor() as cursor:
                cursor.execute("SELECT allow_soak FROM users WHERE snowflake_pk = %s", (str(snowflake),))
                result = cursor.fetchone()
            return bool(result['allow_soak']) if result else False
        
        def recover_missed_deposits(self):
            print("[RECOVERY] Scanning for missed deposits...")

            # Fetch all users
            with self.__setup_cursor() as cursor:
                cursor.execute("SELECT snowflake_pk, address FROM users")
                users = cursor.fetchall()
            address_to_snowflake = {u["address"]: u["snowflake_pk"] for u in users}

            try:
                # ✅ Only pass 3 arguments to listreceivedbyaddress
                received_list = rpc.listreceivedbyaddress(
                    minconf=0,
                    include_empty=True,
                    include_watch_only=True
                )
            except Exception as e:
                print(f"[RECOVERY] RPC error fetching received list: {e}")
                return

            # Process all received entries
            for entry in received_list:
                address = entry.get("address")
                txids = entry.get("txids", [])

                # Skip addresses that are not in our DB
                if not address or address not in address_to_snowflake or not txids:
                    continue

                snowflake = address_to_snowflake[address]

                for txid in txids:
                    # Skip if deposit already recorded
                    if self.get_transaction_status_by_txid(txid) != "DOESNT_EXIST":
                        continue

                    try:
                        tx = rpc.gettransaction(txid)
                    except Exception as e:
                        print(f"[RECOVERY] Failed to fetch tx {txid}: {e}")
                        continue

                    confirmations = tx.get("confirmations", 0)

                    # Sum multi-output amounts
                    amount = Decimal("0")
                    for d in tx.get("details", []):
                        if d.get("category") == "receive" and d.get("address") == address:
                            amount += Decimal(d.get("amount", 0))

                    if amount <= 0:
                        continue

                    # Unconfirmed
                    if confirmations < MIN_CONFIRMATIONS_FOR_DEPOSIT:
                        self.add_to_balance_unconfirmed(snowflake, amount)
                        self.add_deposit(snowflake, amount, txid, "UNCONFIRMED")
                    else:  # Confirmed
                        self.add_to_balance(snowflake, amount)
                        self.add_deposit(snowflake, amount, txid, "CONFIRMED")

            print("[RECOVERY] Complete")

        # -------------------- AIRDROPS --------------------
        def create_airdrop(
            self,
            guild_id: int,
            channel_id: int,
            creator_id: int,
            amount: Decimal,
            split: bool,
            role_id: Optional[int],
            execute_at: datetime
        ) -> int:
            """Insert a scheduled airdrop and return its ID"""
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO airdrops
                    (guild_id, channel_id, creator_id, amount, split, role_id, execute_at, executed)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 0)
                    """,
                    (guild_id, channel_id, creator_id, str(amount), int(split), role_id, execute_at)
                )
                return cursor.lastrowid

        def fetch_pending_airdrops(self, now: datetime):
            """Get a list of airdrops ready to execute"""
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM airdrops WHERE executed = 0 AND execute_at <= %s",
                    (now,)
                )
                return cursor.fetchall()

        def fetch_airdrop_by_id(self, airdrop_id: int):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM airdrops WHERE id = %s",
                    (airdrop_id,)
                )
                return cursor.fetchone()

        def mark_airdrop_executed(self, airdrop_id: int):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "UPDATE airdrops SET executed = 1 WHERE id = %s",
                    (airdrop_id,)
                )
