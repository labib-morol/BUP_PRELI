# GridWise — Video Recording Sheet

**Target 2:30. Stretch 2:45. Hard limit 3:00.**
Screen recording + voiceover. No camera needed. No terminal needed.

Narration totals ~350 words, which is about 2:25 at a normal pace — the rest is
breathing room, so nobody has to rush.

---

## STEP 1 — Set up exactly this (5 minutes, before recording)

Open in this order. The tab numbers are used in the shot list.

| Tab | What | URL |
|---|---|---|
| **Tab 1** | Health check | `https://gridwise-llm-rm21.onrender.com/health` |
| **Tab 2** | Interactive demo | `https://gridwise-llm-rm21.onrender.com/demo` |
| **Tab 3** | The prompt | `github.com/labib-morol/BUP_PRELI/blob/main/app/prompt.py` |
| **Tab 4** | The optimizer | `github.com/labib-morol/BUP_PRELI/blob/main/app/optimizer.py` |
| **Tab 5** | Architecture diagram | the diagram at the bottom of this file, open in a text editor |

Then:

1. **Warm the service first.** Go to Tab 2, pick `SAMPLE-01`, click **Run optimization**,
   and let it finish. Render wakes on the first request; doing it now means the on-camera
   click takes about 1.5 seconds instead of stalling.
2. Browser zoom **110%**.
3. Do Not Disturb on. Close chat apps.

---

## STEP 2 — Record

| Time | Tab | On screen | Say |
|---|---|---|---|
| **0:00–0:15** | **Tab 5** | Diagram. Cursor resting at the top. | "Campus operators send notes in plain English, and those notes change how we should run the campus battery today. We turn that language into a provably optimal 24-hour energy schedule. The hard part: the text has to be understood, and then trusted with arithmetic." |
| **0:15–0:40** | **Tab 5** | Trace left to right with the cursor: LLM → guardrails → optimizer → verifier. Pause on each box. | "Our pipeline has four stages. An LLM reads each note and returns structured directives. Deterministic guardrails validate that output — language models are never trusted as maths. Those directives become constraints in a linear program that finds the minimum-cost schedule. And a verifier replays the finished plan against every rule before we return it." |
| **0:40–0:58** | **Tab 3** | Scroll so **TIME WINDOWS** is centred. Underline `1 PM to 3 PM -> [13, 14]` with the cursor. | "Two details decide whether this works. First, time. A window from 1 PM to 3 PM means hours thirteen and fourteen — start included, end excluded. Off by one, and every schedule is wrong." |
| **0:58–1:15** | **Tab 3** | Scroll to **PERCENTAGES**. Point at the contrast lines `drops to 20%` and `drops by 20%`. | "Second, percentage direction. 'Solar drops to twenty percent' leaves twenty percent usable. 'Drops by twenty percent' leaves eighty. Same words, opposite meaning. So the model returns strict JSON at temperature zero, and our deterministic layer independently re-derives the window and the factor from the raw text." |
| **1:15–1:45** | **Tab 4** | Optimizer code. Point at the constraints block, then the objective line. | "When the check disagrees with the model, we don't guess. Every directive has a safe direction — a stricter constraint that can never invalidate the plan. We enforce the union of both readings, so the plan stays valid whichever is correct, while still reporting the model's own interpretation. Then we solve: a real linear program — energy balance, battery limits, directive windows, end-of-day neutrality — minimised with CBC. Our formulation reproduces the organisers' reference optimum on all ten public cases." |
| **1:45–2:10** | **Tab 1**, then **Tab 2** | Tab 1: let the JSON sit for two seconds. Tab 2: pick `SAMPLE-01`, click **Run optimization**, wait for the green **OPTIMAL** banner, then scroll slowly through the chart and the plan table. | "Everything is reachable from a browser. Health confirms readiness with no credentials. This demo page runs the whole pipeline in one click — it interprets the notes, solves the schedule, and checks the cost against the organiser's reference, which you can see it matches exactly. The API contract is documented, and the service ships as a Docker image." |
| **2:10–2:30** | **Tab 5** | Back to the diagram. Let it hold. | "On the live deployment: ten out of ten public cases interpreted correctly, every plan valid, and the optimal cost every time, in under two seconds. Thank you." |

**Running long?** Trim 1:15–1:45 to its first and last sentences — keep the safe-direction
idea and the "reproduces the reference optimum" claim.
**Never cut 0:40–1:15.** The two traps are the highest-scoring content in the video.
**Running short?** Scroll the 24-hour table on Tab 2 more slowly. Don't add sentences.

---

## STEP 3 — Before uploading

1. **Check it is under 3:00.** If it is over, re-record — it is a hard maximum.
2. Export **MP4**.
3. Upload somewhere a judge can open **without logging in** (unlisted YouTube, or Drive
   set to "anyone with the link"). Test the link in a private browser window.
4. Paste the link into the submission form, with the other artifacts from
   `docs/SUBMISSION.md`.

---

## Architecture diagram (Tab 5)

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
