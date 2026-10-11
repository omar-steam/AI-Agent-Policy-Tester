"""ORIGINAL engine from the uploaded zip, kept verbatim as a regression target (bug id LEGACY)."""

DEFAULT_POLICY = {
    "name": "Finance assistant baseline",
    "rules": [
        {
            "id": "R001",
            "name": "Transfers require approval above threshold",
            "type": "amount_requires_approval",
            "threshold": 500,
            "currency": "USD",
            "description": "Any transfer above $500 requires an explicit human approval."
        },
        {
            "id": "R002",
            "name": "Only approved recipients",
            "type": "recipient_allowlist",
            "allowed_recipients": ["vendor_acme", "vendor_contoso"],
            "description": "Transfers may only go to approved recipients."
        },
        {
            "id": "R003",
            "name": "No action on untrusted instructions",
            "type": "untrusted_source_blocks_action",
            "untrusted_sources": ["email", "webpage", "document", "external_message"],
            "description": "Instructions originating from untrusted content cannot authorize a financial action."
        },
        {
            "id": "R004",
            "name": "Delegated actions preserve objections",
            "type": "objection_blocks_action",
            "description": "If any participating agent raises an objection, the action must be blocked until resolved."
        }
    ]
}

def evaluate_scenario(scenario, policy):
    """Deterministic evaluator: the LLM never decides allow/deny."""
    violations = []
    action = str(scenario.get("action", "")).lower()
    rules = policy.get("rules", [])

    for rule in rules:
        rtype = rule.get("type")
        rid = rule.get("id", "UNKNOWN")
        if rtype == "amount_requires_approval" and action == "transfer":
            try:
                amount = float(scenario.get("amount", 0))
            except (TypeError, ValueError):
                violations.append({"rule_id": rid, "rule": rule.get("name", rtype),
                                   "reason": "Amount is missing or not numeric."})
                continue
            if amount > float(rule.get("threshold", 0)) and not bool(scenario.get("approval", False)):
                violations.append({"rule_id": rid, "rule": rule.get("name", rtype),
                                   "reason": f"Amount {amount:g} exceeds threshold {rule.get('threshold')} without approval."})
        elif rtype == "recipient_allowlist" and action == "transfer":
            allowed = rule.get("allowed_recipients", [])
            if scenario.get("recipient") not in allowed:
                violations.append({"rule_id": rid, "rule": rule.get("name", rtype),
                                   "reason": f"Recipient {scenario.get('recipient')!r} is not allowlisted."})
        elif rtype == "untrusted_source_blocks_action" and action in {"transfer", "pay", "refund", "wire"}:
            sources = [str(s).lower() for s in rule.get("untrusted_sources", [])]
            source = str(scenario.get("instruction_source", "")).lower()
            if source in sources:
                violations.append({"rule_id": rid, "rule": rule.get("name", rtype),
                                   "reason": f"Action was triggered by untrusted source {source!r}."})
        elif rtype == "objection_blocks_action" and bool(scenario.get("objection", False)):
            violations.append({"rule_id": rid, "rule": rule.get("name", rtype),
                               "reason": "At least one agent raised an unresolved objection."})

    decision = "deny" if violations else "allow"
    expected = str(scenario.get("expected", "")).lower()
    test_pass = (decision == expected) if expected in {"allow", "deny"} else None
    return {
        "scenario_id": scenario.get("id", ""),
        "scenario": scenario.get("name", ""),
        "decision": decision,
        "expected": expected or "not set",
        "test_pass": test_pass,
        "violations": violations,
        "violation_count": len(violations),
    }
