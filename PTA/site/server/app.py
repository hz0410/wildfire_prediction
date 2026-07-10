"""Serve the static site and grounded reports from the local Qwen3-14B model."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .qwen import QwenReporter
from .web_tools import collect_fire_context

ROOT = Path(__file__).resolve().parents[2]
SITE_DIR = ROOT / "site"
MODEL_DIR = Path(os.getenv("QWEN_MODEL_PATH", ROOT / "Models" / "Qwen3-14B"))
ADAPTER_DIR = os.getenv("QWEN_ADAPTER_PATH")

class Prediction(BaseModel):
    data_type: str
    probability: float | None = Field(default=None, ge=0, le=1)
    risk_band: str
    predicted_scale: str | None = None
    model_auc: float | None = None
    limitations: list[str] = []

class ReportRequest(BaseModel):
    question: str = Field(default="Summarize the wildfire risk for this place and date.", max_length=1500)
    address: str = Field(max_length=500)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    date: str
    nearby_causes: list[str] = []
    prediction: Prediction

app = FastAPI(title="PTA Qwen Wildfire Reporter", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
reporter = QwenReporter(MODEL_DIR, Path(ADAPTER_DIR) if ADAPTER_DIR else None)

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "model": "Qwen3-14B", "model_path_exists": MODEL_DIR.exists(), "model_loaded": reporter.loaded, "adapter": ADAPTER_DIR}

@app.post("/api/report")
def report(req: ReportRequest) -> dict[str, Any]:
    try:
        web_context = collect_fire_context(req.latitude, req.longitude, req.date)
        evidence = {"user_question": req.question, "location": {"address": req.address, "latitude": req.latitude, "longitude": req.longitude}, "date": req.date, "statistical_prediction": req.prediction.model_dump(), "nearby_historical_causes": req.nearby_causes, "live_and_historical_web_tools": web_context}
        return {"report": reporter.generate(evidence), "sources": web_context["sources"], "model": "Qwen3-14B"}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}") from exc

app.mount("/", StaticFiles(directory=SITE_DIR, html=True), name="site")
