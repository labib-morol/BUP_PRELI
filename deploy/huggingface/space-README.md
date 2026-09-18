---
title: GridWise LLM
emoji: ⚡
colorFrom: green
colorTo: blue
sdk: docker
app_port: 8000
pinned: false
---

# GridWise - Smart Campus Energy Optimization

LLM-assisted operator-note interpretation with a deterministic guardrail layer and a
linear-programming optimizer. Rename this file to `README.md` in the Space repository.

Endpoints: `GET /health` and `POST /optimize-energy`.

Set `GEMINI_API_KEY` under **Settings -> Variables and secrets** as a secret. `/health`
is ready without it.
