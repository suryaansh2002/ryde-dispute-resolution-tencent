from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import cases, decisions, demo, events, evidence, l2
from app.config import settings

app = FastAPI(title="RydeResolve backend")
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


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
