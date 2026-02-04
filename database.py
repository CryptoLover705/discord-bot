import pymysql.cursors
import warnings
from utils import parsing, output

config = parsing.parse_json('config.json')["mysql"]
host = config["db_host"]
try:
    port = int(config["db_port"])
except KeyError:
    port = 3306
db_user = config["db_user"]
db_pass = config["db_pass"]
db = config["db"]
connection = pymysql.connect(
    host=host,
    port=port,
    user=db_user,
    password=db_pass,
    db=db)
cursor = connection.cursor(pymysql.cursors.DictCursor)

#cursor.execute("DROP DATABASE IF EXISTS {};".format(database))
#cursor.execute("CREATE DATABASE IF NOT EXISTS {};".format(database))
#conn.commit()

#cursor.execute("USE {};".format(database))


def run():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')

        # ---------------- USERS ----------------
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            snowflake_pk BIGINT UNSIGNED NOT NULL,
            balance DECIMAL(20, 8) NOT NULL DEFAULT 0,
            balance_unconfirmed DECIMAL(20, 8) NOT NULL DEFAULT 0,
            address VARCHAR(128) NOT NULL,
            allow_soak TINYINT(1) NOT NULL DEFAULT 1,
            PRIMARY KEY (snowflake_pk),
            UNIQUE KEY uq_users_address (address)
        )
        """)

        # ---------------- DEPOSITS ----------------
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS deposit (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            snowflake_fk BIGINT UNSIGNED NOT NULL,
            amount DECIMAL(20, 8) NOT NULL,
            txid VARCHAR(256) NOT NULL,
            status VARCHAR(20) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_deposit_txid (txid),
            FOREIGN KEY (snowflake_fk) REFERENCES users(snowflake_pk)
                ON DELETE CASCADE
        )
        """)

        # ---------------- WITHDRAWALS ----------------
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS withdrawal (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            snowflake_fk BIGINT UNSIGNED NOT NULL,
            amount DECIMAL(20, 8) NOT NULL,
            txid VARCHAR(256) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_withdraw_txid (txid),
            FOREIGN KEY (snowflake_fk) REFERENCES users(snowflake_pk)
                ON DELETE CASCADE
        )
        """)

        # ---------------- TIPS ----------------
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tip (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            snowflake_from_fk BIGINT UNSIGNED NOT NULL,
            snowflake_to_fk BIGINT UNSIGNED NOT NULL,
            amount DECIMAL(20, 8) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            FOREIGN KEY (snowflake_from_fk) REFERENCES users(snowflake_pk)
                ON DELETE CASCADE,
            FOREIGN KEY (snowflake_to_fk) REFERENCES users(snowflake_pk)
                ON DELETE CASCADE
        )
        """)

        # ---------------- SERVERS ----------------
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS server (
            server_id BIGINT UNSIGNED NOT NULL,
            enable_soak TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (server_id)
        )
        """)

        # ---------------- CHANNELS ----------------
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS channel (
            channel_id BIGINT UNSIGNED NOT NULL,
            server_id BIGINT UNSIGNED NOT NULL,
            enabled TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (channel_id),
            FOREIGN KEY (server_id) REFERENCES server(server_id)
                ON DELETE CASCADE
        )
        """)

        # ---------------- AIRDROPS ----------------
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS airdrops (
            id INT UNSIGNED NOT NULL AUTO_INCREMENT,
            guild_id BIGINT UNSIGNED NOT NULL,
            channel_id BIGINT UNSIGNED NOT NULL,
            creator_id BIGINT UNSIGNED NOT NULL,
            amount DECIMAL(20, 8) NOT NULL,
            split TINYINT(1) NOT NULL DEFAULT 0,
            role_id BIGINT UNSIGNED DEFAULT NULL,
            execute_at DATETIME NOT NULL,
            executed TINYINT(1) NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_airdrops_execute (execute_at, executed),
            KEY idx_airdrops_guild (guild_id)
        )
        """)

        connection.commit()
