import os

loaded_extensions = []
startup_extensions = [
    f.replace(".py", "") for f in os.listdir("./cogs") if f.endswith(".py")
]
