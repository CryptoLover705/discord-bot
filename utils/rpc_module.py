import json
import requests
from utils import parsing


class Rpc:
    def __init__(self):
        config = parsing.parse_json("config.json")["rpc"]

        self.rpc_host = config["rpc_host"]
        self.rpc_port = int(config["rpc_port"])  # ensure int
        self.rpc_user = config["rpc_user"]
        self.rpc_pass = config["rpc_pass"]

        # <-- NO TRAILING SLASH
        self.server_url = f"http://{self.rpc_host}:{self.rpc_port}"
        self.headers = {"content-type": "application/json"}

    # =====================
    # Internal helper
    # =====================
    def _call(self, method: str, params=None):
        """Generic RPC call"""
        if params is None:
            params = []

        payload = json.dumps({"method": method, "params": params, "jsonrpc": "2.0"})
        try:
            response = requests.post(
                self.server_url,
                headers=self.headers,
                data=payload,
                auth=(self.rpc_user, self.rpc_pass),
                timeout=10  # avoid hanging
            )
            response.raise_for_status()
            data = response.json()
            if "error" in data and data["error"] is not None:
                raise Exception(data["error"])
            return data.get("result")
        except requests.RequestException as e:
            raise RuntimeError(f"RPC connection failed: {e}")
        except json.JSONDecodeError:
            raise RuntimeError("Invalid JSON response from RPC server")

    # =====================
    # RPC METHODS
    # =====================
    def listreceivedbyaddress(self, minconf=1, include_empty=False, include_watch_only=False):
        return self._call("listreceivedbyaddress", [minconf, include_empty, include_watch_only])

    def getnewaddress(self, account=""):
        return self._call("getnewaddress", [account])

    def listtransactions(self, account="*", count=10):
        return self._call("listtransactions", [account, count])

    def getconnectioncount(self):
        return self._call("getconnectioncount")

    def getblockcount(self):
        return self._call("getblockcount")

    def getblockchaininfo(self):
        return self._call("getblockchaininfo")

    def getnetworkinfo(self):
        return self._call("getnetworkinfo")

    def getwalletinfo(self):
        return self._call("getwalletinfo")

    # def listmasternodes(self):
    #     return self._call("listmasternodes")

    def getmininginfo(self):
        return self._call("getmininginfo")

    def validateaddress(self, address):
        return self._call("validateaddress", [address])

    def sendtoaddress(self, address, amount):
        return self._call("sendtoaddress", [address, amount])

    def settxfee(self, amount):
        return self._call("settxfee", [amount])
