from contextlib import asynccontextmanager

import logfire
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import cases, decisions, demo, events, evidence, golden, l2
from app.config import settings
from app.data.db import close_pools


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Every agent run, tool call and model request becomes a Logfire span (system design
    # §6.3). Configured at server startup rather than import time, so tests that build a
    # TestClient without starting the app don't send spans. Without a token, nothing is
    # sent and nothing in the request path depends on Logfire.
    logfire.configure(
        token=settings.logfire_token or None, service_name="ryde-resolve-api",
        send_to_logfire="if-token-present", console=False,
    )
    logfire.instrument_pydantic_ai()
    yield
    await close_pools()


app = FastAPI(title="RydeResolve backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

# One router per domain, so parallel work rarely touches the same routes file.
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(decisions.router)
app.include_router(l2.router)
app.include_router(events.router)
app.include_router(demo.router)
app.include_router(golden.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
