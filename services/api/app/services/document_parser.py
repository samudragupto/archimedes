"""Document parsing: PDF/URL → clean, chunked text for the agent nodes.

Pipeline: bytes or URL → per-page extraction (pypdf) or HTML→text →
``clean_text`` (dehyphenate, normalize whitespace) → ``chunk_text`` (greedy
paragraph packing at ~6k tokens with overlap).

WHY chunking with overlap: extract_requirements runs per chunk with a bounded
context window; a page-limit rule that happens to straddle a chunk boundary
must survive, so each chunk carries the tail of the previous one. Chunks are
the unit the NANO extractor sees — never the whole document.
"""

from __future__ import annotations

import io
import re
import unicodedata
from html.parser import HTMLParser

import httpx
from pypdf import PdfReader

from ..config import Settings, get_settings
from ..models.schemas import Chunk, ParsedDocument, estimate_tokens


class DocumentParseError(RuntimeError):
    """Raised when a source URL is unreachable or a document is unusable."""


# ---------------------------------------------------------------------------
# Pure text functions (unit-tested directly)
# ---------------------------------------------------------------------------
def clean_text(text: str) -> str:
    """Normalize extracted text: unicode NFC, CRLF→LF, dehyphenate words that
    PDF line-wraps split ('docu-\\nment' → 'document'), collapse whitespace.
    Content-faithful: never drops words, only repairs formatting."""
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    t = t.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n\n")  # \x0c = PDF form feed
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", t)  # dehyphenate line-broken words
    t = re.sub(r"[ \t]+", " ", t)  # collapse intra-line whitespace
    t = re.sub(r" ?\n ?", "\n", t)  # trim spaces around newlines
    t = re.sub(r"\n{3,}", "\n\n", t)  # collapse blank-line runs
    return t.strip()


def _split_long_paragraph(paragraph: str, target_chars: int) -> list[str]:
    """Split an oversized paragraph into ≤target_chars pieces, preferring
    sentence boundaries and falling back to word boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= target_chars or not current:
            current = f"{current} {sentence}".strip() if current else sentence
        else:
            pieces.append(current)
            current = sentence
        while len(current) > target_chars:  # pathological single sentence
            cut = current.rfind(" ", 0, target_chars)
            cut = cut if cut > 0 else target_chars
            pieces.append(current[:cut])
            current = current[cut:].lstrip()
    if current:
        pieces.append(current)
    return pieces


def chunk_text(
    text: str,
    target_tokens: int = 6000,
    overlap_tokens: int = 200,
) -> list[Chunk]:
    """Greedy paragraph packing into ≤~target_tokens chunks with overlap.

    Guarantees: chunks are content-faithful (no words dropped or reordered);
    each chunk stays at or marginally above the target (a single oversized
    paragraph is split, never truncated); consecutive chunks share an
    ≈overlap_tokens tail so boundary-straddling rules survive.
    """
    cleaned = clean_text(text)
    if not cleaned:
        return []

    target_chars = target_tokens * 4  # ~4 chars per token heuristic
    overlap_chars = overlap_tokens * 4

    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    pieces: list[str] = []
    for p in paragraphs:
        if len(p) <= target_chars:
            pieces.append(p)
        else:
            pieces.extend(_split_long_paragraph(p, target_chars))

    chunk_texts: list[str] = []
    current: list[str] = []
    size = 0
    for piece in pieces:
        if current and size + len(piece) + 2 > target_chars:
            chunk_texts.append("\n\n".join(current))
            # start the next chunk with an ≈overlap tail (word-aligned)
            tail = current[-1][-overlap_chars:] if overlap_chars else ""
            if tail:
                space = tail.find(" ")
                tail = tail[space + 1 :] if space != -1 else tail
                current = [tail]
                size = len(tail)
            else:
                current, size = [], 0
        current.append(piece)
        size += len(piece) + 2
    if current:
        chunk_texts.append("\n\n".join(current))

    return [
        Chunk(index=i, text=ct, token_estimate=estimate_tokens(ct))
        for i, ct in enumerate(chunk_texts)
    ]


# ---------------------------------------------------------------------------
# HTML → text (stdlib only — no bs4 dependency for one narrow job)
# ---------------------------------------------------------------------------
_BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "main",
    "aside",
    "nav",
    "ul",
    "ol",
    "li",
    "table",
    "tr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
    "pre",
    "figure",
    "figcaption",
    "br",
    "hr",
    "form",
    "dl",
    "dt",
    "dd",
}
_SKIP_TAGS = {"script", "style", "noscript", "template", "head", "svg", "iframe"}


class _HTMLToText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")
        elif tag in {"td", "th"}:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        return clean_text("".join(self._parts))


def html_to_text(html: str) -> str:
    parser = _HTMLToText()
    try:
        parser.feed(html)
    except Exception as e:  # malformed HTML must not kill a job
        raise DocumentParseError(f"failed to parse HTML: {e}") from e
    return parser.text()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def pdf_pages(data: bytes) -> list[str]:
    """Extract text per page. A single corrupt page yields '' rather than
    failing the whole parse — grant PDFs are often assembled from scans."""
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as e:
        raise DocumentParseError(f"unreadable PDF: {e}") from e
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages


# ---------------------------------------------------------------------------
# DocumentParser — the IO wrapper used by routers and agent nodes
# ---------------------------------------------------------------------------
class DocumentParser:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client

    async def parse_bytes(self, filename: str | None, data: bytes) -> ParsedDocument:
        """Parse an upload by sniffing extension and magic bytes."""
        name = (filename or "").lower()
        if name.endswith(".pdf") or data[:5] == b"%PDF-":
            pages = pdf_pages(data)
            parsed = ParsedDocument(text=clean_text("\n\n".join(pages)), page_count=len(pages))
        elif name.endswith((".html", ".htm")) or data[:1] == b"<":
            parsed = ParsedDocument(text=html_to_text(data.decode("utf-8", errors="replace")))
        else:  # .txt / .md / anything textual
            parsed = ParsedDocument(text=clean_text(data.decode("utf-8", errors="replace")))
        return self._finish(parsed, filename=filename)

    async def parse_url(self, url: str) -> ParsedDocument:
        """Fetch a solicitation URL (HTML page or direct PDF link)."""
        client = self._http()
        try:
            resp = await client.get(url)
        except httpx.HTTPError as e:
            raise DocumentParseError(f"could not fetch {url}: {e}") from e
        if resp.status_code >= 400:
            raise DocumentParseError(f"GET {url} returned HTTP {resp.status_code}")

        ctype = resp.headers.get("content-type", "").lower()
        path = url.split("?")[0].lower()
        if "application/pdf" in ctype or path.endswith(".pdf"):
            pages = pdf_pages(resp.content)
            parsed = ParsedDocument(
                text=clean_text("\n\n".join(pages)), page_count=len(pages), source_url=url
            )
        elif "html" in ctype:
            parsed = ParsedDocument(text=html_to_text(resp.text), source_url=url)
        else:  # text/plain, markdown, anything else readable
            parsed = ParsedDocument(text=clean_text(resp.text), source_url=url)
        return self._finish(parsed, filename=None)

    # -- internals ---------------------------------------------------------------
    def _finish(self, parsed: ParsedDocument, filename: str | None) -> ParsedDocument:
        parsed.filename = filename or parsed.filename
        parsed.chunks = chunk_text(
            parsed.text, self.settings.chunk_target_tokens, self.settings.chunk_overlap_tokens
        )
        return parsed

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=self.settings.tavily_timeout_seconds
                + 30,  # documents are bigger than search payloads
                headers={
                    # identified UA: some funders' sites block default client UAs
                    "User-Agent": "Archimedes/0.2 (grant-writing agent; +https://github.com/archimedes-grants/archimedes)"
                },
            )
        return self._client
