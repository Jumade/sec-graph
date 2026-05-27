"""Celery task chain: download → parse → chunk → extract → resolve → index."""
import asyncio
import json
import logging
from typing import Any

import redis as redis_lib
from celery.exceptions import MaxRetriesExceededError
from openai import AsyncOpenAI

from core.config import get_settings
from extraction.batch_extractor import build_batch_request, parse_batch_response
from extraction.entity_extractor import extract_entities
from extraction.entity_resolution import EntityResolver
from extraction.relationship_extractor import extract_relationships
from graph.neo4j_client import Neo4jClient
from graph.traversal import upsert_entity, upsert_relationship
from ingestion.chunker import chunk_document, Chunk
from ingestion.document_parser import parse_filing
from ingestion.sec_edgar import download_filing
from tasks.celery_app import celery_app
from vector_store.embeddings import embed_texts
from vector_store.qdrant_client import QdrantStore

logger = logging.getLogger(__name__)


def _settings():
    return get_settings()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _status_key(job_id: str) -> str:
    return f"job:{job_id}:status"


def _set_status(r: redis_lib.Redis, job_id: str, stage: str, detail: str = "") -> None:
    r.set(_status_key(job_id), json.dumps({"stage": stage, "detail": detail}), ex=86400)


@celery_app.task(bind=True, name="pipeline.ingest_filing")
def ingest_filing(
    self,
    job_id: str,
    url: str,
    filing_meta: dict,
    max_chunks: int | None = None,
    extraction_model: str | None = None,
) -> dict:
    settings = _settings()
    r = redis_lib.from_url(settings.redis_url, decode_responses=True)

    _set_status(r, job_id, "downloading")
    logger.info(f"[{job_id}] task={self.request.id} Downloading {url}")
    raw = _run(download_filing(url))

    _set_status(r, job_id, "parsing")
    text = parse_filing(raw, url)
    logger.info(f"[{job_id}] Parsed {len(text)} chars")

    _set_status(r, job_id, "chunking")
    all_chunks = chunk_document(
        text,
        filing_id=filing_meta["filing_id"],
        ticker=filing_meta["ticker"],
        form_type=filing_meta["form_type"],
        filed_date=filing_meta["filed_date"],
    )
    chunks = all_chunks[:max_chunks] if max_chunks else all_chunks
    logger.info(f"[{job_id}] {len(chunks)}/{len(all_chunks)} chunks (max_chunks={max_chunks})")

    model = extraction_model or settings.openai_extraction_model
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    neo4j = Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    qdrant = QdrantStore(settings.qdrant_host, settings.qdrant_port, settings.qdrant_collection)
    resolver = EntityResolver(settings.redis_url)

    try:
        all_entities: list[dict] = []
        all_relationships: list[dict] = []
        extraction_errors = 0

        for i, chunk in enumerate(chunks):
            _set_status(r, job_id, "extracting", f"chunk {i+1}/{len(chunks)}")
            try:
                entities = _run(extract_entities(openai_client, chunk.text, model=model))
                relationships = _run(extract_relationships(openai_client, chunk.text, entities, model=model))
            except Exception as e:
                extraction_errors += 1
                logger.warning(f"[{job_id}] Extraction error chunk {i} (model={model}): {e}")
                if extraction_errors == 1:
                    _set_status(r, job_id, "extracting", f"chunk {i+1}/{len(chunks)} — extraction errors: {extraction_errors} (check model name)")
                continue

            for ent in entities:
                canonical = resolver.resolve(ent.name)
                all_entities.append({"name": canonical, "type": ent.type.value})
                upsert_entity(neo4j, canonical, ent.type.value, {
                    "source_filing": filing_meta["filing_id"],
                    "ticker": filing_meta["ticker"],
                })

            for rel in relationships:
                head = resolver.resolve(rel.head)
                tail = resolver.resolve(rel.tail)
                all_relationships.append({"head": head, "rel": rel.rel.value, "tail": tail})
                upsert_relationship(
                    neo4j,
                    head=head, head_label=rel.head_type,
                    rel_type=rel.rel.value,
                    tail=tail, tail_label=rel.tail_type,
                    props={
                        "confidence": rel.confidence,
                        "source_filing": filing_meta["filing_id"],
                        "evidence": rel.evidence[:200],
                        "date": filing_meta["filed_date"],
                    },
                )

        _set_status(r, job_id, "embedding")
        chunk_dicts = [
            {
                "chunk_id": c.chunk_id,
                "filing_id": c.filing_id,
                "ticker": c.ticker,
                "form_type": c.form_type,
                "filed_date": c.filed_date,
                "chunk_index": c.chunk_index,
                "text": c.text,
            }
            for c in chunks
        ]
        texts = [c["text"] for c in chunk_dicts]
        embeddings = _run(embed_texts(openai_client, texts, settings.openai_embedding_model))
        _run(qdrant.ensure_collection())
        _run(qdrant.upsert_chunks(chunk_dicts, embeddings))

        error_note = f", {extraction_errors} extraction errors (model={model})" if extraction_errors else ""
        _set_status(r, job_id, "complete", f"{len(chunks)} chunks, {len(all_entities)} entities, {len(all_relationships)} relationships{error_note}")

    except Exception as exc:
        _set_status(r, job_id, "error", str(exc)[:300])
        raise

    finally:
        neo4j.close()

    return {
        "job_id": job_id,
        "chunks": len(chunks),
        "entities": len(all_entities),
        "relationships": len(all_relationships),
    }


# ── Batch API pipeline ────────────────────────────────────────────────────────

def _build_chunk_dicts(chunks: list[Chunk]) -> list[dict]:
    return [
        {
            "chunk_id": c.chunk_id,
            "filing_id": c.filing_id,
            "ticker": c.ticker,
            "form_type": c.form_type,
            "filed_date": c.filed_date,
            "chunk_index": c.chunk_index,
            "text": c.text,
        }
        for c in chunks
    ]


def _write_extraction_results(
    entities_list,
    relationships_list,
    filing_meta: dict,
    neo4j: Neo4jClient,
    resolver: EntityResolver,
) -> tuple[list[dict], list[dict]]:
    all_entities: list[dict] = []
    all_relationships: list[dict] = []

    for ent in entities_list:
        canonical = resolver.resolve(ent.name)
        all_entities.append({"name": canonical, "type": ent.type.value})
        upsert_entity(neo4j, canonical, ent.type.value, {
            "source_filing": filing_meta["filing_id"],
            "ticker": filing_meta["ticker"],
        })

    for rel in relationships_list:
        head = resolver.resolve(rel.head)
        tail = resolver.resolve(rel.tail)
        all_relationships.append({"head": head, "rel": rel.rel.value, "tail": tail})
        upsert_relationship(
            neo4j,
            head=head, head_label=rel.head_type.value,
            rel_type=rel.rel.value,
            tail=tail, tail_label=rel.tail_type.value,
            props={
                "confidence": rel.confidence,
                "source_filing": filing_meta["filing_id"],
                "evidence": rel.evidence[:200],
                "date": filing_meta["filed_date"],
            },
        )

    return all_entities, all_relationships


@celery_app.task(bind=True, name="pipeline.ingest_filing_submit_batch")
def ingest_filing_submit_batch(
    self,
    job_id: str,
    url: str,
    filing_meta: dict,
    max_chunks: int | None = None,
    extraction_model: str | None = None,
) -> dict:
    settings = _settings()
    r = redis_lib.from_url(settings.redis_url, decode_responses=True)

    try:
        _set_status(r, job_id, "downloading")
        logger.info(f"[{job_id}] task={self.request.id} Batch submit — downloading {url}")
        raw = _run(download_filing(url))

        _set_status(r, job_id, "parsing")
        text = parse_filing(raw, url)

        _set_status(r, job_id, "chunking")
        all_chunks = chunk_document(
            text,
            filing_id=filing_meta["filing_id"],
            ticker=filing_meta["ticker"],
            form_type=filing_meta["form_type"],
            filed_date=filing_meta["filed_date"],
        )
        chunks = all_chunks[:max_chunks] if max_chunks else all_chunks
        model = extraction_model or settings.openai_extraction_model

        _set_status(r, job_id, "submitting_batch", f"building {len(chunks)} requests")
        jsonl = "\n".join(
            json.dumps(build_batch_request(c.chunk_id, c.text, model))
            for c in chunks
        )

        openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

        file_obj = _run(openai_client.files.create(
            file=("batch.jsonl", jsonl.encode(), "application/jsonl"),
            purpose="batch",
        ))
        batch = _run(openai_client.batches.create(
            input_file_id=file_obj.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
        ))
        logger.info(f"[{job_id}] Batch submitted: {batch.id}")

        filing_id = filing_meta["filing_id"]
        # Per-filing key so multiple filings in the same job don't overwrite each other
        r.set(f"job:{job_id}:batch_ctx:{filing_id}", json.dumps({
            "batch_id": batch.id,
            "url": url,
            "filing_meta": filing_meta,
            "model": model,
            "max_chunks": max_chunks,
            "total_chunks": len(chunks),
        }), ex=90000)

        _set_status(r, job_id, "waiting_for_batch",
                    f"{len(chunks)} chunks submitted (batch {batch.id[:12]}…) — results in up to 24h")

        # Schedule finalize to start checking in 5 minutes
        ingest_filing_finalize_batch.apply_async(args=[job_id, filing_id], countdown=300)

    except Exception as exc:
        _set_status(r, job_id, "error", str(exc)[:300])
        raise

    return {"job_id": job_id, "batch_id": batch.id}


def _filing_done(r: redis_lib.Redis, job_id: str, *, error: bool, detail: str = "", stats: dict | None = None) -> None:
    """Increment per-job completion counters and set final status when every filing is done."""
    if error:
        r.incr(f"job:{job_id}:errors")
    done  = r.incr(f"job:{job_id}:done")
    total = int(r.get(f"job:{job_id}:total") or done)   # fall back to done if key missing
    errors = int(r.get(f"job:{job_id}:errors") or 0)

    if done >= total:
        if errors:
            _set_status(r, job_id, "error",
                        f"{errors}/{total} filing(s) failed — last error: {detail}" if detail
                        else f"{errors}/{total} filing(s) failed")
        else:
            s = stats or {}
            _set_status(r, job_id, "complete",
                        f"{s.get('chunks',0)} chunks, {s.get('entities',0)} entities, "
                        f"{s.get('relationships',0)} relationships (via batch)")
    elif error:
        # Partial failure: surface it immediately so the user isn't left waiting
        _set_status(r, job_id, "error", detail or "A filing batch failed")


@celery_app.task(bind=True, name="pipeline.ingest_filing_finalize_batch", max_retries=288)
def ingest_filing_finalize_batch(self, job_id: str, filing_id: str | None = None) -> dict:
    """filing_id may be None for tasks queued before the per-filing key fix (backward compat)."""
    settings = _settings()
    r = redis_lib.from_url(settings.redis_url, decode_responses=True)

    ctx_key = f"job:{job_id}:batch_ctx:{filing_id}" if filing_id else f"job:{job_id}:batch_ctx"
    ctx_raw = r.get(ctx_key)
    if not ctx_raw:
        _filing_done(r, job_id, error=True, detail="Batch context expired before results arrived")
        return {}

    ctx = json.loads(ctx_raw)
    batch_id = ctx["batch_id"]
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    batch = _run(openai_client.batches.retrieve(batch_id))
    logger.info(f"[{job_id}] filing={filing_id} batch={batch_id} status={batch.status}")

    if batch.status in ("validating", "in_progress", "finalizing"):
        counts = batch.request_counts
        detail = (
            f"OpenAI processing: {counts.completed}/{counts.total} done"
            if counts else "waiting for batch"
        )
        # Only overwrite status if the job hasn't already been marked error by another filing
        current_raw = r.get(_status_key(job_id))
        if not current_raw or json.loads(current_raw).get("stage") != "error":
            _set_status(r, job_id, "waiting_for_batch", detail)
        try:
            self.retry(countdown=300)
        except MaxRetriesExceededError:
            _filing_done(r, job_id, error=True, detail="Batch did not complete within 24h")
        return {}

    if batch.status in ("failed", "expired", "cancelled", "cancelling"):
        _filing_done(r, job_id, error=True, detail=f"Batch {batch.status}: {batch_id}")
        return {}

    # ── completed ─────────────────────────────────────────────────────────────
    _set_status(r, job_id, "processing_results", f"downloading results for {filing_id or 'filing'}")

    output = _run(openai_client.files.content(batch.output_file_id))
    lines = [json.loads(l) for l in output.content.decode().strip().splitlines() if l.strip()]
    result_map = {line["custom_id"]: line for line in lines}

    # Re-chunk deterministically (same filing_id → same chunk_ids)
    filing_meta = ctx["filing_meta"]
    max_chunks = ctx.get("max_chunks")
    raw = _run(download_filing(ctx["url"]))
    text = parse_filing(raw, ctx["url"])
    all_chunks = chunk_document(
        text,
        filing_id=filing_meta["filing_id"],
        ticker=filing_meta["ticker"],
        form_type=filing_meta["form_type"],
        filed_date=filing_meta["filed_date"],
    )
    chunks = all_chunks[:max_chunks] if max_chunks else all_chunks

    neo4j = Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    qdrant = QdrantStore(settings.qdrant_host, settings.qdrant_port, settings.qdrant_collection)
    resolver = EntityResolver(settings.redis_url)

    try:
        all_entities: list[dict] = []
        all_relationships: list[dict] = []

        for chunk in chunks:
            result_line = result_map.get(chunk.chunk_id)
            if not result_line:
                continue
            entities, relationships = parse_batch_response(result_line)
            ents, rels = _write_extraction_results(entities, relationships, filing_meta, neo4j, resolver)
            all_entities.extend(ents)
            all_relationships.extend(rels)

        _set_status(r, job_id, "embedding")
        chunk_dicts = _build_chunk_dicts(chunks)
        texts = [c["text"] for c in chunk_dicts]
        embeddings = _run(embed_texts(openai_client, texts, settings.openai_embedding_model))
        _run(qdrant.ensure_collection())
        _run(qdrant.upsert_chunks(chunk_dicts, embeddings))

        _filing_done(r, job_id, error=False, stats={
            "chunks": len(chunks),
            "entities": len(all_entities),
            "relationships": len(all_relationships),
        })

    except Exception as exc:
        _filing_done(r, job_id, error=True, detail=str(exc)[:280])
        raise

    finally:
        neo4j.close()

    return {"job_id": job_id, "chunks": len(chunks), "entities": len(all_entities), "relationships": len(all_relationships)}
