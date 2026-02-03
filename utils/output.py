from utils import parsing

config = parsing.parse_json("config.json")["logging"]

color = ["\033[1;31;49m", "\033[1;33;49m", "\033[1;32;49m", "\033[1;36;49m"]
message = ["[ERROR]   ", "[WARNING] ", "[SUCCESS] ", "[INFO]    "]


def do_syn(string, var):
    if var <= config["print_level"]:
        print(f"{color[var]}{message[var]}\033[1;37;49m{string}")

    if var <= config["file_level"]:
        with open(config["file"], "a", encoding="utf-8") as f:
            f.write(f"{message[var]}{string}\n")


def error(string):
    do_syn(string, 0)


def warning(string):
    do_syn(string, 1)


def success(string):
    do_syn(string, 2)


def info(string):
    do_syn(string, 3)
