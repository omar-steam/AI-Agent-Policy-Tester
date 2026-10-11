# AI Agent Policy Tester

Find bugs in the **rules that decide what an AI agent may do** (for example "transfers over $500 need approval" or "never email private data to an outsider").

A small local model (under 3B parameters, running in Ollama) invents tricky test cases. A strict reference checker, written separately from the policy, says what the right answer is. Any difference between the two is a bug in the policy.

```
 local model ──► tricky test cases ──┬──► policy under test ──► allow / deny ─┐
 (Ollama, <3B)                       │                                        ├─► same answer? ──► if not: a bug
                                     └──► reference oracle  ──► allow / deny ─┘
```

The model only **proposes inputs**. It never decides whether an action is allowed.

> **Research prototype.** Synthetic data only. Not a security guarantee, and not for authorizing real actions.

## 1. Quick start

You need Python 3.10+ and [Ollama](https://ollama.com/).

**In VS Code**

1. `File > Open Folder…` and choose this folder. Accept the prompt to install the Python extension.
2. In the VS Code terminal, run the setup once:
   - macOS/Linux: `bash setup.sh`
   - Windows PowerShell: `.\setup.ps1` (if blocked, run `Set-ExecutionPolicy -Scope Process Bypass` first)
3. `Ctrl/Cmd+Shift+P` → `Python: Select Interpreter` → choose the one inside `.venv`.
4. Pull a model, then press **F5**:
   ```bash
   ollama pull qwen2.5:1.5b
   ```

The browser opens the workbench (usually http://localhost:8501).

**From any terminal**

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
ollama pull qwen2.5:1.5b
python -m streamlit run app.py
```

## 2. Use it

In the sidebar, pick a **Domain** (`finance` or `mail`), type your **Model** name exactly as `ollama list` shows it, and click **Check Ollama**. Then:

| Step | Tab | What to do | What you should see |
|---|---|---|---|
| 1 | **1 · Spec & bugs** | Read the rules and the list of injectable bugs. | The spec the reference checker follows. |
| 2 | **2 · Try a scenario** | Set the variant to `LEGACY`, click **Evaluate**. | **FALSE ALLOW**: the original engine allows something the spec forbids. |
| 3 | **3 · Fuzz one policy** | Variant `CLEAN`, generator `ollama`, run. | **0 findings.** Anything else is a disagreement to investigate. |
| 4 | **4 · Mutation matrix** | Select `ollama`, `mutation`, `random`, run. | A table of which bugs each generator found, and after how many cases. |

Download the JSON report and note the model, temperature, cases per call, and seed beside it. Repeat with another model and compare.

### The three generators

| Generator | What it is | Why it is there |
|---|---|---|
| `ollama` | Your local model writes hostile cases. | **The main generator.** |
| `mutation` | Hand-built nasty inputs (wrong types, missing fields, lookalike values) in plain code. | A strong baseline: does the model beat it? |
| `random` | Ordinary valid inputs in plain code. | A weak baseline. |

### The score

For each generator: **how many of the injected bugs it finds**, and **0 findings on the clean policy** (no false alarms). A model is useful here only if it finds bugs the `mutation` baseline misses. If it does not, that is a valid result.

## 3. Choosing a model

Any model Ollama can run works. Type the exact name from `ollama list`.

| Model | Notes |
|---|---|
| `qwen2.5:1.5b` (default) | Plain instruct model, no thinking, good at JSON for its size, about 1 GB. Start here. |
| `gemma2:2b` | Slightly larger and from a different family. Try it if the default gives repetitive or broken cases. |
| `llama3.2:1b` | Faster; tiny models often ignore "be hostile". |
| `qwen2.5:0.5b` | Fastest; expect many malformed outputs. |

These are suggestions, not benchmark results.

- **Models of 3B or more are refused** unless you tick **Allow models >= 3B** (CLI: `--allow-large`). The check reads the size from the name, so tags without one (`llama3`, `mistral`) slip through; confirm with `ollama list`.
- **Reasoning models** (the qwen3 family) can spend their whole token budget on hidden thinking. Tick **Disable thinking** (CLI: `--no-think`).
- Ollama only. LM Studio and llama.cpp servers are not supported.

## 4. Command line

```bash
python -m policy_fuzz list                                         # specs and bug ids
python -m policy_fuzz check-ollama --model qwen2.5:1.5b
python -m policy_fuzz matrix --domain finance --n 200              # ollama + mutation + random
python -m policy_fuzz matrix --domain finance --gens mutation,random --n 400    # no model needed
python -m policy_fuzz matrix --domain finance --model qwen3:4b --allow-large --no-think
python -m policy_fuzz run --domain finance --target LEGACY --gen mutation       # replay the original engine's failures
python -m unittest discover -s tests -v
```

Useful flags: `--seed`, `--temperature` (default 0.8), `--batch` (cases per model call, default 4), `--host`, `--out reports/x.json`.

The *Run and Debug* dropdown in VS Code has ready-made versions of these, and `Terminal > Run Task…` has *Run unit tests* and *Pull small model (ollama)*.

## 5. What is being tested

### Finance policy

A finance action is allowed **only if every line holds** (default deny):

| ID | Requirement |
|---|---|
| F-S1 | `action` is one of `transfer`, `pay`, `refund`, `wire` (trimmed, lowercased). |
| F-S2 | All fields are present: `action`, `amount`, `currency`, `recipient`, `approval`, `instruction_source`, `objection`. |
| F-S3 | `amount` is a real, finite number above 0 (not a boolean, string, or NaN). |
| F-S4 | `currency` is `USD`. |
| F-S5 | `instruction_source` is on the **trusted allowlist** (`user`). |
| F-S6 | `recipient` is exactly `vendor_acme` or `vendor_contoso`. |
| F-S7 | `approval` and `objection` are real booleans (the string `"false"` is not `False`). |
| F-S8 | `objection` is `False`. |
| F-S9 | If `amount` is above 500, `approval` is `True` **and** `approval_source` is `human`. Exactly 500 needs none. |

### Injected bugs (finance)

| ID | Bug |
|---|---|
| `LEGACY` | The original engine from the earlier POC, unchanged |
| `F1` | Amount and recipient rules run only for `transfer`, so `wire` and `pay` bypass them |
| `F2` | A missing amount defaults to a tiny valid amount |
| `F3` | Amount converted with `float()`, so `NaN`, `"900"`, and negatives slip through |
| `F4` | Approval read with `bool()`, so the string `"false"` counts as approved |
| `F5` | Untrusted sources are a blocklist instead of an allowlist of trusted ones |
| `F6` | Currency ignored |
| `F7` | Approval accepted without checking who approved |
| `F8` | Threshold off by one (`>=` instead of `>`) |
| `F9` | A missing objection is treated as no objection |
| `F10` | An unknown action is allowed |
| `F11` | Recipient matched by prefix, so `vendor_acme_evil` passes |

### Mail policy

A `send_email` call tracks where each piece of data came from and who may read it. Mail bugs are `B1`–`B9` (lookalike domains, display-name tricks, multiple recipients, and similar). Run `python -m policy_fuzz list` to see the full spec and bug list.

## 6. Results so far

Offline baselines only (400 scenarios, seed 0, **no model involved**):

| Domain | `random` | `mutation` | Clean-policy false positives |
|---|---|---|---|
| finance (12 targets including `LEGACY`) | 5 / 12 found | **12 / 12** found | 0 |
| mail (9 bugs) | 6 / 9 found | **9 / 9** found | 0 |

**No real-model results are reported yet.** The model path was tested only against a mock Ollama server (request format, messy output, duplicates, retries). Run the `ollama` generator on your machine and add your numbers here.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `Ollama HTTP 500 ... token repeat limit reached` | The model looped while writing JSON. The client retries at a lower temperature. If it persists, lower **Temperature** (0.5–0.6) and **Cases per model call** (2–3), or try `gemma2:2b`. |
| `Cannot reach Ollama` | Start it with `ollama serve` and check the URL. |
| `Ollama HTTP 404` | The model is not pulled: `ollama pull <name>`. |
| "no scenarios were generated" | The model returned nothing usable. Read the error under the matrix; try a lower temperature, a smaller batch, or **Disable thinking**. |
| Model refused as "3B or more" | Choose a smaller model, or tick **Allow models >= 3B** knowingly. |
| Timeouts on a CPU | Use a smaller model or `--n 50`. The request timeout is 180 seconds. |
| `python` not found | Activate `.venv` first, or call `.venv/bin/python` (Windows: `.venv\Scripts\python.exe`). |

## 8. Limits and safety

- The policy and the reference checker come from **the same written spec**, so a mistake in the spec itself is invisible to this method.
- Inputs are structured fields. Nothing here runs an agent that reads free-text prompt injections.
- Injected bugs are the ones someone thought of. Finding all of them does not prove there are no others.
- The finance policy is a toy, not a real payment control.
- Use synthetic data only. Do not connect this to real tools, accounts, or payment systems. Model output is treated as untrusted data: it is parsed and displayed, never executed.

## 9. Project layout

| Path | Role |
|---|---|
| `app.py` | Streamlit workbench |
| `policy_fuzz/domains/finance.py`, `domains/mail/` | Each policy (clean + injectable bugs), its reference checker, and the `random` / `mutation` generators |
| `policy_fuzz/domains/legacy_finance_engine.py` | The original engine, unchanged (`LEGACY`) |
| `policy_fuzz/ollama.py` | Ollama client with lenient JSON parsing, the under-3B guard, and retries |
| `policy_fuzz/runner.py`, `cli.py` | Running scenarios, scoring, command line |
| `tests/` | Unit tests, including a mock Ollama server |
| `.vscode/` | Launch configurations, tasks, settings |

## 10. Background and references

This project tests policies of the kind used in **CaMeL**, a design that defends AI agents against prompt injection by tracking where data came from and enforcing explicit capability policies in a separate interpreter, instead of trusting the model to behave. The `mail` domain follows that idea (data provenance and "who may read this"). The `finance` domain started as a separate Qwen red-team prototype and was rebuilt here with default-deny rules and an independent oracle.

This is an independent project. It is **not** an implementation of CaMeL and is not affiliated with its authors. CaMeL enforces policies; this workbench tests whether such policies have bugs, which is a separate question.

**The paper that inspired this project**

- Debenedetti et al. *Defeating Prompt Injections by Design* (CaMeL). arXiv:2503.18813, 2025. https://arxiv.org/abs/2503.18813
