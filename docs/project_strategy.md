# GridWise Smart Campus Energy Optimization - Project Overview & Strategy

## 1. Project Explanation: What Are We Building?

At its core, this project is an **AI-augmented Mathematical Optimization Pipeline**. You are operating a smart campus with three components:
1. **Grid Electricity**: You buy power from the grid (price changes every hour).
2. **Rooftop Solar**: Free energy, but availability varies.
3. **Battery Storage**: Can store excess energy or cheap grid energy to use later when prices are high.

**The Challenge:**
Every day, you receive a 24-hour forecast (demand, solar, grid price) AND 1 to 3 **operator notes** written in plain English (e.g., *"We are cleaning solar panels from 1PM to 3PM, expect an 80% drop in solar"* or *"Do not charge the battery at 5 PM"*).

**The Flow:**
1. **Input**: A JSON payload containing the 24-hour data and the English operator notes.
2. **LLM Interpretation**: An AI (LLM) reads the English notes and extracts them into strict, machine-readable JSON directives (e.g., `solar_reduction`, `no_charge_window`).
3. **Guardrails**: Deterministic code checks the LLM's output to ensure it didn't hallucinate or invent rules.
4. **Mathematical Optimization**: A Linear Programming (LP) solver calculates the *perfect* 24-hour schedule (when to charge, discharge, or stay idle) to minimize the total electricity bill while respecting the rules.
5. **Output**: A JSON payload with the LLM's interpretation and the 24-hour schedule.

---

## 2. Strategy to Reach the Top 3 (Out of 400+ Teams)

To win, we must exploit the **Evaluation Rubric**. Many teams will build a basic LLM script and a flawed "greedy" algorithm. We will build an enterprise-grade pipeline that maxes out every scoring category.

### A. Perfect Optimization Score (10/10 Points)
*The Trap:* Many teams will write a manual loop (e.g., `if price is high, discharge battery`). This will fail complex edge cases and lose points.
*Our Solution:* We will use **Linear Programming (LP)** using Python's `PuLP` library. LP translates all rules into mathematical equations and finds the **absolute mathematical minimum cost**. It is guaranteed to be 100% optimal. If the lowest possible bill is 34,500 BDT, our solver will find exactly 34,500 BDT every single time.

### B. High-Speed LLM Interpretation (10/10 Performance Points)
*The Trap:* The rubric heavily penalizes slow APIs. You need a **p95 latency of under 5 seconds** to get full points. Heavy models (like GPT-4 or Gemini 1.5 Pro) might take 6-10 seconds, losing you critical points.
*Our Solution:* We will use **Gemini 2.5 Flash** (or a similarly fast model) combined with **Structured Outputs (JSON Schema)**. Flash evaluates in `< 2 seconds` and using native JSON schemas prevents parsing errors. We will also write a highly optimized prompt using few-shot examples from the public cases so it never gets confused by paraphrased text.

### C. Bulletproof Reliability (Zero 5xx Errors)
*The Trap:* If the LLM hallucinates an invalid directive and crashes the backend, you lose points.
*Our Solution:* We will implement **Safe Failure & Fallbacks**. If the LLM outputs something weird, Pydantic validators will catch it. We will implement an automatic 1-time fast-retry. If it still fails, we default to `no_op` (ignore the confusing note) rather than crashing the server. A suboptimal schedule is worth more points than a crashed server.

### D. Flawless Constraint Application (25/25 Points)
*The Trap:* Applying "time windows" wrong. The problem says `1 PM to 3 PM` means hours `[13, 14]` (start-inclusive, end-exclusive). Teams will mess this up and output `[13, 14, 15]`, instantly failing the hidden test cases.
*Our Solution:* We will write rigorous unit tests for the time-window logic against the public sample cases to ensure we never make an off-by-one error. 

### E. Exceptional Local Reproducibility & Docker (20/20 Points)
*The Trap:* Judges will dock points if the `README.md` is messy or the Docker container crashes due to missing environment variables.
*Our Solution:* 
- We will build a production-ready `Dockerfile` (multi-stage build, non-root user).
- A beautifully formatted `README.md` with copy-paste commands.
- We will clearly document how to pass the `GEMINI_API_KEY`.

### F. Winning the Tie-Breaker (The 3-Minute Video)
In a hackathon with 400+ teams, multiple teams *will* score 100/100. The judge will use the **3-minute architecture video** as the #1 tie-breaker.
*Our Solution:* When we finish the code, I will write a video script for you. You will record a clean, technical video highlighting:
1. That we used **Linear Programming** (proving we understand mathematical optimality).
2. That we used **Structured JSON Generation** for zero-latency LLM parsing.
3. That we implemented strict **Pydantic guardrails** for safety.

---

## 3. Technology Stack Recommendation

- **Framework**: Python 3.11+ with **FastAPI** (Extremely fast, built-in Pydantic validation).
- **LLM Integration**: `google-genai` using **Gemini 2.5 Flash** (For sub-2-second latency).
- **Optimizer**: **PuLP** with the CBC solver (Industry standard for Linear Programming).
- **Deployment**: Docker (Standardized environment).

## Next Steps

If you approve this strategy, we will proceed to Phase 1: Building the Pydantic schemas and the core FastAPI shell.
