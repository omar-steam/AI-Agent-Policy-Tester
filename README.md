# AI Agent Policy Tester

Find bugs in AI-agent action policies (CaMeL-style capability checks, finance approval rules) by comparing
the policy against an **independent spec oracle**, using hostile inputs from a deterministic mutator and,
a **small local LLM (< 3B parameters, via Ollama)** that generates the test cases.
`random` and `mutation` are non-model baselines: they show whether the model finds bugs those cheap generators miss.

> Research prototype. Synthetic data only. Not a security guarantee, and not for authorizing real actions.

## Quick start (VS Code)

1. **Open the folder** in VS Code (`File > Open Folder…` → this directory). Accept the "install recommended extensions" prompt (Python).
2. **Create the environment** (one time), in the VS Code terminal:
   - macOS/Linux: `./setup.sh`
   - Windows PowerShell: `.\setup.ps1`
3. **Select the interpreter:** `Ctrl/Cmd+Shift+P` → `Python: Select Interpreter` → choose `.venv`.
4. **Press F5** (default config *Streamlit app*). The browser opens the workbench. No model needed for the offline generators.

Other launch configs are in the *Run and Debug* dropdown: offline mutation matrix, matrix with Ollama,
"show the original engine's bugs", and "check Ollama". `Terminal > Run Task…` has *Run unit tests* and
*Pull small model*. Tests also show up in the Testing sidebar (unittest).

Python 3.10+ (developed on 3.13). Only `streamlit` and `pandas` are required; the Ollama client uses the standard library.

## Using a local model (the main generator)

```bash
ollama serve                 # if it is not already running
ollama pull qwen2.5:1.5b     # any model under 3B: qwen2.5:0.5b, llama3.2:1b, qwen3:1.7b, gemma2:2b
python -m policy_fuzz check-ollama --model qwen2.5:1.5b
python -m policy_fuzz matrix --domain finance --gens random,mutation,ollama --n 200 --model qwen2.5:1.5b
```

Reasoning models such as qwen3 can burn their token budget on hidden thinking; add `--no-think` (or tick the box in the app) to send `think: false`.
Models of 3B or more are refused unless you pass `--allow-large` (or tick the box in the app).
The model only **proposes inputs**; it never labels them and never decides allow/deny.

## Command line

```bash
python -m policy_fuzz list                                      # specs + bug ids for each domain
python -m policy_fuzz matrix --domain finance --n 400           # every generator x every injected bug
python -m policy_fuzz run --domain finance --target LEGACY      # replay the original engine's failures
python -m policy_fuzz run --domain mail --target B5 --gen mutation
python -m unittest discover -s tests -v
```

## How it works

| Piece | Role |
|---|---|
| `domains/finance.py`, `domains/mail/` | The **policy under test** (clean version + injectable bugs), the **oracle** written from the spec, and scenario generators. |
| `domains/legacy_finance_engine.py` | The uploaded engine, untouched, as target `LEGACY`. |
| `ollama.py` | stdlib Ollama client, lenient JSON parsing, <3B guard, seeded generation. |
| `runner.py` | Runs scenarios, classifies `false_allow` (security), `false_deny` (utility), `crash`; builds the mutation matrix. |

**Score** = fraction of injected bugs a generator detects, plus **0 findings on the clean policy** (no false positives).

| Original behavior | Now |
|---|---|
| `wire`, `pay`, `"Transfer "`, unknown or missing action skip the amount and recipient rules | Action must be a known value; otherwise deny. |
| Missing `amount` defaults to 0; `NaN`, `"nan"` and negatives pass | Strict finite number > 0. |
| `bool("false")` is `True`, so string `"false"` counts as approval | `approval` / `objection` must be real booleans. |
| Untrusted sources were a blocklist (`slack`, `web_page`, `"Email "` pass; missing source passes) | Allowlist of trusted sources, normalized. |
| Missing `objection` passes (an objection can be lost in delegation) | All fields required. |
| `currency` rule field never read (450 GBP ≈ $600 allowed) | Non-USD denied (no FX guessing). |
| `approval` was just a boolean anyone could set | Approval above the threshold must also come from `approval_source == "human"`. |
| Unknown rule types silently ignored | Policy is code, not editable JSON; bugs are explicit mutants. |

App/UX fixes: generated scenarios no longer vanish on "Save" (the old text area used `value=` with `key=`);
no duplicate IDs; no all-or-nothing validation that discarded a whole batch over one missing key; the
LLM's `expected` label is no longer ground truth; the Kev integration was removed (out of scope, unverified API).

## Limits

- The oracle and the policy come from the **same written spec**. A mistake in the spec is invisible to this method.
- Both are small reference implementations by one author; a shared misreading is possible.
- Structured inputs only. This does not run an agent that reads free-text prompt injections.
- Injected bugs are the ones someone thought of. Finding all of them does not show no others exist.
- The finance policy is a toy re-implementation, not a real payment control.
