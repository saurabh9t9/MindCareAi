"""Coping toolkit: short, widely used self-help exercises (breathing, grounding,
journaling, study-stress and sleep habits). Review with a counsellor before real use."""
import re

TOOLS = {
    "breathing": ("Box breathing (2 minutes)",
        "1. Breathe in slowly through your nose for 4 seconds.\n2. Hold for 4 seconds.\n"
        "3. Breathe out slowly for 4 seconds.\n4. Hold for 4 seconds.\nRepeat 5-8 times. "
        "If you feel dizzy, go back to normal breathing."),
    "grounding": ("5-4-3-2-1 grounding",
        "Look around and name: 5 things you can see, 4 you can touch, 3 you can hear, "
        "2 you can smell, 1 you can taste. Go slowly. It brings your attention back to now."),
    "journaling": ("Three-line journal",
        "Write three lines: 1) What is weighing on me right now? 2) What is one small thing that "
        "went okay today? 3) What is one kind thing I can do for myself tonight?"),
    "exam_stress": ("Exam stress reset",
        "1. Write every topic on paper. 2. Pick just one and study for 25 minutes, then rest 5. "
        "3. Tick it off. 4. Protect your sleep; tired minds remember less. "
        "Marks don't measure your worth."),
    "sleep": ("Wind-down for sleep",
        "30 minutes before bed: phone away, dim lights, write tomorrow's top 3 tasks so your mind "
        "can let go, then try box breathing in bed."),
}


def list_tools() -> str:
    lines = [f"- {k}: {v[0]}" for k, v in TOOLS.items()]
    return "Try one with /tool <name>:\n" + "\n".join(lines)


def get_tool(name: str):
    t = TOOLS.get((name or "").strip().lower())
    return f"{t[0]}\n{t[1]}" if t else None


def suggest(mood=None, stress=None, text="") -> str:
    t = (text or "").lower()
    if re.search(r"exam|test|marks|result|study|assignment", t):
        return "exam_stress"
    if re.search(r"sleep|insomnia|awake|tired", t):
        return "sleep"
    if (stress or 0) >= 4 or re.search(r"anxi|panic|nervous|worr", t):
        return "breathing"
    if (mood or 5) <= 2:
        return "journaling"
    return "grounding"
