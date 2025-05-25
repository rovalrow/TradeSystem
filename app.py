# ── app.py ────────────────────────────────────────────────────────────
"""
Stateless-style trading API for two players who are **in-game at the same
time**.  Each player is identified by their Roblox name string.

┌────────┐          set_target          ┌────────┐
│ Alice  │ ───────────────────────────► │ Bob    │
└────────┘ ◄─────────────────────────── └────────┘
          offer / remove / accept  (live-polled)

When BOTH sides .accepted == True the clients will:
  1. equip every item they offered
  2. FireServer('GivePet', otherPlayer) for each item (client side)
  3. POST /reset so a new trade can start
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading, time

app = Flask(__name__)
CORS(app)

# ──────────────────────────────────────────────────────────────────────
# In-memory “DB”.  Key = player name.  (If you deploy to production,
# switch to Redis / Dynamo / Postgres so data isn’t lost on restart.)
#   { player : {target:str, offer:list[str], accepted:bool, ts:float } }
trades = {}
OFFER_TTL = 30 * 60          # 30 minutes until stale trade auto-clears

# Helpers ­–––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
def fresh(p):                           # ensure entry exists & isn’t stale
    now = time.time()
    if p not in trades or now - trades[p]["ts"] > OFFER_TTL:
        trades[p] = {"target":"", "offer":[], "accepted":False, "ts":now}
    trades[p]["ts"] = now
    return trades[p]

def counterpart(p):
    tgt = trades.get(p, {}).get("target")
    if tgt and trades.get(tgt, {}).get("target") == p:
        return tgt
    return None

# Routes ­–––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
@app.route("/set_target", methods=["POST"])
def set_target():
    d = request.get_json()
    user, target = d["user"], d["target"]
    fresh(user)["target"] = target
    return jsonify(ok=True)

@app.route("/offer", methods=["POST"])
def add_offer():
    d = request.get_json()
    user, item = d["user"], d["item"]
    u = fresh(user)
    if item not in u["offer"]:
        u["offer"].append(item)
    return jsonify(ok=True, offer=u["offer"])

@app.route("/remove_offer", methods=["POST"])
def remove_offer():
    d = request.get_json()
    user, item = d["user"], d["item"]
    u = fresh(user)
    if item in u["offer"]:
        u["offer"].remove(item)
    return jsonify(ok=True, offer=u["offer"])

@app.route("/accept", methods=["POST"])
def accept():
    d = request.get_json()
    fresh(d["user"])["accepted"] = True
    return jsonify(ok=True)

@app.route("/status", methods=["GET"])
def status():
    user = request.args["user"]
    u = fresh(user)
    other = counterpart(user)
    both = other and u["accepted"] and trades[other]["accepted"]
    return jsonify(
        other=other,
        myOffer=u["offer"],
        otherOffer=trades.get(other, {}).get("offer", []),
        iAccepted=u["accepted"],
        otherAccepted=trades.get(other, {}).get("accepted", False),
        bothAccepted=both
    )

@app.route("/reset", methods=["POST"])
def reset():
    d = request.get_json()
    trades.pop(d["user"], None)
    return jsonify(ok=True)

# Optional: background task to purge stale sessions
def janitor():
    while True:
        time.sleep(60)
        now = time.time()
        stale = [p for p,v in trades.items() if now - v["ts"] > OFFER_TTL]
        for p in stale: trades.pop(p, None)
threading.Thread(target=janitor, daemon=True).start()

if __name__ == "__main__":
    app.run("0.0.0.0", 5000)
# ──────────────────────────────────────────────────────────────────────
