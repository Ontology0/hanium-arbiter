#!/usr/bin/env python3
"""Measure glyph + neon bounds against visible labels, nodes, and connectors."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / "layout-bounds.json").read_text())
DURATIONS = {"problem": 16, "connections": 8, "cta": 13}


def ease(value):
    value = max(0, min(1, value))
    return value * value * (3 - 2 * value)


def opacity(item, at):
    if not item["moving"]:
        return 1
    return ease((at - item["start"]) / .7) * (1 - ease((at - item["end"]) / .5))


def offset(item, at):
    return 10 * (1 - opacity(item, at)) if item["moving"] else 0


def box(item, at):
    dy = offset(item, at)
    return item["left"], item["top"] + dy, item["right"], item["bottom"] + dy


def point_box(x, y, bounds):
    return math.hypot(max(bounds[0] - x, 0, x - bounds[2]), max(bounds[1] - y, 0, y - bounds[3]))


def point_segment(x, y, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    progress = max(0, min(1, ((x - start[0]) * dx + (y - start[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - start[0] - progress * dx, y - start[1] - progress * dy)


def segment_box(start, end, bounds):
    low, high = 0., 1.
    dx, dy = end[0] - start[0], end[1] - start[1]
    hit = True
    for p, q in [(-dx, start[0] - bounds[0]), (dx, bounds[2] - start[0]), (-dy, start[1] - bounds[1]), (dy, bounds[3] - start[1])]:
        if p == 0:
            if q < 0:
                hit = False
                break
        elif p < 0:
            low = max(low, q / p)
        else:
            high = min(high, q / p)
    if hit and low <= high:
        return 0
    return min(point_box(*start, bounds), point_box(*end, bounds), *(point_segment(x, y, start, end) for x, y in [(bounds[0], bounds[1]), (bounds[2], bounds[1]), (bounds[2], bounds[3]), (bounds[0], bounds[3])]))


report = {
    "method": "Measured Pretendard glyph ink + 14px neon bounds, full connector glow and node glow; every encoded frame above 15% opacity",
    "intentional_containment": "Protocol labels, CF and ? are placed inside their named node. Icon-internal decorative strokes have no text labels.",
    "minimum_required_clearance_px": 20,
    "subtitle_safe_area_top_px": 900,
    "scenes": {}, "failures": [],
}
for scene, duration in DURATIONS.items():
    texts = [item for item in DATA["texts"] if item["scene"] == scene]
    rings = [item for item in DATA["rings"] if item["scene"] == scene]
    lines = [item for item in DATA["lines"] if item["scene"] == scene]
    minimum = {"text": (9999, None), "ring": (9999, None), "line": (9999, None)}
    overlaps, extents, max_bottom = [], [], 0
    for frame in range(duration * 30):
        at = frame / 30
        active = [item for item in texts if opacity(item, at) > .15]
        for index, item in enumerate(active):
            bounds = box(item, at)
            max_bottom = max(max_bottom, bounds[3])
            if bounds[0] < 60 or bounds[2] > 1860 or bounds[1] < 24 or bounds[3] > 900:
                extents.append({"at": at, "label": item["str"], "bounds": bounds})
            for other in active[index + 1:]:
                other_bounds = box(other, at)
                gap = math.hypot(max(bounds[0] - other_bounds[2], other_bounds[0] - bounds[2], 0), max(bounds[1] - other_bounds[3], other_bounds[1] - bounds[3], 0))
                if gap < minimum["text"][0]:
                    minimum["text"] = gap, {"at": at, "labels": [item["str"], other["str"]]}
                if min(bounds[2], other_bounds[2]) > max(bounds[0], other_bounds[0]) and min(bounds[3], other_bounds[3]) > max(bounds[1], other_bounds[1]):
                    overlaps.append({"at": at, "labels": [item["str"], other["str"]]})
            for ring in rings:
                if opacity(ring, at) <= .15 or item["container"] == ring["id"]:
                    continue
                gap = point_box(ring["x"], ring["y"] + offset(ring, at), bounds) - ring["radius"]
                if gap < minimum["ring"][0]:
                    minimum["ring"] = gap, {"at": at, "label": item["str"], "node": ring["id"]}
            for line in lines:
                if opacity(line, at) <= .15:
                    continue
                dy = offset(line, at)
                gap = segment_box((line["x1"], line["y1"] + dy), (line["x2"], line["y2"] + dy), bounds) - line["halfWidth"]
                if gap < minimum["line"][0]:
                    minimum["line"] = gap, {"at": at, "label": item["str"]}
    result = {
        "sampled_frames": duration * 30,
        "text_overlap_count": len(overlaps), "out_of_bounds_count": len(extents),
        "minimum_clearance_px": {key: round(value[0], 2) for key, value in minimum.items()},
        "minimum_locations": {key: value[1] for key, value in minimum.items()},
        "maximum_text_bottom_px": round(max_bottom, 2),
    }
    report["scenes"][scene] = result
    if overlaps or extents or any(value[0] < 20 for value in minimum.values()):
        report["failures"].append({"scene": scene, "overlaps": overlaps[:3], "extents": extents[:3], "minimums": result["minimum_clearance_px"]})
(ROOT / "spacing-validation.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
if report["failures"]:
    raise SystemExit(1)
