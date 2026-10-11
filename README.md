# AI Agent Policy Testing Workbench

A local-first Streamlit prototype for testing explicit policies used by AI-agent workflows. The red-team feature uses **only the local Qwen model through Ollama** to generate synthetic adversarial test cases. A deterministic Python policy engine evaluates the structured action fields; the model does not decide whether an action is allowed.

> **Research prototype only.** No payment or external tool integrations are included. Use synthetic data, keep Ollama bound to localhost, and do not use this prototype to authorize real actions.

## What’s new: adversarial red-team lab

The **5 · Red team** tab adds an attacker-versus-policy-testing workflow:

1. **Seed attacks** — load six synthetic cases covering untrusted email/webpage instructions, fake approval claims, recipient spoofing, delegated objections, and a boundary control.
2. **Qwen as attacker** — ask the local model to generate diverse synthetic cases such as prompt-injection attempts, authority spoofing, instruction laundering, boundary manipulation, conflicts, and missing data.
3. **Deterministic evaluation** — run each structured scenario against the explicit policy rules.
4. **Triage potential bypasses** — highlight cases labeled `expected=deny` that the policy engine allows, plus all expected/actual mismatches.
5. **Export evidence** — download a JSON report containing the policy, generated cases, outcomes, model name, timestamp, and limitations.

The red-team feature calls Ollama’s local `/api/generate` endpoint. **No cloud model or Kev service is required for red-team testing.** The existing optional Kev analysis tab remains separate from this workflow; you can ignore it entirely when running the Qwen red-team POC.

### Important limitation

This is a **structured policy-logic red-team POC**, not a full end-to-end prompt-injection test. The current deterministic evaluator reads fields such as `instruction_source`, `recipient`, `amount`, `approval`, and `objection`; it does not run an AI agent that interprets the free-text `attack_text`. A “potential bypass” means the structured test was expected to be denied but the current rule engine allowed it. It is a review signal, not proof of a real-world compromise. Model-generated cases and expected outcomes must be reviewed by a human.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/) installed and running locally
- A local Qwen model; the example below uses `qwen2.5:3b`

## Run locally

```bash
python -m venv .venv

# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
ollama pull qwen2.5:3b
streamlit run app.py
```

Open the local Streamlit URL shown in the terminal. In the sidebar, use:

- **Ollama URL:** `http://localhost:11434`
- **Model name:** `qwen2.5:3b`

Check the Ollama connection from the sidebar before generating attacks. The model must already be available locally. Once downloaded, prompts are sent to the local Ollama server rather than a hosted inference API.

## Suggested red-team runbook

1. Open **1 · Policy** and review the sample policy and supported rules.
2. Open **5 · Red team** and select **Load seed attack suite**.
3. Run the seed cases against the deterministic policy and download the report.
4. Select **Generate attacks with local Qwen** to replace the current red-team suite with model-generated cases.
5. Inspect the attack fixtures and expected outcomes before running them.
6. Run the cases, investigate **Potential bypasses** and **Oracle mismatches**, and download the report.
7. Repeat with controlled policy mutations (for example, remove a rule or alter a threshold) to verify whether the test suite catches the seeded regression.
8. Record which cases were human-reviewed. Do not treat the model’s labels as ground truth.

## Other tabs

- **1 · Policy:** edit and validate the policy JSON.
- **2 · Test cases:** inspect hand-written scenarios or generate general cases with local Qwen.
- **3 · Results:** run the regular deterministic test suite and export results.
- **4 · Kev analysis:** optional pre-existing integration for a separately hosted local Kev service; not needed for the Qwen red-team lab.
- **5 · Red team:** generate adversarial cases with local Qwen, run them through the policy engine, inspect mismatches, and export a report.
- **6 · Method & limits:** review evaluation limitations and suggested research metrics.

## Supported rule types

- `amount_requires_approval`: block transfers above a numeric threshold unless `approval` is true.
- `recipient_allowlist`: block transfers to recipients not in `allowed_recipients`.
- `untrusted_source_blocks_action`: block transfer-like actions when `instruction_source` is listed as untrusted.
- `objection_blocks_action`: block an action when `objection` is true.

Rules are combined conjunctively: any violation causes a deny. Unknown rule types are currently ignored by the evaluator; the policy validator warns about them. Treat unsupported rules as a test failure in any serious evaluation.

## Research metrics

Track at least:

- Potential-bypass rate on manually reviewed adversarial cases.
- Expected/actual mismatch rate.
- Unique counterexamples found per 100 generated tests.
- Seeded regression detection rate when known rules are intentionally removed or mutated.
- Human-review time per finding.
- Repeatability across runs and model settings.

## Safety and interpretation

- All examples are synthetic. Never paste secrets, personal data, production prompts, or real transaction details into the POC.
- Do not connect the app to real tools, accounts, financial systems, or production agents.
- Treat `attack_text` as untrusted data. It is displayed for inspection and must never be executed as code or followed as an instruction.
- A passing test suite does not prove the policy is secure or complete.
- The model may produce malformed, incomplete, biased, or incorrect cases. Review each case and expected outcome before drawing conclusions.

# Research Paper That Inspired This Project 

CaMeL orchestrated with Temporal logic for static verification and liveness: https://arxiv.org/pdf/2609.18674
The LLMbda Calculus: https://arxiv.org/pdf/2602.20064
