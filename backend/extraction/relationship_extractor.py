"""Extract relationships between entities using GPT structured output."""
from enum import Enum

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from core.config import get_settings
from extraction.entity_extractor import Entity, EntityType


class RelType(str, Enum):
    INVESTED_IN = "INVESTED_IN"
    SUPPLIES_TO = "SUPPLIES_TO"
    ACQUIRED = "ACQUIRED"
    COMPETES_WITH = "COMPETES_WITH"
    EXPOSED_TO_RISK = "EXPOSED_TO_RISK"
    MANUFACTURES = "MANUFACTURES"
    PARTNERS_WITH = "PARTNERS_WITH"
    SUED_BY = "SUED_BY"
    EMPLOYS = "EMPLOYS"
    REGULATES = "REGULATES"
    DEPENDS_ON = "DEPENDS_ON"


class Relationship(BaseModel):
    head: str
    head_type: EntityType
    rel: RelType
    tail: str
    tail_type: EntityType
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str


class RelationshipList(BaseModel):
    relationships: list[Relationship]


SYSTEM_PROMPT = """You are a financial knowledge graph expert.
Given a list of entities and a text excerpt, extract relationships between them.
Only extract relationships explicitly supported by the text.
Confidence should reflect textual evidence strength (0.0–1.0)."""


async def extract_relationships(
    client: AsyncOpenAI,
    text: str,
    entities: list[Entity],
    model: str | None = None,
) -> list[Relationship]:
    if not entities:
        return []

    entity_list = "\n".join(f"- {e.name} ({e.type.value})" for e in entities)
    settings = get_settings()

    response = await client.beta.chat.completions.parse(
        model=model or settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Entities:\n{entity_list}\n\n"
                f"Text:\n{text[:4000]}\n\n"
                "Extract relationships between these entities."
            )},
        ],
        response_format=RelationshipList,
        temperature=0,
    )
    return response.choices[0].message.parsed.relationships
