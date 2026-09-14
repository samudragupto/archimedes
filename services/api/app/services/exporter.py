"""Proposal export: assembled Markdown → DOCX (python-docx) and PDF
(reportlab), plus the Markdown passthrough.

Design notes:
  * The converters consume the SAME markdown the editor stores (GitHub-flavored
    subset produced by the drafting node: #/##/### headings, paragraphs, bullet
    and numbered lists, **bold**, *italic*, `code`, [n] citations). Tables and
    images are intentionally out of scope for grant narratives.
  * The PDF uses a clean serif template (Times family) with a cover page —
    title, funder/organization line, date — because grant reviewers still
    print things.
  * Both converters are pure functions bytes-in/bytes-out, fully unit-tested
    offline (docx read back with python-docx, PDF read back with pypdf).
"""

from __future__ import annotations

import io
import re
from datetime import UTC, datetime

from markdown_it import MarkdownIt

# ---------------------------------------------------------------------------
# Shared markdown parsing (markdown-it tokens)
# ---------------------------------------------------------------------------
_mdit = MarkdownIt("commonmark").enable(["list", "smartquotes"])


def _inline_text_md(children: list) -> str:
    """Flatten inline markdown-it children to plain text (docx path)."""
    out: list[str] = []
    for child in children:
        ctype = child.type
        if ctype == "text":
            out.append(child.content)
        elif ctype in ("code_inline",):
            out.append(child.content)
        elif ctype == "softbreak":
            out.append(" ")
        elif ctype in (
            "strong_open",
            "strong_close",
            "em_open",
            "em_close",
            "link_open",
            "link_close",
        ):
            continue
        elif ctype == "html_inline":
            continue
        elif child.children:
            out.append(_inline_text_md(child.children))
    return "".join(out)


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------
def markdown_to_docx_bytes(
    markdown: str, *, title: str | None = None, organization: str | None = None
) -> bytes:
    """Render the proposal to a .docx (headings, lists, bold/italic runs)."""
    import docx
    from docx.shared import Pt

    document = docx.Document()
    style = document.styles["Normal"]
    style.font.name = "Georgia"
    style.font.size = Pt(11)

    if title:
        heading = document.add_heading(title, level=0)
        _ = heading
        if organization:
            document.add_paragraph(organization)

    tokens = _mdit.parse(markdown)
    list_stack: list[str] = []  # 'bullet' | 'ordered'

    # Simple two-pass inline renderer: tokens lose open/close pairing when we
    # walk linearly, so track bold/italic state on a small stack instead.
    def render_inline(paragraph, children: list, *, bold=False, italic=False) -> None:
        # markdown-it emits a FLAT inline token stream (strong_open … strong_close
        # with no nesting), so we track open/close state across siblings.
        b, it = bold, italic
        for child in children:
            if child.type == "strong_open":
                b = True
            elif child.type == "strong_close":
                b = bold
            elif child.type == "em_open":
                it = True
            elif child.type == "em_close":
                it = italic
            elif child.type == "text":
                run = paragraph.add_run(child.content)
                run.bold = b or None
                run.italic = it or None
            elif child.type == "code_inline":
                run = paragraph.add_run(child.content)
                run.font.name = "Courier New"
            elif child.type == "link_open":
                label = "".join(c.content for c in (child.children or []) if c.type == "text")
                run = paragraph.add_run(label or "[link]")
                run.underline = True
            elif child.type == "softbreak":
                paragraph.add_run(" ")

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            level = int(tok.tag[1])
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            text = _inline_text_md(inline.children or []) if inline else ""
            document.add_heading(text, level=min(level, 4))
            i += 2
            continue
        if tok.type in ("bullet_list_open", "ordered_list_open"):
            list_stack.append("bullet" if tok.type == "bullet_list_open" else "number")
            i += 1
            continue
        if tok.type in ("bullet_list_close", "ordered_list_close"):
            list_stack.pop()
            i += 1
            continue
        if tok.type == "list_item_open":
            # find the item's paragraph inline token
            j = i + 1
            while j < len(tokens) and tokens[j].type not in ("list_item_close",):
                if tokens[j].type == "inline":
                    paragraph = document.add_paragraph(
                        style=(
                            "List Bullet"
                            if (list_stack and list_stack[-1] == "bullet")
                            else "List Number"
                        )
                    )
                    render_inline(paragraph, tokens[j].children or [])
                    break
                j += 1
            i += 1
            continue
        if tok.type == "paragraph_open":
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            paragraph = document.add_paragraph()
            if inline:
                render_inline(paragraph, inline.children or [])
            i += 2
            continue
        if tok.type == "code_block" or tok.type == "fence":
            paragraph = document.add_paragraph()
            run = paragraph.add_run(tok.content.rstrip())
            run.font.name = "Courier New"
            run.font.size = Pt(9.5)
            i += 1
            continue
        if tok.type == "inline":  # stray inline (rare outside paragraphs)
            paragraph = document.add_paragraph()
            render_inline(paragraph, tok.children or [])
            i += 1
            continue
        i += 1

    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# PDF — clean serif template with a cover page (reportlab platypus)
# ---------------------------------------------------------------------------
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBER_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline_to_rl(text: str) -> str:
    """Markdown inline → reportlab paragraph markup (escape first, then style)."""
    out = _escape(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", out)
    out = re.sub(r"`([^`]+)`", r'<font face="Courier" size="9.5">\1</font>', out)
    return out


def markdown_to_pdf_bytes(
    markdown: str, *, title: str | None = None, organization: str | None = None
) -> bytes:
    """Render the proposal to a serif PDF with a cover page."""
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
    )

    styles = getSampleStyleSheet()
    cover_title = ParagraphStyle(
        "CoverTitle",
        parent=styles["Title"],
        fontName="Times-Bold",
        fontSize=26,
        leading=32,
        alignment=TA_CENTER,
        spaceAfter=18,
    )
    cover_meta = ParagraphStyle(
        "CoverMeta",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=12,
        leading=18,
        alignment=TA_CENTER,
        textColor="#444444",
    )
    h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontName="Times-Bold",
        fontSize=17,
        spaceBefore=14,
        spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName="Times-Bold",
        fontSize=14,
        spaceBefore=12,
        spaceAfter=6,
    )
    h3 = ParagraphStyle(
        "H3",
        parent=styles["Heading3"],
        fontName="Times-Bold",
        fontSize=12,
        spaceBefore=10,
        spaceAfter=5,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=15.5,
        spaceAfter=7,
    )
    bullet = ParagraphStyle("Bullet", parent=body, leftIndent=16, bulletIndent=4, spaceAfter=3)

    story: list = []
    # -- cover page ---------------------------------------------------------
    when = datetime.now(UTC).strftime("%B %d, %Y")
    story.append(Spacer(1, 150))
    story.append(Paragraph(_escape(title or "Grant Proposal"), cover_title))
    if organization:
        story.append(Paragraph(_escape(organization), cover_meta))
    story.append(Spacer(1, 24))
    story.append(Paragraph("Prepared with Archimedes — autonomous grant-writing agent", cover_meta))
    story.append(Paragraph(_escape(when), cover_meta))
    story.append(PageBreak())

    # -- body: line-based conversion (our narrative markdown is simple) -----
    for raw in markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(_inline_to_rl(stripped[4:]), h3))
        elif stripped.startswith("## "):
            story.append(Paragraph(_inline_to_rl(stripped[3:]), h2))
        elif stripped.startswith("# "):
            story.append(Paragraph(_inline_to_rl(stripped[2:]), h1))
        elif stripped in ("---", "***", "___"):
            story.append(Spacer(1, 6))
        else:
            m = _BULLET_RE.match(stripped)
            if m:
                story.append(Paragraph(_inline_to_rl(m.group(1)), bullet, bulletText="•"))
                continue
            m = _NUMBER_RE.match(stripped)
            if m:
                story.append(
                    Paragraph(
                        _inline_to_rl(m.group(1)), bullet, bulletText=stripped.split(".")[0] + "."
                    )
                )
                continue
            story.append(Paragraph(_inline_to_rl(stripped), body))

    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=72,
        rightMargin=72,
        topMargin=72,
        bottomMargin=72,
        title=title or "Grant Proposal",
        author=organization or "Prepared with Archimedes",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame])])
    doc.build(story)
    return buf.getvalue()
