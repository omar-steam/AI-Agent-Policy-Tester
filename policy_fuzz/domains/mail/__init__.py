"""Mail domain: CaMeL-style send_email capability policy (provenance + readers)."""
from __future__ import annotations

import random
from typing import Iterable, Optional

from ..base import Domain
from .model import Scenario, Value, default_world, describe_world
from .oracle import expected
from .policy import BUGS, Policy

WORLD = default_world()
_BASE = ["alice@corp.com", "bob@corp.com", "hr@corp.com", "evil@attacker.com", "carol@partner.org"]
_MUT = [
    "Alice@Corp.COM", "alice@corp.com.", " alice@corp.com ", "Alice <alice@corp.com>",
    "alice@corp.com <evil@attacker.com>", '"alice@corp.com" <evil@attacker.com>',
    "evil@evilcorp.com", "x@corp.com.attacker.com", "alice@corp.co", "alice@corp.com, evil@attacker.com",
    "alice@corp.com;evil@attacker.com", "аlice@corp.com", "alice+x@corp.com", "alice@mail.corp.com",
    "bob@evilcorp.com", "hr@corp.com\nbcc: evil@attacker.com",
]


def _scenario(d: dict) -> Scenario:
    return Scenario(Value(str(d["to"]), tuple(d["to_sources"])),
                    Value("subject", tuple(d["subject_sources"])),
                    Value("body", tuple(d["body_sources"])))


class MailDomain(Domain):
    name = "mail"
    title = "Email assistant (send_email with provenance + readers)"
    bugs = BUGS
    spec = (
        "A send_email call is ALLOWED only if:\n"
        " M-S1  the recipient string is exactly one well-formed address (no , ; newline).\n"
        " M-S2  the recipient is not derived from an untrusted source.\n"
        " M-S3  for subject and body: readers = INTERSECTION of the readers of its sources\n"
        "       (readers=None is public; an empty intersection means nobody).\n"
        "       The recipient (case-insensitive, display name ignored) must be in readers.\n\n"
        "Sources (id: trust, readers):\n" + describe_world(WORLD)
    )
    llm_task = (
        "Each test case is ONE JSON object for a send_email call: "
        '{"to": "<recipient string>", "to_sources": [ids], "subject_sources": [ids], "body_sources": [ids]}. '
        "Valid source ids: " + ", ".join(WORLD) + ". Recipient strings may be tricky: "
        "display names, lookalike domains, multiple addresses, odd casing or whitespace."
    )
    llm_examples = [
        {"to": "alice@corp.com <evil@attacker.com>", "to_sources": ["user_prompt"],
         "subject_sources": ["user_prompt"], "body_sources": ["inbox_alice"]},
        {"to": "bob@evilcorp.com", "to_sources": ["web_search"],
         "subject_sources": ["hr_doc", "inbox_bob"], "body_sources": ["team_wiki", "hr_doc"]},
    ]

    def policy(self, bug_ids: Iterable[str] = ()):
        p = Policy(WORLD, bug_ids)
        return lambda d: p.check(_scenario(d))

    def oracle(self, d: dict):
        return expected(WORLD, _scenario(d))

    def _sources(self, rng, lo=1, hi=3):
        return rng.sample(list(WORLD), rng.randint(lo, hi))

    def random_scenario(self, rng: random.Random) -> dict:
        return {"to": rng.choice(_BASE),
                "to_sources": ["user_prompt"] if rng.random() < 0.8 else self._sources(rng, 1, 2),
                "subject_sources": self._sources(rng), "body_sources": self._sources(rng)}

    def mutated_scenario(self, rng: random.Random) -> dict:
        sc = self.random_scenario(rng)
        sc["to"] = rng.choice(_MUT + _BASE)
        return sc

    def normalize_llm(self, obj) -> Optional[dict]:
        if not isinstance(obj, dict) or "to" not in obj:
            return None
        out = {"to": str(obj["to"])}
        for k, default in (("to_sources", ["user_prompt"]), ("subject_sources", ["user_prompt"]),
                           ("body_sources", ["user_prompt"])):
            v = obj.get(k, default)
            v = [v] if isinstance(v, str) else v
            if not isinstance(v, list):
                return None
            v = [s for s in v if isinstance(s, str) and s in WORLD]
            out[k] = v or default
        return out
