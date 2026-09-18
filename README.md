# GridWise — Smart Campus Energy Optimization (LLM-assisted)

BUP CSE Fest 2026 · Online Preliminary · `GET /health` + `POST /optimize-energy`

An HTTP service that reads natural-language campus operator notes, converts them into
machine-checkable energy directives with a language model, validates those directives
deterministically, and returns a **provably cost-optimal** 24-hour grid/solar/battery schedule.

The pipeline the judges evaluate:

```
operator_notes
      │
      ▼
┌─────────────┐   structured JSON    ┌──────────────┐   validated    ┌──────────────┐
│ LLM (2      │ ───────────────────► │ deterministic│ ─────────────► │ LP optimizer │
│ providers)  │  one object per note │  guardrails  │   directives   │ (PuLP + CBC) │
└─────────────┘                      └──────────────┘                └──────┬───────┘
                                                                            │
                        final response  ◄──── replay verification ◄─────────┘
```

**Contents**
[Quickstart](#quickstart) · [API](#api) · [Environment](#environment-variables) ·
[Architecture](#architecture) · [Testing](#testing-and-evidence) · [Docker](#docker-fallback) ·
[Dependencies](#dependencies-and-credits) · [Limitations](#known-limitations) ·
[Secrets](#secret-handling)

---

## Quickstart

Requires Python 3.11+ (developed and tested on 3.14) or Docker.

```bash
git clone https://github.com/labib-morol/BUP_PRELI.git
cd BUP_PRELI          # the repository directory (a local checkout may be named differently)

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt

# Provide at least one provider key (see Environment variables). Never commit it.
#   Windows PowerShell:  $env:GEMINI_API_KEY="..."
#   bash:                export GEMINI_API_KEY="..."

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then, in a second terminal:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}

curl -X POST http://127.0.0.1:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d @public_sample_01.json
```

`public_sample_01.json` is any `cases[].input` object from
`docs/BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json`. A ready-made one-liner that
posts every public case and scores the response is in
[Testing and evidence](#testing-and-evidence).

---

## API

### `GET /health`

Returns `200` with `{"status":"ok"}` once the service is ready. It performs no I/O and
needs **no credentials**, so the Docker fallback image becomes ready before any API key
is supplied.

### `POST /optimize-energy`

Request (exactly the Problem Statement schema):

```json
{
  "scenario_id": "GRID-101",
  "operator_notes": ["Solar output will drop to about 20% from 1 PM to 3 PM."],
  "hours": [
    {"hour": 0, "demand_kwh": 180, "solar_kwh": 0, "tariff_bdt_per_kwh": 7},
    "… 22 more hourly entries, hours 0-23 …"
  ],
  "battery": {
    "capacity_kwh": 500,
    "initial_energy_kwh": 200,
    "minimum_energy_kwh": 50,
    "max_charge_kwh_per_hour": 100,
    "max_discharge_kwh_per_hour": 100
  }
}
```

Response: `scenario_id`, `directive_interpretation` (one entry per note, in
`note_index` order), `hourly_plan` (24 entries), `total_grid_kwh`, `total_cost_bdt`,
`peak_grid_kwh`, `plan_summary`.

Error contract: `400` malformed JSON · `422` well-formed but semantically invalid ·
`500` controlled internal error with no stack trace or secret in the body.

The request parser is intentionally liberal where the Problem Statement is silent:
`hours` are indexed by their `hour` field rather than array position, unknown extra
fields are ignored, and more than three notes are still interpreted rather than
rejected.

---

## Environment variables

Only the names are listed here — never values. Copy `.env.example` to `.env` (git-ignored)
or set them in the platform dashboard.

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | one of these | Google Gemini provider (primary) |
| `GEMINI_API_KEY_2` | no | second Google key from a different project: an independent quota bucket used as failover |
| `EXTRA_API_KEY` / `EXTRA_BASE_URL` / `EXTRA_MODEL` / `EXTRA_NAME` | no | any OpenAI-compatible endpoint as a final failover provider |
| `GROQ_API_KEY` | one of these | Groq provider (spare capacity) |
| `OPENAI_API_KEY` | one of these | OpenAI provider |
| `OPENROUTER_API_KEY` | one of these | OpenRouter provider |
| `GRIDWISE_GEMINI_MODEL` | no | primary model, default `gemini-flash-lite-latest` |
| `GRIDWISE_GEMINI_MODEL_2` | no | spare Gemini model, default `gemini-3.1-flash-lite`; set empty to disable |
| `GRIDWISE_GROQ_MODEL` | no | default `openai/gpt-oss-20b` |
| `GRIDWISE_OPENAI_MODEL` | no | default `gpt-4o-mini` |
| `GRIDWISE_CONSENSUS` | no | how many providers to consult in parallel, default `1` |
| `GRIDWISE_LLM_DEADLINE` | no | ceiling for the retry path when every provider failed, default `12` |
| `GRIDWISE_LLM_TIMEOUT` | no | per-call timeout in seconds, default `7` |
| `GRIDWISE_LLM_BUDGET` | no | total wall-clock allowance for consensus, default `4.0`; the second opinion is dropped rather than delaying the response |
| `GRIDWISE_CONSENSUS_GRACE` | no | extra window for a second opinion, default `2.0`, capped by `GRIDWISE_LLM_BUDGET` |
| `GRIDWISE_LLM_CONCURRENCY` | no | max concurrent provider calls, default `4` |
| `GRIDWISE_LLM_CHAIN` | no | comma-separated provider preference order |
| `PORT` | no | listen port, default `8000` |

`GET /` reports which providers are currently configured, which makes a
misconfigured deployment obvious in one request.

**Model and provider disclosure (Parallel LLM Consensus).** Interpretation uses Google
`gemini-flash-lite-latest` as the primary model, `openai/gpt-oss-20b` on Groq as an
independent cross-family second opinion, and `gemini-3.1-flash-lite` as spare capacity from
the same Google key. The two opinions are requested in parallel, so p95 is the slower of the
two rather than their sum. Temperature is `0` for determinism. Model names are configuration
rather than code: each is an environment variable, and `python tools/check_providers.py`
reports what a given key can actually reach.

---

## Architecture

### LLM role (mandatory requirement)

The language model is the interpretation stage that *produces the constraints the
optimizer consumes* — it is not used for cosmetic text. For each note it decides
relevance, directive type, the affected hours and the numeric value. A note that does
not affect today's 24-hour schedule becomes `no_op` with `applies=false`.

### Deterministic guardrails (`app/guardrails.py`)

LLM output is treated as untrusted until it passes validation:

* **Normalization** — hours are de-duplicated, sorted, and restricted to integers 0-23;
  `factor` is clamped to `[0,1]`; a reserve is clamped to battery capacity; unsupported
  or malformed output degrades to `no_op` instead of inventing a constraint.
* **Grounding checks** — explicit clock expressions and percentages in the note are
  re-derived independently. This catches the two traps that dominate this directive
  space: percentage *direction* ("drops to 20%" is factor 0.2, "drops by 20%" is 0.8,
  "an 80% reduction" is 0.2) and clock normalization (noon, midnight, 12 AM vs 12 PM).
  A value that appears in neither the note nor a percentage-of-capacity calculation is
  flagged as ungrounded.
* **Safe-direction hedging** — every directive type has a direction in which a stricter
  constraint can never invalidate a plan against ground truth (lower solar factor,
  higher reserve, wider no-charge/no-discharge windows, lower grid cap). When two
  providers disagree, the service reports the most likely single reading but enforces
  the union of their readings, so the schedule stays valid whichever reading is correct.
  Hedging is only applied where disagreement was actually detected, because it costs a
  little optimization quality.

### Optimizer (`app/optimizer.py`)

A linear program solved with **PuLP + CBC**. Variables per hour: `grid`, `solar_used`,
`charge`, `discharge`, `battery_energy`. Constraints: energy balance, solar availability
after directive factors, battery bounds (with `max(base_minimum, directive_reserve)`),
charge/discharge rate limits, directive windows and caps, and end-of-day neutrality.
Objective: minimize `Σ grid_kwh[h] × tariff_bdt_per_kwh[h]`.

The formulation was validated against the organizer's own reference optima — see
[Testing and evidence](#testing-and-evidence).

Two numerical details matter for correctness:

* The LP admits degenerate vertices where an hour charges and discharges by the same
  amount. That circulation is cost-neutral but unreportable, because an hour carries a
  single `battery_action`; it is cancelled after the solve, provably without changing
  any constraint or the cost.
* Rounded output recomputes derived values rather than rounding them independently: the
  battery chain is regenerated by exact recursion, and `grid` and the totals are derived
  from the rounded rows, so the numbers the judge recomputes match the numbers reported.

### Verifier (`app/verifier.py`)

Every returned plan is replayed hour by hour — balance, effective solar, battery
transitions, bounds, rate limits, directive-specific rules, end-of-day neutrality, and
the reported totals — before the response leaves the process. If the faithful directive
set cannot be satisfied, the service walks down a 4-tier feasibility ladder (1. full directives, 2. drop the least
confident directive, 3. base rules only, 4. static plan) instead of failing the
request. A provider outage degrades to `no_op` interpretations with a valid plan and a
warning in `plan_summary`; it never returns a 5xx.

---

## Testing and evidence

Three test entry points, none of which need an API key except the last.

```bash
# 1. the deterministic guardrails against organizer ground truth
python tools/test_public.py --guards

# 2. ground-truth directives -> optimizer -> rounding -> replay, cost vs reference
python tools/test_public.py --direct

# 3. the full HTTP contract with a stubbed model (no key needed)
python tools/test_http_stub.py

# 4. end-to-end against a running server (needs a provider key)
python tools/test_public.py --http http://127.0.0.1:8000

# 5. the optimizer model itself against the published optima
python tools/model_check.py
```

Expected results:

| Command | Expected output |
|---|---|
| `tools/model_check.py` | `MODEL VERIFIED` — LP optimum equals the reference optimum on all 10 public cases, gap `0.000000` |
| `tools/test_public.py --guards` | `14 windows and 3 factors cross-checked, 0 disagreement(s)` |
| `tools/test_public.py --direct` | `10/10 valid and optimal, mean cost ratio 1.0000 (optimization quality 10.00/10)` |
| `tools/test_http_stub.py` | `ALL STUB HTTP TESTS PASSED` |
| `tools/test_public.py --http <url>` | every case `interp=ok plan=ok ratio=1.0000` |
| `tools/eval_notes.py` | `fully correct notes: 39/39 (100.0%)`, `projected interpretation category: 25.00/25` |
| `tools/check_providers.py` | `all providers reachable` |
| `tools/load_test.py --url <url>` | p50 ~4.1 s, p95 ~4.1 s, 0 failures on 30 distinct notes |

`tools/test_public.py --http` prints one line per public case with the interpretation
match, plan validity, cost ratio and the p95 latency measured across the run — that is
the score-shaped view of the service.

---

## Docker fallback

The image contains **no credentials**. `/health` is ready without any environment
variable; a provider key is only needed to interpret operator notes.

```bash
# build locally
docker build -t labibmorol/gridwise-llm:1.0.0 .

# or pull the published fallback image
docker pull labibmorol/gridwise-llm:1.0.0

docker run --rm -p 8000:8000 \
  -e GEMINI_API_KEY=<your-key> \
  labibmorol/gridwise-llm:1.0.0

curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

Published reference: `labibmorol/gridwise-llm:1.0.0`
(`sha256:5ecc8e427dd989a6d6ac3ab8fb6e9f4afa20391ed79fe9a9c193748d5205bcd4`).

Verified before publishing: `/health` answers `200 {"status":"ok"}` in ~13 ms with
**no environment variables set at all**, and the image contains no credentials -
`env` inside the container reports zero `*_API_KEY` values and `/srv` holds only
`app/`, `docs/` and `tools/`.

The container binds `0.0.0.0`, honours `$PORT` (default `8000`), runs as a non-root
user, and ships `libgomp1` for the bundled CBC solver.

---

## Dependencies and credits

| Dependency | Role |
|---|---|
| FastAPI, uvicorn | HTTP service |
| Pydantic v2 | request/response schemas and validation |
| PuLP (+ bundled CBC) | linear-programming solver |
| google-genai | Gemini provider SDK |
| openai | OpenAI-compatible SDK, used for Groq / OpenAI / OpenRouter |
| httpx | test harness and async HTTP |

AI coding assistants were used during development, as permitted by the official rulebook.
All challenge data used is the synthetic data supplied by the organizers; no live campus,
utility, billing or personal data is used anywhere in this project.

---

## Known limitations

* The primary hosted endpoint depends on a third-party model API. Availability, quota and
  rate limits are the team's responsibility; the provider chain, caching and the
  degraded mode exist to bound that risk, and the Docker fallback image is supplied as an
  independent execution path.
* A time window that wraps past midnight cannot be expressed as ascending hours under the
  Problem Statement's convention. Such a note is reported as ambiguous rather than
  guessed; no hidden case is expected to require it.
* Hedging widens constraints when two providers disagree, which can cost a small amount
  of optimality in exchange for keeping the plan valid against whichever reading is
  correct. It is disabled automatically when readings agree.
* Responses are rounded to 4 decimal places for readability. Derived values are
  recomputed from the rounded rows, so the judge's recalculation is exact.

---

## Secret handling

* No API key, token or `.env` file is committed — `.gitignore` excludes `.env`, and
  `.env.example` contains names only.
* No secret is written to logs or to an API response; stack traces are never returned to
  a client, and the `500` handler returns a generic body.
* Provider keys are read from the environment at call time and are never baked into the
  Docker image.
