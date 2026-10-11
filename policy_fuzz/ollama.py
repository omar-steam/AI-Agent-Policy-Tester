"""Minimal stdlib Ollama client + an LLM scenario generator.

The model ONLY proposes inputs. It never labels them and never decides
allow/deny: the oracle does that. Models >= 3B parameters are refused unless
allow_large=True, matching the project constraint (small local models).
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

DEFAULT_MODEL = "qwen2.5:1.5b"
SUGGESTED_MODELS = ["qwen2.5:0.5b", "qwen2.5:1.5b", "llama3.2:1b", "qwen3:1.7b", "gemma2:2b"]


class OllamaError(RuntimeError):
    """status is the HTTP status for server-side errors, None for connection problems."""

    def __init__(self, msg: str, status: Optional[int] = None):
        super().__init__(msg)
        self.status = status


def default_host() -> str:
    h = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    return h if h.startswith("http") else "http://" + h


def model_size_b(tag: str) -> Optional[float]:
    """Parameter count in billions parsed from a tag like qwen2.5:3b, or None."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*b\b", tag.lower())
    return float(m.group(1)) if m else None


def check_model_size(tag: str, allow_large: bool = False) -> None:
    size = model_size_b(tag)
    if size is not None and size >= 3 and not allow_large:
        raise OllamaError(
            f"{tag} is {size:g}B parameters; this project targets models under 3B "
            f"(try {', '.join(SUGGESTED_MODELS[:3])}). Pass allow_large=True / --allow-large to override.")


def _post(host: str, path: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(host.rstrip("/") + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        hint = ""
        if e.code == 404:
            hint = f" (is the model pulled? `ollama pull {payload.get('model', '')}`)"
        elif "repeat limit" in body:
            hint = " (the model looped; retrying with lower temperature. Try a smaller --batch or --temperature 0.6)"
        raise OllamaError(f"Ollama HTTP {e.code}: {body}{hint}", status=e.code) from e
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise OllamaError(f"Cannot reach Ollama at {host} ({e}). Start it with `ollama serve`.") from e


def list_models(host: Optional[str] = None, timeout: float = 5) -> List[str]:
    host = host or default_host()
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=timeout) as r:
            return [m.get("name", "") for m in json.loads(r.read().decode()).get("models", [])]
    except Exception as e:  # noqa: BLE001
        raise OllamaError(f"Cannot reach Ollama at {host} ({e}). Start it with `ollama serve`.") from e


def extract_json(text: str):
    """Parse model output leniently: full JSON, else the first {...} or [...] block."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i, j = text.find(open_c), text.rfind(close_c)
        if i != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


@dataclass
class LLMStats:
    calls: int = 0
    parse_failures: int = 0
    proposed: int = 0
    accepted: int = 0
    errors: List[str] = field(default_factory=list)


class OllamaScenarioGenerator:
    def __init__(self, domain, model: str = DEFAULT_MODEL, host: Optional[str] = None, batch: int = 4,
                 max_calls: int = 16, temperature: float = 0.8, seed: int = 0, timeout: float = 180,
                 allow_large: bool = False, think: Optional[bool] = None):
        check_model_size(model, allow_large)
        self.domain, self.model, self.host = domain, model, host or default_host()
        self.batch, self.max_calls, self.temperature = batch, max_calls, temperature
        self.seed, self.timeout, self.think = seed, timeout, think
        self.stats = LLMStats()

    def prompt(self) -> str:
        ex = "\n".join(json.dumps(e) for e in self.domain.llm_examples)
        return (
            "You generate adversarial TEST INPUTS for a security policy checker. "
            "You do not decide whether anything is allowed.\n"
            f"{self.domain.llm_task}\n"
            "Be creative and hostile: wrong types, missing keys, odd spellings, whitespace, aliases, "
            "lookalike values, boundary values. Every case must differ from the others.\n"
            f"Examples of the style wanted:\n{ex}\n"
            f'Return JSON only: {{"scenarios": [ ...exactly {self.batch} objects... ]}}'
        )

    def generate(self, n: int) -> List[dict]:
        out: List[dict] = []
        seen = set()
        for i in range(self.max_calls):
            if len(out) >= n:
                break
            self.stats.calls += 1
            try:
                payload = {
                    "model": self.model, "prompt": self.prompt(), "stream": False, "format": "json",
                    "options": {"temperature": self.temperature, "top_p": 0.9, "repeat_penalty": 1.15,
                                "seed": self.seed + i, "num_predict": 900},
                }
                if self.think is not None:       # qwen3-style models: False skips the hidden reasoning phase
                    payload["think"] = self.think
                resp = _post(self.host, "/api/generate", payload, self.timeout)
            except OllamaError as e:
                self.stats.errors.append(str(e))
                if e.status is None:          # server unreachable / timeout: retrying will not help
                    break
                self.temperature = max(0.4, self.temperature - 0.2)   # server-side failure (e.g. loop): cool down, retry
                continue
            data = extract_json(resp.get("response", ""))
            items = data.get("scenarios") if isinstance(data, dict) else data
            if not isinstance(items, list):
                self.stats.parse_failures += 1
                continue
            for obj in items:
                self.stats.proposed += 1
                sc = self.domain.normalize_llm(obj)
                if sc is None:
                    continue
                key = json.dumps(sc, sort_keys=True, default=str)
                if key in seen:
                    continue
                seen.add(key)
                out.append(sc)
                self.stats.accepted += 1
        return out[:n]
