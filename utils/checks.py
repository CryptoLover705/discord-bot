from utils import parsing, mysql_module

config = parsing.parse_json("config.json")
mysql = mysql_module.Mysql()


# =====================
# OWNER CHECKS
# =====================
def is_owner(interaction):
    return interaction.user.id in config["owners"]


def is_server_owner(interaction):
    return interaction.guild is not None and interaction.user.id == interaction.guild.owner_id


def in_server(interaction):
    return interaction.guild is not None


def allow_soak(interaction):
    """Check if soak is allowed in this guild"""
    if not interaction.guild:
        return False
    return mysql.check_soak(interaction.guild)
