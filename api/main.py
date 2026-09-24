from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from analyze import AnalyzeError, CACHE_DIR, analyze

load_dotenv()

JOB_TTL_S = 60 * 60
JOB_DIR = Path(CACHE_DIR) / "jobs"
MEL_LAT = -37.8136
MEL_LON = 144.9631

_background: set[asyncio.Task[None]] = set()


class AnalyzeRequest(BaseModel):
    address: str = Field(min_length=3, max_length=200)
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    placeId: str | None = Field(default=None, max_length=200)


def _job_path(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.json"


def _read_job(job_id: str) -> dict | None:
    path = _job_path(job_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _write_job(job_id: str, job: dict) -> None:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _job_path(job_id).with_suffix(".tmp")
    tmp.write_text(json.dumps(job))
    tmp.replace(_job_path(job_id))


def _purge() -> None:
    now = time.time()
    if not JOB_DIR.exists():
        return
    for path in JOB_DIR.glob("*.json"):
        try:
            job = json.loads(path.read_text())
        except json.JSONDecodeError:
            path.unlink(missing_ok=True)
            continue
        if now - job.get("ts", now) > JOB_TTL_S:
            path.unlink(missing_ok=True)


def _close_interrupted() -> None:
    if not JOB_DIR.exists():
        return
    for path in JOB_DIR.glob("*.json"):
        try:
            job = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if job.get("status") in {"queued", "running"}:
            job = {
                "status": "error",
                "error": "The server restarted during the lookup. Check the sun again.",
                "ts": time.time(),
            }
            path.write_text(json.dumps(job))


def _places(query: str) -> list[dict]:
    key = os.environ.get("GOOGLE_KEY")
    if not key:
        return []
    body = json.dumps(
        {
            "input": query,
            "includedRegionCodes": ["au"],
            "locationBias": {
                "circle": {
                    "center": {"latitude": MEL_LAT, "longitude": MEL_LON},
                    "radius": 50000.0,
                }
            },
        }
    ).encode()
    req = urllib.request.Request(
        "https://places.googleapis.com/v1/places:autocomplete",
        data=body,
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return []
    out = []
    for item in data.get("suggestions", [])[:6]:
        pred = item.get("placePrediction") or {}
        fmt = pred.get("structuredFormat") or {}
        name = ((fmt.get("mainText") or {}).get("text") or "").strip()
        detail = ((fmt.get("secondaryText") or {}).get("text") or "").strip()
        address = ((pred.get("text") or {}).get("text") or "").strip()
        place_id = (pred.get("placeId") or "").strip()
        if address:
            out.append(
                {
                    "name": name or address,
                    "detail": detail,
                    "address": address,
                    "placeId": place_id or None,
                }
            )
    return out


_close_interrupted()
app = FastAPI(title="Schooner Weather")
origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True, "name": "schooner-weather"}


@app.get("/places")
async def places(q: str):
    query = q.strip()
    if len(query) < 2:
        return {"suggestions": []}
    suggestions = await asyncio.to_thread(_places, query)
    return {"suggestions": suggestions}


@app.post("/analyze")
async def start_analyze(body: AnalyzeRequest):
    _purge()
    job_id = uuid.uuid4().hex[:12]
    _write_job(job_id, {"status": "queued", "message": "Lining up a schooner…", "ts": time.time()})
    task = asyncio.create_task(_run(job_id, body.address.strip(), body.date, body.placeId))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return {"jobId": job_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = _read_job(job_id)
    if not job:
        raise HTTPException(404, "The server restarted. Check the sun again.")
    return {k: v for k, v in job.items() if k != "ts"}


async def _run(job_id: str, address: str, date: str | None, place_id: str | None = None) -> None:
    def progress(msg: str) -> None:
        job = _read_job(job_id) or {}
        job.update({"status": "running", "message": msg, "ts": time.time()})
        _write_job(job_id, job)

    _write_job(job_id, {"status": "running", "message": "Finding the optimal beer-drinking hour…", "ts": time.time()})
    try:
        result = await asyncio.to_thread(analyze, address, date, place_id=place_id, progress=progress)
        _write_job(job_id, {"status": "done", "result": result, "ts": time.time()})
    except AnalyzeError as e:
        _write_job(job_id, {"status": "error", "error": str(e), "ts": time.time()})
    except Exception as e:
        _write_job(job_id, {"status": "error", "error": f"Lookup failed: {e}", "ts": time.time()})
