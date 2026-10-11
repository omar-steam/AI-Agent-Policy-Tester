import json
import os
import random
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from policy_fuzz import ollama as ol  # noqa: E402
from policy_fuzz.domains import get_domain, get_domains  # noqa: E402
from policy_fuzz.runner import evaluate, make_scenarios, matrix  # noqa: E402

FIN = get_domain("finance")
BASE = dict(action="transfer", amount=900, currency="USD", recipient="vendor_acme", approval=False,
            approval_source="human", instruction_source="user", objection=False)


def case(**kw):
    s = dict(BASE)
    s.update(kw)
    return {k: v for k, v in s.items() if v is not KeyError}


class CleanPolicyMatchesOracle(unittest.TestCase):
    def test_zero_false_positives_both_domains(self):
        for d in get_domains().values():
            scs, _ = make_scenarios(d, "mutation", 2000, seed=7)
            scs += make_scenarios(d, "random", 1000, seed=8)[0]
            r = evaluate(d, "CLEAN", scs)
            self.assertEqual(r.findings, 0, f"{d.name}: {r.examples[:2]}")


class EveryInjectedBugIsDetected(unittest.TestCase):
    def test_mutation_generator_finds_all_bugs(self):
        for d in get_domains().values():
            scs, _ = make_scenarios(d, "mutation", 2500, seed=3)
            for bug in d.bugs:
                self.assertTrue(evaluate(d, bug, scs).detected, f"{d.name}/{bug} was missed")


class OriginalEngineBugs(unittest.TestCase):
    """Each line is a bug I confirmed in the uploaded engine; the hardened policy must fix it."""
    CASES = {
        "action alias 'wire'": case(action="wire", recipient="evil"),
        "action trailing space": case(action="Transfer ", recipient="evil"),
        "unknown action": case(action="send_money", recipient="evil"),
        "missing action": case(action=KeyError, recipient="evil"),
        "NaN amount": case(amount=float("nan"), approval=False),
        "negative amount": case(amount=-900),
        "missing amount": case(amount=KeyError),
        "approval 'false' string": case(approval="false"),
        "untrusted source slack": case(instruction_source="slack", amount=10),
        "source with whitespace": case(instruction_source="Email ", amount=10),
        "missing source": case(instruction_source=KeyError, amount=10),
        "missing objection": case(objection=KeyError, amount=10),
        "currency GBP": case(currency="GBP", amount=450),
        "approval by agent": case(approval=True, approval_source="agent"),
        "recipient prefix": case(recipient="vendor_acme_evil", amount=10),
    }

    def test_hardened_denies_and_legacy_allows_most(self):
        clean, legacy = FIN.policy(), FIN.policy(["LEGACY"])
        legacy_allows = 0
        for name, sc in self.CASES.items():
            self.assertFalse(clean(sc)[0], f"hardened policy allowed: {name}")
            self.assertFalse(FIN.oracle(sc)[0], f"oracle allowed: {name}")
            legacy_allows += legacy(sc)[0]
        self.assertGreaterEqual(legacy_allows, 9)  # the original engine fails open on most of these

    def test_valid_cases_still_allowed(self):
        clean = FIN.policy()
        for sc in (case(amount=500, approval=False), case(amount=900, approval=True),
                   case(amount=100, approval=False, approval_source=KeyError), case(action="wire", amount=80)):
            self.assertTrue(clean(sc)[0], sc)
            self.assertTrue(FIN.oracle(sc)[0], sc)

    def test_threshold_boundary(self):
        clean = FIN.policy()
        self.assertTrue(clean(case(amount=500))[0])
        self.assertFalse(clean(case(amount=500.01))[0])
        self.assertFalse(FIN.policy(["F8"])(case(amount=500))[0])  # off-by-one mutant over-blocks


class MailDomain(unittest.TestCase):
    def test_display_name_trick_and_lookalike(self):
        d = get_domain("mail")
        sc = {"to": "alice@corp.com <evil@attacker.com>", "to_sources": ["user_prompt"],
              "subject_sources": ["user_prompt"], "body_sources": ["inbox_alice"]}
        self.assertFalse(d.oracle(sc)[0])
        self.assertFalse(d.policy()(sc)[0])
        self.assertTrue(d.policy(["B5"])(sc)[0])
        look = dict(sc, to="eve@evilcorp.com")        # lookalike of corp.com; alice is the only reader
        self.assertFalse(d.oracle(look)[0])
        self.assertFalse(d.policy()(look)[0])
        self.assertTrue(d.policy(["B1"])(look)[0])    # suffix-match bug lets it through


class OllamaClient(unittest.TestCase):
    def test_size_guard(self):
        for tag in ("qwen2.5:3b", "llama3.1:8b", "qwen2.5:7b-instruct"):
            with self.assertRaises(ol.OllamaError):
                ol.check_model_size(tag)
        for tag in ("qwen2.5:1.5b", "qwen2.5:0.5b", "llama3.2:1b", "gemma2:2b", "qwen3:1.7b", "qwen2.5"):
            ol.check_model_size(tag)
        ol.check_model_size("qwen2.5:3b", allow_large=True)

    def test_extract_json_lenient(self):
        self.assertEqual(ol.extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(ol.extract_json('Sure! {"a": [1]} done'), {"a": [1]})
        self.assertEqual(ol.extract_json("[1,2]"), [1, 2])
        self.assertIsNone(ol.extract_json("no json"))
        self.assertTrue(ol.extract_json('{"x": NaN}')["x"] != ol.extract_json('{"x": NaN}')["x"])  # NaN parses

    def _serve(self, responder):
        class H(BaseHTTPRequestHandler):
            def do_POST(s):  # noqa: N805
                body = json.loads(s.rfile.read(int(s.headers["Content-Length"])))
                H.seen.append(body)
                out = json.dumps({"response": responder(len(H.seen))}).encode()
                s.send_response(200); s.send_header("Content-Length", str(len(out))); s.end_headers(); s.wfile.write(out)

            def do_GET(s):  # noqa: N805
                out = json.dumps({"models": [{"name": "qwen2.5:1.5b"}]}).encode()
                s.send_response(200); s.send_header("Content-Length", str(len(out))); s.end_headers(); s.wfile.write(out)

            def log_message(s, *a):  # noqa: N805
                pass
        H.seen = []
        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_port}", H

    def test_generator_with_mock_server(self):
        def responder(call):
            if call == 1:   # messy model output: junk item, duplicate, NaN, hostile types
                return ('{"scenarios": ["junk", {"action":"wire","amount":NaN,"currency":"USD",'
                        '"recipient":"vendor_acme","approval":"false","instruction_source":"slack","objection":false},'
                        '{"action":"wire","amount":NaN,"currency":"USD","recipient":"vendor_acme",'
                        '"approval":"false","instruction_source":"slack","objection":false}]}')
            if call == 2:
                return "not json at all"
            return '[{"action":"Pay ","amount":-5,"recipient":"vendor_acme"}]'
        host, H = self._serve(responder)
        self.assertEqual(ol.list_models(host), ["qwen2.5:1.5b"])
        g = ol.OllamaScenarioGenerator(FIN, model="qwen2.5:1.5b", host=host, max_calls=3)
        scs = g.generate(10)
        self.assertEqual(len(scs), 2)                 # junk dropped, duplicate dropped
        self.assertEqual(g.stats.parse_failures, 1)
        self.assertEqual(H.seen[0]["format"], "json")
        self.assertEqual(H.seen[0]["model"], "qwen2.5:1.5b")
        self.assertNotEqual(H.seen[0]["options"]["seed"], H.seen[1]["options"]["seed"])
        # LLM-proposed inputs flow through the same oracle: legacy engine fails open on the NaN/slack wire
        r = evaluate(FIN, "LEGACY", scs, "ollama")
        self.assertGreaterEqual(r.false_allow, 1)
        self.assertEqual(evaluate(FIN, "CLEAN", scs, "ollama").findings, 0)

    def test_repeat_limit_500_is_retried_not_fatal(self):
        class H(BaseHTTPRequestHandler):
            calls = []

            def do_POST(s):  # noqa: N805
                body = json.loads(s.rfile.read(int(s.headers["Content-Length"])))
                H.calls.append(body["options"]["temperature"])
                if len(H.calls) <= 2:
                    out, code = b'{"error":"prediction aborted, token repeat limit reached"}', 500
                else:
                    out, code = json.dumps({"response": '{"scenarios":[{"action":"wire","amount":9}]}'}).encode(), 200
                s.send_response(code); s.send_header("Content-Length", str(len(out))); s.end_headers(); s.wfile.write(out)

            def log_message(s, *a):  # noqa: N805
                pass
        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        g = ol.OllamaScenarioGenerator(FIN, host=f"http://127.0.0.1:{srv.server_port}", max_calls=5)
        scs = g.generate(1)
        self.assertEqual(len(scs), 1)                         # recovered after two loop failures
        self.assertEqual(len(g.stats.errors), 2)
        self.assertNotIn("is the model pulled", g.stats.errors[0])
        self.assertLess(H.calls[2], H.calls[0])               # temperature lowered after failures

    def test_think_flag_is_sent_only_when_requested(self):
        host, H = self._serve(lambda c: '{"scenarios":[{"action":"wire"}]}')
        ol.OllamaScenarioGenerator(FIN, host=host, max_calls=1).generate(1)
        ol.OllamaScenarioGenerator(FIN, host=host, max_calls=1, think=False).generate(1)
        self.assertNotIn("think", H.seen[0])
        self.assertIs(H.seen[1]["think"], False)

    def test_unreachable_server_is_a_friendly_error(self):
        g = ol.OllamaScenarioGenerator(FIN, host="http://127.0.0.1:9", max_calls=1, timeout=2)
        self.assertEqual(g.generate(5), [])
        self.assertIn("Cannot reach Ollama", g.stats.errors[0])

    def test_matrix_runs_with_ollama_generator(self):
        host, _ = self._serve(lambda c: '{"scenarios":[{"action":"wire","amount":900,"currency":"USD",'
                                        '"recipient":"vendor_acme","approval":true,"instruction_source":"user",'
                                        '"objection":false}]}')
        m = matrix(FIN, ["mutation", "ollama"], 50, 0, model="qwen2.5:1.5b", host=host, allow_large=False)
        self.assertEqual(m["summary"]["mutation"]["clean_false_positives"], 0)
        self.assertIn("ollama", m["summary"])


if __name__ == "__main__":
    unittest.main()
