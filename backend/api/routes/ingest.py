import json
import uuid
from typing import Literal

import redis as redis_lib
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import get_settings
from ingestion.sec_edgar import search_filings
from tasks.celery_app import celery_app
from tasks.pipeline import ingest_filing, ingest_filing_submit_batch

router = APIRouter()


class IngestRequest(BaseModel):
    ticker: str
    form_type: Literal["10-K", "10-Q", "8-K"] = "10-K"
    years: list[int]
    max_chunks: int | None = None
    extraction_model: str | None = None
    use_batch: bool = False


class IngestResponse(BaseModel):
    job_id: str
    filings_queued: int
    message: str


class StatusResponse(BaseModel):
    job_id: str
    stage: str
    detail: str


@router.post("", response_model=IngestResponse)
async def start_ingest(req: IngestRequest):
    filings = await search_filings(req.ticker, req.form_type, req.years)
    if not filings:
        raise HTTPException(404, f"No {req.form_type} filings found for {req.ticker} in years {req.years}")

    job_id = str(uuid.uuid4())
    settings = get_settings()
    r = redis_lib.from_url(settings.redis_url, decode_responses=True)

    # Write initial status immediately so the first frontend poll doesn't get a 404
    # (without this, the job would be marked "stale" before the worker even starts)
    r.set(f"job:{job_id}:status", json.dumps({"stage": "queued", "detail": ""}), ex=86400)

    # Store total filing count so finalize tasks know when all filings are done
    r.set(f"job:{job_id}:total", len(filings), ex=90000)

    task_fn = ingest_filing_submit_batch if req.use_batch else ingest_filing
    task_ids = []
    for filing in filings:
        result = task_fn.delay(
            job_id=job_id,
            url=filing.document_url,
            max_chunks=req.max_chunks,
            extraction_model=req.extraction_model,
            filing_meta={
                "filing_id": filing.filing_id,
                "ticker": filing.ticker,
                "cik": filing.cik,
                "form_type": filing.form_type,
                "filed_date": filing.filed_date,
                "title": filing.title,
            },
        )
        task_ids.append(result.id)

    # Store task IDs so the cancel endpoint can revoke them
    r.set(f"job:{job_id}:tasks", json.dumps(task_ids), ex=86400)

    mode = "batch (results in up to 24h)" if req.use_batch else "real-time"
    return IngestResponse(
        job_id=job_id,
        filings_queued=len(filings),
        message=f"Queued {len(filings)} filing(s) for {req.ticker.upper()} [{mode}]",
    )


@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    settings = get_settings()
    r = redis_lib.from_url(settings.redis_url, decode_responses=True)
    raw = r.get(f"job:{job_id}:status")
    if not raw:
        raise HTTPException(404, "Job not found or expired")
    data = json.loads(raw)
    return StatusResponse(job_id=job_id, stage=data["stage"], detail=data.get("detail", ""))


@router.delete("/{job_id}")
async def cancel_job(job_id: str):
    settings = get_settings()
    r = redis_lib.from_url(settings.redis_url, decode_responses=True)
    if not r.get(f"job:{job_id}:status"):
        raise HTTPException(404, "Job not found or expired")

    r.set(
        f"job:{job_id}:status",
        json.dumps({"stage": "cancelled", "detail": "Cancelled by user"}),
        ex=86400,
    )

    task_ids_raw = r.get(f"job:{job_id}:tasks")
    if task_ids_raw:
        for task_id in json.loads(task_ids_raw):
            celery_app.control.revoke(task_id, terminate=False)

    return {"cancelled": True}
