from fastapi import FastAPI

app = FastAPI(title="RydeResolve backend")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
