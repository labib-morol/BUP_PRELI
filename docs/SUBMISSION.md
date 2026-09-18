# Submission package — copy these into the form

Everything below is verified. Values marked `[ ]` still need to be filled from your side.

## 1. Live base URL

```
https://gridwise-llm-rm21.onrender.com
```

| Endpoint | Verified |
|---|---|
| `GET /health` | `200 {"status":"ok"}` in ~0.26 s |
| `POST /optimize-energy` | 10/10 public cases correct, p50 1.60 s, max 1.75 s |

Reachability from outside the development machine: **confirmed** (tested from this
machine against the public URL; both endpoints answered).

Recommended: an UptimeRobot HTTP monitor on `/health` every 5 minutes. This is not
cosmetic — the Render free tier spins the container down after 15 minutes without
traffic, and the first request after a wake is either a `502` while the container
boots or a slow cold call. A monitor removes both, and it is the difference between
2/3 and 3/3 on the latency score.

## 2. GitHub repository

```
https://github.com/labib-morol/BUP_PRELI
```

- Created after question reveal, kept **private** during the event.
- Must be switched to **public after the submission deadline** (rulebook requirement).
- No secrets committed: verified across the live branch, every ref, and every object
  in the repository.

## 3. Docker fallback image

```
labibmorol/gridwise-llm:1.0.0
sha256:ff07caa8271ec7ed5d7c995b740d65b061fa011f1470e333a8bae3f8ee3cc498
```

Repository is **public**, so judges can pull without credentials. Verified
anonymously pullable, and verified that `/health` answers with **no environment
variables set at all**.

```bash
docker pull labibmorol/gridwise-llm:1.0.0
docker run --rm -p 8000:8000 -e GEMINI_API_KEY=<key> labibmorol/gridwise-llm:1.0.0
curl http://127.0.0.1:8000/health
```

## 4. Environment variables (names only — never values)

Required for interpretation: `GEMINI_API_KEY`

Configured on Render:

| Variable | Value |
|---|---|
| `GRIDWISE_GEMINI_MODEL` | `gemini-flash-lite-latest` |
| `GRIDWISE_GEMINI_MODEL_2` | `gemini-3.1-flash-lite` |
| `GRIDWISE_GROQ_MODEL` | `openai/gpt-oss-20b` |
| `GRIDWISE_CONSENSUS` | `1` |
| `GRIDWISE_LLM_TIMEOUT` | `10` |
| `GRIDWISE_LLM_BUDGET` | `8.0` |
| `GRIDWISE_LLM_DEADLINE` | `20` |
| `GROQ_API_KEY` | optional spare |

## 5. Model / provider disclosure

- Primary: Google `gemini-flash-lite-latest` (temperature 0, JSON output).
- Spare chain: `openai/gpt-oss-20b` on Groq, then `gemini-3.1-flash-lite`, then any
  OpenAI-compatible endpoint configured through `EXTRA_*`.
- Solver: PuLP with the bundled CBC linear-programming solver.
- Refusal of hard-coded interpretation: the model performs the interpretation; the
  deterministic layer only normalizes, validates and hedges.

## 6. 3-minute video

`[ ]` record from `docs/VIDEO_SCRIPT.md`, upload, paste the link here.

## 7. Evidence to cite

```
python tools/model_check.py            -> MODEL VERIFIED, gap 0.000000 on all 10 public cases
python tools/test_public.py --guards   -> 14 windows and 3 factors cross-checked, 0 disagreement(s)
python tools/test_public.py --direct   -> 10/10 valid and optimal, ratio 1.0000
python tools/test_public.py --http URL -> 10/10 fully correct
python tools/eval_notes.py             -> 39/39 paraphrases, projected 25.00/25 interpretation
python tools/test_http_stub.py         -> ALL STUB HTTP TESTS PASSED
python tools/load_test.py --url URL    -> p50 ~1.6 s, 0 failures on distinct payloads
```

## Known limitations (state these honestly if asked)

- A time window that wraps past midnight cannot be expressed as ascending hours under
  the Problem Statement convention; such a note is treated as ambiguous rather than
  guessed.
- Free-tier hosting scales to zero, so the first request after an idle period is slow
  unless a keep-alive monitor is running (see item 1).
- AgentRouter was configured as a spare but its key is rejected with
  `401 unauthorized client detected` by the vendor; it is inert and never blocks the
  request path.
