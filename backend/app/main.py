from fastapi import FastAPI
from sqlalchemy import text

from app.db import engine
from app.routers import bikes, components, rides

app = FastAPI(title="Bike Tracker")

app.include_router(bikes.router)
app.include_router(components.router)
app.include_router(rides.router)


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
