import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.deps import close_clients, init_clients
from graph.schema import init_schema
from vector_store.qdrant_client import QdrantStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    logger.info("Initializing clients...")
    init_clients(settings)

    logger.info("Initializing Neo4j schema...")
    from core.deps import get_neo4j
    init_schema(get_neo4j())

    logger.info("Initializing Qdrant collection...")
    from core.deps import get_qdrant
    await get_qdrant().ensure_collection()

    logger.info("Startup complete.")
    yield

    logger.info("Shutting down...")
    close_clients()


app = FastAPI(
    title="SEC Graph API",
    description="Financial intelligence graph platform",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"http://localhost(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.routes import ingest, query, graph  # noqa: E402
app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
app.include_router(query.router, prefix="/query", tags=["query"])
app.include_router(graph.router, prefix="/graph", tags=["graph"])


@app.get("/health")
async def health():
    return {"status": "ok"}
