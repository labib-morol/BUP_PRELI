# GridWise — 3-Minute Video Script (shoot this as-is)

**Total runtime target: 2:50** (hard limit 3:00 — do not exceed)
**Format:** screen recording + voiceover. You do not need to be on camera. Production
quality is not judged; technical clarity is.

**The rubric asks for exactly five things.** Every segment below maps to one of them:

| What judges score | Where it is covered |
|---|---|
| Problem understanding | 0:00–0:20 |
| Architecture overview | 0:20–0:50 |
| Solution flow: LLM → deterministic guardrails → optimizer | 0:50–2:05 |
| Key implementation choices | 0:50–2:05 |
| How the submission is run/tested | 2:05–2:30 |

---

## Before you record (10 minutes of prep)

1. Open a terminal at 120% zoom, clear font, dark background.
2. Have these four windows ready to switch to:
   - **A** — a text editor showing `app/prompt.py` lines 1–40 (the system prompt)
   - **B** — a text editor showing `app/optimizer.py` lines 60–100 (the LP constraints)
   - **C** — the terminal, scrolled to a clean prompt
   - **D** — the architecture diagram (draw it once — see the box below)
3. Paste this in the terminal (do **not** press Enter yet):

```bash
curl -s -X POST https://gridwise-llm-rm21.onrender.com/optimize-energy \
  -H "Content-Type: application/json" \
  -d @public_sample_01.json | python -m json.tool
```

4. Silence notifications. Record the whole thing in one take if you can.

**Architecture diagram (draw this once, show it at 0:20 and again at 2:35):**

```
 operator_notes
       |
       v
 +-------------+   structured JSON   +--------------+   validated    +--------------+
 |     LLM     | -----------------> | DETERMINISTIC| -------------> | OPTIMIZER    |
 |  interprets |  1 object per note |  GUARDRAILS  |   directives   | LP + CBC     |
 +-------------+                    +--------------+                +------+-------+
       (Gemini)                       normalize                          |
                                      ground-check                  provably optimal
                                      hedge safely                        |
                                                                         v
                            final response  <---- REPLAY VERIFIER <---- hourly_plan
```

---

## 0:00–0:20 — The problem (20s)

**Visual:** Title card — *"GridWise — Smart Campus Energy Optimization"* — then the
architecture diagram.

**Narration:**
> "Campus operators write notes in plain English, and those notes change how we should
> run the campus battery today. Our job is to turn that language into a provably optimal
> 24-hour energy schedule. The challenge is that a note has to be understood, and then
> trusted with arithmetic — and those are two very different problems."

**Why this works:** states the problem in the operator's terms and names the core
tension the whole design resolves.

---

## 0:20–0:50 — Architecture in one pass (30s)

**Visual:** Keep the diagram up. Trace it with the cursor as you speak.

**Narration:**
> "Our pipeline has four stages. An LLM reads each note and returns structured
> directives. Deterministic guardrails validate and repair that output — language models
> are never trusted as maths. Those directives become constraints in a linear program,
> which finds the minimum-cost schedule. And before we return anything, a verifier
> replays the plan hour by hour against every rule. The language model is mandatory, and
> it drives the optimizer — it is not decoration."

**Why this works:** the rubric explicitly checks that the LLM is on the interpretation
path, not writing summaries. Say so out loud.

---

## 0:50–1:30 — Stage 1: the LLM, and the two traps (40s)

**Visual:** Switch to window **A** (`app/prompt.py`). Highlight the time-window line and
the percentage line as you say them.

**Narration:**
> "Two details decide whether this works. The first is time. A window from 1 PM to 3 PM
> means hours thirteen and fourteen — the start hour is included, the end hour is not.
> Get that off by one and every schedule is wrong.
>
> The second is percentage direction. 'Solar drops to twenty percent' leaves twenty
> percent usable. 'Solar drops by twenty percent' leaves eighty. Same words, opposite
> meaning, and reading it backwards invalidates the case.
>
> So the model returns strict JSON, one object per note, at temperature zero. Then our
> deterministic layer independently derives the window and the factor from the raw text
> as a cross-check."

**Why this works:** judges see you understood the spec's actual traps, not generic LLM
usage. Both examples come straight from the Problem Statement.

---

## 1:30–2:05 — Stages 2 and 3: guardrails and the optimizer (35s)

**Visual:** Return briefly to the diagram, then switch to window **B**
(`app/optimizer.py`), highlighting the constraints.

**Narration:**
> "When the check disagrees with the model, we don't guess. Every directive has a safe
> direction — a stricter constraint that can never invalidate the plan. Lower the solar
> factor, widen an outage window, raise a reserve. So we enforce the union of both
> readings: the plan stays valid whichever one is correct, while we still report the
> model's own interpretation.
>
> Then we solve. This is a real linear program, not a heuristic — energy balance, battery
> bounds and rate limits, directive windows, and end-of-day neutrality, minimised with
> the CBC solver. Our formulation reproduces the organisers' own reference optimum on
> all ten public cases, with a gap of zero point zero zero zero zero zero zero."

**Why this works:** the safe-direction idea is the strongest technical contribution in
the project, and the zero-gap claim is verifiable evidence of exactness.

---

## 2:05–2:30 — How it runs and how we tested it (25s)

**Visual:** Switch to the terminal (window **C**). Press Enter on the prepared `curl`.
Let the JSON response appear on screen. Then run:

```bash
python tools/test_public.py --http https://gridwise-llm-rm21.onrender.com
```

**Narration:**
> "The service is a FastAPI app on Render, containerised as a Docker fallback image, and
> the health check runs with no credentials at all. Everything is reproducible from the
> README. We tested it three ways: all ten public cases, a hand-built corpus of
> paraphrases covering every wording the spec warns about, and a replay verifier that
> re-checks each returned plan before it leaves the service."

**Why this works:** the rubric scores *how the submission is run and tested*. Show the
command actually running rather than describing it.

---

## 2:30–2:50 — Results and close (20s)

**Visual:** Back to the architecture diagram. Overlay the numbers as you say them.

**Narration:**
> "On the live deployment: ten out of ten public cases interpreted correctly, every plan
> valid, and a cost ratio of exactly one — the optimal cost, every time. Median response
> under two seconds. Thank you."

**Why this works:** ends on measured, verifiable numbers rather than adjectives.

---

## Delivery notes

- **Speak from the script, don't read it robotically.** Judges are comparing
  understanding, not elocution.
- **Pace marker:** each 30-second block is roughly 75–80 spoken words. If you run over,
  cut from the 1:30–2:05 segment, never from 0:50–1:30 — the LLM traps are the highest
  scoring content.
- **If you cannot screen-record:** replace windows A, B and C with three static
  screenshots of the same code and terminal output. Everything else stays identical.
- **Check the length before uploading.** If it is over 3:00 the submission may be
  rejected; the requirement is a hard maximum.
- **Do not name a model version you are unsure about.** Say "a Gemini Flash model" — the
  exact identifier lives in the README, and naming a retired version on video is a
  needless inconsistency.
