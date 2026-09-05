"""Ink-only SVG rendering of GoodNotes strokes: white background, no ruling,
no attachments. Reuses the parser's ribbon builder so stroke shapes match its
own export; only what gets drawn differs.

Two things mirrored from goodnotes_re.export.page_to_svg matter for fidelity:
strokes carrying a precomputed `native_cgpaths` mesh are drawn from that mesh,
and pressure is sanitized before it becomes a ribbon half-width. Both guard
against the same real bug: some pencil strokes decode with a garbage pressure
(e.g. 287 instead of 0-1) which otherwise blows a stroke up into a
page-covering blob (seen on Fis3 Pr3.goodnotes, page 2, stroke 135).

Coordinates: stroke points are in GoodNotes' 132 DPI space and get scaled by
DPI_SCALE into the 72 DPI page space; `page.dimensions` is already in that
72 DPI space and must not be scaled again.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from goodnotes_re import Page, Stroke
from goodnotes_re.stroke import StrokePoint, build_stroke_ribbon, is_valid_pressure

DPI_SCALE = 72.0 / 132.0


@dataclass(frozen=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def diagonal(self) -> float:
        return math.hypot(self.width, self.height)

    def expanded(self, margin: float) -> "BBox":
        return BBox(self.x0 - margin, self.y0 - margin, self.x1 + margin, self.y1 + margin)

    def intersects(self, other: "BBox") -> bool:
        return not (self.x1 < other.x0 or other.x1 < self.x0 or self.y1 < other.y0 or other.y1 < self.y0)

    @staticmethod
    def union(boxes: Iterable["BBox"]) -> "BBox":
        boxes = list(boxes)
        return BBox(
            min(b.x0 for b in boxes),
            min(b.y0 for b in boxes),
            max(b.x1 for b in boxes),
            max(b.y1 for b in boxes),
        )


def stroke_bbox(stroke: Stroke) -> BBox:
    """Bounding box of a stroke in 72 DPI page points."""
    xs = [p.x * DPI_SCALE for p in stroke.points]
    ys = [p.y * DPI_SCALE for p in stroke.points]
    half_w = stroke.width * DPI_SCALE / 2
    return BBox(min(xs) - half_w, min(ys) - half_w, max(xs) + half_w, max(ys) + half_w)


def _sanitize_points(points: Sequence[StrokePoint]) -> list[StrokePoint]:
    valid = [p.pressure for p in points if is_valid_pressure(p.pressure)]
    fallback = valid[0] if valid else 1.0
    return [p if is_valid_pressure(p.pressure) else StrokePoint(p.x, p.y, fallback) for p in points]


def _native_cgpath_to_d(native_cgpaths, scale: float) -> str:
    segments = []
    for seg_cmds in native_cgpaths:
        cmds = []
        for op, args in seg_cmds:
            if op == "M":
                cmds.append(f"M {args[0] * scale:.2f} {args[1] * scale:.2f}")
            elif op == "C":
                c1x, c1y, c2x, c2y, px, py = args
                cmds.append(
                    f"C {c1x * scale:.2f} {c1y * scale:.2f}, "
                    f"{c2x * scale:.2f} {c2y * scale:.2f}, {px * scale:.2f} {py * scale:.2f}"
                )
            elif op == "A":
                cx, cy, r, a0, a1, flag = args
                d_theta = (a0 - a1) % (2.0 * math.pi)
                sweep = 0 if int(flag) == 1 else 1
                large_arc = 1 if d_theta > math.pi else 0
                end_x = cx + r * math.cos(a1)
                end_y = cy + r * math.sin(a1)
                cmds.append(
                    f"A {r * scale:.2f} {r * scale:.2f} 0 {large_arc} {sweep} "
                    f"{end_x * scale:.2f} {end_y * scale:.2f}"
                )
        cmds.append("Z")
        segments.append(" ".join(cmds))
    return " ".join(segments)


def _stroke_element(stroke: Stroke) -> str | None:
    fill = f'fill="{stroke.color_hex}" fill-opacity="{stroke.alpha:.2f}" stroke="none"'

    if stroke.native_cgpaths:
        return f'<path d="{_native_cgpath_to_d(stroke.native_cgpaths, DPI_SCALE)}" {fill}/>'

    if not stroke.points:
        return None

    if stroke.is_dot:
        pt = stroke.points[0]
        pressure = pt.pressure if is_valid_pressure(pt.pressure) else 1.0
        r = max(0.12, (stroke.width * pressure * 0.5) * DPI_SCALE)
        return f'<circle cx="{pt.x * DPI_SCALE:.2f}" cy="{pt.y * DPI_SCALE:.2f}" r="{r:.2f}" {fill}/>'

    ribbon_d = build_stroke_ribbon(
        _sanitize_points(stroke.points),
        stroke.width,
        DPI_SCALE,
        tpl_format=stroke.tpl_format,
        is_cut_start=stroke.is_cut_start,
        is_cut_end=stroke.is_cut_end,
        start_cut_vec=stroke.start_cut_vec,
        end_cut_vec=stroke.end_cut_vec,
    )
    return f'<path d="{ribbon_d}" {fill}/>' if ribbon_d else None


def _svg(view: BBox, elements: Iterable[str], extra: str = "") -> str:
    w, h = view.width, view.height
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.2f}" height="{h:.2f}" '
        f'viewBox="{view.x0:.2f} {view.y0:.2f} {w:.2f} {h:.2f}">'
        f'<rect x="{view.x0:.2f}" y="{view.y0:.2f}" width="{w:.2f}" height="{h:.2f}" fill="#ffffff"/>'
        + "".join(e for e in elements if e)
        + extra
        + "</svg>"
    )


def render_strokes_svg(strokes: Sequence[Stroke], bbox: BBox | None = None, padding: float = 6.0) -> str:
    """Ink-only SVG of a subset of strokes, viewBox fitted to their bounding box."""
    if bbox is None:
        bbox = BBox.union(stroke_bbox(s) for s in strokes)
    return _svg(bbox.expanded(padding), (_stroke_element(s) for s in strokes))


def render_page_svg(page: Page, overlay: str = "") -> str:
    """Ink-only SVG of the whole page; `overlay` is raw SVG appended on top."""
    view = BBox(0, 0, page.dimensions.width, page.dimensions.height)
    return _svg(view, (_stroke_element(s) for s in page.strokes), overlay)
