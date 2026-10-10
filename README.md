# AI Agent Policy Testing Workbench

**A local-first research prototype for testing security policies in AI-agent workflows.**

This Streamlit app explores whether systematic test generation and a small local decision model can help find bugs in agent policies. Initial financial-agent examples cover approval thresholds, recipient allowlists, untrusted instructions, and delegated-agent objections.

> **Status:** Research POC. Not production-ready and not a formal verification system.

## Research question

**Can a small local decision model improve automated policy-bug detection beyond a manually written test suite?**

## Features

- Streamlit policy editor for structured JSON rules.
- Deterministic allow/deny evaluation in a UI-independent `policy_engine.py` module, with unit tests.
- Hand-written scenarios and optional Ollama-based test generation.
- Optional **Kev local decision analysis** using Kev's `/v1/systemone` API.
- Comparison of deterministic decisions with Kev's risk classification.
- Disagreement flags for human review.
- JSON export of test results and Kev analysis.
- No cloud inference API required. After dependencies and model weights are downloaded, inference can run locally.

## Architecture

```text
                   Streamlit UI
                        |
              Policy + test scenarios
                        |
           +------------+-------------+
           |                          |
   Deterministic evaluator      Test generation
           |                   (optional Ollama)
           +------------+-------------+
                        |
                 Policy test results
                        |
                 Optional Kev analysis
                        |
            Risk classification + review score
                        |
                 Disagreement report
```

The deterministic evaluator is the reference for supported rules. Kev supplies an independent advisory classification; it does not authorize actions or replace the evaluator. A disagreement is a signal to investigate, not proof that either component is wrong.

## Technology

- Python 3.10+ for the Streamlit app.
- Streamlit and Pandas.
- [Ollama](https://ollama.com/) (optional) for local test generation.
- [Kev](https://github.com/jaredpalmer/kev) for local decision analysis.
- JSON for policies, scenarios, and exported results.

Kev's own server currently requires Python 3.12 or 3.13 and `uv`, so run it in a separate environment.

## Quick start: Streamlit app

```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
streamlit run app.py
```

Open the local URL displayed by Streamlit, usually `http://localhost:8501`. The deterministic evaluator and seven included sample scenarios work without Ollama or Kev.

## Run Kev locally

Follow the latest instructions in the [official Kev repository](https://github.com/jaredpalmer/kev). The following commands reflect its documented serving workflow.

Kev requires Python 3.12 or 3.13 and `uv`. Clone it separately:

```bash
git clone https://github.com/jaredpalmer/kev.git
cd kev
uv sync --extra serve
```

Start the smallest released checkpoint:

```bash
uv run --extra serve python -m kev.serve \
  --run jaredpalmer/kev-0.8b \
  --port 8009
```

The first launch downloads the model and base weights, so internet access is needed during setup unless those files are already cached. Inference can run locally afterward. Kev-0.8B is the size-oriented option, but is weaker than larger models on some out-of-domain tasks; validate it on your own data.

In the Streamlit sidebar, set:

- **Kev local server URL:** `http://127.0.0.1:8009`
- **Kev model ID:** `kev-latest`

Use **Check Kev connection**. Then run policy tests and open **4 · Kev analysis** to compare selected scenarios.

If your hardware supports it, compare with `jaredpalmer/kev-4b`. Consult the official repository and model cards for current requirements.

### Offline and privacy notes

- Do not enter a remote URL if you require offline-only inference.
- Keep Kev bound to localhost; do not expose its unauthenticated local endpoint to a network.
- Dependencies and model weights must be downloaded before going offline.
- Optional Ollama generation also runs locally once its model is downloaded.
- Avoid using real financial or personal data in experimental scenarios.

## Optional Ollama test generation

Install Ollama and download a small model:

```bash
ollama pull qwen2.5:3b
```

Keep Ollama running. The app defaults to `http://localhost:11434`. Test generation is optional; you can edit scenarios manually.

## Supported policy rules

| Rule type | Purpose |
|---|---|
| `amount_requires_approval` | Require approval for transfers above a configured threshold. |
| `recipient_allowlist` | Block recipients not on the approved list. |
| `untrusted_source_blocks_action` | Block transfer-like actions initiated by a configured untrusted source. |
| `objection_blocks_action` | Block an action when an unresolved agent objection is present. |

Any applicable violation causes a deny. The initial evaluator supports only these rule types. Unknown rule types are not enforced; the UI warns about them.

## Kev decision analysis

For each selected scenario, the app sends the scenario and current policy JSON to the configured Kev server and asks:

1. **Risk classification:** `likely_violation`, `likely_compliant`, or `ambiguous`.
2. **Human review:** probability that the scenario should be reviewed before relying on the assessment.

The app displays Kev's probabilities and flags obvious disagreements with the rule engine. Kev does not execute tools, change the policy, or make the authoritative allow/deny decision.

Probabilities are not measured accuracy on this project. Evaluate them against independently labeled cases; do not assume a confidence threshold is reliable without measurement.

## Research plan

Compare three configurations on the same held-out scenarios:

1. **Rules only:** deterministic evaluator and manually written tests.
2. **Rules + generated tests:** add locally generated edge cases.
3. **Rules + generated tests + Kev:** use Kev to classify scenarios and prioritize review.

Introduce seeded defects such as removing approval checks, changing threshold boundaries, removing recipient checks, inverting source trust, and dropping delegated-agent objections.

Suggested metrics: mutation detection rate, false-positive rate, incremental detection, counterexample diversity, disagreement rate on manually labeled cases, runtime, and compute requirements. Use independently specified or human-reviewed expected outcomes. A model must not be treated as its own ground-truth evaluator.

## Limitations and safety

- This is a research prototype, not a formal verifier.
- Passing tests do not prove policy correctness or completeness.
- The evaluator handles a limited set of structured, single-step rules.
- Generated scenarios and model classifications can be wrong.
- A model/evaluator disagreement is not automatically a bug.
- Kev must not be used to authorize financial actions.
- Do not connect the prototype to production payment systems, credentials, or real transaction APIs.

## Project status

- [x] Streamlit policy editor
- [x] Deterministic evaluator for four rule types
- [x] Seven sample scenarios
- [x] Optional Ollama test generation
- [x] Optional local Kev analysis via `/v1/systemone`
- [x] Disagreement and human-review indicators
- [x] JSON export
- [ ] Unit tests and property-based testing
- [ ] Seeded mutation-test harness
- [ ] Benchmark dataset with human-reviewed labels
- [ ] Multi-step temporal and delegation testing

## License

Apache License. Kev has its own license and model terms; consult its official repository.

## Acknowledgements

Inspired by research on AI agent security, deterministic action mediation, information-flow control, and decision models.

**Goal:** Find policy failures before agents can take consequential actions.

## Run unit tests

```bash
python -m unittest discover -s tests -v
```
 
