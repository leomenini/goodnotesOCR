"""Deterministic spatial segmentation of a page's strokes into units, plus
deterministic extraction of a drawing region out of a unit.

Grouping is a recursive XY-cut on stroke bounding boxes: split on horizontal
blank bands taller than `y_gap` × median stroke size, then on vertical blank
gaps wider than `x_gap` × median inside each band, and recurse. Blank space
between blocks is what separates exercises, which is the criterion agreed on
for this project; this formulation is robust to long horizontal strokes
(underlines, fraction bars, arrows) that would otherwise bridge blocks.
Writing order is kept only as a tie-break for reading order.

Locating drawings geometrically was tried and dropped: sketches made of
dashed segments and thin arrows have no reliable stroke-level signature, and
relaxing thresholds floods the page with integral signs and underlines. The
pipeline instead asks the VLM *where* a diagram is (a normalized box on the
unit's crop) and this module does the deterministic part: mapping that box
back to page coordinates and splitting the unit's strokes by it.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Literal, Sequence

from goodnotes_re import Page, Stroke

from goodnotesocr.clean_svg import BBox, stroke_bbox

Kind = Literal["text", "drawing"]


@dataclass
class Unit:
    strokes: list[Stroke]
    bbox: BBox
    first_stroke_index: int
    kind: Kind = "text"
    boxes: list[BBox] = field(default_factory=list, repr=False)


@dataclass(frozen=True)
class Params:
    # Blank band / gap thresholds, as multiples of the median stroke size.
    y_gap: float = 0.8  # calibrated by eye on three real pages; 1.2+ merges whole pages
    x_gap: float = 2.0
    # Units with fewer strokes than this are merged into the nearest unit.
    min_unit_strokes: int = 3
    # A located drawing must capture at least this many strokes to count.
    # Calibrated on real pages: real sketches had 28+ strokes, false positives
    # (a crossed-out mark, a lone arrow) had 6-7.
    min_drawing_strokes: int = 8


def _median_size(boxes: Sequence[BBox]) -> float:
    sizes = [max(b.width, b.height) for b in boxes if max(b.width, b.height) > 0]
    return statistics.median(sizes) if sizes else 1.0


def _split_on_gaps(indices: list[int], boxes: list[BBox], axis: str, gap: float) -> list[list[int]]:
    lo = (lambda b: b.y0) if axis == "y" else (lambda b: b.x0)
    hi = (lambda b: b.y1) if axis == "y" else (lambda b: b.x1)
    order = sorted(indices, key=lambda i: lo(boxes[i]))
    groups: list[list[int]] = []
    cur: list[int] = []
    cur_end = -math.inf
    for i in order:
        if cur and lo(boxes[i]) - cur_end > gap:
            groups.append(cur)
            cur = []
        cur.append(i)
        cur_end = max(cur_end, hi(boxes[i]))
    if cur:
        groups.append(cur)
    return groups


def _xy_cut(indices: list[int], boxes: list[BBox], gy: float, gx: float) -> list[list[int]]:
    for axis, gap in (("y", gy), ("x", gx)):
        parts = _split_on_gaps(indices, boxes, axis, gap)
        if len(parts) > 1:
            return [leaf for part in parts for leaf in _xy_cut(part, boxes, gy, gx)]
    return [indices]


def _distance(a: BBox, b: BBox) -> float:
    dx = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    dy = max(0.0, max(a.y0, b.y0) - min(a.y1, b.y1))
    return math.hypot(dx, dy)


def _merge_tiny(groups: list[list[int]], boxes: list[BBox], min_strokes: int) -> list[list[int]]:
    big = [g for g in groups if len(g) >= min_strokes]
    tiny = [g for g in groups if len(g) < min_strokes]
    if not big:
        return groups
    big_boxes = [BBox.union(boxes[i] for i in g) for g in big]
    for g in tiny:
        gb = BBox.union(boxes[i] for i in g)
        nearest = min(range(len(big)), key=lambda k: _distance(gb, big_boxes[k]))
        big[nearest].extend(g)
        big_boxes[nearest] = BBox.union([big_boxes[nearest], gb])
    return big


def _make_unit(members: list[int], strokes: list[Stroke], boxes: list[BBox], kind: Kind = "text") -> Unit:
    members = sorted(members)
    unit_boxes = [boxes[i] for i in members]
    return Unit(
        strokes=[strokes[i] for i in members],
        bbox=BBox.union(unit_boxes),
        first_stroke_index=members[0],
        kind=kind,
        boxes=unit_boxes,
    )


def segment(page: Page, params: Params = Params()) -> list[Unit]:
    strokes = list(page.strokes)
    if not strokes:
        return []
    boxes = [stroke_bbox(s) for s in strokes]
    median = _median_size(boxes)

    groups = _xy_cut(list(range(len(strokes))), boxes, params.y_gap * median, params.x_gap * median)
    groups = _merge_tiny(groups, boxes, params.min_unit_strokes)

    units = [_make_unit(g, strokes, boxes) for g in groups]
    units.sort(key=lambda u: (round(u.bbox.y0 / median), u.bbox.x0, u.first_stroke_index))
    return units


# --- drawing extraction from a located region ---------------------------------

def region_from_normalized(view: BBox, box_1000: Sequence[float]) -> BBox:
    """Map a [ymin, xmin, ymax, xmax] box in 0-1000 image coordinates onto the
    page-space viewBox the image was rendered from."""
    ymin, xmin, ymax, xmax = (float(v) / 1000.0 for v in box_1000)
    return BBox(
        view.x0 + xmin * view.width,
        view.y0 + ymin * view.height,
        view.x0 + xmax * view.width,
        view.y0 + ymax * view.height,
    )


def _center_inside(box: BBox, region: BBox) -> bool:
    cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    return region.x0 <= cx <= region.x1 and region.y0 <= cy <= region.y1


def split_by_region(unit: Unit, region: BBox, params: Params = Params()) -> tuple[Unit | None, Unit | None]:
    """Split `unit` into (text remainder, drawing) by stroke centers inside
    `region`. Either side can be None. Deterministic given the region."""
    inside = [k for k, b in enumerate(unit.boxes) if _center_inside(b, region)]
    if len(inside) < params.min_drawing_strokes:
        return unit, None
    outside = [k for k in range(len(unit.boxes)) if k not in set(inside)]
    drawing = _make_unit(inside, unit.strokes, unit.boxes, kind="drawing")
    drawing.first_stroke_index += unit.first_stroke_index
    remainder = None
    if outside:
        remainder = _make_unit(outside, unit.strokes, unit.boxes)
        remainder.first_stroke_index += unit.first_stroke_index
    return remainder, drawing


def overlay_svg(units: Sequence[Unit]) -> str:
    """Debug overlay: one rectangle per unit, red for drawings, blue for text."""
    parts = []
    for n, u in enumerate(units, 1):
        color = "#d62728" if u.kind == "drawing" else "#1f77b4"
        b = u.bbox
        parts.append(
            f'<rect x="{b.x0:.1f}" y="{b.y0:.1f}" width="{b.width:.1f}" height="{b.height:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="1" stroke-dasharray="3 2"/>'
            f'<text x="{b.x0 + 2:.1f}" y="{b.y0 + 9:.1f}" font-size="8" fill="{color}">{n} {u.kind[0]}</text>'
        )
    return "".join(parts)
