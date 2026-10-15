from __future__ import annotations

import json
import hmac
import os
from threading import RLock
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)

from flask import Flask, Response, jsonify, render_template, request
from mannmitra.mannmitra.agent import MannMitraAgent
from mannmitra.mannmitra.llm import get_provider
from mannmitra.mannmitra.storage import Store, SupabaseStore

app = Flask(__name__, static_folder="public/static", static_url_path="/static")
supabase_url = os.environ.get("SUPABASE_URL", "").strip()
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
if bool(supabase_url) != bool(supabase_key):
    raise RuntimeError("Set both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, or neither.")
if supabase_url and supabase_key:
    chat_store = SupabaseStore(supabase_url, supabase_key)
    DATA_FILE = None
elif os.environ.get("VERCEL") == "1":
    raise RuntimeError(
        "Configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in Vercel for persistent storage."
    )
else:
    DATA_FILE = BASE_DIR / "data" / "screenings.json"
    CHAT_DB_FILE = BASE_DIR / "data" / "mannmitra.sqlite3"
    chat_store = Store(path=os.environ.get("MANNMITRA_DB", str(CHAT_DB_FILE)))
chat_agent = MannMitraAgent(get_provider(), store=chat_store)
chat_locks = tuple(RLock() for _ in range(32))


@app.context_processor
def inject_chat_provider():
    return {"chat_provider": chat_agent.provider.name}


@app.before_request
def protect_dashboard():
    if request.endpoint != "dashboard":
        return None
    admin_token = os.environ.get("MANNMITRA_ADMIN_TOKEN", "")
    if not admin_token:
        return jsonify({"error": "Dashboard access is not configured."}), 503
    credentials = request.authorization
    if (
        credentials is None
        or credentials.type.lower() != "basic"
        or credentials.username != "admin"
        or not hmac.compare_digest(credentials.password or "", admin_token)
    ):
        return Response(
            "Dashboard authentication required.",
            401,
            {"WWW-Authenticate": 'Basic realm="MannMitra dashboard"'},
        )
    return None


def load_screenings() -> list[dict]:
    if isinstance(chat_store, SupabaseStore):
        return chat_store.list_assessments()
    if DATA_FILE is None:
        raise RuntimeError("Local assessment storage is not configured.")
    if not DATA_FILE.exists():
        return []
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def save_screenings(items: list[dict]) -> None:
    if isinstance(chat_store, SupabaseStore):
        raise RuntimeError("Use save_screening() for Supabase-backed assessment records.")
    if DATA_FILE is None:
        raise RuntimeError("Local assessment storage is not configured.")
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(items, file, indent=2)


def save_screening(item: dict) -> None:
    if isinstance(chat_store, SupabaseStore):
        chat_store.add_assessment(item)
        return
    screenings = load_screenings()
    screenings.insert(0, item)
    save_screenings(screenings)


def calculate_score(payload: dict) -> tuple[int, str, list[str], str]:
    score = 0
    stress = payload.get("stress_level", "Low")
    sleep = payload.get("sleep_hours", "7")
    mood = payload.get("mood", "Okay")
    symptoms = payload.getlist("symptoms") if hasattr(payload, "getlist") else payload.get("symptoms", [])
    days = payload.get("days", "Rarely")
    social = payload.get("social", "Sometimes")

    stress_map = {"Low": 5, "Moderate": 20, "High": 35}
    sleep_map = {"4-5": 25, "6": 15, "7": 5, "8+": 0}
    mood_map = {"Great": 0, "Okay": 8, "Low": 18, "Very low": 28}
    days_map = {"Rarely": 0, "Some days": 10, "Most days": 20, "Almost every day": 28}
    social_map = {"Often": 0, "Sometimes": 10, "Rarely": 20}

    score += stress_map.get(stress, 0)
    score += sleep_map.get(sleep, 0)
    score += mood_map.get(mood, 0)
    score += days_map.get(days, 0)
    score += social_map.get(social, 0)
    score += min(len(symptoms) * 12, 30)
    score = min(score, 100)

    if score >= 70:
        risk = "High risk"
        recommendations = [
            "Speak with a trusted counselor or mental health professional this week.",
            "Try a breathing exercise for 5 minutes when stress spikes.",
            "Reach out to a friend, family member, or campus wellness advisor."
        ]
    elif score >= 40:
        risk = "Moderate risk"
        recommendations = [
            "Schedule a wellness check-in and make sleep a priority.",
            "Practice a short daily mindfulness routine.",
            "Try to connect with one supportive person this week."
        ]
    else:
        risk = "Low risk"
        recommendations = [
            "Keep your routine steady and sleep consistent.",
            "Continue social support and daily movement.",
            "Reflect on what helps you manage stress best."
        ]

    if risk == "High risk":
        message = "If you feel unsafe or in immediate danger, contact emergency services or a trusted local crisis line right away."
    elif risk == "Moderate risk":
        message = "You are showing some signs of stress. Early support can make a meaningful difference."
    else:
        message = "Your check-in suggests a relatively stable emotional state today. Keep building healthy routines."

    return score, risk, recommendations, message


def compute_dashboard_metrics() -> dict:
    screenings = load_screenings()
    if not screenings:
        return {
            "total_screenings": 0,
            "average_score": 0,
            "high_risk_users": 0,
            "support_needed": 0,
        }

    scores = [min(max(int(item["score"]), 0), 100) for item in screenings]
    high_risk = sum(1 for item in screenings if item.get("risk_level") == "High risk")
    support_needed = sum(1 for item in screenings if item.get("risk_level") in {"Moderate risk", "High risk"})

    return {
        "total_screenings": len(screenings),
        "average_score": round(sum(scores) / len(scores), 1),
        "high_risk_users": high_risk,
        "support_needed": support_needed,
    }


@app.route("/")
def index():
    return render_template("index.html", metrics=compute_dashboard_metrics())


@app.route("/assessment")
def assessment_page():
    return render_template("assessment.html")


@app.route("/dashboard")
def dashboard():
    screenings = load_screenings()[:10]
    metrics = compute_dashboard_metrics()
    stats = {
        "total": metrics["total_screenings"],
        "average": metrics["average_score"],
        "high_risk": metrics["high_risk_users"],
        "moderate": sum(1 for item in screenings if item.get("risk_level") == "Moderate risk"),
    }
    return render_template("dashboard.html", stats=stats, screenings=screenings)


@app.route("/assess", methods=["POST"])
def assess():
    payload = request.form
    score, risk_level, recommendations, message = calculate_score(payload)
    symptoms = payload.getlist("symptoms")
    social_support = payload.get("social", "Sometimes")

    explanation = (
        "You are showing signs of stress that could benefit from support and a plan to recover balance."
        if risk_level != "Low risk"
        else "Your current wellbeing indicators are relatively stable. Maintaining healthy habits is a strong foundation."
    )

    result = {
        "student_name": payload.get("student_name", "Student"),
        "age": payload.get("age", "-"),
        "score": score,
        "risk_level": risk_level,
        "status": "Needs attention" if risk_level != "Low risk" else "Positive signs",
        "message": message,
        "explanation": explanation,
        "recommendations": recommendations,
        "symptoms": symptoms,
        "social_support": social_support,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    save_screening(result)

    return render_template("results.html", result=result)


@app.route("/api/summary")
def summary_api():
    return jsonify(compute_dashboard_metrics())


@app.route("/api/chat", methods=["POST"])
def chat_api():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Send a JSON object with user_id and message."}), 400

    message = payload.get("message")
    user_id = payload.get("user_id")
    if not isinstance(message, str) or not isinstance(user_id, str):
        return jsonify({"error": "Both user_id and message must be strings."}), 400
    if len(message) > 2000:
        return jsonify({"error": "Message must be 2,000 characters or fewer."}), 413

    user_lock = chat_locks[hash(user_id[:64]) % len(chat_locks)]
    with user_lock:
        reply = chat_agent.handle(user_id[:64] or "anon", message, "web")
    return jsonify({"reply": reply})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
