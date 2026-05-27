"""Combined entity + relationship extraction request builder for OpenAI Batch API.

The Batch API does not support beta.chat.completions.parse, so we use raw
response_format JSON schema and validate results manually with Pydantic.
One request per chunk extracts both entities and relationships in a single call,
halving the total number of API requests vs the real-time pipeline.
"""
import json
import logging

from extraction.entity_extractor import Entity, EntityList
from extraction.relationship_extractor import Relationship, RelationshipList

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial knowledge graph expert.
From the provided SEC filing excerpt extract in one pass:
1. Named entities — types: Company, Person, Product, Risk, Industry, Location, Regulation
2. Relationships between those entities — types: INVESTED_IN, SUPPLIES_TO, ACQUIRED,
   COMPETES_WITH, EXPOSED_TO_RISK, MANUFACTURES, PARTNERS_WITH, SUED_BY, EMPLOYS,
   REGULATES, DEPENDS_ON

Only include information explicitly stated in the text.
Confidence (0.0–1.0) should reflect strength of textual evidence."""

def _build_combined_schema() -> dict:
    """Build a flat combined schema with merged $defs.

    EntityList/RelationshipList model_json_schema() each produce a wrapper
    object schema ({"type": "object", "properties": {"entities": [...]}, ...}).
    Embedding those directly as property values causes the LLM to generate a
    doubly-nested response.  Instead we pull out the $defs and declare
    `entities` / `relationships` as plain arrays whose items $ref the
    underlying models.
    """
    entity_schema = EntityList.model_json_schema()
    rel_schema = RelationshipList.model_json_schema()
    defs: dict = {}
    defs.update(entity_schema.get("$defs", {}))
    defs.update(rel_schema.get("$defs", {}))
    schema: dict = {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {"$ref": "#/$defs/Entity"},
            },
            "relationships": {
                "type": "array",
                "items": {"$ref": "#/$defs/Relationship"},
            },
        },
        "required": ["entities", "relationships"],
    }
    if defs:
        schema["$defs"] = defs
    return schema


COMBINED_SCHEMA = _build_combined_schema()


def build_batch_request(chunk_id: str, text: str, model: str) -> dict:
    return {
        "custom_id": chunk_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract from:\n\n{text[:4000]}"},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "CombinedExtractionResult",
                    "schema": COMBINED_SCHEMA,
                    "strict": False,
                },
            },
            "temperature": 0,
        },
    }


def parse_batch_response(result_line: dict) -> tuple[list[Entity], list[Relationship]]:
    try:
        error = result_line.get("error")
        if error:
            logger.warning("Batch item error: %s", error)
            return [], []
        content = result_line["response"]["body"]["choices"][0]["message"]["content"]
        data = json.loads(content)

        # Defensive unwrapping: old schema bug caused the LLM to produce
        # {"entities": {"entities": [...]}} instead of {"entities": [...]}.
        raw_entities = data.get("entities", [])
        if isinstance(raw_entities, dict):
            raw_entities = raw_entities.get("entities", [])

        raw_rels = data.get("relationships", [])
        if isinstance(raw_rels, dict):
            raw_rels = raw_rels.get("relationships", [])

        entities = EntityList.model_validate({"entities": raw_entities}).entities
        relationships = RelationshipList.model_validate({"relationships": raw_rels}).relationships
        return entities, relationships
    except Exception as exc:
        logger.warning("Failed to parse batch response: %s", exc)
        return [], []
