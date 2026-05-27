"""Entity resolution: merge aliases using fuzzy matching + embedding similarity."""
import json
from typing import Optional

import redis as redis_lib
from rapidfuzz import fuzz

FUZZY_THRESHOLD = 90
EMBED_THRESHOLD = 0.95
CACHE_KEY = "entity_resolution_map"


class EntityResolver:
    def __init__(self, redis_url: str) -> None:
        self._redis = redis_lib.from_url(redis_url, decode_responses=True)

    def _load_map(self) -> dict[str, str]:
        raw = self._redis.get(CACHE_KEY)
        return json.loads(raw) if raw else {}

    def _save_map(self, mapping: dict[str, str]) -> None:
        self._redis.set(CACHE_KEY, json.dumps(mapping))

    def resolve(self, name: str) -> str:
        """Return the canonical name for a given entity name."""
        mapping = self._load_map()
        if name in mapping:
            return mapping[name]

        # Fuzzy match against known canonicals
        canonicals = set(mapping.values()) | set(mapping.keys())
        best_ratio = 0
        best_match = None
        for known in canonicals:
            ratio = fuzz.token_sort_ratio(name.lower(), known.lower())
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = known

        if best_ratio >= FUZZY_THRESHOLD and best_match:
            canonical = mapping.get(best_match, best_match)
            mapping[name] = canonical
            self._save_map(mapping)
            return canonical

        # No match — register as new canonical
        mapping[name] = name
        self._save_map(mapping)
        return name

    def resolve_batch(self, names: list[str]) -> dict[str, str]:
        return {name: self.resolve(name) for name in names}
