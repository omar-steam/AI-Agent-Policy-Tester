"""Run scenarios through a policy and compare with the oracle."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .domains.base import Domain


def _jsonable(x):
    return json.loads(json.dumps(x, default=str))  # NaN stays NaN; non-JSON types become strings


@dataclass
class Finding:
    index: int
    kind: str            # false_allow (security bug) | false_deny (utility bug) | crash
    scenario: dict
    policy: str
    oracle: str


@dataclass
class Report:
    domain: str
    target: str
    generator: str
    n: int
    false_allow: int = 0
    false_deny: int = 0
    crashes: int = 0
    first_hit: Optional[int] = None
    unique: int = 0
    examples: List[Finding] = field(default_factory=list)

    @property
    def findings(self) -> int:
        return self.false_allow + self.false_deny + self.crashes

    @property
    def detected(self) -> bool:
        return self.findings > 0

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in ("domain", "target", "generator", "n", "false_allow",
                                           "false_deny", "crashes", "first_hit", "unique")}
        d["examples"] = [{"index": f.index, "kind": f.kind, "scenario": _jsonable(f.scenario),
                          "policy": f.policy, "oracle": f.oracle} for f in self.examples]
        return d


def make_scenarios(domain: Domain, gen: str, n: int, seed: int = 0, **llm_kwargs):
    """Return (scenarios, info). gen: random | mutation | ollama."""
    rng = random.Random(seed)
    if gen == "random":
        return [domain.random_scenario(rng) for _ in range(n)], {}
    if gen == "mutation":
        return [domain.mutated_scenario(rng) for _ in range(n)], {}
    if gen == "ollama":
        from .ollama import OllamaScenarioGenerator
        g = OllamaScenarioGenerator(domain, seed=seed, **llm_kwargs)
        scs = g.generate(n)
        return scs, {"model": g.model, **g.stats.__dict__}
    raise ValueError(f"unknown generator {gen!r} (random|mutation|ollama)")


def evaluate(domain: Domain, target: str, scenarios: List[dict], generator: str = "?",
             keep: int = 12) -> Report:
    """target: 'CLEAN' or a bug id (e.g. F1, LEGACY)."""
    check = domain.policy([] if target == "CLEAN" else [target])
    rep = Report(domain.name, target, generator, len(scenarios))
    sigs = set()
    for i, sc in enumerate(scenarios, 1):
        exp_allow, exp_reason = domain.oracle(sc)
        try:
            got_allow, got_reason = check(sc)
        except Exception as e:  # noqa: BLE001 - a crashing policy is itself a finding
            kind, got_reason = "crash", f"{type(e).__name__}: {e}"
        else:
            if got_allow == exp_allow:
                continue
            kind = "false_allow" if got_allow else "false_deny"
        if kind == "false_allow":
            rep.false_allow += 1
        elif kind == "false_deny":
            rep.false_deny += 1
        else:
            rep.crashes += 1
        rep.first_hit = rep.first_hit or i
        sigs.add((kind, got_reason, exp_reason))
        if len(rep.examples) < keep:
            rep.examples.append(Finding(i, kind, sc, got_reason, exp_reason))
    rep.unique = len(sigs)
    return rep


def matrix(domain: Domain, gens: List[str], n: int, seed: int = 0, targets: Optional[List[str]] = None,
           **llm_kwargs) -> dict:
    """Every generator x every target. Same scenario set is reused across targets."""
    targets = targets or ["CLEAN"] + list(domain.bugs)
    sets, infos = {}, {}
    for g in gens:
        sets[g], infos[g] = make_scenarios(domain, g, n, seed, **llm_kwargs)
    rows = [evaluate(domain, t, sets[g], g).to_dict() for g in gens for t in targets]
    mutants = [t for t in targets if t != "CLEAN"]
    summary = {}
    for g in gens:
        killed = sum(1 for r in rows if r["generator"] == g and r["target"] in mutants and r["first_hit"])
        clean = next((r for r in rows if r["generator"] == g and r["target"] == "CLEAN"), None)
        summary[g] = {"scenarios": len(sets[g]), "mutants_detected": killed, "mutants_total": len(mutants),
                      "clean_false_positives": None if clean is None else
                      clean["false_allow"] + clean["false_deny"] + clean["crashes"], "info": infos[g]}
    return {"domain": domain.name, "n": n, "seed": seed, "rows": rows, "summary": summary}


def format_matrix(m: dict, domain: Domain) -> str:
    gens = list(m["summary"])
    head = f"{'target':8s} {'description':64s} " + " ".join(f"{g:>14s}" for g in gens)
    lines = [head, "-" * len(head)]
    by = {(r["target"], r["generator"]): r for r in m["rows"]}
    targets = list(dict.fromkeys(r["target"] for r in m["rows"]))
    for t in targets:
        desc = "(no bug: must report 0 findings)" if t == "CLEAN" else domain.bugs.get(t, "")
        cells = []
        for g in gens:
            r = by[(t, g)]
            if m["summary"][g]["scenarios"] == 0:
                cells.append(f"{'NO SCENARIOS':>14s}")
                continue
            cells.append(f"{(('hit@%d' % r['first_hit']) if r['first_hit'] else 'missed') if t != 'CLEAN' else str(r['false_allow'] + r['false_deny'] + r['crashes']) + ' FP':>14s}")
        lines.append(f"{t:8s} {desc[:64]:64s} " + " ".join(cells))
    lines.append("")
    for g, s in m["summary"].items():
        lines.append(f"{g}: {s['mutants_detected']}/{s['mutants_total']} bugs detected, "
                     f"{s['clean_false_positives']} false positives on the clean policy, {s['scenarios']} scenarios"
                     + (f"  [LLM: {s['info']}]" if s["info"] else ""))
    return "\n".join(lines)
