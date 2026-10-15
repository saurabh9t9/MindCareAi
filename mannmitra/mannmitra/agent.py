"""The MannMitra agent: one entry point, handle(), used by the CLI, web and Telegram.

Order of operations for every message:
  1. Safety check  -> crisis? return fixed helpline message, skip everything else.
  2. Commands      -> /checkin /screen /tools /tool /privacy /delete /help
  3. Active flow   -> check-in or self-check questions, if one is in progress
  4. AI companion  -> provider reply (falls back to offline mode if the provider fails)
  5. Output guard  -> block diagnoses, medication advice or self-harm methods
"""
import re
import logging
from dataclasses import dataclass, field

from . import coping, safety, screening
from .llm import SYSTEM_PROMPT, OfflineProvider, Provider
from .storage import Store

MAX_INPUT = 2000
MAX_HISTORY = 6

HELP = ("I'm MannMitra, an AI companion for how you're feeling. I'm not a doctor or therapist.\n"
        "/checkin  a 1-minute mood check-in\n/screen   a short self-check (PHQ-2 / GAD-2)\n"
        "/tools    calming exercises\n/chat     pause a check-in and chat freely\n"
        "/cancel   stop the current check-in\n/privacy  how your data is handled\n/delete   erase my data\n"
        "Or just tell me what's on your mind.")

PRIVACY = ("Privacy: I don't store chat text in this app; I keep only check-in numbers under an anonymous ID. "
           "Offline mode keeps messages on this server. If a cloud AI provider is configured, your message "
           "and recent chat context are sent to that provider. Type /delete to erase your saved numbers.")

NUDGE = ("It may also help to talk to someone you trust, like a family member, friend, teacher or counsellor.")
LOGGER = logging.getLogger(__name__)


@dataclass
class Session:
    mode: str = ""          # "", "checkin", "screen"
    step: int = 0
    data: list = field(default_factory=list)
    history: list = field(default_factory=list)   # [(role, text)], memory only, never saved
    lang: str = "en"
    turns: int = 0
    last_nudge: int = -10


def _num(text, lo, hi, as_float=False):
    m = re.search(r"\d+(\.\d+)?", text or "")
    if not m:
        return None
    v = float(m.group()) if as_float else int(float(m.group()))
    return v if lo <= v <= hi else None


class MannMitraAgent:
    def __init__(self, provider: Provider = None, store: Store = None):
        self.provider = provider or OfflineProvider()
        self.fallback = OfflineProvider()
        self.store = store or Store()
        self.sessions = {}

    # ------------------------------------------------------------------ public
    def handle(self, platform_id: str, text: str, platform: str = "web") -> str:
        uid = self.store.user_id(platform, platform_id)
        s = self.sessions.setdefault(uid, Session())
        text = (text or "").strip()[:MAX_INPUT]
        if not text:
            return "I'm here whenever you're ready. How are you feeling today?"
        s.turns += 1
        lang = safety.detect_language(text)
        if lang != "en":
            s.lang = lang

        # 1. safety first
        res = safety.check_message(text)
        if res.level == "crisis":
            s.mode, s.step, s.data = "", 0, []
            self.store.add_crisis(uid)
            return safety.crisis_response(s.lang)

        low = text.lower()
        # 2. commands (work any time)
        if low in ("/cancel", "cancel", "stop"):
            s.mode, s.step, s.data = "", 0, []
            return "Okay, we can stop there. I'm here whenever you want to continue."
        if low in ("/chat", "/talk"):
            s.mode, s.step, s.data = "", 0, []
            return "I've paused the check-in. Tell me what's on your mind, or start it again whenever you like."
        if low.startswith("/") or low in ("help", "hi", "hello", "start"):
            cmd = self._command(uid, s, low)
            if cmd is not None:
                return cmd

        # 3. active flows
        if s.mode == "checkin":
            valid = _num(text, 1, 5) is not None if s.step < 2 else _num(text, 0, 24, as_float=True) is not None
            if not valid and _is_conversation(text):
                s.mode, s.step, s.data = "", 0, []
                return "I've paused the check-in so we can talk. " + self._companion(s, text)
            return self._checkin_step(uid, s, text)
        if s.mode == "screen":
            if _num(text, 0, 3) is None and _is_conversation(text):
                s.mode, s.step, s.data = "", 0, []
                return "I've paused the self-check so we can talk. " + self._companion(s, text)
            return self._screen_step(uid, s, text)

        # 4. AI companion
        reply = self._companion(s, text)
        if res.level == "concern" and s.turns - s.last_nudge >= 3:
            reply += "\n\n" + NUDGE
            s.last_nudge = s.turns
        return reply

    # ----------------------------------------------------------------- commands
    def _command(self, uid, s, low):
        if low in ("/start", "start", "hi", "hello"):
            return ("Hi, I'm MannMitra. I'm an AI here to listen and share simple ways to feel a bit better. "
                    "I'm not a doctor or counsellor.\nHow are you feeling today? You can also type /help.")
        if low in ("/help", "help"):
            return HELP
        if low == "/privacy":
            return PRIVACY
        if low == "/delete":
            self.store.delete_user(uid)
            s.history.clear()
            return "Done. Your saved check-in numbers have been erased."
        if low == "/tools":
            return coping.list_tools()
        if low.startswith("/tool"):
            name = low[5:].strip()
            return coping.get_tool(name) or ("I don't know that one.\n" + coping.list_tools())
        if low == "/checkin":
            s.mode, s.step, s.data = "checkin", 0, []
            return ("Let's do a quick check-in. How is your mood right now?\n"
                    "1 = very low, 2 = low, 3 = okay, 4 = good, 5 = great")
        if low == "/screen":
            s.mode, s.step, s.data = "screen", 0, []
            return screening.INTRO + "\n\n" + screening.question_text(0)
        return None

    # --------------------------------------------------------------- check-in
    def _checkin_step(self, uid, s, text):
        if s.step == 0:
            v = _num(text, 1, 5)
            if v is None:
                return "Please answer with a number from 1 (very low) to 5 (great)."
            s.data.append(v); s.step = 1
            return "Thanks. How stressed do you feel? 1 = calm, 2 = a little, 3 = moderate, 4 = high, 5 = very high"
        if s.step == 1:
            v = _num(text, 1, 5)
            if v is None:
                return "Please answer with a number from 1 (calm) to 5 (very stressed)."
            s.data.append(v); s.step = 2
            return "And roughly how many hours did you sleep last night?"
        v = _num(text, 0, 24, as_float=True)
        if v is None:
            return "Please give a number of hours between 0 and 24, like 6 or 7.5."
        mood, stress = s.data
        prev = self.store.last_checkin(uid)
        self.store.add_checkin(uid, mood, stress, v)
        s.mode, s.step, s.data = "", 0, []
        out = [f"Thanks for checking in. Mood {mood}/5, stress {stress}/5, sleep {v:g} h."]
        if prev:
            pm, ps, _ = prev
            if mood > pm:
                out.append("Your mood is a bit higher than last time. Nice.")
            elif mood < pm:
                out.append("Your mood is lower than last time. That's okay, and I'm glad you checked in.")
        tool = coping.suggest(mood, stress)
        if v < 6:
            tool = "sleep" if tool == "grounding" else tool
        out.append("A small idea for now:\n" + (coping.get_tool(tool) or ""))
        if mood <= 2 or stress >= 4:
            out.append(NUDGE)
        return "\n\n".join(out)

    # ------------------------------------------------------------- self-check
    def _screen_step(self, uid, s, text):
        v = _num(text, 0, 3)
        if v is None:
            return "Please answer with 0, 1, 2 or 3.\n(" + screening.OPTIONS + ")"
        s.data.append(v); s.step += 1
        if s.step < len(screening.QUESTIONS):
            return screening.question_text(s.step)
        totals = screening.score(s.data)
        self.store.add_screening(uid, totals["PHQ-2"], totals["GAD-2"])
        s.mode, s.step, s.data = "", 0, []
        return screening.result_message(totals)

    # ---------------------------------------------------------- AI companion
    def _companion(self, s, text):
        try:
            reply = self.provider.reply(SYSTEM_PROMPT, s.history[-MAX_HISTORY:], text)
            if not reply:
                raise ValueError("empty reply")
        except Exception as exc:
            LOGGER.warning("MannMitra provider failed (%s); using offline fallback.", type(exc).__name__)
            reply = self.fallback.reply(SYSTEM_PROMPT, [], text)
            reply = "I'm having trouble reaching the configured AI service, so here's a basic offline reply. " + reply
        ok, _ = safety.check_output(reply)
        if not ok:
            reply = safety.SAFE_FALLBACK
        s.history += [("user", text), ("assistant", reply)]
        s.history = s.history[-MAX_HISTORY * 2:]
        return reply


def _is_conversation(text):
    words = re.findall(r"[a-zA-Z']+", text or "")
    lowered = (text or "").lower()
    return len(words) >= 3 or "?" in text or any(
        phrase in lowered for phrase in ("help", "talk", "feel", "please", "what now")
    )
