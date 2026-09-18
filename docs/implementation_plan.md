# Goal Description

The goal is to build an HTTP API for the BUP CSE Fest 2026 Hackathon (GridWise Smart Campus Energy Optimization Challenge). The service will expose a `GET /health` endpoint for readiness and a `POST /optimize-energy` endpoint that uses an LLM to interpret natural-language operator notes into structured energy directives. These directives are applied to a 24-hour campus energy model, and a mathematical optimizer calculates a valid schedule that minimizes the total grid electricity cost. 

## User Review Required

> [!IMPORTANT]
> The solution requires a Language Model (LLM) API to interpret operator notes. I plan to use the `google-genai` library with Gemini 2.5 models. You will need to provide a valid `GEMINI_API_KEY` environment variable when running the service. Please let me know if you prefer a different LLM provider (e.g., OpenAI).

> [!WARNING]
> Optimization libraries: I plan to use `PuLP`, a reliable Python linear programming library that includes a built-in solver (CBC). This will be used to generate the deterministic mathematical schedule. Ensure that the deployment environment allows installing this C-based dependency (standard Linux/Windows environments are fully supported).

## Open Questions

1. Do you have a preferred LLM provider, or is using Gemini via the `GEMINI_API_KEY` acceptable?
2. The judge requires a Docker fallback image. Do you want me to write the `Dockerfile` and `README.md` containing all setup instructions?

## Proposed Changes

We will create a Python FastAPI backend. The codebase will be modularized into several components for readability and testing.

---

### API Layer & Models
Defines the REST endpoints, Pydantic schemas for the request and response shapes, and validation logic.

#### [NEW] [main.py](file:///c:/Users/T14S/BUP%20Hackathon/app/main.py)
- `GET /health` endpoint returning `{"status": "ok"}`
- `POST /optimize-energy` endpoint to orchestrate LLM interpretation and optimization

#### [NEW] [models.py](file:///c:/Users/T14S/BUP%20Hackathon/app/models.py)
- Pydantic models for the problem statement schema: `OptimizeRequest`, `HourEntry`, `BatteryObject`, `DirectiveInterpretation`, `HourlyPlanEntry`, and `OptimizeResponse`.

---

### LLM Interpreter
Handles communication with the generative model to parse operator notes.

#### [NEW] [llm_interpreter.py](file:///c:/Users/T14S/BUP%20Hackathon/app/llm_interpreter.py)
- Uses `google-genai` to parse natural language notes.
- Uses Gemini's `response_schema` structured output capabilities to ensure the LLM strictly follows the required guardrails, extracting accurate hours (converted to 0-23 format), factors, and properties.
- Normalizes output to match exactly the required `directive_interpretation` format.

---

### Mathematical Optimizer
Applies directives as constraints and solves the cost-minimization problem.

#### [NEW] [optimizer.py](file:///c:/Users/T14S/BUP%20Hackathon/app/optimizer.py)
- Uses `PuLP` to define the Linear Programming (LP) problem.
- Variables for each hour: `grid`, `solar_used`, `charge`, `discharge`, `battery_energy_after`.
- Constraints applied: energy balance, maximum charge/discharge rates, capacity limits, end-of-day neutrality.
- Modifies constraints dynamically based on interpreted directives (e.g., `no_charge_window` sets `charge` max to 0 for those hours).
- Solves the objective function: `minimize(sum(grid[h] * tariff[h]))`.
- Extracts the solution to build the 24-hour `hourly_plan`.

---

### Deployment & Configuration
Provides the necessary artifacts for local reproduction and judging.

#### [NEW] [requirements.txt](file:///c:/Users/T14S/BUP%20Hackathon/requirements.txt)
- `fastapi`, `uvicorn`, `pulp`, `google-genai`, `pydantic`.

#### [NEW] [Dockerfile](file:///c:/Users/T14S/BUP%20Hackathon/Dockerfile)
- Standard Python 3.11+ image, installs dependencies, and runs `uvicorn`.

#### [NEW] [README.md](file:///c:/Users/T14S/BUP%20Hackathon/README.md)
- Explains the architecture, setup instructions, how to run using Docker, and environment variable requirements (as per the participant guide).

## Verification Plan

### Automated Tests
- I will create a script `test_public_cases.py` to parse the `BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json` and send requests to the local server.
- The script will verify that the responses match the expected `hourly_plan` schema, total cost matches the reference (within tolerance), and the API responds in under 5 seconds.

### Manual Verification
- You will need to start the FastAPI server locally (`uvicorn app.main:app --reload`).
- You can manually use `curl` to test the `/health` and `/optimize-energy` endpoints.
