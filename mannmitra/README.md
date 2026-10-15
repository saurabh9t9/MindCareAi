# MannMitra: AI wellness companion for youth (SDG 3)

MannMitra is a chatbot for mental wellness **check-ins and guidance**. It listens, shares simple
coping exercises, offers an optional self-check (PHQ-2 / GAD-2), and, most importantly, has a
**safety layer** that sends anyone in crisis to helplines and trusted adults.

It is a support tool. It does **not** diagnose, treat, or replace a counsellor or doctor.

## Quick start (no installs, no API key)

Requires Python 3.9+.

```bash
python -m mannmitra.cli          # chat in the terminal
python -m mannmitra.web          # chat in the browser at http://127.0.0.1:8000
python -m unittest discover -s tests -v   # run the tests
```

Try: `/help`, `/checkin`, `/screen`, `/tools`, `/privacy`, `/delete`, or just type how you feel.

## Using a real AI model

Default is **offline mode** (rule-based replies, good for demos). To use a language model:

| Provider | Setup |
|---|---|
| Google Gemini (Flash-Lite) | Set `MANNMITRA_PROVIDER=gemini`, `GEMINI_API_KEY=...`, and optionally `GEMINI_MODEL=gemini-3.5-flash-lite` in `.env`. |
| Claude (Anthropic) | `export MANNMITRA_PROVIDER=anthropic ANTHROPIC_API_KEY=...` |
| IBM watsonx.ai (Granite) | `pip install ibm-watsonx-ai`, then `export MANNMITRA_PROVIDER=watsonx WATSONX_API_KEY=... WATSONX_URL=... WATSONX_PROJECT_ID=...` |

See `.env.example` for all settings. If a provider fails, the agent falls back to offline mode
and keeps working. The Anthropic and watsonx providers and the Telegram bot could not be run
against the live services while this was built, so test them with your own keys first.

## How it works

```
message --> [1 Safety check] --crisis--> fixed helpline message (AI model never called)
              |
              +--> [2 Commands] /checkin /screen /tools ...
              +--> [3 Active flow] check-in or self-check questions
              +--> [4 AI companion] provider reply
                        |
                        +--> [5 Output guard] blocks diagnoses, medication advice, self-harm methods
```

| File | Purpose |
|---|---|
| `mannmitra/safety.py` | crisis and concern detection (English, Hindi, Tamil starter lists), output guard, crisis messages |
| `mannmitra/agent.py` | the orchestrator: `MannMitraAgent.handle(user_id, text)` |
| `mannmitra/llm.py` | offline, Gemini, Anthropic and watsonx providers and the system prompt |
| `mannmitra/screening.py` | PHQ-2 and GAD-2 self-check |
| `mannmitra/coping.py` | breathing, grounding, journaling, exam-stress and sleep exercises |
| `mannmitra/storage.py` | anonymous numeric storage and k-anonymous aggregate stats |
| `mannmitra/web.py`, `cli.py`, `telegram_bot.py` | interfaces |
| `config/resources.json` | helpline numbers (edit for your region) |

## Privacy by design

- Chat text is **never stored**. Only check-in numbers, screening scores and crisis counts, under a hashed ID.
- `/delete` erases a user's numbers.
- The institution dashboard (`/api/dashboard?token=...`) shows only combined averages and stays hidden until at least 5 users contributed.
- Set `MANNMITRA_SALT` to a long random string and `MANNMITRA_ADMIN_TOKEN` before deploying.

## Before real students use it (important)

This is a prototype for learning and a pilot demo. Before any real use:

1. **Clinical review.** Have counsellors or psychologists review the coping content, the crisis messages and the keyword lists.
2. **Native-speaker review.** The Hindi and Tamil crisis messages and keywords are starter drafts and must be checked, then extended to every language you support.
3. **Verify helplines.** Confirm the numbers in `config/resources.json` for your region.
4. **Consent and law.** Get institutional and parental consent as required, and follow your local data-protection rules. Add a clear consent screen.
5. **Human in the loop.** Run the pilot with a counsellor on call and a plan for who responds when someone is flagged.
6. **Red-team it.** Test with many risky and tricky messages. Keyword detection misses things (for example indirect or misspelled phrases); consider adding a trained crisis classifier.

## Ideas to extend

- WhatsApp Business API connector (same `handle()` call as Telegram).
- Voice notes with speech-to-text, and more languages.
- Counsellor handover with the student's consent.
- A proper dashboard page, and a Docker file for deployment.
