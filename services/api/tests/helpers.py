"""Test helpers: a dependency-free, spec-correct PDF writer.

pypdf can *read* text but cannot easily *write* text, and we don't want a
binary fixture committed to the repo. ``build_minimal_pdf`` emits a valid
PDF 1.4 (catalog → page tree → per-page content streams with Tj operators,
correct xref offsets) that pypdf extracts cleanly.
"""

from __future__ import annotations


def _escape_pdf_text(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_minimal_pdf(page_texts: list[str]) -> bytes:
    n = len(page_texts)
    font_num = 3 + 2 * n
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [ {kids} ] /Count {n} >>".encode(),
    ]
    for i, text in enumerate(page_texts):
        content_num = 4 + 2 * i
        lines = text.splitlines() or [""]
        content = ["BT", "/F1 12 Tf", "14 TL", "72 720 Td"]
        for j, line in enumerate(lines):
            if j:
                content.append("T*")
            content.append(f"({_escape_pdf_text(line)}) Tj")
        content.append("ET")
        stream = "\n".join(content).encode("latin-1", "replace")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_num} 0 R >> >> "
            f"/Contents {content_num} 0 R >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % num + body + b"\nendobj\n"

    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_pos,
    )
    return bytes(out)
