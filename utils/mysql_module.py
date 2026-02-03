import pymysql.cursors
import discord
from discord.abc import GuildChannel
from utils import parsing, rpc_module
from decimal import Decimal
import asyncio
from typing import Optional, Union

rpc = rpc_module.Rpc()
MIN_CONFIRMATIONS_FOR_DEPOSIT = 2


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

        # -------------------- User --------------------
        def make_user(self, snowflake: int, address: str):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (snowflake_pk, balance, balance_unconfirmed, address, allow_soak) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (str(snowflake), '0', '0', address, 1)
                )

        def check_for_user(self, snowflake: int):
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT snowflake_pk, address, balance, balance_unconfirmed, allow_soak "
                    "FROM users WHERE snowflake_pk = %s",
                    (str(snowflake),)
                )
                result = cursor.fetchone()

            if not result:
                address = rpc.getnewaddress(str(snowflake))
                self.make_user(snowflake, address)

        def get_user(self, snowflake: int) -> Optional[dict]:
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT snowflake_pk, balance, balance_unconfirmed, address, allow_soak "
                    "FROM users WHERE snowflake_pk = %s",
                    (str(snowflake),)
                )
                return cursor.fetchone()

        def get_user_by_address(self, address: str) -> Optional[dict]:
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT snowflake_pk, balance, balance_unconfirmed, address, allow_soak "
                    "FROM users WHERE address = %s",
                    (address,)
                )
                return cursor.fetchone()

        def get_address(self, snowflake: int) -> Optional[str]:
            user = self.get_user(snowflake)
            return user.get("address") if user else None

        # -------------------- Servers/Channels --------------------
        def check_guild(self, guild: discord.Guild):
            if guild is None:
                return
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "SELECT server_id, enable_soak FROM server WHERE server_id = %s",
                    (str(guild.id),)
                )
                result = cursor.fetchone()
            if not result:
                self.add_guild(guild)

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

        # -------------------- Balance --------------------
        def set_balance(self, snowflake: int, amount: Union[int, Decimal], is_unconfirmed=False):
            field = "balance_unconfirmed" if is_unconfirmed else "balance"
            with self.__setup_cursor() as cursor:
                cursor.execute(f"UPDATE users SET {field} = %s WHERE snowflake_pk = %s", (amount, str(snowflake)))

        def get_balance(self, snowflake: int, check_update=False, unconfirmed=False) -> Decimal:
            if check_update:
                self.check_for_updated_balance(snowflake)
            user = self.get_user(snowflake)
            if not user:
                return Decimal(0)
            return Decimal(user["balance_unconfirmed"] if unconfirmed else user["balance"])

        def add_to_balance(self, snowflake: int, amount: Union[int, Decimal], is_unconfirmed=False):
            current = self.get_balance(snowflake, unconfirmed=is_unconfirmed)
            self.set_balance(snowflake, current + Decimal(amount), is_unconfirmed)

        def remove_from_balance(self, snowflake: int, amount: Union[int, Decimal]):
            current = self.get_balance(snowflake)
            self.set_balance(snowflake, current - Decimal(amount))

        def add_to_balance_unconfirmed(self, snowflake: int, amount: Union[int, Decimal]):
            self.add_to_balance(snowflake, amount, is_unconfirmed=True)

        def remove_from_balance_unconfirmed(self, snowflake: int, amount: Union[int, Decimal]):
            self.add_to_balance(snowflake, -Decimal(amount), is_unconfirmed=True)

        async def check_for_updated_balance_async(self, snowflake: int):
            """
            Async wrapper for updating balances from RPC.
            """
            await asyncio.to_thread(self.check_for_updated_balance, snowflake)

        def check_for_updated_balance(self, snowflake: int):
            tx_list = rpc.listtransactions(str(snowflake), 100)
            for tx in tx_list:
                if tx["category"] != "receive":
                    continue
                txid = tx["txid"]
                amount = Decimal(tx["amount"])
                confirmations = tx["confirmations"]
                address = tx["address"]
                status = self.get_transaction_status_by_txid(txid)
                user = self.get_user_by_address(address)
                if not user:
                    continue
                snowflake_cur = user["snowflake_pk"]

                if status == "DOESNT_EXIST" and confirmations >= MIN_CONFIRMATIONS_FOR_DEPOSIT:
                    self.add_to_balance(snowflake_cur, amount)
                    self.add_deposit(snowflake_cur, amount, txid, 'CONFIRMED')
                elif status == "DOESNT_EXIST" and confirmations < MIN_CONFIRMATIONS_FOR_DEPOSIT:
                    self.add_deposit(snowflake_cur, amount, txid, 'UNCONFIRMED')
                    self.add_to_balance_unconfirmed(snowflake_cur, amount)
                elif status == "UNCONFIRMED" and confirmations >= MIN_CONFIRMATIONS_FOR_DEPOSIT:
                    self.add_to_balance(snowflake_cur, amount)
                    self.remove_from_balance_unconfirmed(snowflake_cur, amount)
                    self.confirm_deposit(txid)

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

        def check_soak(self, guild: discord.Guild) -> bool:
            self.check_guild(guild)
            with self.__setup_cursor() as cursor:
                cursor.execute("SELECT enable_soak FROM server WHERE server_id = %s", (str(guild.id),))
                result = cursor.fetchone()
            return bool(result['enable_soak']) if result else False

        def set_soak(self, guild: discord.Guild, enable: bool):
            self.check_guild(guild)
            with self.__setup_cursor() as cursor:
                cursor.execute(
                    "UPDATE server SET enable_soak = %s WHERE server_id = %s",
                    (int(enable), str(guild.id))
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
