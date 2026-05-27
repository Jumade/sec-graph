from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from core.deps import Neo4jDep, OpenAIDep, QdrantDep
from rag.graphrag import GraphRAGAnswer, answer_question

router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    company_filter: Optional[str] = None


class CitationOut(BaseModel):
    filing_id: Optional[str]
    ticker: Optional[str]
    filed_date: Optional[str]
    form_type: Optional[str]
    score: Optional[float]


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    graph_context: str
    entities: list[str]
    graph_subgraph: dict[str, Any]


@router.post("", response_model=QueryResponse)
async def query(
    req: QueryRequest,
    openai_client: OpenAIDep,
    qdrant: QdrantDep,
    neo4j: Neo4jDep,
):
    result = await answer_question(
        question=req.question,
        openai_client=openai_client,
        qdrant=qdrant,
        neo4j=neo4j,
        company_filter=req.company_filter,
    )
    return QueryResponse(
        answer=result.answer,
        citations=[CitationOut(**c) for c in result.citations],
        graph_context=result.graph_context,
        entities=result.entities,
        graph_subgraph=result.graph_subgraph,
    )
