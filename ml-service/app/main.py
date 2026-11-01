"""Phase 1 API. No trained model or signal-control endpoints exist yet."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

SEED = 57


class HealthResponse(BaseModel):
    status: str
    service: str
    seed: int
    data_mode: str
    controller: str
    syllabus: str


app = FastAPI(title="Raah ML Service", version="0.1.0")
origins = [
    origin.strip()
    for origin in os.getenv(
        "RAAH_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness only: does not imply model or controller readiness."""
    return HealthResponse(
        status="ok",
        service="raah-ml-service",
        seed=SEED,
        data_mode="synthetic-only",
        controller="not-implemented",
        syllabus="UNVERIFIED",
    )
