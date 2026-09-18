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

1. **Open the browser tab and warm the service first.** Go to
   `https://gridwise-llm-rm21.onrender.com/demo` and click **Run optimization** once,
   before you start recording. The Render free tier wakes from sleep on the first
   request, so doing this first means the on-camera click responds in about a second
   instead of stalling.
2. Have these windows ready to switch to:
   - **A** — a text editor showing `app/prompt.py` lines 1–40 (the system prompt)
   - **B** — a text editor showing `app/optimizer.py` lines 60–100 (the LP constraints)
   - **C** — the browser, on the `/demo` page
   - **D** — the architecture diagram (draw it once — see the box below)
3. Optional fallback if the browser misbehaves on the day:
   `python tools/demo_request.py` prints the same result in a terminal, and works in
   bash, PowerShell and cmd.
4. Silence notifications. Record the whole thing in one take if you can.

**Do not use raw `curl` for the demo.** On Windows PowerShell, `curl` is an alias for
`Invoke-WebRequest`, `\` is not a line continuation, and `@file` means splatting, so the
command fails for reasons that have nothing to do with the service. The browser page and
`demo_request.py` both avoid shell quoting entirely.

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

## 2:05–2:30 — How it runs, live, in a browser (25s)

**Visual:** Switch to the **browser**. This whole segment is URLs — no terminal at all.

1. Open `https://gridwise-llm-rm21.onrender.com/health` → shows `{"status":"ok"}`
2. Open `https://gridwise-llm-rm21.onrender.com/demo` → pick a case, click **Run
   optimization**. Let the page fill in: the interpretation, the cost against the
   reference with an `OPTIMAL` badge, the per-hour grid chart, and the 24-hour plan.
3. If time allows, open `/docs` for a second to show the OpenAPI contract.

**Narration:**
> "Everything here is reachable from a browser. The health endpoint confirms readiness
> with no credentials at all. This demo page runs the full pipeline in one click — it
> interprets the note, solves the schedule, and checks the result against the
> organizer's own reference optimum, which you can see it matches exactly. The API
> contract is documented at slash docs. And the same service ships as a Docker image,
> so it can be pulled and run anywhere."

**Why this works:** the rubric scores *how the submission is run and tested*, and a
browser demonstration is the least error-prone possible evidence — nothing can fail on
shell quoting, and the judge sees the actual deployed service answering. Showing the
reference-cost comparison on screen is stronger than any spoken claim.

**If the page is slow on the first click:** that is the Render free tier waking up.
Click once before recording so the container is warm.

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
