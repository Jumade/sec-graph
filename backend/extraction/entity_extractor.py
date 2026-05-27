"""Extract named entities from filing chunks using GPT structured output."""
from enum import Enum
from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from core.config import get_settings


class EntityType(str, Enum):
    Company = "Company"
    Person = "Person"
    Product = "Product"
    Risk = "Risk"
    Industry = "Industry"
    Location = "Location"
    Regulation = "Regulation"


class Entity(BaseModel):
    name: str
    type: EntityType
    context: str


class EntityList(BaseModel):
    entities: list[Entity]


SYSTEM_PROMPT = """You are a financial information extraction expert.
Extract all named entities from the provided text.
For each entity, provide its canonical name, type, and a brief context snippet.
Entity types: Company, Person, Product, Risk, Industry, Location, Regulation.
Be precise — only extract entities explicitly mentioned."""


async def extract_entities(client: AsyncOpenAI, text: str, model: str | None = None) -> list[Entity]:
    settings = get_settings()
    response = await client.beta.chat.completions.parse(
        model=model or settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract entities from:\n\n{text[:4000]}"},
        ],
        response_format=EntityList,
        temperature=0,
    )
    return response.choices[0].message.parsed.entities
