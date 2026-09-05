"""End-to-end: .goodnotes page -> stroke units -> drawings as exact vector
figures, text/math via Gemini -> one LaTeX body -> tectonic compile check.

Per text unit the VLM is first asked whether the crop holds a diagram and
where; if so the strokes inside that box become a drawing unit (rendered
from strokes, no model involved) and the rest is transcribed. A unit can
hold more than one diagram, so this repeats up to `max_drawings_per_unit`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cairosvg
from goodnotes_re import GoodNotesDocument

from goodnotesocr import segmentation, verify, vlm
from goodnotesocr.clean_svg import BBox, render_strokes_svg

_RASTER_SCALE = 200 / 72  # points -> ~200 DPI pixels, same as the baseline
_CROP_PADDING = 6.0
_MAX_FIGURE_WIDTH_PT = 420.0  # wider drawings are scaled to \linewidth
MAX_DRAWINGS_PER_UNIT = 2


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


@dataclass
class Tokens:
    prompt: int = 0
    output: int = 0
    thought: int = 0

    def add(self, u: vlm.Usage) -> None:
        self.prompt += u.prompt_tokens
        self.output += u.output_tokens
        self.thought += u.thought_tokens


@dataclass
class UnitResult:
    index: int
    kind: str
    n_strokes: int
    figure: str | None = None
    status: str = ""  # text units: ok | repaired | verbatim
    locate: Tokens = field(default_factory=Tokens)
    transcribe: Tokens = field(default_factory=Tokens)


@dataclass
class PageResult:
    source: str
    page_index: int
    compiled: bool
    out_dir: str
    model: str
    units: list[UnitResult]
    locate: Tokens
    transcribe: Tokens


def _crop_png(unit: segmentation.Unit) -> tuple[bytes, BBox]:
    svg = render_strokes_svg(unit.strokes, unit.bbox, padding=_CROP_PADDING)
    return cairosvg.svg2png(bytestring=svg.encode(), scale=_RASTER_SCALE), unit.bbox.expanded(_CROP_PADDING)


def _figure_latex(name: str, width_pt: float) -> str:
    width = r"\linewidth" if width_pt > _MAX_FIGURE_WIDTH_PT else f"{width_pt:.0f}pt"
    return f"\\begin{{center}}\\includegraphics[width={width}]{{{name}}}\\end{{center}}"


def _emit_drawing(unit: segmentation.Unit, n: int, out_dir: Path, results: list[UnitResult], body: list[str]) -> None:
    fig_name = f"fig_{n}.pdf"
    svg = render_strokes_svg(unit.strokes, unit.bbox, padding=_CROP_PADDING)
    cairosvg.svg2pdf(bytestring=svg.encode(), write_to=str(out_dir / fig_name))
    body.append(_figure_latex(fig_name, unit.bbox.width + 2 * _CROP_PADDING))
    results.append(UnitResult(n, "drawing", len(unit.strokes), figure=fig_name))


def run_page(
    goodnotes_path: str | Path,
    page_index: int,
    out_root: str | Path = "out/pipeline",
    params: segmentation.Params = segmentation.Params(),
    model: str = vlm.DEFAULT_MODEL,
) -> PageResult:
    goodnotes_path = Path(goodnotes_path)
    out_dir = Path(out_root) / f"{goodnotes_path.stem.replace(' ', '_')}_p{page_index + 1}"
    out_dir.mkdir(parents=True, exist_ok=True)

    page = GoodNotesDocument.open(str(goodnotes_path)).pages()[page_index]
    units = segmentation.segment(page, params)

    body: list[str] = []
    results: list[UnitResult] = []
    page_locate, page_transcribe = Tokens(), Tokens()
    n = 0

    for unit in units:
        # Peel diagrams off the unit, one at a time.
        remainder: segmentation.Unit | None = unit
        for _ in range(MAX_DRAWINGS_PER_UNIT):
            if remainder is None:
                break
            png, view = _crop_png(remainder)
            box, usage = vlm.locate_drawing(png, model=model)
            page_locate.add(usage)
            if box is None:
                break
            region = segmentation.region_from_normalized(view, box)
            remainder, drawing = segmentation.split_by_region(remainder, region, params)
            if drawing is None:
                break
            n += 1
            _emit_drawing(drawing, n, out_dir, results, body)

        if remainder is None:
            continue
        n += 1
        png, _ = _crop_png(remainder)
        (out_dir / f"unit_{n}.png").write_bytes(png)
        usage = vlm.transcribe_to_latex(png, model=model)
        page_transcribe.add(usage)
        raw = strip_code_fence(usage.text)
        (out_dir / f"unit_{n}.tex").write_text(raw, encoding="utf-8")
        fixed, status = verify.ensure_compiles(raw, f"unidad {n}")
        body.append(fixed)
        r = UnitResult(n, "text", len(remainder.strokes), status=status)
        r.transcribe.add(usage)
        results.append(r)

    compiled = verify.compile_latex("\n\n".join(body), workdir=out_dir)
    (out_dir / "main.log").write_text(compiled.log, encoding="utf-8")

    page_result = PageResult(
        source=str(goodnotes_path),
        page_index=page_index,
        compiled=compiled.success,
        out_dir=str(out_dir),
        model=model,
        units=results,
        locate=page_locate,
        transcribe=page_transcribe,
    )
    (out_dir / "summary.json").write_text(json.dumps(asdict(page_result), indent=2), encoding="utf-8")
    return page_result
