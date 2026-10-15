"""Vercel WSGI entrypoint for the internal MannMitra service."""
import os

from flask import Flask, jsonify, request

from mannmitra.agent import MannMitraAgent
from mannmitra.llm import get_provider
from mannmitra.storage import Store, SupabaseStore

supabase_url = os.environ.get("SUPABASE_URL", "").strip()
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
if bool(supabase_url) != bool(supabase_key):
    raise RuntimeError("Set both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, or neither.")
if supabase_url and supabase_key:
    store = SupabaseStore(supabase_url, supabase_key)
elif os.environ.get("VERCEL") == "1":
    raise RuntimeError(
        "Configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in Vercel for persistent storage."
    )
else:
    store = Store(path=os.environ.get("MANNMITRA_DB", ":memory:"))

agent = MannMitraAgent(get_provider(), store=store)
app = Flask(__name__)


@app.get("/")
def health():
    return jsonify({"service": "mannmitra", "status": "ok"})


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Send a JSON object with user_id and message."}), 400

    message = payload.get("message")
    user_id = payload.get("user_id")
    if not isinstance(message, str) or not isinstance(user_id, str):
        return jsonify({"error": "Both user_id and message must be strings."}), 400
    if len(message) > 2000:
        return jsonify({"error": "Message must be 2,000 characters or fewer."}), 413

    reply = agent.handle(user_id[:64] or "anon", message, "web")
    return jsonify({"reply": reply})
