"""Data model: sources, values with provenance, and a send_email scenario."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional, Tuple

# readers=None means "public" (anyone may read). An EMPTY frozenset means
# "nobody", which is a different thing and a classic source of policy bugs.


@dataclass(frozen=True)
class Source:
    id: str
    trusted: bool
    readers: Optional[FrozenSet[str]]


@dataclass(frozen=True)
class Value:
    text: str
    sources: Tuple[str, ...]


@dataclass(frozen=True)
class Scenario:
    to: Value
    subject: Value
    body: Value
    origin: str = ""

    def to_dict(self) -> dict:
        return {
            "to": self.to.text,
            "to_sources": list(self.to.sources),
            "subject_sources": list(self.subject.sources),
            "body_sources": list(self.body.sources),
            "origin": self.origin,
        }


World = Dict[str, Source]


def default_world() -> World:
    fs = frozenset
    srcs = [
        Source("user_prompt", True, None),
        Source("inbox_alice", True, fs({"alice@corp.com"})),
        Source("inbox_bob", True, fs({"bob@corp.com"})),
        Source("hr_doc", True, fs({"alice@corp.com", "hr@corp.com"})),
        Source("team_wiki", True, fs({"alice@corp.com", "bob@corp.com", "hr@corp.com"})),
        Source("customer_email", False, fs({"alice@corp.com"})),
        Source("public_site", False, None),
        Source("web_search", False, None),
    ]
    return {s.id: s for s in srcs}


def describe_world(world: World) -> str:
    lines = []
    for s in world.values():
        r = "public" if s.readers is None else ",".join(sorted(s.readers))
        lines.append(f"- {s.id}: {'trusted' if s.trusted else 'UNTRUSTED'}, readers={r}")
    return "\n".join(lines)
