"""Privacy-first storage. Chat text is NEVER stored. Only anonymous numeric check-in
scores, screening scores and crisis-event COUNTS are kept, under a hashed user id."""
import hashlib
import json
import os
import sqlite3
from threading import RLock
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MIN_USERS = 5  # aggregate stats stay hidden until at least this many people contribute


class Store:
    def __init__(self, path=None, salt=None):
        self.path = path or os.environ.get("MANNMITRA_DB", "mannmitra.db")
        self.salt = salt or os.environ.get("MANNMITRA_SALT", "change-me")
        self._db_lock = RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        with self._db_lock:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS checkins(uid TEXT, ts REAL, mood INT, stress INT, sleep REAL);
                CREATE TABLE IF NOT EXISTS screenings(uid TEXT, ts REAL, phq2 INT, gad2 INT);
                CREATE TABLE IF NOT EXISTS crisis(uid TEXT, ts REAL);
            """)

    def user_id(self, platform, raw_id):
        return hashlib.sha256(f"{self.salt}|{platform}|{raw_id}".encode()).hexdigest()[:16]

    def add_checkin(self, uid, mood, stress, sleep):
        with self._db_lock:
            self.db.execute("INSERT INTO checkins VALUES(?,?,?,?,?)", (uid, time.time(), mood, stress, sleep))
            self.db.commit()

    def last_checkin(self, uid):
        with self._db_lock:
            return self.db.execute(
                "SELECT mood, stress, sleep FROM checkins WHERE uid=? ORDER BY ts DESC LIMIT 1", (uid,)).fetchone()

    def add_screening(self, uid, phq2, gad2):
        with self._db_lock:
            self.db.execute("INSERT INTO screenings VALUES(?,?,?,?)", (uid, time.time(), phq2, gad2))
            self.db.commit()

    def add_crisis(self, uid):
        with self._db_lock:
            self.db.execute("INSERT INTO crisis VALUES(?,?)", (uid, time.time()))
            self.db.commit()

    def delete_user(self, uid):
        with self._db_lock:
            for t in ("checkins", "screenings", "crisis"):
                self.db.execute(f"DELETE FROM {t} WHERE uid=?", (uid,))
            self.db.commit()

    def aggregate(self, days=7, min_users=MIN_USERS):
        """Anonymous institution-level trends. Returns no individual data."""
        since = time.time() - days * 86400
        with self._db_lock:
            users = self.db.execute(
                "SELECT COUNT(DISTINCT uid) FROM checkins WHERE ts>=?", (since,)).fetchone()[0]
            if users < min_users:
                return {"insufficient_data": True, "message": f"Needs at least {min_users} users in the period."}
            n, mood, stress, sleep = self.db.execute(
                "SELECT COUNT(*), AVG(mood), AVG(stress), AVG(sleep) FROM checkins WHERE ts>=?", (since,)).fetchone()
            flags = self.db.execute("SELECT COUNT(*) FROM crisis WHERE ts>=?", (since,)).fetchone()[0]
        return {"period_days": days, "users": users, "checkins": n,
                "avg_mood": round(mood, 2), "avg_stress": round(stress, 2),
                "avg_sleep_hours": round(sleep, 2), "crisis_flags": flags}


class SupabaseStore:
    """Persistent storage through Supabase's server-side PostgREST API."""

    def __init__(self, url=None, key=None, salt=None):
        self.url = (url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.key = key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.salt = salt or os.environ.get("MANNMITRA_SALT", "change-me")
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.")
        if not self.url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise ValueError("SUPABASE_URL must use HTTPS (HTTP is allowed for localhost).")

    def _request(self, table, query="", method="GET", payload=None, headers=None):
        url = f"{self.url}/rest/v1/{table}"
        if query:
            url += f"?{query}"
        request_headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Accept": "application/json",
        }
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
            request_headers["Prefer"] = "return=minimal"
        if headers:
            request_headers.update(headers)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(url, data=body, method=method, headers=request_headers)
        with urlopen(request, timeout=15) as response:
            content = response.read()
            if not content:
                return []
            result = json.loads(content)
            if not isinstance(result, list):
                raise ValueError(f"Supabase returned an unexpected response for {table}.")
            return result

    def user_id(self, platform, raw_id):
        return hashlib.sha256(f"{self.salt}|{platform}|{raw_id}".encode()).hexdigest()[:16]

    def add_checkin(self, uid, mood, stress, sleep):
        self._request("wellness_checkins", method="POST", payload={
            "uid": uid, "ts": time.time(), "mood": mood, "stress": stress, "sleep": sleep,
        })

    def last_checkin(self, uid):
        query = urlencode({
            "select": "mood,stress,sleep",
            "uid": f"eq.{uid}",
            "order": "ts.desc",
            "limit": "1",
        })
        rows = self._request("wellness_checkins", query)
        if not rows:
            return None
        row = rows[0]
        return row["mood"], row["stress"], row["sleep"]

    def add_screening(self, uid, phq2, gad2):
        self._request("self_screenings", method="POST", payload={
            "uid": uid, "ts": time.time(), "phq2": phq2, "gad2": gad2,
        })

    def add_crisis(self, uid):
        self._request("crisis_events", method="POST", payload={"uid": uid, "ts": time.time()})

    def delete_user(self, uid):
        for table in ("wellness_checkins", "self_screenings", "crisis_events"):
            query = urlencode({"uid": f"eq.{uid}"})
            self._request(table, query, method="DELETE")

    def aggregate(self, days=7, min_users=MIN_USERS):
        since = time.time() - days * 86400
        checkin_query = urlencode({
            "select": "uid,ts,mood,stress,sleep",
            "ts": f"gte.{since}",
        })
        rows = self._request("wellness_checkins", checkin_query)
        users = {row["uid"] for row in rows}
        if len(users) < min_users:
            return {"insufficient_data": True, "message": f"Needs at least {min_users} users in the period."}
        crisis_query = urlencode({"select": "uid", "ts": f"gte.{since}"})
        flags = len(self._request("crisis_events", crisis_query))
        return {
            "period_days": days,
            "users": len(users),
            "checkins": len(rows),
            "avg_mood": round(sum(row["mood"] for row in rows) / len(rows), 2),
            "avg_stress": round(sum(row["stress"] for row in rows) / len(rows), 2),
            "avg_sleep_hours": round(sum(row["sleep"] for row in rows) / len(rows), 2),
            "crisis_flags": flags,
        }

    def add_assessment(self, assessment):
        self._request("website_assessments", method="POST", payload={"data": assessment})

    def list_assessments(self):
        page_size = 1000
        results = []
        offset = 0
        query = urlencode({"select": "data", "order": "created_at.desc"})
        while True:
            rows = self._request(
                "website_assessments",
                query,
                headers={"Range-Unit": "items", "Range": f"{offset}-{offset + page_size - 1}"},
            )
            results.extend(row["data"] for row in rows)
            if len(rows) < page_size:
                return results
            offset += page_size
