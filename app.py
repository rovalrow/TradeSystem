from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
import os
import datetime
import threading
import time

app = Flask(__name__)
CORS(app)

# Supabase environment variables (configure in Render)
SUPABASE_URL = os.environ.get("https://ikxxvgflnpfyncnaqfxx.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlreHh2Z2ZsbnBmeW5jbmFxZnh4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDYxOTE3NTMsImV4cCI6MjA2MTc2Nzc1M30.YiF46ggItUYuKLfdD_6oOxq2xGX7ac6yqqtEGeM_dg8")  # ⚠️ You may want to remove hardcoded key for security
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

OFFER_TTL = 30 * 60  # 30 minutes

def fresh(player):
    now = datetime.datetime.utcnow().isoformat()
    res = supabase.table("trades").select("*").eq("player", player).execute()
    if not res.data:
        supabase.table("trades").insert({
            "player": player,
            "target": "",
            "offer": [],
            "accepted": False,
            "updated_at": now
        }).execute()
    else:
        supabase.table("trades").update({"updated_at": now}).eq("player", player).execute()

def get_counterpart(player):
    res = supabase.table("trades").select("target").eq("player", player).execute()
    if not res.data:
        return None
    target = res.data[0].get("target")
    if not target:
        return None
    reverse = supabase.table("trades").select("target").eq("player", target).execute()
    if reverse.data and reverse.data[0].get("target") == player:
        return target
    return None

@app.route("/set_target", methods=["POST"])
def set_target():
    d = request.get_json()
    user, target = d["user"], d["target"]
    fresh(user)
    supabase.table("trades").update({
        "target": target,
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).eq("player", user).execute()
    return jsonify(ok=True)

@app.route("/offer", methods=["POST"])
def add_offer():
    d = request.get_json()
    user, item = d["user"], d["item"]
    fresh(user)
    current = supabase.table("trades").select("offer").eq("player", user).single().execute()
    offer = current.data["offer"] or []
    if item not in offer:
        offer.append(item)
    supabase.table("trades").update({
        "offer": offer,
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).eq("player", user).execute()
    return jsonify(ok=True, offer=offer)

@app.route("/remove_offer", methods=["POST"])
def remove_offer():
    d = request.get_json()
    user, item = d["user"], d["item"]
    fresh(user)
    current = supabase.table("trades").select("offer").eq("player", user).single().execute()
    offer = current.data["offer"] or []
    if item in offer:
        offer.remove(item)
    supabase.table("trades").update({
        "offer": offer,
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).eq("player", user).execute()
    return jsonify(ok=True, offer=offer)

@app.route("/accept", methods=["POST"])
def accept():
    d = request.get_json()
    user = d["user"]
    fresh(user)
    supabase.table("trades").update({
        "accepted": True,
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).eq("player", user).execute()
    return jsonify(ok=True)

@app.route("/status", methods=["GET"])
def status():
    user = request.args.get("user")
    fresh(user)
    mine = supabase.table("trades").select("*").eq("player", user).single().execute().data
    other_name = get_counterpart(user)
    other = None
    if other_name:
        other = supabase.table("trades").select("*").eq("player", other_name).single().execute().data
    both = other and mine["accepted"] and other["accepted"]
    return jsonify(
        other=other_name,
        myOffer=mine["offer"],
        otherOffer=other["offer"] if other else [],
        iAccepted=mine["accepted"],
        otherAccepted=other["accepted"] if other else False,
        bothAccepted=both
    )

@app.route("/reset", methods=["POST"])
def reset():
    d = request.get_json()
    user = d["user"]
    supabase.table("trades").delete().eq("player", user).execute()
    return jsonify(ok=True)

def janitor():
    while True:
        time.sleep(60)
        cutoff = (datetime.datetime.utcnow() - datetime.timedelta(seconds=OFFER_TTL)).isoformat()
        supabase.table("trades").delete().lt("updated_at", cutoff).execute()

threading.Thread(target=janitor, daemon=True).start()

if __name__ == "__main__":
    app.run("0.0.0.0", 5000)
          
