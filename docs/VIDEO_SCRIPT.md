# GridWise — Video Recording Sheet

**Runtime target 2:50. Hard limit 3:00. Do not exceed it.**
Screen recording + voiceover. No camera needed.

---

## STEP 1 — Set up exactly this (5 minutes, before recording)

Open these in this order. The order matters: the tab numbers below are used in the
shot list, so switching is a single `Ctrl+Tab` or a click on a fixed tab position.

| Tab | What | URL / file |
|---|---|---|
| **Tab 1** | Health check | `https://gridwise-llm-rm21.onrender.com/health` |
| **Tab 2** | Interactive demo | `https://gridwise-llm-rm21.onrender.com/demo` |
| **Tab 3** | API contract | `https://gridwise-llm-rm21.onrender.com/docs` |
| **Tab 4** | The prompt | `github.com/labib-morol/BUP_PRELI/blob/main/app/prompt.py` |
| **Tab 5** | The optimizer | `github.com/labib-morol/BUP_PRELI/blob/main/app/optimizer.py` |
| **Tab 6** | Architecture diagram | the ASCII diagram at the bottom of this file — keep it open in a text editor |

Then:

1. **Warm the service.** Go to Tab 2, select `SAMPLE-01`, click **Run optimization**,
   and let it finish. Render's free tier wakes on the first request; doing this now means
   the click you show on camera responds in about 1.5 seconds instead of stalling.
2. Browser zoom to **110%** so code and text are readable.
3. Turn on Do Not Disturb. Close Slack, Discord, mail.
4. Terminal not needed. Nothing in this video requires typing.

---

## STEP 2 — Record

| Time | Show this | Do this on screen | Say this |
|---|---|---|---|
| **0:00–0:20** | **Tab 6** (diagram) | Start here. Mouse resting near the top of the diagram. | "Campus operators write notes in plain English, and those notes change how we should run the campus battery today. Our job is to turn that language into a provably optimal 24-hour energy schedule. The challenge is that a note has to be understood, and then trusted with arithmetic — and those are two very different problems." |
| **0:20–0:50** | **Tab 6** (diagram) | Trace the flow with the cursor, left to right: LLM → guardrails → optimizer → verifier. Pause the cursor on each box as you name it. | "Our pipeline has four stages. An LLM reads each note and returns structured directives. Deterministic guardrails validate and repair that output — language models are never trusted as maths. Those directives become constraints in a linear program, which finds the minimum-cost schedule. And before we return anything, a verifier replays the plan hour by hour against every rule. The language model is mandatory and it drives the optimizer — it is not decoration." |
| **0:50–1:10** | **Tab 4** (prompt.py) | Scroll so the **TIME WINDOWS** block is centred. Underline the line `1 PM to 3 PM -> [13, 14]` with the cursor. | "Two details decide whether this works. The first is time. A window from 1 PM to 3 PM means hours thirteen and fourteen — the start hour is included, the end hour is not. Get that off by one and every schedule is wrong." |
| **1:10–1:30** | **Tab 4** (prompt.py) | Scroll slightly down to the **PERCENTAGES** block. Point at the two contrast lines: `drops to 20%` and `drops by 20%`. | "The second is percentage direction. 'Solar drops to twenty percent' leaves twenty percent usable. 'Solar drops by twenty percent' leaves eighty. Same words, opposite meaning, and reading it backwards invalidates the case. So the model returns strict JSON at temperature zero, and our deterministic layer independently derives the window and the factor from the raw text as a cross-check." |
| **1:30–1:50** | **Tab 6** (diagram) briefly, then **Tab 5** (optimizer.py) | One second on the diagram, then switch to optimizer.py and scroll to the constraint block (the energy-balance and battery-bounds lines). | "When the check disagrees with the model, we don't guess. Every directive has a safe direction — a stricter constraint that can never invalidate the plan. Lower the solar factor, widen an outage window, raise a reserve. So we enforce the union of both readings: the plan stays valid whichever one is correct, while we still report the model's own interpretation." |
| **1:50–2:05** | **Tab 5** (optimizer.py) | Stay on the code. Point at the objective line (`lpSum` with the tariff), then the end-of-day constraint. | "Then we solve. This is a real linear program, not a heuristic — energy balance, battery bounds and rate limits, directive windows, and end-of-day neutrality, minimised with the CBC solver. Our formulation reproduces the organisers' own reference optimum on all ten public cases, with a gap of zero point zero zero zero zero zero zero." |
| **2:05–2:20** | **Tab 1** (/health) | Switch to Tab 1. Let the JSON sit on screen. | "Everything here is reachable from a browser. The health endpoint confirms readiness with no credentials at all." |
| **2:20–2:45** | **Tab 2** (/demo) | Switch to Tab 2. Select `SAMPLE-01`, click **Run optimization**. Wait for the green **OPTIMAL** banner. Then **scroll down slowly** past the chart and into the 24-hour plan table so both are seen. | "This demo page runs the full pipeline in one click — it interprets the note, solves the schedule, and checks the result against the organizer's own reference optimum, which you can see it matches exactly. The API contract is documented at slash docs, and the same service ships as a Docker image that can be pulled and run anywhere." |
| **2:45–2:50** | **Tab 6** (diagram) | Cut back to the diagram. Stop talking and let it hold for two seconds. | "On the live deployment: ten out of ten public cases interpreted correctly, every plan valid, and the optimal cost every time. Thank you." |

**If you are running long:** cut from 1:50–2:05. Never cut 0:50–1:30 — the two traps
are the highest-scoring content in the whole video.
**If you are running short:** linger longer on the Tab 2 demo at 2:20, scrolling the
24-hour table slowly. Do not add new sentences.

---

## STEP 3 — Before you upload

1. **Check the length.** It must be **under 3:00**. If it is over, re-record — the
   requirement is a hard maximum and an over-length video risks rejection.
2. Export as **MP4**.
3. Upload where a judge can open it **without logging in** — unlisted YouTube is fine,
   Google Drive with "anyone with the link" also works. Test the link in a private
   browser window before submitting.
4. Paste the link into the submission form alongside the other artifacts from
   `docs/SUBMISSION.md`.

---

## Architecture diagram (paste into a text editor, Tab 6)

```
 operator_notes
       |
       v
 +-------------+   structured JSON   +--------------+   validated    +--------------+
 |     LLM     | -----------------> | DETERMINISTIC| -------------> | OPTIMIZER    |
 |  interprets |  1 object per note |  GUARDRAILS  |   directives   | LP + CBC     |
 +-------------+                    +--------------+                +------+-------+
       (Gemini)                       normalize                          |
                                      ground-check                 provably optimal
                                      hedge safely                        |
                                                                         v
                            final response  <---- REPLAY VERIFIER <---- hourly_plan
```
