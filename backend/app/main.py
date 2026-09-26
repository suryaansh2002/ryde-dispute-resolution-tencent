from fastapi import FastAPI

from app.api import cases, decisions, events, evidence, l2

app = FastAPI(title="RydeResolve backend")

# Routers split by owner (roadmap v3, §0): Dev A owns cases/evidence, Dev B owns
# decisions/l2/events. Keeps both devs from ever editing the same routes file.
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(decisions.router)
app.include_router(l2.router)
app.include_router(events.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
