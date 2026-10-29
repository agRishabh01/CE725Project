"""FastAPI app entry. Week 5 wires every MVP route."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import estimates, exports, mapping, projects, rates, runs, validation
from boq_engine import __version__ as engine_version


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title="CE 725 BOQ API",
    version="0.5.0",
    description=(
        "AI-Assisted BOQ and Cost Estimation. "
        "Single-user API-key auth: send `X-API-Key: <value>` when the server has `API_KEY` set."
    ),
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(RequestValidationError)
async def _validation_handler(_, exc: RequestValidationError) -> JSONResponse:
    """Return Pydantic field-path errors as a flat, UI-friendly list."""
    details = []
    for e in exc.errors():
        details.append(
            {
                "loc": ".".join(str(x) for x in e.get("loc", [])),
                "msg": e.get("msg"),
                "type": e.get("type"),
            }
        )
    return JSONResponse(status_code=422, content={"errors": details})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine_version": engine_version}


app.include_router(projects.router)
app.include_router(estimates.router)
app.include_router(rates.router)
app.include_router(runs.router)
app.include_router(exports.router)
app.include_router(mapping.router)
app.include_router(validation.router)
