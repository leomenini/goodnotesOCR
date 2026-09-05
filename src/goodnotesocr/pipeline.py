"""End-to-end: PDF page -> Gemini -> LaTeX -> tectonic compile check."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from goodnotesocr import pdf_render, verify, vlm

_FENCE_RE = re.compile(r"^\s*```(?:latex|tex)?\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


def strip_code_fence(text: str) -> str:
    m = _FENCE_RE.match(text)
    return m.group(1) if m else text


@dataclass
class PageResult:
    pdf_path: Path
    page_index: int
    compiled: bool
    tex_path: Path
    pdf_out_path: Path | None
    log_path: Path


def run_page(pdf_path: str | Path, page_index: int, out_dir: str | Path = "out/pipeline") -> PageResult:
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{pdf_path.stem.replace(' ', '_')}_p{page_index + 1}"

    png = pdf_render.render_page_png(pdf_path, page_index)
    body = strip_code_fence(vlm.transcribe_to_latex(png))
    result = verify.compile_latex(body)

    tex_path = out_dir / f"{stem}.tex"
    tex_path.write_text(result.tex, encoding="utf-8")
    log_path = out_dir / f"{stem}.log"
    log_path.write_text(result.log, encoding="utf-8")

    pdf_out_path = None
    if result.success:
        pdf_out_path = out_dir / f"{stem}.pdf"
        pdf_out_path.write_bytes(result.pdf_bytes)

    return PageResult(pdf_path, page_index, result.success, tex_path, pdf_out_path, log_path)
