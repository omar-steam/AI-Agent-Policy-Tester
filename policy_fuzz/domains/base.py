"""Domain interface. A domain bundles: the policy under test (with injectable
bugs), an independent spec oracle, and scenario generators. Scenarios are plain
dicts so they can be produced by an LLM and stored as JSON."""
from __future__ import annotations

import random
from typing import Callable, Dict, Iterable, Optional, Tuple

Verdict = Tuple[bool, str]  # (allowed, reason)


class Domain:
    name = ""
    title = ""
    spec = ""                   # human-readable spec shown in the UI/README
    bugs: Dict[str, str] = {}   # id -> description (mutants)
    llm_task = ""               # instructions for the scenario-generating LLM
    llm_examples: list = []

    def policy(self, bug_ids: Iterable[str] = ()) -> Callable[[dict], Verdict]:
        raise NotImplementedError

    def oracle(self, scenario: dict) -> Verdict:
        raise NotImplementedError

    def random_scenario(self, rng: random.Random) -> dict:
        raise NotImplementedError

    def mutated_scenario(self, rng: random.Random) -> dict:
        raise NotImplementedError

    def normalize_llm(self, obj) -> Optional[dict]:
        return obj if isinstance(obj, dict) else None

    def all_targets(self) -> Dict[str, str]:
        return dict(self.bugs)
