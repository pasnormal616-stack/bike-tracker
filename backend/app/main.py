from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.db import engine
from app.routers import (
    bikes,
    components,
    events,
    privacy,
    reminders,
    rides,
    service_history,
    setups,
    torque,
)

app = FastAPI(title="Bike Tracker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    # So the browser lets the frontend read the PDF download's file name.
    expose_headers=["Content-Disposition"],
)

app.include_router(bikes.router)
app.include_router(components.router)
app.include_router(rides.router)
app.include_router(events.router)
app.include_router(reminders.router)
app.include_router(service_history.router)
app.include_router(torque.router)
app.include_router(setups.router)
app.include_router(privacy.router)


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
