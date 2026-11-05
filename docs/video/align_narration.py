#!/usr/bin/env python3
"""Estimate narration cue boundaries from an existing Whisper transcript.

No audio decoding, ASR, model calls, or network access is performed. Example:
  python3 align_narration.py --asr whisper.json --output alignment.json
  python3 align_narration.py --asr whisper.json --silences silence.json \
      --audio-duration 172.4 --output alignment.json

Silences: [{"start": 1.2, "end": 1.5}, ...], or an object containing a
"silences" or "intervals" list. "silence_start"/"silence_end" are also accepted.
Use --output - for stdout. Source times refer to the continuous original audio;
start_seconds/end_seconds remain the request's destination video times.
Confidence scores describe transcript agreement, NOT verified audio accuracy.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def normalize(text: str) -> str:
    """Canonicalize Korean spacing/punctuation and common spoken letter names."""
    text = unicodedata.normalize("NFKC", text).casefold()
    # Latin-only lookarounds allow forms such as 'B가' without rewriting words.
    for spelling, spoken in (("ai", "에이아이"), ("a", "에이"), ("b", "비"), ("i", "아이")):
        text = re.sub(r"(?<![a-z])" + spelling + r"(?![a-z])", spoken, text)
    return "".join(character for character in text if character.isalnum())


def number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite nonnegative number")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a finite nonnegative number") from None
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{label} must be a finite nonnegative number")
    return result


@dataclass(frozen=True)
class Unit:
    text: str
    normalized: str
    start: float
    end: float
    resolution: str


@dataclass(frozen=True)
class Character:
    text: str
    start: float
    end: float
    unit: int


def read_transcript(data: dict[str, Any]) -> tuple[list[Unit], list[Character], float]:
    if not isinstance(data, dict):
        raise ValueError("ASR JSON must be an object")
    units: list[Unit] = []
    duration = 0.0
    segments = data.get("segments")
    if not segments:
        if data.get("words"):
            segments = [{"words": data["words"]}]
        else:
            raise ValueError("ASR JSON requires nonempty segments or timestamped words")
    if not isinstance(segments, list):
        raise ValueError("ASR segments must be a list")
    for segment_index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError("Each ASR segment must be an object")
        if "end" in segment:
            duration = max(duration, number(segment["end"], f"segment {segment_index} end"))
        words = segment.get("words")
        timed_items = words if words else [segment]
        if not isinstance(timed_items, list):
            raise ValueError("ASR words must be a list")
        resolution = "word" if words else "segment"
        for item in timed_items:
            if not isinstance(item, dict):
                raise ValueError("Each ASR word must be an object")
            text = item.get("word", item.get("text", ""))
            if not isinstance(text, str):
                raise ValueError("ASR word/text fields must be strings")
            normalized = normalize(text)
            if not normalized:
                continue
            start = number(item.get("start"), f"{resolution} start")
            end = number(item.get("end"), f"{resolution} end")
            if end < start:
                raise ValueError(f"ASR timestamp ends before it starts: {text!r}")
            if units and start < units[-1].start:
                raise ValueError("ASR timestamps must be in chronological transcript order")
            units.append(Unit(text.strip(), normalized, start, end, resolution))
            duration = max(duration, end)
    if not units:
        raise ValueError("ASR JSON has no timestamped alphanumeric text")
    characters = []
    for index, unit in enumerate(units):
        step = (unit.end - unit.start) / len(unit.normalized)
        for offset, character in enumerate(unit.normalized):
            characters.append(Character(character, unit.start + offset * step,
                                        unit.start + (offset + 1) * step, index))
    return units, characters, duration


def read_silences(data: Any) -> list[tuple[float, float]]:
    if isinstance(data, dict):
        data = data.get("silences", data.get("intervals"))
    if not isinstance(data, list):
        raise ValueError("Silence JSON must be a list or an object with silences/intervals")
    intervals = []
    for item in data:
        if isinstance(item, dict):
            start = item.get("start", item.get("start_seconds", item.get("silence_start")))
            end = item.get("end", item.get("end_seconds", item.get("silence_end")))
        elif isinstance(item, list) and len(item) == 2:
            start, end = item
        else:
            raise ValueError("Each silence must contain start and end")
        start, end = number(start, "silence start"), number(end, "silence end")
        if end < start:
            raise ValueError("Silence ends before it starts")
        intervals.append((start, end))
    # Merge overlaps so two reports of one pause cannot skew midpoint selection.
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def align_characters(expected: str, observed: str) -> tuple[list[int | None], int]:
    """Global weighted edit-distance alignment; diagonal substitution costs 3/2.

    Unlike a greedy phrase search, a global monotone path disambiguates repeated
    Korean sentence endings using the surrounding complete transcript. A byte
    per DP cell stores traceback; scores use two rows. Input size is bounded to
    avoid accidental unbounded memory use with a full meeting transcript.
    """
    rows, columns = len(expected), len(observed)
    if rows * columns > 25_000_000:
        raise ValueError("Transcript too large (over 25 million alignment cells); split it first")
    trace = [bytearray(columns + 1) for _ in range(rows + 1)]
    previous = [2 * j for j in range(columns + 1)]
    for i in range(1, rows + 1):
        current = [2 * i] + [0] * columns
        trace[i][0] = 1
        for j in range(1, columns + 1):
            diagonal = previous[j - 1] + (0 if expected[i - 1] == observed[j - 1] else 3)
            deletion, insertion = previous[j] + 2, current[j - 1] + 2
            best = min(diagonal, deletion, insertion)
            current[j] = best
            trace[i][j] = 0 if best == diagonal else (1 if best == deletion else 2)
        previous = current
    mapping: list[int | None] = [None] * rows
    i, j = rows, columns
    while i or j:
        if i == 0:
            j -= 1
        elif j == 0 or trace[i][j] == 1:
            i -= 1
        elif trace[i][j] == 2:
            j -= 1
        else:
            mapping[i - 1] = j - 1
            i, j = i - 1, j - 1
    return mapping, previous[-1]


def align_narration(request: dict[str, Any], asr: dict[str, Any], *,
                    silences: list[tuple[float, float]] | None = None,
                    audio_duration: float | None = None, padding: float = 0.08,
                    min_match: float = 0.85, max_speed: float = 1.12) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("Narration request JSON must be an object")
    cues = request.get("cues")
    if not isinstance(cues, list) or not cues:
        raise ValueError("Narration request requires a nonempty cues list")
    expected_parts, offsets, ids = [], [0], set()
    previous_end = 0.0
    for cue in cues:
        if not isinstance(cue, dict):
            raise ValueError("Each request cue must be an object")
        cue_id = cue.get("id")
        if not isinstance(cue_id, str) or not cue_id or cue_id in ids:
            raise ValueError("Each cue requires a unique nonempty string id")
        ids.add(cue_id)
        speech = cue.get("speech", cue.get("subtitle", ""))
        if not isinstance(speech, str) or not normalize(speech):
            raise ValueError(f"Cue {cue_id} requires nonempty speech or subtitle")
        start, end = number(cue.get("start_seconds"), "cue start"), number(cue.get("end_seconds"), "cue end")
        if end <= start or start < previous_end:
            raise ValueError(f"Destination cue {cue_id} overlaps or has no duration")
        previous_end = end
        expected_parts.append(normalize(speech))
        offsets.append(offsets[-1] + len(expected_parts[-1]))
    units, characters, inferred_duration = read_transcript(asr)
    duration = inferred_duration if audio_duration is None else number(audio_duration, "audio duration")
    if duration < inferred_duration - 0.001:
        raise ValueError("Audio duration is shorter than the ASR timestamps")
    expected = "".join(expected_parts)
    observed = "".join(character.text for character in characters)
    mapping, cost = align_characters(expected, observed)
    anchors = [i for i, j in enumerate(mapping) if j is not None]
    if not anchors:
        raise ValueError("No transcript alignment could be formed")
    exact = [j is not None and expected[i] == observed[j] for i, j in enumerate(mapping)]
    boundaries = []
    for cue_index, position in enumerate(offsets[1:-1]):
        split = bisect.bisect_left(anchors, position)
        left = anchors[split - 1] if split else None
        right = anchors[split] if split < len(anchors) else None
        reasons = []
        if left is None or right is None:
            time = characters[mapping[right]].start if left is None else characters[mapping[left]].end
            low = high = time
            method = "one_sided_anchor"
            reasons.append("missing_boundary_anchor")
        else:
            left_char, right_char = characters[mapping[left]], characters[mapping[right]]
            low, high = left_char.end, right_char.start
            missing = right - left - 1
            method = "asr_gap_midpoint"
            if missing:
                # A missing whole cue can legitimately yield zero duration; do
                # not fabricate speech, and explicitly require manual review.
                fraction = (position - left - 1) / missing
                time = low + (high - low) * fraction
                method = "missing_text_interpolation"
                reasons.append("unmatched_text_at_boundary")
            else:
                time = (low + high) / 2
            if low > high:
                reasons.append("overlapping_asr_timestamps")
            if left_char.unit == right_char.unit:
                reasons.append(f"boundary_inside_{units[left_char.unit].resolution}")
                method = "within_unit_interpolation"
            if not exact[left] or not exact[right]:
                reasons.append("boundary_anchor_text_mismatch")
            if mapping[right] - mapping[left] > 1:
                reasons.append("unassigned_asr_text_at_boundary")
            # Only a fully bracketed boundary can use a measured silence. The
            # silence intersection stays after the left and before right speech.
            if not missing and high >= low:
                candidates = [(max(low, start), min(high, end)) for start, end in (silences or [])
                              if max(low, start) < min(high, end)]
                if candidates:
                    start, end = min(candidates, key=lambda pair: abs(sum(pair) / 2 - time))
                    time = (start + end) / 2
                    method = "silence_midpoint"
        boundaries.append({"left_cue_id": cues[cue_index]["id"],
                           "right_cue_id": cues[cue_index + 1]["id"],
                           "source_seconds": time, "method": method,
                           "anchor_gap_start_seconds": low, "anchor_gap_end_seconds": high,
                           "needs_review": bool(reasons), "review_reasons": reasons})
    source_start = max(0.0, characters[0].start - padding)
    source_end = min(duration, characters[-1].end + padding)
    cuts = [source_start]
    for boundary in boundaries:
        time = min(source_end, max(cuts[-1], boundary["source_seconds"]))
        if abs(time - boundary["source_seconds"]) > 1e-8:
            boundary["review_reasons"].append("boundary_clamped_to_keep_cues_ordered")
            boundary["needs_review"] = True
        boundary["source_seconds"] = time
        cuts.append(time)
    cuts.append(source_end)
    output_cues = []
    for index, cue in enumerate(cues):
        begin, end = offsets[index:index + 2]
        assigned = [j for j in mapping[begin:end] if j is not None]
        matched = sum(exact[begin:end])
        length = end - begin
        ratio = matched / length
        observed_length = assigned[-1] - assigned[0] + 1 if assigned else 0
        precision = matched / observed_length if observed_length else 0.0
        unit_indices = sorted({characters[j].unit for j in range(assigned[0], assigned[-1] + 1)}) if assigned else []
        resolutions = {units[i].resolution for i in unit_indices}
        resolution = next(iter(resolutions)) if len(resolutions) == 1 else ("mixed" if resolutions else "none")
        reasons = []
        if not assigned:
            reasons.append("no_mapped_speech")
        if ratio < min_match:
            reasons.append("low_text_match")
        if precision < min_match:
            reasons.append("extra_or_repeated_asr_text")
        if "segment" in resolutions:
            reasons.append("segment_timestamps_require_interpolation")
        edge_size = min(4, length)
        if not all(exact[begin:begin + edge_size]) or not all(exact[end - edge_size:end]):
            reasons.append("cue_edge_text_mismatch")
        if any(units[i].end <= units[i].start for i in unit_indices):
            reasons.append("zero_duration_asr_unit")
        for boundary_index in (index - 1, index):
            if 0 <= boundary_index < len(boundaries) and boundaries[boundary_index]["needs_review"]:
                reasons.append("uncertain_start_boundary" if boundary_index == index - 1 else "uncertain_end_boundary")
        source_length = cuts[index + 1] - cuts[index]
        if source_length <= 0:
            reasons.append("empty_source_interval")
        detected_start = characters[assigned[0]].start if assigned else None
        detected_end = characters[assigned[-1]].end if assigned else None
        if assigned and (detected_start < cuts[index] - 0.001 or detected_end > cuts[index + 1] + 0.001):
            reasons.append("source_cut_intersects_mapped_speech")
        slot = float(cue["end_seconds"]) - float(cue["start_seconds"])
        maximum = number(cue.get("max_duration_seconds", slot), "max duration")
        if maximum <= 0 or maximum > slot:
            raise ValueError(f"Invalid max_duration_seconds for {cue['id']}")
        speed = max(1.0, source_length / maximum)
        if speed > max_speed:
            reasons.append("source_exceeds_allowed_speed_for_video_slot")
        # A heuristic text score, deliberately discounted for coarse timestamps.
        confidence = (0.8 * ratio + 0.2 * precision) * (0.75 if "segment" in resolutions else 1.0)
        if "cue_edge_text_mismatch" in reasons:
            confidence *= 0.8
        if "source_cut_intersects_mapped_speech" in reasons:
            confidence *= 0.7
        output_cues.append({
            "id": cue["id"], "filename": cue.get("filename"),
            "start_seconds": cue["start_seconds"], "end_seconds": cue["end_seconds"],
            "max_duration_seconds": maximum, "subtitle": cue.get("subtitle", ""),
            "speech": cue.get("speech", cue.get("subtitle", "")),
            "source_start_seconds": cuts[index], "source_end_seconds": cuts[index + 1],
            "source_duration_seconds": source_length,
            "detected_speech_start_seconds": detected_start, "detected_speech_end_seconds": detected_end,
            "minimum_speed_to_fit": speed, "expected_normalized_text": expected_parts[index],
            "asr_text": " ".join(units[i].text for i in unit_indices),
            "asr_normalized_text": observed[assigned[0]:assigned[-1] + 1] if assigned else "",
            "expected_character_count": length, "matched_character_count": matched,
            "exact_match_ratio": ratio, "mapped_character_ratio": len(assigned) / length,
            "asr_span_precision": precision, "confidence_score": confidence,
            "timestamp_resolution": resolution, "needs_review": bool(reasons),
            "review_reasons": reasons,
        })
    # Count recognized text outside all diagonal anchors; it could be a false
    # intro/outro or genuine missing request text and is never silently certified.
    prefix = mapping[anchors[0]]
    suffix = len(characters) - mapping[anchors[-1]] - 1
    warnings = []
    if prefix or suffix:
        warnings.append("ASR contains leading/trailing text not mapped to the request; review first/last cue")
        for index, count in ((0, prefix), (len(output_cues) - 1, suffix)):
            if count:
                output_cues[index]["needs_review"] = True
                output_cues[index]["review_reasons"].append("unmapped_outer_asr_text")
    result = {
        "schema_version": 1, "method": "normalized_character_global_weighted_edit_distance",
        "status": "estimated_alignment_requires_listening_review", "listening_review_required": True,
        "confidence_note": "Heuristic transcript agreement, not a calibrated probability or audio verification. Character times inside words/segments are interpolated.",
        "normalization": "Unicode NFKC, casefold, remove spacing/punctuation, AI/A/B/I to Korean spoken names",
        "total_duration_seconds": request.get("total_duration_seconds", previous_end),
        "source_duration_seconds": duration,
        "source_duration_basis": "caller_supplied" if audio_duration is not None else "last_asr_timestamp",
        "source_trim_start_seconds": source_start, "source_trim_end_seconds": source_end,
        "cue_count": len(cues), "expected_character_count": len(expected),
        "asr_character_count": len(observed), "matched_character_count": sum(exact),
        "exact_match_ratio": sum(exact) / len(expected), "weighted_edit_cost": cost,
        "edit_cost_weights": {"insertion": 2, "deletion": 2, "substitution": 3},
        "review_cue_ids": [cue["id"] for cue in output_cues if cue["needs_review"]],
        "warnings": warnings, "boundaries": boundaries, "cues": output_cues,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--request", type=Path, default=Path(__file__).with_name("narration-request.json"))
    parser.add_argument("--asr", type=Path, required=True, help="Existing Whisper JSON; use /dev/stdin for stdin")
    parser.add_argument("--output", type=Path, required=True, help="Alignment JSON, or - for stdout")
    parser.add_argument("--silences", type=Path, help="Optional measured silence intervals in source seconds")
    parser.add_argument("--audio-duration", type=float, help="Known original audio duration in seconds")
    parser.add_argument("--padding", type=float, default=0.08, help="Outer trim padding in seconds (default: 0.08)")
    parser.add_argument("--min-match", type=float, default=0.85, help="Text match threshold requiring review")
    parser.add_argument("--max-speed", type=float, default=1.12, help="Flag clips needing faster playback than this")
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.padding) or args.padding < 0:
            raise ValueError("--padding must be finite and nonnegative")
        if not 0 <= args.min_match <= 1:
            raise ValueError("--min-match must be between 0 and 1")
        if not math.isfinite(args.max_speed) or args.max_speed < 1:
            raise ValueError("--max-speed must be finite and at least 1")
        inputs = [args.request, args.asr, Path(__file__)] + ([args.silences] if args.silences else [])
        if str(args.output) != "-" and args.output.resolve() in {path.resolve() for path in inputs}:
            raise ValueError("Output cannot overwrite the request, transcript, silence input, or script")
        request = json.loads(args.request.read_text(encoding="utf-8"))
        asr = json.loads(args.asr.read_text(encoding="utf-8"))
        silences = read_silences(json.loads(args.silences.read_text(encoding="utf-8"))) if args.silences else []
        result = align_narration(request, asr, silences=silences, audio_duration=args.audio_duration,
                                 padding=args.padding, min_match=args.min_match, max_speed=args.max_speed)
        result["inputs"] = {"request": str(args.request), "asr": str(args.asr),
                            "silences": str(args.silences) if args.silences else None}
        payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if str(args.output) == "-":
            sys.stdout.write(payload)
        else:
            args.output.write_text(payload, encoding="utf-8")
        print(f"Estimated {result['cue_count']} cues; exact text match {result['exact_match_ratio']:.1%}; "
              f"{len(result['review_cue_ids'])} cues flagged. Listening review is still required.", file=sys.stderr)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
