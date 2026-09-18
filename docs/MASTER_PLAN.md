# GridWise LLM — Master Plan (v2, upgraded from Gemini's `implementation_plan.md`)

BUP CSE Fest 2026 · Online Preliminary · `POST /optimize-energy` + `GET /health`

---

## PART 1 — The project, explained end to end

### 1.1 What we are actually building

One HTTP API that turns **human operator notes** into **mathematically optimal 24-hour energy schedules**.

The campus has three energy assets:

| Asset | Behaviour |
|---|---|
| **Grid** | Unlimited import, price `tariff_bdt_per_kwh` varies per hour. No export allowed. |
| **Solar** | Free, capped at `solar_kwh[h]`, can be curtailed (unused = wasted). |
| **Battery** | Stores energy, bounded by capacity + reserve + hourly charge/discharge rates. |

Each request gives 24 hourly entries (`demand_kwh`, `solar_kwh`, `tariff_bdt_per_kwh`), a battery
object, and **1–3 English operator notes**. Roughly one third of all notes are **distractors**
("the cafeteria menu changes tomorrow") that must become `no_op`.

The pipeline is fixed by the spec:

```
operator_notes ──► LLM ──► structured directives ──► deterministic guardrails
                                                            │
                        hourly_plan ◄── LP solver ◄─────────┘
                              │
                              └─► replay-verify every rule ──► JSON response
```

The spec states explicitly: *"Human notes are not directly trusted as math"* and *"an LLM used only
for `plan_summary` does not satisfy the requirement."* The language model must produce the
`directive_interpretation` **that actually drives the optimizer**.

### 1.2 The six directive types (exact machine-checkable shapes)

| `directive_type` | `structured_adjustment` | Effect on the math |
|---|---|---|
| `solar_reduction` | `{"hours":[...], "factor": f}` | `effective_solar[h] = solar[h] × f` — **f is the fraction REMAINING** (80 % reduction → 0.2) |
| `minimum_battery_reserve` | `{"hours":[...], "minimum_energy_kwh": v}` | `E_after[h] ≥ max(base_min, v)` for those hours |
| `no_charge_window` | `{"hours":[...]}` | `charge[h] = 0` |
| `no_discharge_window` | `{"hours":[...]}` | `discharge[h] = 0` |
| `max_grid_window` | `{"hours":[...], "max_grid_kwh": v}` | `grid[h] ≤ v` |
| `no_op` | `null` | nothing (and `applies` must be `false`) |

**Time convention (the #1 off-by-one trap):** whole hours, **start inclusive, end exclusive**.
`1 PM → 3 PM` = `[13, 14]`. `noon → 2 PM` = `[12, 13]`. `2 AM → 5 AM` = `[2,3,4]`.
`hours` must be **ascending, unique, integers 0–23**.

### 1.3 The energy rules the judge replays hour by hour

1. Balance: `grid + solar_used + discharge = demand + charge`
2. `0 ≤ solar_used[h] ≤ effective_solar[h]`
3. Battery state: `charge → E_after = E_before + k`; `discharge → E_after = E_before − k`; `idle → k = 0`
4. Bounds: `max(base_min, active_reserve) ≤ E_after ≤ capacity`
5. Rates: `k ≤ max_charge_kwh_per_hour` / `max_discharge_kwh_per_hour`
6. **End-of-day neutrality: `E_after[23] = initial_energy_kwh`** (starting charge is not free energy)
7. `total_grid_kwh`, `total_cost_bdt`, `peak_grid_kwh` must equal values **recalculated from `hourly_plan`**
8. `battery_action` is exactly one of `charge|discharge|idle`; `battery_kwh = 0` when idle

### 1.4 How we are scored (100 pts, automated)

| # | Category | Pts | What actually earns it |
|---|---|---|---|
| 1 | LLM Directive Interpretation | 25 | 5 relevance/no_op + 5 type + 5 hours + 5 numbers/shape + 5 **paraphrase robustness** |
| 2 | Directive Application & Constraint Correctness | 25 | 10 ground-truth directive applied + 5 balance/solar + 5 battery + 5 action/neutrality/non-negative |
| 3 | Optimization Quality | 10 | `min(1, organizer_optimal_cost / our_cost)`, averaged. **Invalid case ⇒ 0 credit** |
| 4 | API Contract & Schema | 10 | endpoints, request validation, `directive_interpretation` schema/order, response schema + `scenario_id` echo |
| 5 | Performance & Reliability | 10 | 2 health + 3 **p95 ≤ 5 s** + 3 stability (no 5xx) + 2 malformed/provider-failure handling + secret safety |
| 6 | Deployment & Docker Fallback | 10 | 3 live reachability + 4 **pullable image that reaches `/health` with the documented command** + 2 clean startup + 1 no debugging needed |
| 7 | Documentation & Local Reproducibility | 10 | quickstart, env vars, public-sample test procedure, architecture, docker pull/run, deps/limitations/secret guidance |

**Tie-break order:** ① 3-minute video → ② directive application → ③ interpretation → ④ optimization
quality → ⑤ API validity → ⑥ reliability → ⑦ docs → ⑧ engineering.

**The asymmetry that decides the competition:** interpreting a note wrongly *and ignoring it* costs
the 10 application points **and** the optimization points for that case (the judge replays your plan
against the **true** directive, not your reported one). Interpreting a distractor as a real
directive only costs a little interpretation credit + a little cost. **Therefore: when in doubt,
apply rather than ignore.**

---

## PART 2 — What I verified before writing this plan (evidence, not opinion)

`tools/model_check.py` (already written and run) does two independent things per public case:
replays the reference plan against every rule, and solves our LP from scratch.

```
SAMPLE-01 … SAMPLE-10   replay_errs=0   lp == reference cost, gap = 0.000000   status=Optimal
MODEL VERIFIED
```

**Our optimizer reproduces the organizer's exact optimal cost on all 10 public cases.** The
mathematical model (including end-of-day neutrality, solar curtailment, `max(base_min, reserve)`)
is confirmed correct. Optimization Quality is therefore a *solved* problem; the competition is won
in interpretation, contract fidelity, and deployment.

Environment status on this machine:

| Item | Status |
|---|---|
| Python 3.14.4, FastAPI, uvicorn, httpx, pydantic | present |
| PuLP 3.3.2 + bundled CBC | installed, **solves correctly on 3.14** (proven above) |
| `google-genai` 2.24.0 | installed and importing |
| `openai` | installing (for the provider chain) |
| Docker CLI 29.6.1 | present, **daemon not running** — must be started for the fallback image |
| git 2.54 | present |
| **LLM API keys** | **none set** — this is the only true blocker |

---

## PART 3 — Verdict on Gemini's plan

### What it got right
- FastAPI + Pydantic + LP (PuLP/CBC) + structured LLM output + Docker + README + video: the right stack.
- Correctly identifies that greedy heuristics lose and LP guarantees optimality.
- Correctly identifies the time-window off-by-one as the highest-risk detail.
- Correctly identifies "safe failure" as a requirement (no crashes).

### What is wrong or dangerously under-specified

| # | Issue | Severity | Fix in this plan |
|---|---|---|---|
| 1 | **"If it still fails, default to `no_op`"** — exactly backwards. Ignoring an applicable directive forfeits interpretation **and** application **and** optimization for that case. | 🔴 critical | Keep the best-effort extraction; hedge in the *safe direction* instead (§4.3) |
| 2 | **Single LLM provider** ("`GEMINI_API_KEY`"). A quota/outage during judging = catastrophic; the guide says judges will not repair your dependency. | 🔴 critical | Provider chain with timeouts + failover + cache (§4.7) |
| 3 | **No paraphrase-robustness programme.** 5 of the 25 interpretation points are explicitly paraphrase robustness, and hidden notes are reworded. This is the single largest score pool in play. | 🔴 critical | Public-case few-shot prompt + a 100-note self-built eval harness, iterated to ≥95 % (§4.1) |
| 4 | **No post-solve replay verifier**, even though the spec's guardrail table *requires* it ("Final replay"). | 🔴 critical | `verifier.py` replays the returned plan against the directives before responding (§4.5) |
| 5 | **No feasibility ladder.** A wrong extraction can make the LP infeasible → exception → 5xx → reliability + contract points gone. | 🟠 high | 4-tier ladder, never 500 (§4.4) |
| 6 | **No numeric-consistency policy** for `total_*` vs `hourly_plan` (an explicit penalty: "Reported totals disagree with `hourly_plan`"). Float noise can exceed the 0.01 tolerance if rounding is done naively. | 🟠 high | Derived-recomputation rounding (§4.6) |
| 7 | **Docker path ignores "no baked-in secrets" + `/health` with no key.** The image must serve `/health` before any key exists. | 🟠 high | Lazy key loading; `/health` never depends on the LLM (§4.8) |
| 8 | **Deployment left to the end and unspecified.** Free tiers that sleep after 15 min will silently fail a 30 s request timeout. | 🟠 high | Deployment-first in hour 0 + keep-alive ping (§6) |
| 9 | No caching (hurts p95 **and** burns quota), no temperature/max-token determinism, no 400/422/500 error contract, no `scenario_id` echo test, no concurrency plan. | 🟡 medium | Covered in §4.5–§4.9 |
| 10 | Does not exploit **safe-direction monotonicity** of all five directives (a free safety margin against misinterpretation). | 🟡 medium | §4.3 |
| 11 | Says "p95 ≤ 5 s for 10 performance points" — it is 3 of 10 points; health-readiness and stability carry the rest. | ⚪ minor | Corrected in §1.4 |

---

## PART 4 — The winning design (differentiators)

### 4.1 Interpretation accuracy system (25 pts, the biggest pool)
- **One LLM call per request** for all 1–3 notes (lower latency than per-note calls, and the model
  sees full context — necessary to tell a distractor from a directive).
- **Few-shot prompt containing all 10 public cases** (notes → expected directive JSON), *plus* a
  hand-built corpus of paraphrase variants. Using public cases as examples is explicitly fine — it is
  in-context learning, not the forbidden "hard-coded phrase matching as the sole interpreter".
- **Cover the documented paraphrase axes in the examples:**
  - percentage direction: "drops to 20 %" (0.2) vs "drops by 20 %" (0.8) vs "80 % reduction" (0.2)
    vs "one-fifth of normal" (0.2) vs "about half" (0.5)
  - time expressions: "1 PM to 3 PM", "13:00–15:00", "noon until 2 PM", "2 AM until 5 AM",
    "6 PM until 10 PM", "between X and Y", "from X through Y"
  - reserve as absolute kWh **and** as % of capacity (capacity is passed in the prompt)
  - grid cap: "must not exceed", "at or below", "capped at", "no more than", "limit … to"
  - distractors: non-energy topics; energy topics scoped to "next week/month"; past events
- `temperature = 0`, `top_p = 1`, fixed `max_tokens`; schema-enforced JSON output.
- **A self-built eval harness** (`tools/eval_notes.py`) with ~100 generated notes whose ground truth
  I write by hand, scored automatically for relevance/type/hours/numbers. Iterate the prompt until
  accuracy ≥ 95 %. This is the single highest-ROI hour of the hackathon.

### 4.2 Deterministic cross-check layer (explicitly allowed by the guide)
The guide permits "deterministic preprocessing/postprocessing for normalization, JSON validation,
guardrails, and applying structured directives". We use it as a **verifier that can trigger a repair
round** — never as the primary interpreter:
- regex extractor for clock ranges and percentages from the raw note;
- if it disagrees with the LLM (e.g. note says "13:00–15:00" but the LLM emitted `[14,15]`), issue
  **one** repair call that includes the disagreement, then take the repaired answer;
- normalization regardless: dedupe + sort hours, clamp `factor` to [0,1], reject/repair
  `hours` outside 0–23, coerce `applies`/`no_op` consistency.

### 4.3 Safe-direction monotonicity — hedging without invalidation
Every supported directive has a direction that can never invalidate the case against ground truth:

| Directive | Safe direction |
|---|---|
| `solar_reduction` | **lower** factor (use less solar) |
| `minimum_battery_reserve` | **higher** reserve, superset of hours |
| `no_charge_window` / `no_discharge_window` | **superset** of hours |
| `max_grid_window` | **lower** cap, superset of hours |

So when the cross-check layer flags **low confidence** on a note, we may bias one step in the safe
direction (e.g. factor 0.25 → 0.24; window `[13,14]` → `[13,14]` kept exact but reserve rounded up).
The schedule stays *valid* against ground truth in every hedging scenario; worst case is a few BDT of
cost. Conversely, a wrong-but-loose interpretation invalidates the whole case. **Hedge only on
uncertainty — otherwise apply the exact extraction** (hedging always costs a little optimization quality).

### 4.4 Feasibility ladder (never return 5xx)
1. **Tier 1** — LP with all directives → replay-verify → return.
2. **Tier 2** — drop the *least confident* directive (per the cross-check layer), re-solve, verify.
3. **Tier 3** — LP with base energy rules only (no directives), battery idle-biased.
4. **Tier 4** — closed-form static plan (`grid = demand`, `solar_used = 0`, battery idle; always valid).

Each tier re-runs the replay verifier before it is allowed to be returned.

### 4.5 Modules
```
app/main.py         FastAPI app, /health, /optimize-energy, error contract (400/422/500, no stack traces)
app/schemas.py      Pydantic request/response models + validators (24 hours, 1..3 notes)
app/llm.py          provider chain (Gemini → Groq → OpenAI-compatible), schema output, timeout, 1 retry, LRU cache
app/prompt.py       system prompt + few-shot bank (public cases + paraphrase corpus)
app/guardrails.py   normalize/repair/validate LLM output; confidence flags; cross-check layer
app/optimizer.py    PuLP/CBC LP (verified) + tiers + rounding
app/verifier.py     replay of the final plan against directives + energy rules + totals recomputation
app/summary.py      deterministic templated plan_summary (no extra LLM latency)
tools/model_check.py  <- already written: proves the LP matches organizer optima on all 10 public cases
tools/eval_notes.py   <- paraphrase eval harness (interpretation accuracy)
tools/test_public.py  <- end-to-end: POST every public case, score interpretation + validity + cost ratio
```

### 4.6 Numeric hygiene (protects 5 correctness points + the totals violation penalty)
- Solve in floats, then emit `round(x, 4)` with **derived recomputation**:
  round `charge`/`discharge`/`solar_used` first → recompute `E_after` by **exact recursion** (so the
  state chain is exact by construction) → recompute `grid` from the balance equation → `total_*` from
  the rounded rows.
- Clamp `-0.0`/tiny negatives to `0.0`; assert every value is finite and non-negative.
- Final internal assertion: every constraint holds within `1e-6`, else fall back to the unrounded solve.

### 4.7 Reliability (10 pts)
- Provider chain with per-call timeout ≈ 8 s, one retry, provider failover on 429/5xx/timeout.
- **LRU cache keyed on `(notes, capacity_kwh)`** → repeated judge cases return in ~1 ms, protecting
  both p95 and quota.
- Async handler (`httpx.AsyncClient`); LP runs in a thread executor so the event loop never blocks.
- Custom 500 handler with a generic body; nothing sensitive in logs or responses.

### 4.8 Deployment (10 pts)
- **Deploy in hour 0** with a stub endpoint so the live URL exists from the start; redeploy on every push.
- Primary host must be **always-on** (Cloud Run with min-instances=1, a small VPS, or HF Space Docker)
  — *not* a free tier that sleeps, because a cold start + LLM call breaks the 30 s request timeout.
  If a sleeping tier is unavoidable, add a keep-alive self-ping every 5 minutes.
- Fallback image: multi-stage, non-root, pinned `python:3.12-slim`, `libgomp1` for CBC, **no secrets**,
  **`/health` must work with no API key at all** (lazy key loading). Push to Docker Hub **and** GHCR with
  an exact tag; verify with a clean `docker pull` + `docker run` on a fresh shell.

### 4.9 Contract fidelity (10 pts)
- Exact endpoint names, exact field names, `scenario_id` echo, one interpretation entry per note in
  `note_index` order, `no_op ⇒ applies=false + null`, all other directives `applies=true`.
- Malformed JSON → 400; well-formed but semantically invalid → 422; controlled 500 — all with JSON bodies.

---

## PART 5 — 4-hour execution timeline

| Time | Work | Notes |
|---|---|---|
| **0:00–0:20** | Repo + skeleton + **deploy immediately** (stub `/optimize-energy`), keys in env, Dockerfile | Live URL exists before anything else |
| **0:20–1:20** | Pydantic schemas, LLM client + provider chain, prompt with public-case few-shot, guardrails, LP + verifier wired end-to-end | LP core is already proven |
| **1:20–2:00** | Paraphrase eval harness (~100 notes); iterate the prompt to ≥95 %; add cross-check + hedging | **Highest-ROI hour** |
| **2:00–2:40** | Feasibility ladder, caching, timeouts, error contract; redeploy; run `tools/test_public.py` against the **live URL** | |
| **2:40–3:10** | Docker build + push + verify clean pull/run; README to the rubric checklist; load/soak test (30 sequential + 10 concurrent) | Measures p95 honestly |
| **3:10–3:45** | Malformed-input battery of tests; secret scan; 3-minute video (script → record → upload) | Video is tie-break #1 |
| **3:45–4:00** | Final pre-submit checklist pass; freeze | Buffer |

If you have teammates, run 4 parallel tracks: **(A)** prompt + eval harness, **(B)** optimizer +
verifier + ladder, **(C)** API + deployment + Docker, **(D)** README + video. Tracks touch different
files; merge at 2:00.

---

## PART 6 — Risk register

| Risk | Mitigation |
|---|---|
| Provider outage / quota exhaustion mid-judging | 3-provider chain, cache, retry, failover; never remove the LLM from the path |
| Free-tier host sleeps → 30 s timeout | always-on host, else keep-alive ping every 5 min |
| CBC binary missing in a slim image | `libgomp1`; test `docker run` early; HiGHS via scipy as a drop-in alternative |
| Misinterpreting a paraphrase (esp. % direction) | few-shot coverage of both directions + eval harness + safe-direction hedging |
| LP infeasible from a bad extraction | 4-tier feasibility ladder, never 5xx |
| Float noise breaking totals/balance checks | derived-recomputation rounding + internal 1e-6 assertion |
| Judge never warms the service | `/health` must be a pure liveness check that does no I/O and needs no key |
| Missing a required artifact | README/checklist mapped 1:1 to the guide's pre-submit checklist (§1.4 + guide §11) |

---

## PART 7 — Do this in the next 15 minutes

1. **Get LLM keys** (the only hard blocker): create a **Groq** key (fastest, free, sub-second Llama-3.3-70B)
   and a **Gemini** key (free tier). Put them in `.env` / environment — **never** in the repo.
2. **Start Docker Desktop** and log in to Docker Hub (needed for the fallback image).
3. **Create the GitHub repo** (private during the event per the rulebook) and pick the always-on host.
4. Then say **go** — I will build Phase 1 (schemas → LLM → guardrails → LP → verifier) and get the
   live URL green as the first checkpoint.
