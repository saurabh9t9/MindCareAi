"""Safety layer. Runs BEFORE any AI model sees a message, and checks every model reply.

Design rules:
  * Be conservative: a false alarm is far better than a missed crisis.
  * When a crisis is detected, the normal flow and the AI model are bypassed and a
    fixed, reviewed message with helplines and trusted-adult options is returned.
  * The keyword lists are a STARTER set. They must be reviewed and extended by
    counsellors and native speakers of every language you support.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_RES_PATH = Path(__file__).resolve().parent.parent / "config" / "resources.json"


def load_resources(path=_RES_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---- crisis phrases (English, romanised Hindi, Hindi, Tamil) ----------------------
_CRISIS_EN = [
    r"\bkill (myself|me)\b", r"\bsuicid", r"\bend (my|my own) life\b", r"\bend it all\b",
    r"\bwant(ed)? to die\b", r"\bwish i (was|were) dead\b", r"\bbetter off (dead|without me)\b",
    r"\bno (reason|point) (to|in) (live|living|going on)\b", r"\bhurt(ing)? myself\b",
    r"\bself[- ]?harm", r"\bcut(ting)? myself\b", r"\bdon'?t want to (live|be alive|wake up)\b",
    r"\boverdos", r"\btake my (own )?life\b", r"\bdo not want to be here anymore\b",
    r"\bdon'?t want to be here anymore\b",
]
_CRISIS_NATIVE = [
    "marna chahta", "marna chahti", "jaan de dunga", "jaan de dungi", "khudkushi",
    "आत्महत्या", "मरना चाहता", "मरना चाहती", "जीना नहीं चाहता", "जीना नहीं चाहती", "खुद को खत्म",
    "தற்கொலை", "சாக வேண்டும்", "சாகணும்", "உயிரை மாய்",
]
_CONCERN_EN = [
    r"\bhopeless\b", r"\bworthless\b", r"\bcan'?t cope\b", r"\bcannot cope\b", r"\bcan'?t go on\b",
    r"\bpanic attack", r"\bnobody cares\b", r"\bno one cares\b", r"\bcompletely alone\b",
    r"\bbreaking down\b", r"\bgive up\b", r"\bfeel empty\b", r"\bcan'?t stop crying\b",
]

CRISIS_RE = [re.compile(p, re.I) for p in _CRISIS_EN]
CONCERN_RE = [re.compile(p, re.I) for p in _CONCERN_EN]


def normalize(text: str) -> str:
    t = (text or "").replace("\u2019", "'").replace("\u2018", "'").lower()
    return re.sub(r"\s+", " ", t).strip()


def detect_language(text: str) -> str:
    if re.search(r"[\u0900-\u097F]", text or ""):
        return "hi"
    if re.search(r"[\u0B80-\u0BFF]", text or ""):
        return "ta"
    return "en"


@dataclass
class SafetyResult:
    level: str = "none"          # "none" | "concern" | "crisis"
    matches: list = field(default_factory=list)


def check_message(text: str) -> SafetyResult:
    t = normalize(text)
    hits = [p.pattern for p in CRISIS_RE if p.search(t)]
    hits += [s for s in _CRISIS_NATIVE if s in t]
    if hits:
        return SafetyResult("crisis", hits)
    hits = [p.pattern for p in CONCERN_RE if p.search(t)]
    return SafetyResult("concern", hits) if hits else SafetyResult()


# ---- output guard -------------------------------------------------------------------
_BAD_OUTPUT = [re.compile(p, re.I) for p in [
    r"\byou (clearly |probably |likely )?(have|are suffering from|suffer from) (depression|an anxiety disorder|bipolar|ptsd|ocd|adhd|schizophrenia)",
    r"\byou('re| are) (clinically )?(depressed|bipolar|schizophrenic)\b",
    r"\bi diagnose\b", r"\byour diagnosis\b",
    r"\b\d+\s?(mg|milligrams?)\b",
    r"\b(sertraline|fluoxetine|escitalopram|alprazolam|clonazepam|diazepam|lorazepam|zolpidem|antidepressants?)\b",
    r"\b(take|stop taking|increase|reduce) (your|the|some) (medication|medicine|pills|tablets|dose)\b",
    r"\b(how to|ways to|methods? (of|for)) (kill|harm|hurt|end)\b", r"\blethal dose\b",
]]


def check_output(text: str):
    """Return (ok, reason). Replies that diagnose, give medication advice or describe
    methods of self-harm are blocked and replaced with a safe fallback."""
    for p in _BAD_OUTPUT:
        if p.search(text or ""):
            return False, p.pattern
    return True, ""


SAFE_FALLBACK = ("I want to be careful here. I can't give medical advice or a diagnosis, "
                 "but a doctor or counsellor can. I'm happy to keep listening, or we can try a "
                 "short calming exercise (type /tools).")

_CRISIS_MSG = {
    "en": ("I'm really glad you told me, and I'm sorry things feel this heavy right now. "
           "You don't have to carry this alone. Please reach out to someone right now:\n"
           "{lines}\n{intl}\n\n"
           "If you might act on these thoughts, or you are in immediate danger, call your local "
           "emergency number or go to the nearest hospital, and please tell a trusted adult "
           "(a family member, friend or teacher) so they can be with you.\n\n"
           "I'm an AI and can't replace a person who can be there with you, but I'm here to keep "
           "talking if you would like."),
    "hi": ("मुझे खुशी है कि आपने मुझे बताया, और मुझे दुख है कि अभी सब कुछ इतना भारी लग रहा है। "
           "आप अकेले नहीं हैं। कृपया अभी किसी से बात करें:\n{lines}\n\n"
           "अगर आपको लगता है कि आप खुद को नुकसान पहुँचा सकते हैं या आप तुरंत खतरे में हैं, तो आपातकालीन "
           "नंबर पर कॉल करें या नज़दीकी अस्पताल जाएँ, और किसी भरोसेमंद व्यक्ति (परिवार, दोस्त, शिक्षक) को अभी बताएँ।\n\n"
           "मैं एक AI हूँ और किसी व्यक्ति की जगह नहीं ले सकता, लेकिन आप चाहें तो मैं यहाँ बात करने के लिए हूँ।"),
    "ta": ("நீங்கள் என்னிடம் சொன்னது எனக்கு மகிழ்ச்சி. இப்போது எல்லாம் இவ்வளவு கனமாக இருப்பதற்காக வருந்துகிறேன். "
           "நீங்கள் தனியாக இல்லை. தயவுசெய்து இப்போதே யாரிடமாவது பேசுங்கள்:\n{lines}\n\n"
           "உங்களுக்கு நீங்களே தீங்கு செய்துகொள்ளக்கூடும் என்று தோன்றினால் அல்லது உடனடி ஆபத்தில் இருந்தால், "
           "அவசர எண்ணை அழைக்கவும் அல்லது அருகிலுள்ள மருத்துவமனைக்குச் செல்லவும். நம்பகமான ஒருவரிடம் "
           "(குடும்பத்தினர், நண்பர், ஆசிரியர்) இப்போதே சொல்லுங்கள்.\n\n"
           "நான் ஒரு AI; ஒரு மனிதருக்கு மாற்றாக முடியாது, ஆனால் நீங்கள் விரும்பினால் பேசுவதற்கு இங்கே இருக்கிறேன்."),
}


def crisis_response(lang: str = "en", resources=None) -> str:
    res = resources or load_resources()
    lines = "\n".join(f"- {h['name']}: {h['number']}" for h in res["helplines"])
    intl = res.get("international", "")
    tpl = _CRISIS_MSG.get(lang, _CRISIS_MSG["en"])
    return tpl.format(lines=lines, intl=intl).strip()
