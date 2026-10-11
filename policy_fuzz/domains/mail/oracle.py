"""Independent reference oracle, written from the spec (not from policy.py).

Uses the stdlib RFC-style parser (email.utils.parseaddr) instead of regexes,
and set algebra instead of the policy's incremental loop. Differential testing
therefore finds implementation bugs, NOT mistakes in the spec itself.
"""
from __future__ import annotations

import re
from email.utils import parseaddr
from typing import Optional, Set, Tuple

from .model import Scenario, Value, World


def _readers(world: World, v: Value) -> Optional[Set[str]]:
    sets = [set(world[s].readers) for s in v.sources if world[s].readers is not None]
    if not sets:
        return None
    return set.intersection(*sets)


def expected(world: World, sc: Scenario) -> Tuple[bool, str]:
    text = sc.to.text
    if re.search(r"[,;\r\n]", text):
        return False, "multiple recipients"
    if "<" in text and "@" in text.split("<")[0]:
        return False, "ambiguous display name"
    addr = parseaddr(text)[1].strip().lower().rstrip(".")
    local, _, domain = addr.partition("@")
    wellformed = (addr.isascii() and addr.count("@") == 1 and local != ""
                  and "." in domain and " " not in addr)
    if not wellformed:
        return False, "malformed address"
    if any(not world[s].trusted for s in sc.to.sources):
        return False, "recipient derived from untrusted data"
    for name, v in (("subject", sc.subject), ("body", sc.body)):
        r = _readers(world, v)
        if r is not None and addr not in r:
            return False, f"{name}: recipient not in readers"
    return True, "ok"
