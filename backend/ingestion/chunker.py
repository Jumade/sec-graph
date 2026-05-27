"""Split documents into overlapping chunks with source metadata."""
from dataclasses import dataclass

from langchain.text_splitter import RecursiveCharacterTextSplitter

CHUNK_SIZE = 1800   # ~512 tokens at ~3.5 chars/token
CHUNK_OVERLAP = 200


@dataclass
class Chunk:
    chunk_id: str
    filing_id: str
    ticker: str
    form_type: str
    filed_date: str
    chunk_index: int
    text: str


def chunk_document(text: str, filing_id: str, ticker: str, form_type: str, filed_date: str) -> list[Chunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    pieces = splitter.split_text(text)
    return [
        Chunk(
            chunk_id=f"{filing_id}_{i}",
            filing_id=filing_id,
            ticker=ticker,
            form_type=form_type,
            filed_date=filed_date,
            chunk_index=i,
            text=piece,
        )
        for i, piece in enumerate(pieces)
    ]
