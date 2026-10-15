"""Optional self-check using the public PHQ-2 and GAD-2 questionnaires.
These are SCREENING questions, not a diagnosis. A score of 3 or more on either is the
commonly used cut-off for suggesting a conversation with a professional."""

OPTIONS = "0 = Not at all, 1 = Several days, 2 = More than half the days, 3 = Nearly every day"
PREFIX = "Over the last 2 weeks, how often have you been bothered by: "

QUESTIONS = [
    ("PHQ-2", "little interest or pleasure in doing things?"),
    ("PHQ-2", "feeling down, depressed or hopeless?"),
    ("GAD-2", "feeling nervous, anxious or on edge?"),
    ("GAD-2", "not being able to stop or control worrying?"),
]
CUTOFF = 3

INTRO = ("This is a short self-check (4 questions). It is not a diagnosis, and only a "
         "qualified professional can assess how you are doing. Answer with a number 0-3.\n"
         f"{OPTIONS}\nType /cancel to stop.")


def question_text(i: int) -> str:
    return f"Q{i + 1}/{len(QUESTIONS)}. {PREFIX}{QUESTIONS[i][1]}\n({OPTIONS})"


def score(answers):
    totals = {"PHQ-2": 0, "GAD-2": 0}
    for (kind, _), a in zip(QUESTIONS, answers):
        totals[kind] += a
    return totals


def result_message(totals) -> str:
    high = [k for k, v in totals.items() if v >= CUTOFF]
    head = f"Your scores: PHQ-2 = {totals['PHQ-2']}/6, GAD-2 = {totals['GAD-2']}/6."
    if high:
        return (head + "\nA score of 3 or more is the usual point at which people are encouraged to "
                "talk to a counsellor or doctor. That doesn't mean something is wrong with you; it "
                "means support could help. Is there a trusted adult or counsellor you could talk to "
                "this week? I can also guide you through a calming exercise (/tools).")
    return (head + "\nThese are below the usual cut-off, but how you feel still matters. If things "
            "change or feel heavy, a counsellor is always a good person to talk to.")
