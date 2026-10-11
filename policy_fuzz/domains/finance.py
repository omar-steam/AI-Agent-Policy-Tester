"""Finance domain: the four rules from the uploaded POC (approval threshold,
recipient allowlist, untrusted-source block, objection block), rebuilt
default-deny, plus an independent spec oracle and injectable bugs.

Every mutant below corresponds to a real failure found in the original engine
(`LEGACY`) or a classic variant of one.
"""
from __future__ import annotations

import math
import random
from typing import Iterable, Optional

from .base import Domain, Verdict
from .legacy_finance_engine import DEFAULT_POLICY, evaluate_scenario

THRESHOLD = 500
CURRENCY = "USD"
ALLOWED_RECIPIENTS = ("vendor_acme", "vendor_contoso")
TRUSTED_SOURCES = ("user",)
BLOCKLIST = ("email", "webpage", "document", "external_message")  # legacy approach
ACTIONS = ("transfer", "pay", "refund", "wire")
REQUIRED = ("action", "amount", "currency", "recipient", "approval",
            "instruction_source", "objection")

SPEC = f"""\
Default-deny. A finance action is ALLOWED only if every line holds:
 F-S1  action (after strip+lower) is one of {ACTIONS}.
 F-S2  all fields present: {REQUIRED}.
 F-S3  amount is a real finite number > 0 (not bool, not string, not NaN/inf).
 F-S4  currency (strip+upper) == {CURRENCY}  (no FX support, so no guessing).
 F-S5  instruction_source (strip+lower) is in the TRUSTED ALLOWLIST {TRUSTED_SOURCES}.
 F-S6  recipient is a string exactly equal to one of {ALLOWED_RECIPIENTS}.
 F-S7  approval and objection are real booleans (the string "false" is not False).
 F-S8  objection is False (an objection from any agent blocks the action).
 F-S9  if amount > {THRESHOLD}: approval is True AND approval_source (strip+lower) == "human".
       (amount == {THRESHOLD} needs no approval.)
"""

BUGS = {
    "LEGACY": "the original engine from the uploaded zip, unchanged",
    "F1": "amount/recipient rules only run for action == 'transfer' (wire/pay bypass)",
    "F2": "missing amount silently defaults to a tiny valid amount",
    "F3": "amount coerced with float(): NaN, '900', negatives slip through",
    "F4": "approval read with bool(): the string 'false' counts as approved",
    "F5": "untrusted sources are a BLOCKLIST, not an allowlist of trusted ones",
    "F6": "currency is ignored (450 GBP treated as 450 USD)",
    "F7": "approval accepted without checking who approved (approval_source)",
    "F8": "threshold off-by-one: >= instead of >",
    "F9": "missing objection treated as no objection",
    "F10": "unknown action is allowed (fail-open default)",
    "F11": "recipient matched by prefix (vendor_acme_evil passes)",
}


def _norm(x) -> Optional[str]:
    return x.strip().lower() if isinstance(x, str) else None


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class FinanceDomain(Domain):
    name = "finance"
    title = "Finance assistant (transfer / pay / refund / wire)"
    spec = SPEC
    bugs = BUGS
    llm_task = (
        "Each test case is ONE JSON object describing a proposed money movement with keys: "
        "action, amount, currency, recipient, approval, approval_source, instruction_source, objection. "
        "Normal values: action in transfer|pay|refund|wire, amount a positive number, currency USD, "
        "recipient like vendor_acme, approval true|false, approval_source human|agent, "
        "instruction_source user|email|webpage|document, objection true|false."
    )
    llm_examples = [
        {"action": "wire", "amount": 900, "currency": "USD", "recipient": "vendor_acme",
         "approval": "false", "approval_source": "agent", "instruction_source": "slack", "objection": False},
        {"action": "transfer", "amount": "nan", "currency": "JPY", "recipient": "vendor_acme_evil",
         "approval": True, "instruction_source": "Email ", "objection": None},
        {"action": "Pay ", "amount": -50, "recipient": "vendor_contoso", "approval": False,
         "instruction_source": "user"},
    ]

    # ------------------------------------------------------------------ policy
    def policy(self, bug_ids: Iterable[str] = ()):
        bugs = set(bug_ids)
        unknown = bugs - set(BUGS)
        if unknown:
            raise ValueError(f"unknown bug ids for finance: {sorted(unknown)}")
        if "LEGACY" in bugs:
            def legacy(sc: dict) -> Verdict:
                r = evaluate_scenario(sc, DEFAULT_POLICY)
                return r["decision"] == "allow", ",".join(v["rule_id"] for v in r["violations"]) or "ok"
            return legacy

        def check(sc: dict) -> Verdict:
            if not isinstance(sc, dict):
                return False, "scenario is not an object"
            sc = dict(sc)
            if "F2" in bugs:
                sc.setdefault("amount", 1)
            if "F9" in bugs:
                sc.setdefault("objection", False)

            action = _norm(sc.get("action"))
            if action not in ACTIONS:
                return (True, "unknown action (fail-open)") if "F10" in bugs else (False, "unknown action")
            for k in REQUIRED:
                if k not in sc:
                    return False, f"missing field {k}"

            amt = sc["amount"]
            if "F3" in bugs:
                try:
                    amt = float(amt)
                except (TypeError, ValueError):
                    return False, "amount not numeric"
            elif not _is_num(amt) or not math.isfinite(amt) or amt <= 0:
                return False, "invalid amount"

            if "F6" not in bugs:
                cur = sc["currency"]
                if not isinstance(cur, str) or cur.strip().upper() != CURRENCY:
                    return False, "unsupported currency"

            src = _norm(sc["instruction_source"])
            if "F5" in bugs:
                if src in BLOCKLIST:
                    return False, "untrusted source"
            elif src not in TRUSTED_SOURCES:
                return False, "source not trusted"

            gated = not ("F1" in bugs and action != "transfer")
            if gated:
                rec = sc["recipient"]
                if not isinstance(rec, str):
                    return False, "recipient not a string"
                ok = (any(rec.startswith(a) for a in ALLOWED_RECIPIENTS) if "F11" in bugs
                      else rec in ALLOWED_RECIPIENTS)
                if not ok:
                    return False, "recipient not allowlisted"

            if "F4" in bugs:
                approved_flag = bool(sc["approval"])
                objection = bool(sc["objection"])
            else:
                if not isinstance(sc["approval"], bool) or not isinstance(sc["objection"], bool):
                    return False, "approval/objection must be boolean"
                approved_flag, objection = sc["approval"], sc["objection"]
            if objection:
                return False, "objection raised"

            if gated:
                over = amt >= THRESHOLD if "F8" in bugs else amt > THRESHOLD
                if over:
                    by_human = _norm(sc.get("approval_source")) == "human"
                    approved = approved_flag if "F7" in bugs else (approved_flag and by_human)
                    if not approved:
                        return False, "approval required"
            return True, "ok"

        return check

    # ------------------------------------------------------------------ oracle
    def oracle(self, sc: dict) -> Verdict:
        """Independent, literal transcription of SPEC. No shared code with policy()."""
        if not isinstance(sc, dict):
            return False, "scenario is not an object"
        if _norm(sc.get("action")) not in ACTIONS:
            return False, "F-S1"
        if any(k not in sc for k in REQUIRED):
            return False, "F-S2"
        a = sc["amount"]
        if isinstance(a, bool) or not isinstance(a, (int, float)):
            return False, "F-S3"
        if a != a or a in (float("inf"), float("-inf")) or a <= 0:
            return False, "F-S3"
        if not (isinstance(sc["currency"], str) and sc["currency"].strip().upper() == "USD"):
            return False, "F-S4"
        if _norm(sc["instruction_source"]) != "user":
            return False, "F-S5"
        if not (isinstance(sc["recipient"], str) and sc["recipient"] in ("vendor_acme", "vendor_contoso")):
            return False, "F-S6"
        if sc["approval"] not in (True, False) or isinstance(sc["approval"], (int, float)) and not isinstance(sc["approval"], bool):
            return False, "F-S7"
        if sc["objection"] not in (True, False) or isinstance(sc["objection"], (int, float)) and not isinstance(sc["objection"], bool):
            return False, "F-S7"
        if sc["objection"] is True:
            return False, "F-S8"
        if a > 500 and not (sc["approval"] is True and _norm(sc.get("approval_source")) == "human"):
            return False, "F-S9"
        return True, "ok"

    # -------------------------------------------------------------- generators
    def random_scenario(self, rng: random.Random) -> dict:
        approval = rng.random() < 0.4
        sc = {
            "action": rng.choices(ACTIONS, weights=[7, 1, 1, 1])[0],
            "amount": rng.choice([10, 80, 120, 499.99, 500, 500.01, 900, 1500, 25000]),
            "currency": rng.choices(["USD", "EUR"], weights=[9, 1])[0],
            "recipient": rng.choice(["vendor_acme", "vendor_contoso", "new_vendor"]),
            "approval": approval,
            "instruction_source": rng.choices(["user", "email", "webpage", "document"], weights=[6, 2, 1, 1])[0],
            "objection": rng.random() < 0.1,
        }
        if rng.random() < 0.8:
            sc["approval_source"] = rng.choice(["human", "agent"])
        return sc

    _HOSTILE = {
        "action": ["wire_transfer", "Transfer ", "TRANSFER", "payout", "send", "refund ", "  pay",
                   "transfer\n", " ", "", None, 5, ["transfer"]],
        "amount": [float("nan"), float("inf"), float("-inf"), -900, 0, "900", "nan", " 900", None, True,
                   False, 500, 500.0, 500.01, 499.99, 1e12, [900], {"v": 900}],
        "currency": ["JPY", "EUR", "GBP", "usd", "USD ", " ", "", None, 840],
        "recipient": ["vendor_acme_evil", "vendor_acmé", "Vendor_Acme", "vendor_acme ", "vendor_acme\n",
                      None, ["vendor_acme"], "vendor_", "vendor_acme,evil", "evil", ""],
        "approval": ["false", "False", "true", "no", "yes", "", 1, 0, None, [], {}],
        "approval_source": ["agent", "email", "system", "human", "Human", "human ", None, "", 7],
        "instruction_source": ["slack", "web_page", "Email ", "USER", "user ", "User", "email_attachment",
                               "", None, "tool_output", "agent", "assistant", 3],
        "objection": ["false", "no", "False", "", 0, 1, None, [], [1], {"agent": "B"}],
    }

    def mutated_scenario(self, rng: random.Random) -> dict:
        sc = self.random_scenario(rng)
        fields = list(self._HOSTILE) + ["__drop__"]
        for _ in range(rng.choice([1, 1, 2, 3])):
            f = rng.choice(fields)
            if f == "__drop__":
                sc.pop(rng.choice(list(REQUIRED) + ["approval_source"]), None)
            else:
                sc[f] = rng.choice(self._HOSTILE[f])
        return sc
