"""Unit tests for document parsing: text cleaning, chunking, PDF extraction
(via a generated in-test PDF), HTML→text, and URL fetching via httpx mocks."""

from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.services.document_parser import (
    DocumentParseError,
    DocumentParser,
    chunk_text,
    clean_text,
    html_to_text,
)
from tests.helpers import build_minimal_pdf


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------
def test_clean_text_dehyphenates_line_broken_words():
    assert "document" in clean_text("This is a docu-\nment about grants.")


def test_clean_text_collapses_whitespace_runs():
    out = clean_text("a    b\t\tc\n\n\n\n\nd")
    assert out == "a b c\n\nd"


def test_clean_text_normalizes_crlf_and_form_feeds():
    out = clean_text("page one\x0cpage two\r\npage three")
    assert "\r" not in out and "\x0c" not in out
    assert "page one" in out and "page two" in out


def test_clean_text_preserves_content():
    src = "Requirement (a): max 1 page.   Requirement (b): max 3 pages."
    assert clean_text(src).startswith("Requirement (a)")


def test_clean_text_empty():
    assert clean_text("") == ""


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------
def _long_text(paragraphs: int = 40, words_per_paragraph: int = 120) -> str:
    return "\n\n".join(
        f"Paragraph {i} " + " ".join(f"word{j}x{i}" for j in range(words_per_paragraph)) + "."
        for i in range(paragraphs)
    )


def test_chunk_text_empty_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_text_small_input_single_chunk():
    chunks = chunk_text("hello world", target_tokens=100, overlap_tokens=10)
    assert len(chunks) == 1 and chunks[0].text == "hello world"


def test_chunk_text_respects_target_size():
    chunks = chunk_text(_long_text(), target_tokens=6000, overlap_tokens=200)
    assert len(chunks) > 1
    for c in chunks:
        assert c.token_estimate <= 6000 + 16  # never meaningfully above target
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunk_text_consecutive_chunks_overlap():
    chunks = chunk_text(_long_text(), target_tokens=800, overlap_tokens=100)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        # the next chunk opens with an ≈overlap_tokens tail of the previous one
        tail_words = set(prev.text.split()[-60:])
        head_words = set(nxt.text.split()[:12])
        assert tail_words & head_words, "expected an overlap tail on the next chunk"


def test_chunk_text_loses_no_content():
    src = _long_text(paragraphs=25, words_per_paragraph=90)
    joined = " ".join(c.text for c in chunk_text(src, target_tokens=1500, overlap_tokens=100))
    assert set(src.split()) <= set(joined.split())


def test_chunk_text_splits_oversized_single_paragraph():
    monster = " ".join(f"word{i}" for i in range(20_000))
    chunks = chunk_text(monster, target_tokens=1000, overlap_tokens=50)
    assert len(chunks) >= 18
    # each chunk stays within target + one overlap tail
    assert all(c.token_estimate <= 1000 + 50 + 8 for c in chunks)


# ---------------------------------------------------------------------------
# HTML → text
# ---------------------------------------------------------------------------
SAMPLE_HTML = """
<html><head><title> ignored </title><style>body{color:red}</style></head>
<body>
  <h1>Community Resilience Grants</h1>
  <script>var tracked = "nope";</script>
  <p>Proposals are due &amp; delivered by <b>November 15, 2026</b>.</p>
  <ul><li>Budget cap: $250,000</li><li>16-page limit</li></ul>
</body></html>
"""


def test_html_to_text_drops_script_style_and_head():
    out = html_to_text(SAMPLE_HTML)
    assert "tracked" not in out
    assert "color:red" not in out
    assert "ignored" not in out


def test_html_to_text_keeps_content_and_unescapes_entities():
    out = html_to_text(SAMPLE_HTML)
    assert "Community Resilience Grants" in out
    assert "due & delivered" in out
    assert "$250,000" in out


# ---------------------------------------------------------------------------
# PDF parsing (real pypdf round-trip against a generated fixture)
# ---------------------------------------------------------------------------
def test_parse_pdf_upload():
    pdf = build_minimal_pdf(
        [
            "COMMUNITY RESILIENCE PLANNING GRANTS PROGRAM\n"
            "Proposals are due November 15, 2026.\n"
            "Award ceiling: $250,000."
        ]
    )
    parser = DocumentParser(settings=Settings(chunk_target_tokens=6000))
    parsed = _run(parser.parse_bytes("solicitation.pdf", pdf))
    assert parsed.page_count == 1
    assert "COMMUNITY RESILIENCE PLANNING GRANTS PROGRAM" in parsed.text
    assert "$250,000" in parsed.text
    assert len(parsed.chunks) == 1


def test_parse_multi_page_pdf_counts_pages():
    pdf = build_minimal_pdf(["Page one text.", "Page two text.", "Page three text."])
    parser = DocumentParser(settings=Settings())
    parsed = _run(parser.parse_bytes("rfp.pdf", pdf))
    assert parsed.page_count == 3
    for marker in ("Page one text.", "Page two text.", "Page three text."):
        assert marker in parsed.text


def test_parse_pdf_magic_bytes_win_over_extension():
    pdf = build_minimal_pdf(["content is what matters"])
    parser = DocumentParser(settings=Settings())
    parsed = _run(parser.parse_bytes("misnamed.txt", pdf))
    assert "content is what matters" in parsed.text


def test_parse_txt_upload():
    parser = DocumentParser(settings=Settings())
    parsed = _run(parser.parse_bytes("notes.md", b"# Org profile\n\n501(c)(3) non-profit."))
    assert "501(c)(3) non-profit." in parsed.text


def test_parse_corrupt_pdf_raises_friendly_error():
    with pytest.raises(DocumentParseError, match="unreadable PDF"):
        _run(DocumentParser(settings=Settings()).parse_bytes("x.pdf", b"definitely not a pdf"))


# ---------------------------------------------------------------------------
# URL fetching (httpx MockTransport — no network)
# ---------------------------------------------------------------------------
def _parser_with(handler) -> DocumentParser:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return DocumentParser(settings=Settings(), client=client)


def _run(coro):
    import asyncio

    return asyncio.run(coro)


async def test_parse_url_html():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SAMPLE_HTML, headers={"content-type": "text/html"})

    parsed = await _parser_with(handler).parse_url("https://funder.example/rfp")
    assert parsed.source_url == "https://funder.example/rfp"
    assert "November 15, 2026" in parsed.text
    assert len(parsed.chunks) >= 1


async def test_parse_url_direct_pdf():
    pdf = build_minimal_pdf(["FUNDING OPPORTUNITY ANNOUNCEMENT", "Page limit: 16 pages."])

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})

    parsed = await _parser_with(handler).parse_url("https://funder.example/rfp.pdf")
    assert parsed.page_count == 2
    assert "Page limit: 16 pages." in parsed.text


async def test_parse_url_http_error_is_friendly():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with pytest.raises(DocumentParseError, match="HTTP 404"):
        await _parser_with(handler).parse_url("https://funder.example/gone.html")
