from __future__ import annotations

from pathlib import Path

import pymupdf


def render_page_png(pdf_path: str | Path, page_index: int, dpi: int = 200) -> bytes:
    with pymupdf.open(str(pdf_path)) as doc:
        return doc[page_index].get_pixmap(dpi=dpi).tobytes("png")


def page_count(pdf_path: str | Path) -> int:
    with pymupdf.open(str(pdf_path)) as doc:
        return doc.page_count
