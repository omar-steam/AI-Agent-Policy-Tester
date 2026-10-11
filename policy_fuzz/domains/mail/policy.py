"""The policy UNDER TEST: a CaMeL-style send_email capability check.

Spec (what the policy is supposed to enforce):
  S1 integrity:       the recipient must not be derived from untrusted data.
  S2 confidentiality: every readers-restricted value (subject, body) may only
                      be sent to an address in the intersection of its sources'
                      readers. readers=None is public; empty set is nobody.
  S3 the recipient must be exactly one well-formed address (no lists, and no
     '@' inside a display name: 'a@x.com <b@y.com>' is ambiguous, so denied).
  S4 address comparison is case-insensitive and ignores display names.

`bugs` injects realistic implementation mistakes (mutants) so we can measure
whether a test generator is able to find them.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Set, Tuple

from .model import Scenario, Value, World

BUGS = {
    "B1": "reader match by domain suffix (lookalike domains / wrong person pass)",
    "B2": "no case normalisation (false denies on Alice@Corp.com)",
    "B3": "subject line is never checked",
    "B4": "readers of derived value = UNION of sources, not intersection",
    "B5": "address parsed with first-regex-match (display-name trick)",
    "B6": "empty readers set treated as public ('if not readers')",
    "B7": "integrity check skipped for internal-domain recipients",
    "B8": "multi-recipient string: only the first address is checked",
    "B9": "only the first source of a value is considered",
}

_ADDR_RE = re.compile(r"[a-z0-9._+-]+@[a-z0-9.-]+\.[a-z]{2,}")


class Policy:
    def __init__(self, world: World, bugs: Iterable[str] = ()):
        self.world = world
        self.bugs: Set[str] = set(bugs)
        unknown = self.bugs - set(BUGS)
        if unknown:
            raise ValueError(f"unknown bug ids: {sorted(unknown)}")

    # -- helpers -----------------------------------------------------------
    def _sources(self, v: Value):
        srcs = [self.world[s] for s in v.sources]
        return srcs[:1] if "B9" in self.bugs else srcs

    def _readers(self, v: Value) -> Optional[Set[str]]:
        result: Optional[Set[str]] = None
        for s in self._sources(v):
            if s.readers is None:
                continue
            if result is None:
                result = set(s.readers)
            elif "B4" in self.bugs:
                result = result | set(s.readers)
            else:
                result = result & set(s.readers)
        return result

    def _trusted(self, v: Value) -> bool:
        return all(s.trusted for s in self._sources(v))

    def _address(self, text: str) -> str:
        if "B8" in self.bugs:
            text = text.split(",")[0]
        if "B5" in self.bugs:
            m = re.search(r"[\w.+-]+@[\w.-]+", text)
            addr = m.group(0) if m else ""
        else:
            m = re.search(r"<([^<>]*)>\s*$", text)
            addr = m.group(1) if m else text
        addr = addr.strip().rstrip(".")
        if "B2" not in self.bugs:
            addr = addr.lower()
        return addr

    def _may_read(self, addr: str, readers: Optional[Set[str]]) -> bool:
        if "B6" in self.bugs:
            if not readers:
                return True
        elif readers is None:
            return True
        if "B1" in self.bugs:
            dom = addr.split("@")[-1]
            return any(dom.endswith(r.split("@")[-1]) for r in readers)
        return addr in readers

    # -- the check ---------------------------------------------------------
    def check(self, sc: Scenario) -> Tuple[bool, str]:
        if "B8" not in self.bugs and re.search(r"[,;\r\n]", sc.to.text):
            return False, "multiple recipients"
        if "<" in sc.to.text and "B5" not in self.bugs and "@" in sc.to.text.split("<")[0]:
            return False, "ambiguous display name"
        addr = self._address(sc.to.text)
        if not _ADDR_RE.fullmatch(addr.lower()):
            return False, "malformed address"
        internal = addr.lower().endswith("@corp.com")
        if not (("B7" in self.bugs) and internal):
            if not self._trusted(sc.to):
                return False, "recipient derived from untrusted data"
        for name, v in (("subject", sc.subject), ("body", sc.body)):
            if name == "subject" and "B3" in self.bugs:
                continue
            if not self._may_read(addr, self._readers(v)):
                return False, f"{name}: recipient not in readers"
        return True, "ok"
