# AI Agent Policy Testing Workbench

A local-first prototype for testing explicit policies used by AI-agent workflows. A **small local model (under 3B parameters, run through Ollama)** generates hostile test cases. A deterministic Python policy is then compared against an **independent oracle written from a plain-language spec**. The model only proposes inputs: it never labels them and never decides whether an action is allowed.

> **Research prototype only.** No payment or external tool integrations are included. Use synthetic data, keep Ollama bound to localhost, and do not use this prototype to authorize real actions.

1. **Default-deny finance policy.** The original engine allowed anything it did not recognize (unknown action, missing field, string `"false"`, untrusted source not on a blocklist). The rebuilt policy denies unless every rule in the spec holds. The original engine is kept unchanged as target `LEGACY` so you can replay its failures.
2. **Independent oracle instead of model labels.** The old "potential bypass" meant "the model's `expected` label disagreed with the engine", which is only as reliable as a 1–4B model. Now an oracle written separately from the spec decides what is correct.
3. **Seeded bugs (mutation testing).** Each domain has injectable bugs (finance `F1`–`F11` plus `LEGACY`; mail `B1`–`B9`). The score is how many bugs a generator finds, plus **0 findings on the clean policy**.
4. **The model is the main generator.** `ollama` is the default generator. `mutation` (hand-built hostile edge cases) and `random` (ordinary valid inputs) are plain-code **baselines** that show whether the model finds anything the cheap generators miss.
5. **Two domains.** `finance` (transfer / pay / refund / wire) and `mail` (send_email with provenance and readers, as in CaMeL).
6. **Runs from VS Code** with one setup script, debug configurations, tasks, and unit tests.
7. **Fixed app bugs.** Generated scenarios no longer disappear on "Save", no duplicate IDs, and one bad model output no longer discards a whole batch. The Kev integration was removed (out of scope; its API could not be verified).

### Important limitation

This is a **structured policy-logic test**, not an end-to-end prompt-injection test. It checks fields such as `action`, `amount`, `recipient`, `approval`, and `instruction_source`; it does not run an AI agent that reads free text. The oracle and the policy come from the **same written spec**, so a mistake in the spec itself is invisible to this method. A finding is a review signal that the implementation disagrees with the spec, not proof of a real-world compromise.

## Requirements

- Python 3.10+ (developed on 3.13)
- [Ollama](https://ollama.com/) installed and running locally
- A local model under 3B parameters. Default: `qwen2.5:1.5b`
- `streamlit` and `pandas` (installed by the setup script). The Ollama client uses only the standard library.

## Run locally

### In VS Code

1. `File > Open Folder…` and choose this folder. Accept the prompt to install the Python extension.
2. Create the environment once, in the VS Code terminal:
   - macOS/Linux: `bash setup.sh`
   - Windows PowerShell: `.\setup.ps1` (if blocked, run `Set-ExecutionPolicy -Scope Process Bypass` first)
3. `Ctrl/Cmd+Shift+P` → `Python: Select Interpreter` → choose the one inside `.venv`.
4. Press **F5** (the *Streamlit app (F5)* configuration). The browser opens the workbench, usually at http://localhost:8501.

The *Run and Debug* dropdown also has: *CLI: finance mutation matrix (offline)*, *CLI: finance matrix + Ollama model*, *CLI: show original engine's bugs (LEGACY)*, and *CLI: check Ollama*. `Terminal > Run Task…` offers *Run unit tests*, *Start Streamlit app*, and *Pull small model (ollama)*. Tests also appear in the Testing sidebar.

### From a plain terminal

```bash
python -m venv .venv

# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
ollama pull qwen2.5:1.5b
python -m streamlit run app.py
```

In the sidebar, set:

- **Ollama URL:** `http://localhost:11434`
- **Model:** the exact name shown by `ollama list` (for example `qwen2.5:1.5b`)

Click **Check Ollama** before generating. It lists your installed models and warns if the one you typed is not pulled. Prompts are sent only to your local Ollama server.

## Choosing a model

| Model | Notes |
|---|---|
| `qwen2.5:1.5b` (default) | Plain instruct model (no thinking), good at JSON for its size, about 1 GB. Start here. |
| `gemma2:2b` | Slightly larger, different family. Try it if the default gives repetitive or malformed cases. |
| `llama3.2:1b` | Faster, but tiny models ignore "be hostile and weird" more often. |
| `qwen2.5:0.5b` | Fastest; expect many malformed outputs. |

These are suggestions, not benchmarked results. Compare models yourself in the matrix.

- **Models of 3B or more are refused** unless you tick **Allow models >= 3B** (CLI: `--allow-large`). The size check reads the model name, so a tag with no size in it (`llama3`, `mistral`) passes unchecked; confirm the size with `ollama list`.
- **Reasoning models** (the qwen3 family) can spend their token budget on hidden thinking and return nothing. Tick **Disable thinking** (CLI: `--no-think`) to send `think: false`.
- **Any model Ollama can run works**, including ones you already have installed. It must be served by Ollama; LM Studio or llama.cpp servers are not supported currently.

## Suggested runbook

1. Start Ollama, pull a model, and open the app. Pick a **Domain** in the sidebar.
2. Open **1 · Spec & bugs** and read the spec the oracle implements, plus the list of injectable bugs.
3. Open **2 · Try a scenario**, keep the example, set the variant to `LEGACY`, and click **Evaluate**. You should see a **FALSE ALLOW**: the original engine allows something the spec forbids.
4. Open **3 · Fuzz one policy**, choose `CLEAN` and the `ollama` generator, and run. The clean policy must show **0 findings**. If it does not, the model found a disagreement between policy and oracle; inspect it, because it is either an implementation bug or a spec ambiguity.
5. Open **4 · Mutation matrix**, select `ollama`, `mutation`, and `random`, and run. Read the table: which bugs did each generator find, and after how many scenarios (`found @ #N`)?
6. Download the JSON report. Record the **model, temperature, cases per call, and seed** next to it.
7. Repeat with a second model or different settings and compare detection counts, parse failures, and how many proposed cases were accepted.
8. Review a sample of the model's cases by hand. Do not treat model output as ground truth.

## Tabs

- **1 · Spec & bugs:** the specification, and every injectable bug with a description.
- **2 · Try a scenario:** paste one scenario as JSON (`NaN` allowed) and see the policy verdict beside the oracle verdict.
- **3 · Fuzz one policy:** run one generator against one policy variant; shows false allows (security), false denies (utility), crashes, and unique failure types, with the first findings.
- **4 · Mutation matrix:** every generator against every injected bug on the same scenarios, plus the clean-policy false-positive check. Exports JSON.
- **5 · Method & limits:** what the method can and cannot show.

Sidebar controls: domain, seed, Ollama URL, model, allow-large, **Temperature**, **Cases per model call**, **Disable thinking**, **Check Ollama**.

## Command line

```bash
python -m policy_fuzz list                                        # specs and bug ids for each domain
python -m policy_fuzz check-ollama --model qwen2.5:1.5b
python -m policy_fuzz matrix --domain finance --n 200 --model qwen2.5:1.5b      # ollama, mutation, random
python -m policy_fuzz matrix --domain finance --gens mutation,random --n 400    # no model, baselines only
python -m policy_fuzz matrix --domain finance --model qwen3:4b --allow-large --no-think
python -m policy_fuzz run --domain finance --target LEGACY --gen mutation       # replay the original engine's failures
python -m policy_fuzz run --domain mail --target B5 --gen ollama
python -m unittest discover -s tests -v
```

Useful flags: `--seed`, `--temperature` (default 0.8), `--batch` (cases per model call, default 4), `--host`, `--out reports/x.json`.

## Policy specification (finance)

A finance action is **allowed only if every line holds** (default deny):

| ID | Requirement |
|---|---|
| F-S1 | `action` (trimmed, lowercased) is one of `transfer`, `pay`, `refund`, `wire`. |
| F-S2 | All fields are present: `action`, `amount`, `currency`, `recipient`, `approval`, `instruction_source`, `objection`. |
| F-S3 | `amount` is a real, finite number greater than 0 (not a boolean, string, or NaN). |
| F-S4 | `currency` (trimmed, uppercased) is `USD`. No FX guessing. |
| F-S5 | `instruction_source` (trimmed, lowercased) is on the **trusted allowlist** (`user`). |
| F-S6 | `recipient` is a string exactly equal to `vendor_acme` or `vendor_contoso`. |
| F-S7 | `approval` and `objection` are real booleans (the string `"false"` is not `False`). |
| F-S8 | `objection` is `False`: an objection from any agent blocks the action. |
| F-S9 | If `amount` is above 500, `approval` is `True` **and** `approval_source` is `human`. Exactly 500 needs no approval. |

The mail domain's spec is printed by `python -m policy_fuzz list` and shown in the app.

## Project layout

| Path | Role |
|---|---|
| `app.py` | Streamlit workbench. |
| `policy_fuzz/domains/finance.py`, `domains/mail/` | Policy under test (clean + injectable bugs), oracle, and the `random` / `mutation` generators for each domain. |
| `policy_fuzz/domains/legacy_finance_engine.py` | The original engine, unchanged, as target `LEGACY`. |
| `policy_fuzz/ollama.py` | Standard-library Ollama client, lenient JSON parsing, under-3B guard, retries when the model loops. |
| `policy_fuzz/runner.py` | Runs scenarios, classifies `false_allow`, `false_deny`, `crash`, and builds the matrix. |
| `policy_fuzz/cli.py` | Command-line interface. |
| `tests/test_policy_fuzz.py` | Unit tests, including a mock Ollama server. |
| `.vscode/` | Launch configurations, tasks, settings. |
| `reports/` | Where `--out` reports are written. |

## Results from the offline baselines

400 scenarios, seed 0, no model involved:

| Domain | `random` | `mutation` | Clean-policy false positives |
|---|---|---|---|
| finance (12 targets including `LEGACY`) | 5 / 12 found | **12 / 12** found | 0 |
| mail (9 bugs) | 6 / 9 found | **9 / 9** found | 0 |

The model path was tested only against a **mock Ollama server** (request shape, messy output, duplicates, retries after the "token repeat limit" error), **not against real model output**. No real model results are reported here. Run the `ollama` generator on your machine and compare it with `mutation`; a sub-3B model may well find fewer bugs than the deterministic mutator, and that is a legitimate result.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Ollama HTTP 500 ... token repeat limit reached` | The model looped while writing JSON. The client retries automatically at a lower temperature. If it persists, lower **Temperature** (0.5–0.6) and **Cases per model call** (2–3), or try another model such as `gemma2:2b`. |
| `Cannot reach Ollama` | Start it with `ollama serve`, and check the Ollama URL. |
| `Ollama HTTP 404` | The model is not pulled: `ollama pull <name>`. |
| "no scenarios were generated" | The model returned nothing usable; see the LLM stats line and the error under the matrix. Try a lower temperature, smaller batch, or **Disable thinking** for qwen3-style models. |
| Model refused as "3B or more" | Pick a smaller model, or tick **Allow models >= 3B** knowingly. |
| Timeouts on a CPU | Use a smaller model or fewer scenarios (`--n 50`); the request timeout is 180 seconds. |
| `python` not found in the terminal | Activate `.venv` first, or call `.venv/bin/python` (Windows: `.venv\Scripts\python.exe`). |

## Research metrics

Track at least:

- **Bugs detected / bugs injected**, per generator and per model.
- **False positives on the clean policy** (must be 0).
- **Scenarios until first detection** (`found @ #N`) per bug.
- **Unique failure types** found per run, not just raw counts.
- **Model usability:** accepted / proposed cases and parse failures from the LLM stats line.
- **Repeatability:** results across seeds, temperatures, batch sizes, and models.
- **Baseline comparison:** does the model find any bug that `mutation` misses?
- Human-review time per finding.

## Limits

- The oracle and the policy share one written spec; a spec mistake is invisible here.
- Both are small reference implementations by one author, so a shared misreading is possible.
- Structured inputs only; no live agent reads free-text prompt injections.
- Injected bugs are the ones someone thought of. Finding all of them does not show that no others exist.
- The finance policy is a toy re-implementation, not a real payment control.

## Safety and interpretation

- All examples are synthetic. Never paste secrets, personal data, production prompts, or real transaction details.
- Do not connect the app to real tools, accounts, financial systems, or production agents.
- Treat model output as untrusted data. It is parsed as JSON and displayed; it is never executed or followed as an instruction.
- A passing test run does not prove a policy is secure or complete.
- The model may produce malformed, repetitive, biased, or incorrect cases. Review a sample before drawing conclusions.

# Research Paper That Inspired This Project 

CaMeL orchestrated with Temporal logic for static verification and liveness: https://arxiv.org/pdf/2609.18674
The LLMbda Calculus: https://arxiv.org/pdf/2602.20064
