import json
import threading
import unittest
import urllib.request
from unittest.mock import Mock, patch

from mannmitra import safety, screening
from mannmitra.agent import MannMitraAgent
from mannmitra.llm import GeminiProvider, OfflineProvider, Provider, get_provider
from mannmitra.storage import Store, SupabaseStore
from mannmitra.web import make_server


class Boom(Provider):
    name = "boom"
    called = 0

    def reply(self, system, history, user_text):
        Boom.called += 1
        raise RuntimeError("provider down")


class Bad(Provider):
    name = "bad"

    def reply(self, system, history, user_text):
        return "You have depression. Take 50 mg of sertraline."


def agent(provider=None):
    return MannMitraAgent(provider or OfflineProvider(), Store(":memory:", salt="t"))


class SafetyTests(unittest.TestCase):
    CRISIS = ["I want to die", "i wanna kill myself", "thinking about suicide", "I don't want to live anymore",
              "I can't do this, I'm going to end my life", "I'm better off dead", "I keep cutting myself",
              "no reason to live", "मैं आत्महत्या करना चाहता हूँ", "நான் தற்கொலை செய்ய நினைக்கிறேன்",
              "main marna chahta hoon", "I DON’T WANT TO BE HERE ANYMORE"]
    SAFE = ["I have an exam tomorrow", "I'm so stressed about marks", "my phone died", "I killed it in my presentation",
            "I'm dying to see my friends", "feeling a bit low today"]

    def test_crisis_detected(self):
        for m in self.CRISIS:
            self.assertEqual(safety.check_message(m).level, "crisis", m)

    def test_normal_not_crisis(self):
        for m in self.SAFE:
            self.assertNotEqual(safety.check_message(m).level, "crisis", m)

    def test_concern_level(self):
        self.assertEqual(safety.check_message("I feel hopeless").level, "concern")

    def test_output_guard(self):
        for bad in ["You have depression.", "Take 50 mg of it", "Try sertraline", "I diagnose you with anxiety"]:
            self.assertFalse(safety.check_output(bad)[0], bad)
        self.assertTrue(safety.check_output("That sounds hard. Want to try slow breathing?")[0])

    def test_crisis_message_has_helplines_in_all_languages(self):
        for lang in ("en", "hi", "ta"):
            msg = safety.crisis_response(lang)
            self.assertIn("14416", msg)
            self.assertIn("112", msg)

    def test_language_detection(self):
        self.assertEqual(safety.detect_language("नमस्ते"), "hi")
        self.assertEqual(safety.detect_language("வணக்கம்"), "ta")
        self.assertEqual(safety.detect_language("hello"), "en")


class GeminiProviderTests(unittest.TestCase):
    def test_gemini_request_uses_key_history_and_system_instruction(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "A supportive Gemini reply."}]}}]
        }).encode()

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False):
            provider = GeminiProvider()
        with patch("mannmitra.llm.urllib.request.urlopen", return_value=response) as urlopen:
            reply = provider.reply("Support safely.", [("user", "I feel worried"),
                                                       ("assistant", "I hear you.")], "What can I do?")

        self.assertEqual(reply, "A supportive Gemini reply.")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        self.assertIn("/models/gemini-3.5-flash-lite:generateContent", request.full_url)
        body = json.loads(request.data)
        self.assertEqual(body["systemInstruction"]["parts"][0]["text"], "Support safely.")
        self.assertEqual([item["role"] for item in body["contents"]], ["user", "model", "user"])
        self.assertEqual(body["generationConfig"]["maxOutputTokens"], 768)
        self.assertEqual(body["generationConfig"]["thinkingConfig"]["thinkingLevel"], "low")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 25)

    def test_gemini_rejects_output_truncated_by_token_limit(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = json.dumps({
            "candidates": [{
                "finishReason": "MAX_TOKENS",
                "content": {"parts": [{"text": "This reply stops"}]},
            }]
        }).encode()

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False):
            provider = GeminiProvider()
        with patch("mannmitra.llm.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "truncated"):
                provider.reply("Support safely.", [], "What can I do?")

    def test_provider_selection_uses_gemini_when_configured(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            self.assertIsInstance(get_provider(), GeminiProvider)

    def test_missing_gemini_key_keeps_app_in_offline_mode(self):
        with patch.dict("os.environ", {"MANNMITRA_PROVIDER": "gemini"}, clear=True):
            self.assertIsInstance(get_provider(), OfflineProvider)


class SupabaseStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = SupabaseStore(
            "https://example.supabase.co",
            "service-role-test-key",
            salt="test-salt",
        )

    def test_add_checkin_uses_server_credentials_and_expected_record(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = b""

        with patch("mannmitra.storage.urlopen", return_value=response) as urlopen:
            self.store.add_checkin("hashed-user", 4, 2, 7.5)

        request = urlopen.call_args.args[0]
        self.assertIn("/rest/v1/wellness_checkins", request.full_url)
        self.assertEqual(request.get_header("Apikey"), "service-role-test-key")
        self.assertEqual(request.get_header("Authorization"), "Bearer service-role-test-key")
        record = json.loads(request.data)
        self.assertEqual(
            {key: record[key] for key in ("uid", "mood", "stress", "sleep")},
            {"uid": "hashed-user", "mood": 4, "stress": 2, "sleep": 7.5},
        )

    def test_last_checkin_reads_latest_matching_record(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = json.dumps([
            {"mood": 3, "stress": 4, "sleep": 6.5},
        ]).encode()

        with patch("mannmitra.storage.urlopen", return_value=response):
            self.assertEqual(self.store.last_checkin("hashed-user"), (3, 4, 6.5))

    def test_aggregate_respects_minimum_user_threshold(self):
        checkins = [
            {"uid": f"user-{i}", "mood": i, "stress": 6 - i, "sleep": 6.0 + i / 2}
            for i in range(1, 6)
        ]
        responses = []
        for payload in (checkins, [{"uid": "user-1"}]):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=None)
            response.read.return_value = json.dumps(payload).encode()
            responses.append(response)

        with patch("mannmitra.storage.urlopen", side_effect=responses):
            result = self.store.aggregate()

        self.assertEqual(result["users"], 5)
        self.assertEqual(result["checkins"], 5)
        self.assertEqual(result["avg_mood"], 3)
        self.assertEqual(result["crisis_flags"], 1)

    def test_assessments_are_stored_and_loaded_as_records(self):
        assessment = {"student_name": "Example", "score": 20}
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = b""
        with patch("mannmitra.storage.urlopen", return_value=response) as urlopen:
            self.store.add_assessment(assessment)
        self.assertEqual(json.loads(urlopen.call_args.args[0].data), {"data": assessment})

        response.read.return_value = json.dumps([{"data": assessment}]).encode()
        with patch("mannmitra.storage.urlopen", return_value=response):
            self.assertEqual(self.store.list_assessments(), [assessment])

    def test_missing_supabase_configuration_is_reported(self):
        with self.assertRaisesRegex(ValueError, "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"):
            SupabaseStore("", "")


class AgentTests(unittest.TestCase):
    def test_crisis_bypasses_model(self):
        Boom.called = 0
        a = agent(Boom())
        r = a.handle("u1", "I want to die")
        self.assertIn("14416", r)
        self.assertEqual(Boom.called, 0)

    def test_crisis_interrupts_screening(self):
        a = agent()
        a.handle("u1", "/screen")
        r = a.handle("u1", "I want to kill myself")
        self.assertIn("14416", r)
        self.assertEqual(a.sessions[a.store.user_id("web", "u1")].mode, "")

    def test_provider_failure_falls_back(self):
        a = agent(Boom())
        r = a.handle("u1", "I'm worried about my exam")
        self.assertTrue(len(r) > 10)

    def test_bad_model_output_blocked(self):
        a = agent(Bad())
        r = a.handle("u1", "I feel sad")
        self.assertEqual(r, safety.SAFE_FALLBACK)

    def test_checkin_flow_and_validation(self):
        a = agent()
        a.handle("u1", "/checkin")
        self.assertIn("1 (very low)", a.handle("u1", "banana"))
        self.assertIn("calm", a.handle("u1", "2"))
        self.assertIn("1 (calm)", a.handle("u1", "9"))
        self.assertIn("sleep", a.handle("u1", "4"))
        r = a.handle("u1", "5")
        self.assertIn("Mood 2/5, stress 4/5, sleep 5 h", r)
        uid = a.store.user_id("web", "u1")
        self.assertEqual(a.store.last_checkin(uid), (2, 4, 5.0))
        self.assertIn("someone you trust", r)  # low mood/high stress nudge

    def test_screening_scores(self):
        a = agent()
        a.handle("u1", "/screen")
        for ans in ["2", "2", "0", "1"]:
            r = a.handle("u1", ans)
        self.assertIn("PHQ-2 = 4/6, GAD-2 = 1/6", r)
        self.assertIn("not a diagnosis", screening.INTRO)
        self.assertIn("talk to a counsellor", r)

    def test_screening_can_be_interrupted_with_conversation(self):
        a = agent()
        a.handle("u1", "/screen")
        r = a.handle("u1", "I need help and want to talk")
        self.assertIn("paused the self-check", r)
        self.assertNotIn("Please answer with 0, 1, 2 or 3", r)
        self.assertEqual(a.sessions[a.store.user_id("web", "u1")].mode, "")

    def test_checkin_can_be_interrupted_with_conversation(self):
        a = agent()
        a.handle("u1", "/checkin")
        r = a.handle("u1", "I feel anxious and need help")
        self.assertIn("paused the check-in", r)
        self.assertNotIn("Please answer with a number", r)
        self.assertEqual(a.sessions[a.store.user_id("web", "u1")].mode, "")

    def test_user_can_explicitly_pause_checkin(self):
        a = agent()
        a.handle("u1", "/checkin")
        r = a.handle("u1", "/chat")
        self.assertIn("paused the check-in", r)
        self.assertEqual(a.sessions[a.store.user_id("web", "u1")].mode, "")

    def test_commands(self):
        a = agent()
        self.assertIn("breathing", a.handle("u1", "/tools"))
        self.assertIn("Box breathing", a.handle("u1", "/tool breathing"))
        self.assertIn("/checkin", a.handle("u1", "/help"))
        self.assertIn("don't store", a.handle("u1", "/privacy"))

    def test_delete_erases_data(self):
        a = agent()
        a.handle("u1", "/checkin"); a.handle("u1", "3"); a.handle("u1", "3"); a.handle("u1", "7")
        uid = a.store.user_id("web", "u1")
        self.assertIsNotNone(a.store.last_checkin(uid))
        a.handle("u1", "/delete")
        self.assertIsNone(a.store.last_checkin(uid))

    def test_no_message_text_is_stored(self):
        a = agent()
        a.handle("u1", "my secret worry about my family")
        tables = [r[0] for r in a.store.db.execute("select name from sqlite_master where type='table'")]
        for t in tables:
            for row in a.store.db.execute(f"select * from {t}"):
                self.assertNotIn("secret", str(row))

    def test_aggregate_needs_minimum_users(self):
        a = agent()
        for i in range(4):
            a.store.add_checkin(f"x{i}", 3, 3, 7)
        self.assertTrue(a.store.aggregate().get("insufficient_data"))
        a.store.add_checkin("x5", 5, 1, 8)
        agg = a.store.aggregate()
        self.assertEqual(agg["users"], 5)
        self.assertNotIn("uid", json.dumps(agg))


class WebTests(unittest.TestCase):
    def test_chat_endpoint(self):
        srv = make_server(agent(), port=0)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/chat", method="POST",
                data=json.dumps({"user_id": "w1", "message": "I want to die"}).encode(),
                headers={"Content-Type": "application/json"})
            reply = json.loads(urllib.request.urlopen(req, timeout=5).read())["reply"]
            self.assertIn("14416", reply)
            html = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read().decode()
            self.assertIn("not a doctor", html)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/dashboard", timeout=5)
            self.assertEqual(cm.exception.code, 403)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
