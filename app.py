"""Policy Fuzz Workbench (Streamlit). Run:  streamlit run app.py

Patched version of the uploaded Qwen red-team POC:
  * the policy engine is default-deny and checked against an independent spec oracle
  * the LLM only proposes inputs; it never labels them or decides allow/deny
  * scoring = bug-detection rate on seeded mutants, with a clean-policy false-positive check
  * widget state fixed (no `value=` + `key=` clobbering), duplicate-ID and brittle-validation bugs removed
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from policy_fuzz import ollama as ol
from policy_fuzz.domains import get_domains
from policy_fuzz.runner import evaluate, make_scenarios, matrix

st.set_page_config(page_title="Policy Fuzz Workbench", page_icon="📜", layout="wide")
DOMAINS = get_domains()


def jdump(x) -> str:
    return json.dumps(x, default=str)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Setup")
    dom_name = st.selectbox("Domain", list(DOMAINS), format_func=lambda k: DOMAINS[k].title)
    domain = DOMAINS[dom_name]
    seed = st.number_input("Seed", 0, 10_000, 0, help="Same seed + same generator = same scenarios.")
    st.divider()
    st.subheader("Local model (Ollama, < 3B)")
    host = st.text_input("Ollama URL", value=ol.default_host())
    model = st.text_input("Model", value=ol.DEFAULT_MODEL, help="Suggested: " + ", ".join(ol.SUGGESTED_MODELS))
    allow_large = st.checkbox("Allow models >= 3B", value=False)
    temperature = st.slider("Temperature", 0.2, 1.2, 0.8, 0.1, help="Lower it if you see 'token repeat limit reached'.")
    batch = st.slider("Cases per model call", 1, 8, 4, help="Smaller batches loop less on tiny models.")
    no_think = st.checkbox("Disable thinking (qwen3-style models)", value=False,
                           help="Sends think=false so reasoning models answer directly instead of spending tokens thinking.")
    if st.button("Check Ollama"):
        try:
            names = ol.list_models(host)
            st.success("Ollama reachable.")
            st.write("Models:", ", ".join(names) or "(none pulled)")
            if model not in names:
                st.warning(f"Not pulled yet: `ollama pull {model}`")
        except ol.OllamaError as e:
            st.error(str(e))
    st.caption("The local model generates the test cases. `random` and `mutation` are plain-code baselines used to check whether the model adds anything.")

llm_kwargs = {"model": model, "host": host, "allow_large": allow_large, "think": False if no_think else None,
              "temperature": temperature, "batch": batch}

st.title("📜 Policy Fuzz Workbench")
st.caption("Finds bugs in agent action policies by comparing them with an independent spec. "
           "Synthetic data only. Research prototype: not a security guarantee.")

tab_spec, tab_try, tab_fuzz, tab_matrix, tab_method = st.tabs(
    ["1 · Spec & bugs", "2 · Try a scenario", "3 · Fuzz one policy", "4 · Mutation matrix", "5 · Method & limits"])

# ------------------------------------------------------------------ 1 spec
with tab_spec:
    st.subheader(domain.title)
    st.markdown("**Specification** (the oracle implements exactly this, independently of the policy code):")
    st.code(domain.spec, language="text")
    st.markdown("**Injectable bugs** (mutants). A good test generator should detect each one:")
    st.dataframe(pd.DataFrame([{"ID": k, "Bug": v} for k, v in domain.bugs.items()]), hide_index=True)

# ------------------------------------------------------------------ 2 try
EXAMPLES = {
    "finance": {"action": "wire", "amount": 900, "currency": "USD", "recipient": "vendor_acme",
                "approval": "false", "approval_source": "agent", "instruction_source": "slack", "objection": False},
    "mail": {"to": "alice@corp.com <evil@attacker.com>", "to_sources": ["user_prompt"],
             "subject_sources": ["user_prompt"], "body_sources": ["inbox_alice"]},
}
with tab_try:
    st.markdown("Paste one scenario as JSON (`NaN` is allowed) and compare the policy with the oracle.")
    key = f"try_text_{dom_name}"
    if key not in st.session_state:
        st.session_state[key] = json.dumps(EXAMPLES[dom_name], indent=2)
    st.text_area("Scenario JSON", key=key, height=230)
    target = st.selectbox("Policy variant", ["CLEAN"] + list(domain.bugs), key=f"try_target_{dom_name}")
    if st.button("Evaluate scenario", type="primary"):
        try:
            sc = json.loads(st.session_state[key])
            p_allow, p_reason = domain.policy([] if target == "CLEAN" else [target])(sc)
            o_allow, o_reason = domain.oracle(sc)
            c1, c2 = st.columns(2)
            c1.metric(f"Policy ({target})", "ALLOW" if p_allow else "DENY", p_reason)
            c2.metric("Oracle (spec)", "ALLOW" if o_allow else "DENY", o_reason)
            if p_allow and not o_allow:
                st.error("FALSE ALLOW: the policy allows something the spec forbids (security bug).")
            elif o_allow and not p_allow:
                st.warning("FALSE DENY: the policy blocks something the spec permits (utility bug).")
            else:
                st.success("Policy and oracle agree.")
        except Exception as e:  # noqa: BLE001
            st.error(f"{type(e).__name__}: {e}")

# ------------------------------------------------------------------ 3 fuzz
with tab_fuzz:
    c1, c2, c3 = st.columns(3)
    target = c1.selectbox("Policy variant", ["CLEAN"] + list(domain.bugs), key="fuzz_target")
    gen = c2.selectbox("Generator", ["ollama", "mutation", "random"], key="fuzz_gen",
                       help="ollama = your local model (the main generator); mutation / random = non-model baselines")
    n = c3.slider("Scenarios", 20, 2000, 300, 20, key="fuzz_n")
    if st.button("Run fuzz", type="primary"):
        try:
            with st.spinner("Generating and evaluating..."):
                scs, info = make_scenarios(domain, gen, n, int(seed), **(llm_kwargs if gen == "ollama" else {}))
                rep = evaluate(domain, target, scs, gen)
            st.session_state["fuzz_result"] = {"report": rep.to_dict(), "info": info, "domain": dom_name}
        except (ol.OllamaError, ValueError) as e:
            st.session_state.pop("fuzz_result", None)
            st.error(str(e))
    res = st.session_state.get("fuzz_result")
    if res and res["domain"] == dom_name:
        r = res["report"]
        m = st.columns(5)
        m[0].metric("Scenarios", r["n"])
        m[1].metric("False allows (security)", r["false_allow"])
        m[2].metric("False denies (utility)", r["false_deny"])
        m[3].metric("Crashes", r["crashes"])
        m[4].metric("Unique failure types", r["unique"])
        if r["target"] == "CLEAN" and (r["false_allow"] + r["false_deny"] + r["crashes"]) == 0:
            st.success("Clean policy matches the oracle on every scenario (0 false positives).")
        if res["info"]:
            st.caption(f"LLM stats: {res['info']}")
            if res["info"].get("errors"):
                st.error(res["info"]["errors"][0])
        if r["examples"]:
            st.markdown("**First findings** (oracle reason vs policy reason):")
            st.dataframe(pd.DataFrame([{"#": f["index"], "Kind": f["kind"], "Policy": f["policy"],
                                        "Oracle": f["oracle"], "Scenario": jdump(f["scenario"])}
                                       for f in r["examples"]]), hide_index=True)
        st.download_button("Download fuzz report (JSON)", json.dumps(
            {"created_at": datetime.now(timezone.utc).isoformat(), "seed": int(seed), **res}, indent=2, default=str),
            file_name="fuzz-report.json", mime="application/json")

# ------------------------------------------------------------------ 4 matrix
with tab_matrix:
    st.markdown("Runs **every generator against every injected bug** on the same scenarios. "
                "Detection rate = how many bugs a generator finds. The CLEAN row must show 0 findings.")
    gens = st.multiselect("Generators", ["ollama", "mutation", "random"], default=["ollama", "mutation", "random"])
    n2 = st.slider("Scenarios per generator", 50, 2000, 400, 50, key="matrix_n")
    if st.button("Run matrix", type="primary", disabled=not gens):
        try:
            with st.spinner("Running matrix..."):
                st.session_state["matrix_result"] = matrix(domain, gens, n2, int(seed), **llm_kwargs)
        except (ol.OllamaError, ValueError) as e:
            st.session_state.pop("matrix_result", None)
            st.error(str(e))
    mr = st.session_state.get("matrix_result")
    if mr and mr["domain"] == dom_name:
        cols = st.columns(len(mr["summary"]))
        for col, (g, s) in zip(cols, mr["summary"].items()):
            col.metric(g, f"{s['mutants_detected']}/{s['mutants_total']} bugs found",
                       f"{s['clean_false_positives']} false positives", delta_color="off")
        by = {(r["target"], r["generator"]): r for r in mr["rows"]}
        targets = list(dict.fromkeys(r["target"] for r in mr["rows"]))
        table = []
        for t in targets:
            row = {"Target": t, "Bug": "(clean policy: expect 0)" if t == "CLEAN" else domain.bugs.get(t, "")}
            for g in mr["summary"]:
                r = by[(t, g)]
                row[g] = ("no scenarios generated" if mr["summary"][g]["scenarios"] == 0 else
                          str(r["false_allow"] + r["false_deny"] + r["crashes"]) if t == "CLEAN"
                          else (f"found @ #{r['first_hit']}" if r["first_hit"] else "MISSED"))
            table.append(row)
        st.dataframe(pd.DataFrame(table), hide_index=True)
        for g, s in mr["summary"].items():
            if s["scenarios"] == 0:
                err = (s["info"].get("errors") or ["the model returned nothing usable"])[0] if s["info"] else "no scenarios"
                st.error(f"{g}: no scenarios were generated. {err}")
            elif s["info"]:
                st.caption(f"{g}: {s['info']}")
        st.download_button("Download matrix report (JSON)", json.dumps(mr, indent=2, default=str),
                           file_name="mutation-matrix.json", mime="application/json")

# ------------------------------------------------------------------ 5 method
with tab_method:
    st.markdown("""
**What this measures.** Whether a test generator can find implementation bugs in a policy, using a
reference oracle written from the spec. Score = fraction of injected bugs found, plus 0 false
positives on the correct policy.

**Why the LLM never labels anything.** The original POC used the model's `expected` label as ground
truth, so a "bypass" only meant "the model disagreed with the engine". Here the oracle decides.

**Limits (read these).**
- The oracle and policy come from the same spec. A mistake *in the spec* is invisible to this method.
- Both are small reference implementations written by the same author; shared misreadings are possible.
- Structured inputs only: this does not run an agent that reads free-text prompt injections.
- Injected bugs are the ones we thought of. Detecting all of them does not show the absence of others.
- Small (<3B) models make weaker, more repetitive generators than the deterministic mutator. Compare them
  in the matrix rather than assuming they help.
""")
