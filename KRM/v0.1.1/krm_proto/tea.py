"""TEA: conservative time-domain transient-event candidate analysis.

This module emits candidates and measurements only. It does not classify
musical noise, instruments, or semantic sound sources, and it never mutates
KRM raw residual data.
"""
from __future__ import annotations

import math
from collections import deque
from statistics import median
from typing import Iterable, Iterator, Sequence


def _positive_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _nonnegative_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _finite_number(value: float, name: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number) or (number < 0 if allow_zero else number <= 0):
        relation = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be finite and {relation}")
    return number


def _validate_geometry(window_samples: int, hop_samples: int | None) -> int:
    _positive_int(window_samples, "window_samples")
    hop = window_samples if hop_samples is None else _positive_int(hop_samples, "hop_samples")
    return hop


def _frame_metrics(samples: Sequence[int | float], start: int) -> dict:
    if len(samples) == 0:
        raise ValueError("Cannot analyze an empty frame")

    # Scale by the largest magnitude before squaring/summing. This avoids
    # intermediate overflow for large but finite floating-point inputs.
    values: list[float] = []
    peak = 0.0
    for raw in samples:
        if isinstance(raw, bool):
            raise ValueError("Samples must be finite real numbers, not booleans")
        try:
            value = float(raw)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Samples must be finite real numbers") from exc
        if not math.isfinite(value):
            raise ValueError("Samples must be finite")
        values.append(value)
        peak = max(peak, abs(value))

    if peak == 0.0:
        rms = 0.0
        mean_abs = 0.0
        crest = 0.0
    else:
        scaled_square_sum = math.fsum((value / peak) ** 2 for value in values)
        scaled_abs_sum = math.fsum(abs(value) / peak for value in values)
        rms = peak * math.sqrt(scaled_square_sum / len(values))
        mean_abs = peak * (scaled_abs_sum / len(values))
        crest = peak / rms

    return {
        "start_sample": start,
        "end_sample_exclusive": start + len(samples),
        "sample_count": len(samples),
        "rms": rms,
        "peak": peak,
        "mean_abs": mean_abs,
        "crest_factor": crest,
    }


def frame_metrics(
    samples: Sequence[int | float], window_samples: int, hop_samples: int | None = None
) -> list[dict]:
    """Measure fixed windows; the final partial window is retained."""
    hop = _validate_geometry(window_samples, hop_samples)
    rows = []
    for start in range(0, len(samples), hop):
        frame = samples[start : start + window_samples]
        if len(frame):
            rows.append(_frame_metrics(frame, start))
    return rows


class _StreamingFrameMetrics:
    """Bounded-carryover frame extractor matching :func:`frame_metrics`."""

    def __init__(self, window_samples: int, hop_samples: int | None = None) -> None:
        self.window_samples = _positive_int(window_samples, "window_samples")
        self.hop_samples = _validate_geometry(window_samples, hop_samples)
        self._pending: list[int | float] = []
        self._pending_start = 0
        self._total_seen = 0
        self._next_start = 0
        self._finished = False

    def feed(self, chunk: Sequence[int | float]) -> Iterator[dict]:
        if self._finished:
            raise RuntimeError("Cannot feed a finished TEA frame extractor")
        if len(chunk) == 0:
            return
        self._pending.extend(chunk)
        self._total_seen += len(chunk)
        while self._next_start + self.window_samples <= self._total_seen:
            offset = self._next_start - self._pending_start
            if offset < 0:
                raise RuntimeError("Internal TEA frame offset underflow")
            frame = self._pending[offset : offset + self.window_samples]
            yield _frame_metrics(frame, self._next_start)
            self._next_start += self.hop_samples
        drop_until = min(self._next_start, self._total_seen)
        drop_count = drop_until - self._pending_start
        if drop_count > 0:
            del self._pending[:drop_count]
            self._pending_start = drop_until

    def finish(self) -> Iterator[dict]:
        if self._finished:
            return
        self._finished = True
        while self._next_start < self._total_seen:
            offset = self._next_start - self._pending_start
            frame = self._pending[offset:]
            if frame:
                yield _frame_metrics(frame, self._next_start)
            self._next_start += self.hop_samples
        self._pending.clear()


def _candidate_reasons(
    frame: dict,
    history: Sequence[float],
    rise_limit: float,
    crest_limit: float,
    floor: float,
) -> tuple[float, float, list[str]]:
    baseline = median(history) if history else 0.0
    rise_ratio = frame["rms"] / max(baseline, floor, 1e-30) if history else 0.0
    reasons: list[str] = []
    if frame["rms"] >= floor and frame["rms"] > 0.0:
        if history and rise_ratio >= rise_limit:
            reasons.append("energy_rise")
        if frame["crest_factor"] >= crest_limit:
            reasons.append("high_crest_factor")
    return baseline, rise_ratio, reasons


def _new_event(frame_index: int, frame: dict, reasons: list[str], rise_ratio: float) -> dict:
    return {
        "onset_sample": frame["start_sample"],
        "end_sample_exclusive": frame["end_sample_exclusive"],
        "frame_indices": [frame_index],
        "frame_count": 1,
        "peak": frame["peak"],
        "max_rms": frame["rms"],
        "max_crest_factor": frame["crest_factor"],
        "max_rise_ratio": rise_ratio,
        "candidate_reasons": set(reasons),
    }


def _extend_event(event: dict, frame_index: int, frame: dict, reasons: list[str], rise_ratio: float) -> None:
    event["end_sample_exclusive"] = max(event["end_sample_exclusive"], frame["end_sample_exclusive"])
    event["frame_indices"].append(frame_index)
    event["frame_count"] += 1
    event["peak"] = max(event["peak"], frame["peak"])
    event["max_rms"] = max(event["max_rms"], frame["rms"])
    event["max_crest_factor"] = max(event["max_crest_factor"], frame["crest_factor"])
    event["max_rise_ratio"] = max(event["max_rise_ratio"], rise_ratio)
    event["candidate_reasons"].update(reasons)


def _finalize_event(event: dict, event_id: int, parameters: dict) -> dict:
    result = dict(event)
    result["event_id"] = event_id
    result["detector_id"] = "KRM-TEA-TD-Candidate-v0.2"
    result["parameters"] = dict(parameters)
    result["duration_samples"] = result["end_sample_exclusive"] - result["onset_sample"]
    result["candidate_reasons"] = sorted(result["candidate_reasons"])
    result["classification"] = "transient_activity_candidate"
    result["confidence"] = None
    return result


def _validate_detector_parameters(
    baseline_frames: int,
    rise_ratio_threshold: float,
    crest_factor_threshold: float,
    absolute_rms_floor: float,
    merge_gap_frames: int,
) -> tuple[float, float, float]:
    _positive_int(baseline_frames, "baseline_frames")
    _nonnegative_int(merge_gap_frames, "merge_gap_frames")
    rise_limit = _finite_number(rise_ratio_threshold, "rise_ratio_threshold")
    crest_limit = _finite_number(crest_factor_threshold, "crest_factor_threshold")
    floor = _finite_number(absolute_rms_floor, "absolute_rms_floor", allow_zero=True)
    return rise_limit, crest_limit, floor


def _detect_frames(
    frames: Iterable[dict],
    *,
    baseline_frames: int,
    rise_limit: float,
    crest_limit: float,
    floor: float,
    merge_gap_frames: int,
    parameters: dict,
) -> Iterator[dict]:
    history: deque[float] = deque(maxlen=baseline_frames)
    current = None
    last_candidate_index = -1
    frame_index = 0
    event_id = 1

    for frame in frames:
        _, rise_ratio, reasons = _candidate_reasons(frame, history, rise_limit, crest_limit, floor)
        if reasons:
            if current is None or frame_index - last_candidate_index - 1 > merge_gap_frames:
                if current is not None:
                    yield _finalize_event(current, event_id, parameters)
                    event_id += 1
                current = _new_event(frame_index, frame, reasons, rise_ratio)
            else:
                _extend_event(current, frame_index, frame, reasons, rise_ratio)
            last_candidate_index = frame_index

        history.append(frame["rms"])
        frame_index += 1

    if current is not None:
        yield _finalize_event(current, event_id, parameters)


def detect_transient_candidates(
    samples: Sequence[int | float],
    window_samples: int,
    hop_samples: int | None = None,
    *,
    baseline_frames: int = 8,
    rise_ratio_threshold: float = 3.0,
    crest_factor_threshold: float = 5.0,
    absolute_rms_floor: float = 0.0,
    merge_gap_frames: int = 1,
) -> dict:
    """Detect transient/activity candidates from a complete sample sequence.

    This convenience API retains frame measurements. For long recordings,
    prefer :func:`iter_transient_candidates_from_chunks`, which retains only
    bounded frame carryover and a short baseline history.
    """
    hop = _validate_geometry(window_samples, hop_samples)
    rise_limit, crest_limit, floor = _validate_detector_parameters(
        baseline_frames, rise_ratio_threshold, crest_factor_threshold,
        absolute_rms_floor, merge_gap_frames,
    )
    parameters = {
        "window_samples": window_samples,
        "hop_samples": hop,
        "baseline_frames": baseline_frames,
        "rise_ratio_threshold": rise_limit,
        "crest_factor_threshold": crest_limit,
        "absolute_rms_floor": floor,
        "merge_gap_frames": merge_gap_frames,
    }
    frames = frame_metrics(samples, window_samples, hop)

    # Annotate per-frame measurements for diagnostics and reproducibility.
    history: deque[float] = deque(maxlen=baseline_frames)
    for frame in frames:
        baseline, rise_ratio, reasons = _candidate_reasons(frame, history, rise_limit, crest_limit, floor)
        frame["preceding_rms_median"] = baseline
        frame["rise_ratio"] = rise_ratio
        frame["candidate_reasons"] = reasons
        history.append(frame["rms"])

    events = list(_detect_frames(
        frames,
        baseline_frames=baseline_frames,
        rise_limit=rise_limit,
        crest_limit=crest_limit,
        floor=floor,
        merge_gap_frames=merge_gap_frames,
        parameters=parameters,
    ))
    return {
        "detector": "KRM-TEA-TD-Candidate-v0.2",
        "parameters": parameters,
        "frames": frames,
        "events": events,
    }


def iter_transient_candidates_from_chunks(
    chunks: Iterable[Sequence[int | float]],
    window_samples: int,
    hop_samples: int | None = None,
    *,
    baseline_frames: int = 8,
    rise_ratio_threshold: float = 3.0,
    crest_factor_threshold: float = 5.0,
    absolute_rms_floor: float = 0.0,
    merge_gap_frames: int = 1,
) -> Iterator[dict]:
    """Yield TEA candidates from chunks with bounded signal/frame memory.

    Output event records match ``detect_transient_candidates(...)["events"]``
    for the same concatenated samples and parameters. The iterator does not
    retain all frame measurements or all previously closed events.
    """
    _validate_geometry(window_samples, hop_samples)
    rise_limit, crest_limit, floor = _validate_detector_parameters(
        baseline_frames, rise_ratio_threshold, crest_factor_threshold,
        absolute_rms_floor, merge_gap_frames,
    )
    parameters = {
        "window_samples": window_samples,
        "hop_samples": window_samples if hop_samples is None else hop_samples,
        "baseline_frames": baseline_frames,
        "rise_ratio_threshold": rise_limit,
        "crest_factor_threshold": crest_limit,
        "absolute_rms_floor": floor,
        "merge_gap_frames": merge_gap_frames,
    }
    extractor = _StreamingFrameMetrics(window_samples, hop_samples)

    def frames() -> Iterator[dict]:
        for chunk in chunks:
            yield from extractor.feed(chunk)
        yield from extractor.finish()

    yield from _detect_frames(
        frames(),
        baseline_frames=baseline_frames,
        rise_limit=rise_limit,
        crest_limit=crest_limit,
        floor=floor,
        merge_gap_frames=merge_gap_frames,
        parameters=parameters,
    )
