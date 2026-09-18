# GridWise — 3-Minute Video Script

**Target Audience:** Hackathon Judges
**Topic:** Smart Campus Energy Optimization Pipeline
**Key Features Highlighted:** Linear Programming optimality, parallel LLM consensus (Flash + Flash-lite), and the 4-tier feasibility ladder.

---

### [0:00 - 0:30] Introduction & Pipeline Overview
**(Visual: Title slide "GridWise - BUP CSE Fest 2026", fading into an architecture diagram showing Operator Notes -> LLM -> Deterministic Guardrails -> LP Optimizer -> Final Schedule)**

**Speaker (Voiceover/On-camera):**
"Welcome to GridWise. Today, we're showing you our complete solution for the Smart Campus Energy Optimization challenge. The problem is clear: how do we translate messy, natural-language notes from campus operators into a mathematically optimal, 24-hour battery and grid schedule? 

Our pipeline solves this in three steps: robust language modeling, deterministic validation, and provable mathematical optimization. Let me walk you through the highlights."

### [0:30 - 1:15] Parallel LLM Consensus (Flash + Flash-lite)
**(Visual: Screen recording or animation of the LLM interpretation phase. Show an operator note like 'Solar output drops to 20% from 1 PM to 3 PM'. Show Gemini 2.5 Flash and Flash-lite processing it in parallel.)**

**Speaker:**
"It starts with parsing the operator notes. We treat language models as untrusted engines, so we use a parallel LLM consensus model. 
By default, we run Google's Gemini 2.5 Flash alongside Gemini 2.5 Flash-lite to independently interpret the same note. 

If they agree, we proceed confidently. If they disagree—say, on whether a percentage implies a drop *to* 20% or a drop *by* 20%—our deterministic guardrails apply 'safe-direction hedging'. We enforce the union of their constraints so the final schedule remains valid against whichever interpretation reflects the actual ground truth. This ensures we never produce an illegal plan just because a model hallucinated."

### [1:15 - 2:00] Linear Programming Optimality (PuLP + CBC)
**(Visual: Code snippet of `app/optimizer.py` highlighting PuLP constraints, transitioning into a graph showing grid cost minimized over 24 hours.)**

**Speaker:**
"Once we have structured, validated directives, we pass them to our Optimizer. We don't use heuristics or approximations. We formulate the entire 24-hour scheduling problem as a Linear Program and solve it using the industry-standard CBC solver via PuLP.

We account for energy balance, solar availability, battery rate limits, and end-of-day neutrality. The result is mathematically guaranteed to be the absolute minimum cost schedule possible under the constraints. When tested against the organizers' reference optima, our model achieves a perfect 1.0 cost ratio with a zero-gap difference. Every time."

### [2:00 - 2:40] The 4-Tier Feasibility Ladder
**(Visual: Flowchart showing the fallback mechanism: 1. Full Directives -> 2. Drop Least Confident -> 3. Base Rules -> 4. Static Plan. Show a 'Safety Net' graphic.)**

**Speaker:**
"But what happens if an operator inputs a contradictory requirement that makes the math literally unsolvable? 
Instead of returning a 500 error, our Verifier catches this and triggers our 4-Tier Feasibility Ladder:
1. **Tier 1:** We try to solve using the full faithful directive set.
2. **Tier 2:** If infeasible, we drop the least confident directive and retry.
3. **Tier 3:** If still infeasible, we fall back to base physics and baseline rules only.
4. **Tier 4:** Finally, if all else fails, we return a safe, static zero-action plan.

We guarantee a valid, properly formatted JSON response for every request, no matter what."

### [2:40 - 3:00] Outro & Quickstart
**(Visual: Terminal window showing the quickstart commands `docker run ...` and a successful `curl` request. Final slide with team info.)**

**Speaker:**
"GridWise is built for reliability. It’s fully containerized, requires no API key just to boot the health check, and includes comprehensive test suites proving our exactness. 
You can run it locally with one Docker command or a standard Python virtual environment. 

Thank you for watching, and we look forward to your feedback."
