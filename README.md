# MindCare AI — SDG 3 Wellness Project

MindCare AI is a student mental-wellness prototype aligned with SDG 3: Good Health and Well-being. It includes structured check-ins, a dashboard, and **MannMitra**, an integrated conversational wellness companion.

MannMitra is a support tool, not a clinician. Its check-ins are not diagnoses and do not replace professional care.

## Features

- Guided mental-wellness questionnaire with a result summary and suggested next steps
- Dashboard of locally stored questionnaire results
- MannMitra chat widget available throughout the website
- Chat commands for `/checkin`, `/screen`, `/tools`, `/chat`, `/cancel`, `/privacy`, and `/delete`
- Natural-language messages pause an in-progress numeric check-in so users can continue the conversation
- Crisis-first response with India helplines (Tele-MANAS 14416 and emergency services 112)
- Safety check before any configured model is called, plus an output guard for unsafe medical advice
- Offline companion replies by default; no model API key or additional package is needed

## Run locally

Python 3.10+ is recommended. Install the website dependency and start Flask:

```powershell
python -m pip install -r requirements.txt
python app.py
```

The app automatically reads environment settings from the project-root `.env` file. Open <http://127.0.0.1:5000>.

## Deploy to Vercel with Supabase

Import this project into Vercel with the repository root as the project root. Vercel detects the Flask
application in `app.py`, installs dependencies from `requirements.txt`, and uses `vercel.json` to
allow up to 60 seconds for a chat request. Static assets are served from `public/static/`; the local
`python app.py` workflow continues to serve them at the same `/static/` URLs.

The Vercel project defines two services: `app` serves all public paths, while `mannmitra` is an
internal Python service with its own WSGI entrypoint at `vercel_app:app` in `mannmitra/`. The public app
continues to handle its embedded chat directly; it does not call the internal service, so no binding
is configured. Add a public rewrite or a caller-side binding only if you later want to route traffic
to or call that standalone service.

Create a Supabase project and run [`supabase/schema.sql`](./supabase/schema.sql) in its SQL Editor.
In Vercel Project Settings → Environment Variables, set:

- `SUPABASE_URL` to the project URL from Supabase.
- `SUPABASE_SERVICE_ROLE_KEY` to the project's service-role secret. Keep this server-side only; never
  add it to frontend code or expose it as a `NEXT_PUBLIC_` variable.
- `GEMINI_API_KEY` and `MANNMITRA_PROVIDER=gemini` for Gemini chat.
- `GEMINI_MODEL=gemini-3.5-flash-lite` (optional; this is the default).
- `MANNMITRA_SALT` to a long, random secret value.
- `MANNMITRA_ADMIN_TOKEN` to a separate long random token. The `/dashboard` page prompts for
  HTTP Basic authentication; use username `admin` and this token as the password.

Redeploy after setting the variables. Vercel requires both Supabase variables and will fail startup
with a clear error if they are missing. With them configured, anonymous chat check-in data and website
assessment records are stored persistently in Supabase. Local development remains unchanged and uses
the local SQLite database and `data/screenings.json`. `.vercelignore` omits local data, archives, and
the virtual environment from deployment without deleting them locally.

The `/dashboard` page requires `MANNMITRA_ADMIN_TOKEN` in every environment; if it is unset, the
page returns an explicit configuration error instead of exposing submitted assessment details.

## Enable Gemini AI

The project-root `.env` file is ready for your Gemini key. Open it and replace the empty value:

```dotenv
GEMINI_API_KEY=paste-your-Google-AI-Studio-key-here
```

Create a key in [Google AI Studio](https://aistudio.google.com/app/apikey), save `.env`, then **stop and restart** Flask. The widget header shows `Your assistant`. The default model is Google's `gemini-3.5-flash-lite`, configured for low-latency replies; set `GEMINI_MODEL` in `.env` to use a different model. If the key is empty, the app still works in labeled offline demo mode. Keep the key private; `.env` is excluded by `.gitignore`. Gemini requests time out after 25 seconds; on provider errors, the app logs the failure and clearly prefixes its offline fallback reply.

## Data and privacy notes

- Chat text and chat history are held in memory only and are not written to the database.
- With the default offline provider, chat messages are processed on this server. If you enable a cloud provider, the current message and recent in-memory chat context are sent to that provider; review its privacy and retention policies first.
- The browser stores a random identifier in local storage; the server hashes it before storing numeric check-in, screening, and crisis-count data. Locally these are in `data/mannmitra.sqlite3`; on Vercel they are in Supabase.
- Use `/delete` in the chat to erase the anonymous record associated with that browser identifier.
- The website's separate questionnaire stores the submitted name and answers locally in `data/screenings.json`, or in Supabase when deployed on Vercel. Do not use real student data in this demo.
- Set a strong `MANNMITRA_SALT` in `.env` before deployment. The bundled default salt is only suitable for local testing.
- The bundled helplines and crisis keyword lists are starter resources. Verify them for your location and have qualified clinicians/native speakers review the content before any real pilot.

## Tests

Run the included MannMitra agent tests from its source directory:

```powershell
Set-Location .\mannmitra
python -m unittest discover -s tests -v
```

The Flask website uses `app.py`; the included `mannmitra` folder contains the agent implementation, tests, configuration, and upstream documentation.
