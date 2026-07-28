#!/usr/bin/env python3
"""Live challenge service for ProvablyFair.

- runs an anvil node (internal),
- exposes JSON-RPC at POST /  (point cast/web3 here),
- POST /launch {"team": "..."} deploys a fresh ProvablyFair for that team,
- GET  /flag?team=...  returns the flag once that team's instance isSolved().

The flag lives here (env FLAG), never in the participant artifact.
"""
import json, os, subprocess, time, atexit
from pathlib import Path
from flask import Flask, request, jsonify, Response
import requests
from web3 import Web3
from eth_account import Account

ROOT = Path(__file__).resolve().parents[1]
ART = json.loads((ROOT / "out" / "ProvablyFair.sol" / "ProvablyFair.json").read_text())
ABI, BYTECODE = ART["abi"], ART["bytecode"]["object"]
FLAG = os.environ.get("FLAG", "SCAN{flag_set_via_env}")
ANVIL_PORT = int(os.environ.get("ANVIL_PORT", "8545"))
PORT = int(os.environ.get("PORT", "8000"))
ANVIL_RPC = f"http://127.0.0.1:{ANVIL_PORT}"

# deterministic anvil accounts (default mnemonic): [0]=service, [1..9]=players
KEYS = [
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
    "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
    "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
    "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
    "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
    "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073d0af2d8f8f",
]
_anvil = None
teams = {}   # team -> {"address":..., "player_key":..., "player_addr":...}
_next = [1]  # next player account index

def _anvil_bin():
    import shutil
    return shutil.which("anvil") or os.path.expanduser("~/.foundry/bin/anvil")

def start_anvil():
    global _anvil
    _anvil = subprocess.Popen(
        [_anvil_bin(), "--silent", "--host", "127.0.0.1", "--port", str(ANVIL_PORT)])
    atexit.register(lambda: _anvil and _anvil.terminate())
    for _ in range(50):
        try:
            if Web3(Web3.HTTPProvider(ANVIL_RPC)).is_connected():
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("anvil did not start")

def w3():
    return Web3(Web3.HTTPProvider(ANVIL_RPC))

app = Flask(__name__)

@app.get("/")
def index():
    return Response(
        "ProvablyFair live challenge.\n\n"
        "1) POST /launch  {\"team\":\"yourname\"}  -> your instance address + a funded key + this RPC URL\n"
        "2) Use this URL as an EVM RPC (cast/web3) to interact with your instance.\n"
        "3) GET /flag?team=yourname  -> the flag, once your vault isSolved().\n",
        mimetype="text/plain")

@app.post("/launch")
def launch():
    body = request.get_json(force=True, silent=True) or {}
    team = str(body.get("team", "")).strip()
    if not team:
        return jsonify(error="provide {'team': '...'}"), 400
    if team in teams:
        return jsonify(**teams[team], note="already launched"), 200
    if _next[0] >= len(KEYS):
        return jsonify(error="no free player slots"), 503
    c = w3()
    svc = Account.from_key(KEYS[0])
    contract = c.eth.contract(abi=ABI, bytecode=BYTECODE)
    tx = contract.constructor().build_transaction({
        "from": svc.address, "nonce": c.eth.get_transaction_count(svc.address),
        "gas": 3_000_000, "gasPrice": c.eth.gas_price})
    signed = svc.sign_transaction(tx)
    rcpt = c.eth.wait_for_transaction_receipt(c.eth.send_raw_transaction(signed.raw_transaction))
    pk = KEYS[_next[0]]; _next[0] += 1
    rec = {"address": rcpt.contractAddress, "player_key": pk,
           "player_addr": Account.from_key(pk).address, "rpc_url": (request.headers.get("X-Forwarded-Proto","https") + "://" + request.host)}
    teams[team] = rec
    return jsonify(**rec), 200

@app.get("/flag")
def flag():
    team = request.args.get("team", "").strip()
    if team not in teams:
        return jsonify(error="unknown team; POST /launch first"), 404
    c = w3()
    v = c.eth.contract(address=teams[team]["address"], abi=ABI)
    if v.functions.isSolved().call():
        return jsonify(flag=FLAG), 200
    return jsonify(error="vault not open yet — keep going"), 200

@app.post("/")
def rpc_proxy():
    r = requests.post(ANVIL_RPC, data=request.get_data(),
                      headers={"Content-Type": "application/json"}, timeout=30)
    return Response(r.content, status=r.status_code, mimetype="application/json")

if __name__ == "__main__":
    start_anvil()
    app.run(host="0.0.0.0", port=PORT)
