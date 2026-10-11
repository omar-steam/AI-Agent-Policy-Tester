from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import ollama as ol
from .domains import get_domain, get_domains
from .runner import evaluate, format_matrix, make_scenarios, matrix


def _llm_kwargs(a) -> dict:
    return {"model": a.model, "host": a.host, "allow_large": a.allow_large,
            "think": False if a.no_think else None,
            "temperature": a.temperature, "batch": a.batch}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="policy_fuzz", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--domain", default="finance", choices=sorted(get_domains()))
        sp.add_argument("--n", type=int, default=300, help="scenarios per generator")
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument("--model", default=ol.DEFAULT_MODEL, help="Ollama model (<3B)")
        sp.add_argument("--host", default=None, help="Ollama URL (default $OLLAMA_HOST or localhost:11434)")
        sp.add_argument("--allow-large", action="store_true", help="allow models >= 3B")
        sp.add_argument("--temperature", type=float, default=0.8, help="sampling temperature (lower if the model loops)")
        sp.add_argument("--batch", type=int, default=4, help="scenarios requested per model call")
        sp.add_argument("--no-think", action="store_true", help="send think=false (qwen3-style reasoning models)")

    sp = sub.add_parser("matrix", help="detect every injected bug with each generator")
    common(sp)
    sp.add_argument("--gens", default="ollama,mutation,random", help="comma list; ollama = local model, mutation/random = baselines")
    sp.add_argument("--out", default=None, help="write JSON report here")

    sp = sub.add_parser("run", help="fuzz a single policy variant and print findings")
    common(sp)
    sp.add_argument("--target", default="CLEAN", help="CLEAN or a bug id such as F1 / LEGACY")
    sp.add_argument("--gen", default="mutation")

    sub.add_parser("list", help="list domains, specs and bug ids")
    sp = sub.add_parser("check-ollama", help="check the Ollama server and model")
    sp.add_argument("--model", default=ol.DEFAULT_MODEL)
    sp.add_argument("--host", default=None)

    a = p.parse_args(argv)
    try:
        if a.cmd == "list":
            for d in get_domains().values():
                print(f"== {d.name}: {d.title}\n{d.spec}\nBugs:")
                for k, v in d.bugs.items():
                    print(f"  {k:7s} {v}")
                print()
        elif a.cmd == "check-ollama":
            names = ol.list_models(a.host)
            print("Ollama reachable. Models:", ", ".join(names) or "(none)")
            ol.check_model_size(a.model)
            print(("OK: " if a.model in names else "NOT PULLED: run `ollama pull %s` -> " % a.model) + a.model)
        elif a.cmd == "matrix":
            d = get_domain(a.domain)
            m = matrix(d, a.gens.split(","), a.n, a.seed, **_llm_kwargs(a))
            print(format_matrix(m, d))
            if a.out:
                Path(a.out).parent.mkdir(parents=True, exist_ok=True)
                Path(a.out).write_text(json.dumps(m, indent=2, default=str))
                print("report written to", a.out)
        elif a.cmd == "run":
            d = get_domain(a.domain)
            scs, info = make_scenarios(d, a.gen, a.n, a.seed, **(_llm_kwargs(a) if a.gen == "ollama" else {}))
            r = evaluate(d, a.target, scs, a.gen)
            print(f"{d.name}/{a.target} via {a.gen}: {r.n} scenarios -> false_allow={r.false_allow} "
                  f"false_deny={r.false_deny} crashes={r.crashes} unique={r.unique} first_hit={r.first_hit}")
            for f in r.examples[:8]:
                print(f"  #{f.index} {f.kind}: policy={f.policy!r} oracle={f.oracle!r}\n     {f.scenario}")
            if info:
                print("LLM:", info)
    except (ol.OllamaError, KeyError, ValueError) as e:
        print("error:", e, file=sys.stderr)
        return 2
    return 0
