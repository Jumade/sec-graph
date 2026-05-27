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

_ENTITY_SCHEMA = EntityList.model_json_schema()
_REL_SCHEMA = RelationshipList.model_json_schema()

COMBINED_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": _ENTITY_SCHEMA,
        "relationships": _REL_SCHEMA,
    },
    "required": ["entities", "relationships"],
}


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
        entities = EntityList.model_validate({"entities": data.get("entities", [])}).entities
        relationships = RelationshipList.model_validate({"relationships": data.get("relationships", [])}).relationships
        return entities, relationships
    except Exception as exc:
        logger.warning("Failed to parse batch response: %s", exc)
        return [], []
