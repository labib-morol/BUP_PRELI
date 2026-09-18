"""HTTP contract for the GridWise preliminary service.

Error contract from the Problem Statement:
    400  malformed JSON or structurally invalid request
    422  well-formed but semantically invalid request (optional)
    500  controlled internal error, never a stack trace or a secret

/health performs no I/O and needs no credentials, so the Docker fallback image
becomes ready before any API key is supplied.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .llm import available_providers
from .pipeline import run
from .schemas import OptimizeRequest, OptimizeResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("gridwise")

app = FastAPI(title="GridWise Smart Campus Energy Optimization", version="1.0.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
async def optimize_energy(request: OptimizeRequest) -> OptimizeResponse:
    response, diagnostics = await run(request)
    log.info("scenario=%s tier=%s applied=%s flags=%s",
             request.scenario_id, diagnostics["tier"], diagnostics["applied"],
             diagnostics["flags"])
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Malformed JSON is 400; a well-formed but invalid payload is 422."""
    errors = exc.errors()
    malformed = any(error.get("type") == "json_invalid" for error in errors)
    return JSONResponse(
        status_code=400 if malformed else 422,
        content={
            "detail": "malformed JSON body" if malformed else "request failed validation",
            "errors": [
                {"loc": [str(part) for part in error.get("loc", [])],
                 "type": error.get("type", "value_error")}
                for error in errors
            ],
        },
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal error"})


@app.get("/")
async def root() -> dict:
    return {
        "service": "GridWise Smart Campus Energy Optimization",
        "endpoints": ["GET /health", "POST /optimize-energy"],
        "llm_providers_configured": [provider.name for provider in available_providers()],
    }


def main() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=int(__import__("os").getenv("PORT", "8000")))
