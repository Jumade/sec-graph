"""Parse raw HTML or PDF filings into clean plain text."""
import io
import re

from bs4 import BeautifulSoup


def parse_html(raw: str) -> str:
    soup = BeautifulSoup(raw, "lxml")

    for tag in soup(["script", "style", "header", "footer", "nav"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def parse_pdf(raw_bytes: bytes) -> str:
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def parse_filing(raw: str | bytes, url: str = "") -> str:
    if isinstance(raw, bytes):
        return parse_pdf(raw)
    if url.lower().endswith(".pdf"):
        return parse_pdf(raw.encode())
    return parse_html(raw)
