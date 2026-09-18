# EXECUTION — 3 people, 3 hours, rebased on what is already built

This supersedes `MASTER_PLAN.md` (v2) and the v3 revision reviewed elsewhere.
It is short on purpose: the analysis is done, the deterministic half is built and
verified, and the remaining time should go into the LLM layer, deployment and the video.

---

## 1. Already built, tested and pushed — do not rebuild

| Module | State |
|---|---|
| `app/optimizer.py` | LP (PuLP/CBC). Reproduces the organizer's published optimal cost on **all 10 public cases, gap 0.000000** |
| `app/verifier.py` | required "final replay": balance, effective solar, battery chain, bounds, rates, directives, end-of-day, totals |
| `app/guardrails.py` | normalization, grounding checks, safe-direction hedging |
| `app/directives.py` | directive model + **same-type overlap merge** in the safe direction |
| `app/schemas.py` | request/response contract, liberal request parsing |
| `app/prompt.py` | system prompt + few-shot bank over the paraphrase axes |
| `app/llm.py` | parallel consensus across providers, cache, timeouts, retries |
| `app/pipeline.py` | orchestration + fallback ladder |
| `app/main.py` | FastAPI, `400/422/500` contract, `/health` needs no key |
| `tools/` | `model_check.py`, `test_public.py --guards/--direct/--http`, `test_http_stub.py`, `eval_notes.py` |
| `README.md`, `Dockerfile`, `requirements.txt`, `.env.example`, `render.yaml` | required submission artifacts |

Verified output (re-run any of these to confirm):

```
python tools/model_check.py            -> MODEL VERIFIED (gap 0.000000 on all 10)
python tools/test_public.py --guards   -> 14 windows + 3 factors, 0 disagreements
python tools/test_public.py --direct   -> 10/10 valid and optimal, ratio 1.0000
python tools/test_http_stub.py         -> ALL STUB HTTP TESTS PASSED
```

Consequence for the schedule: **the 25-point application category, the 10-point
optimization category, the 10-point contract category and most of reliability are
already earned.** What is left is the LLM layer with a real key, deployment, and the video.

---

## 2. Hosting decision

**Do not use Vercel for this service.** Not because it is bad, but because it is the wrong
shape here, and with three hours left the wrong shape is expensive:

* it needs an adapter rewrite (`api/index.py` + `vercel.json`, no `uvicorn`) that we cannot
  test locally, so we would be debugging the deployment instead of the prompt;
* the function bundle must stay under 250 MB unzipped, and PuLP ships **compiled CBC solver
  binaries** in the wheel - a real size and execution risk in a serverless sandbox;
* the execution-time limit is a separate dashboard setting, so a slow provider call can hit
  it, and each change needs a redeploy.

A Docker host runs the exact artifact we already tested. In order of preference:

| Option | Cost | Sleeps? | Why |
|---|---|---|---|
| **Render free + keep-alive** ← recommended | $0, no card | only after 15 min idle → neutralised by a free UptimeRobot monitor pinging `/health` every 5 min | Docker deploy from the **private** repo, `render.yaml` already in the repo, one click |
| Hugging Face Spaces (Docker) | $0, no card | only after **48 h** of zero traffic → no ping needed | Most robust free option; `deploy/huggingface/` is ready |
| Cloud Run `min-instances=1` | ~$5–10/mo, card | never | Best reliability if a card exists |
| Vercel | $0 | n/a but cold starts | Not recommended; see above |

Required regardless of host: the **Docker image on Docker Hub with an exact tag** (4 points,
and the documented fallback path). GHCR second, only if time allows.

Deploy steps (Render):
1. `render.com` → sign in with GitHub → **New → Blueprint** → select `BUP_PRELI` → Apply.
2. Add `GEMINI_API_KEY` in the service's Environment tab.
3. Add an UptimeRobot HTTP monitor on `https://<service>.onrender.com/health`, 5-minute interval.
4. Verify from outside: `python tools/test_public.py --http https://<service>.onrender.com`.

---

## 3. Corrections to the v3 plan

1. **The "same-type overlap merge rule" (§3.14/§4.2r) is already implemented and tested.**
   `union()` in `app/directives.py` merges same-type readings in the safe direction (min factor,
   max reserve, union of hours, min cap) and leaves different types as independent LP
   constraints. Do not spend Person B's first hour rebuilding it.
2. **Drop the "repair round" (§4.2).** A second LLM round trip on every flagged note spends
   latency inside a 5 s p95 budget and quota we may want later. Hedging already makes a wrong
   reading harmless. Cheap improvement instead: when the deterministic clock parser is
   unambiguous, add **its** reading as one more candidate in the union — it costs nothing and
   covers the case where every model misreads the window.
3. **Tier 4 is not "always valid" (§4.4).** A static idle plan violates the base reserve when
   `initial_energy_kwh < minimum_energy_kwh`. Use `grid = max(demand - solar, 0)` and
   `solar_used = min(demand, solar)` (cheaper than dumping solar), and treat tier 4 as
   "best effort, may be invalid" rather than guaranteed.
4. **The 1e-6 assertion (§4.6) belongs on the unrounded solve.** A plan rounded to 4 dp cannot
   pass a 1e-6 check — 4 dp rounding legitimately moves values by up to 5e-5. Verify the
   unrounded solution at 1e-6, then verify the rounded plan at 1e-3 (still 10× inside the
   judge's 0.01 tolerance). That is what `app/verifier.py` does.
5. **"Two-provider chain (Gemini → Groq)" describes failover; what we need is consensus.**
   Two readings compared in parallel are what produce the disagreement signal that decides
   whether to hedge; a sequential failover produces no signal at all. One Gemini key already
   gives two readings (`gemini-2.5-flash` + `gemini-2.5-flash-lite`), so **no Groq signup is
   needed** — the calls run in parallel, so p95 is the slower of the two, not their sum.
6. **The video is tie-break #1 and v3 schedules it in the busiest slot.** Write the script
   during the first deployment wait, record it as soon as the endpoint is live and green, and
   keep it under 3:00. It is worth more than any remaining polish.

---

## 4. Three hours, three owners

Everything below assumes the key exists by 0:10. If it does not, Person A works on the
eval corpus (writable without a key) and the schedule shifts right.

| Time | Person A — Interpretation | Person B — Verification & load | Person C — Ship & submit |
|---|---|---|---|
| **0:00–0:20** | Live smoke test against the real key; confirm the response shape on 1 public case | Start Docker Desktop; build the image; confirm `/health` with **no** key | `render.com` Blueprint deploy; set the key; UptimeRobot monitor |
| **0:20–1:10** | Run the eval corpus (35–40 notes); iterate the prompt until two consecutive passes find no new failure mode | `docker run` + clean `docker pull` verify; push image to Docker Hub with tag `1.0.0` | README final pass against the rubric checklist; write the video script |
| **1:10–1:40** | Re-run `tools/test_public.py --http` against the live URL; fix anything the real model gets wrong | Load/soak: 30 sequential + 10 concurrent; honest p95; confirm no 5xx and no 429 | Record the video (≤3:00); upload; collect the submission package |
| **1:40–2:10** | Second prompt iteration only if the eval set still shows failures | Malformed-input battery (400/422), secret scan, `--guards`/`--direct` re-run | Fill the submission form: base URL, repo, README, image ref, video link |
| **2:10–2:40** | Freeze the prompt; final live verification of all 10 public cases | Final `/health` + external reachability from a second network (phone hotspot) | Confirm repo public-after-deadline plan, image pullable, links accessible |
| **2:40–3:00** | **Buffer.** Nothing new ships after this point. | | |

Hard rule: **after 1:40 nothing that has not already passed a test goes into the live service.**

---

## 5. Parallel agent split (non-overlapping ownership)

| Agent | Owns these files only | Deliverable |
|---|---|---|
| 1 | `app/prompt.py`, `tools/notes_corpus.json` | the 35–40-note corpus and prompt iterations |
| 2 | `deploy/**`, `Dockerfile`, `render.yaml` | working image pushed to Docker Hub, both host paths documented |
| 3 | `README.md`, `docs/VIDEO_SCRIPT.md` | rubric-complete README and a shootable script |
| main | `app/llm.py`, `app/guardrails.py`, `app/pipeline.py` | live key wiring, eval scoring, prompt-fix integration |

No two agents edit the same file. Agents 1 and 3 need no API key and can start immediately.
