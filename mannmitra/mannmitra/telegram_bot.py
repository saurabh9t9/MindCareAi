"""Telegram bot (long polling, standard library only).
Create a bot with @BotFather, then:  export TELEGRAM_BOT_TOKEN=...  python -m mannmitra.telegram_bot
NOTE: not tested against the live Telegram API in this project's sandbox."""
import json
import os
import time
import urllib.request

from .agent import MannMitraAgent
from .llm import get_provider


def _call(token, method, payload):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    agent = MannMitraAgent(get_provider())
    offset = None
    print(f"MannMitra Telegram bot running ({agent.provider.name} mode)")
    while True:
        try:
            upd = _call(token, "getUpdates", {"timeout": 30, "offset": offset})
            for u in upd.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                if "text" in msg:
                    reply = agent.handle(str(msg["chat"]["id"]), msg["text"], "telegram")
                    _call(token, "sendMessage", {"chat_id": msg["chat"]["id"], "text": reply})
        except Exception:
            time.sleep(3)


if __name__ == "__main__":
    main()
