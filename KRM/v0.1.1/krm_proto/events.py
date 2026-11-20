"""Coarse time-domain residual activity probes (not MP/HPSS/EMD)."""
from __future__ import annotations

import math
from statistics import median
from typing import Iterable, Iterator, Sequence


def _frame_record(frame: Sequence[int], start: int) -> dict:
    if not frame:
        raise ValueError("Cannot measure an empty frame")
    energy = sum(int(value) * int(value) for value in frame)
    rms = math.sqrt(energy / len(frame))
    peak = max(abs(int(value)) for value in frame)
    crossings = sum(
        1 for a, b in zip(frame, frame[1:])
        if (a < 0 <= b) or (b < 0 <= a)
    )
    return {
        "start_sample": start,
        "end_sample_exclusive": start + len(frame),
        "rms": rms,
        "peak": peak,
        "zero_crossing_rate": crossings / max(1, len(frame) - 1),
        "sample_count": len(frame),
    }


def frame_features(samples: Sequence[int], window_samples: int, hop_samples: int | None = None) -> list[dict]:
    if window_samples < 1:
        raise ValueError("window_samples must be positive")
    hop = window_samples if hop_samples is None else hop_samples
    if hop < 1:
        raise ValueError("hop_samples must be positive")
    return [
        _frame_record(samples[start : start + window_samples], start)
        for start in range(0, len(samples), hop)
        if samples[start : start + window_samples]
    ]


class StreamingFrameFeatures:
    """Incremental frame extractor retaining only the current window carryover."""

    def __init__(self, window_samples: int, hop_samples: int | None = None) -> None:
        if window_samples < 1:
            raise ValueError("window_samples must be positive")
        hop = window_samples if hop_samples is None else hop_samples
        if hop < 1:
            raise ValueError("hop_samples must be positive")
        self.window_samples = int(window_samples)
        self.hop_samples = int(hop)
        self._pending: list[int] = []
        self._pending_start = 0
        self._total_seen = 0
        self._next_start = 0
        self._finished = False

    def feed(self, chunk: Sequence[int]) -> Iterator[dict]:
        if self._finished:
            raise RuntimeError("Cannot feed a finished frame extractor")
        if not chunk:
            return
        self._pending.extend(int(value) for value in chunk)
        self._total_seen += len(chunk)
        while self._next_start + self.window_samples <= self._total_seen:
            offset = self._next_start - self._pending_start
            if offset < 0:
                raise RuntimeError("Internal streaming frame offset underflow")
            frame = self._pending[offset : offset + self.window_samples]
            frame_start = self._next_start
            self._next_start += self.hop_samples
            yield _frame_record(frame, frame_start)
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
            frame_start = self._next_start
            self._next_start += self.hop_samples
            if frame:
                yield _frame_record(frame, frame_start)
        self._pending.clear()


def iter_frame_features_from_chunks(
    chunks: Iterable[Sequence[int]],
    window_samples: int,
    hop_samples: int | None = None,
) -> Iterator[dict]:
    """Yield frames from a chunk stream while retaining only one window of carryover."""
    extractor = StreamingFrameFeatures(window_samples, hop_samples)
    for chunk in chunks:
        yield from extractor.feed(chunk)
    yield from extractor.finish()


class P2Quantile:
    """Constant-memory P² quantile estimator (Jain & Chlamtac), default median."""

    def __init__(self, probability: float = 0.5) -> None:
        if not 0.0 < probability < 1.0:
            raise ValueError("probability must be between 0 and 1")
        self.p = float(probability)
        self._initial: list[float] = []
        self.q: list[float] = []
        self.n: list[int] = []
        self.np: list[float] = []
        self.dn = [0.0, self.p / 2, self.p, (1 + self.p) / 2, 1.0]
        self.count = 0

    def add(self, value: float) -> None:
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Quantile input must be finite")
        self.count += 1
        if len(self._initial) < 5:
            self._initial.append(value)
            if len(self._initial) == 5:
                self._initial.sort()
                self.q = self._initial[:]
                self.n = [1, 2, 3, 4, 5]
                p = self.p
                self.np = [1.0, 1.0 + 2 * p, 1.0 + 4 * p, 3.0 + 2 * p, 5.0]
            return

        if value < self.q[0]:
            self.q[0] = value
            k = 0
        elif value < self.q[1]:
            k = 0
        elif value < self.q[2]:
            k = 1
        elif value < self.q[3]:
            k = 2
        elif value <= self.q[4]:
            k = 3
        else:
            self.q[4] = value
            k = 3

        for i in range(k + 1, 5):
            self.n[i] += 1
        for i in range(5):
            self.np[i] += self.dn[i]

        for i in (1, 2, 3):
            delta = self.np[i] - self.n[i]
            direction = 1 if delta >= 1 and self.n[i + 1] - self.n[i] > 1 else (
                -1 if delta <= -1 and self.n[i - 1] - self.n[i] < -1 else 0
            )
            if direction == 0:
                continue
            left_gap = self.n[i] - self.n[i - 1]
            right_gap = self.n[i + 1] - self.n[i]
            total_gap = self.n[i + 1] - self.n[i - 1]
            parabolic = self.q[i] + direction / total_gap * (
                (left_gap + direction) * (self.q[i + 1] - self.q[i]) / right_gap
                + (right_gap - direction) * (self.q[i] - self.q[i - 1]) / left_gap
            )
            if self.q[i - 1] < parabolic < self.q[i + 1]:
                self.q[i] = parabolic
            else:
                neighbor = i + direction
                self.q[i] += direction * (self.q[neighbor] - self.q[i]) / (self.n[neighbor] - self.n[i])
            self.n[i] += direction

    @property
    def value(self) -> float:
        if not self._initial:
            return 0.0
        if len(self._initial) < 5:
            return float(median(self._initial))
        return self.q[2]


def _validate_detector_parameters(threshold, baseline_multiplier, absolute_floor, merge_gap_frames):
    if not math.isfinite(float(baseline_multiplier)) or baseline_multiplier <= 0:
        raise ValueError("baseline_multiplier must be finite and positive")
    if not math.isfinite(float(absolute_floor)) or absolute_floor < 0:
        raise ValueError("absolute_floor must be finite and non-negative")
    if isinstance(merge_gap_frames, bool) or not isinstance(merge_gap_frames, int) or merge_gap_frames < 0:
        raise ValueError("merge_gap_frames must be a non-negative integer")
    if threshold is not None and (not math.isfinite(float(threshold)) or threshold < 0):
        raise ValueError("threshold must be finite and non-negative")


def detect_energy_events(
    samples: Sequence[int],
    window_samples: int,
    hop_samples: int | None = None,
    threshold: float | None = None,
    baseline_multiplier: float = 3.0,
    absolute_floor: float = 1.0,
    merge_gap_frames: int = 1,
) -> dict:
    """In-memory reference detector retained for small fixtures and comparisons."""
    _validate_detector_parameters(threshold, baseline_multiplier, absolute_floor, merge_gap_frames)
    frames = frame_features(samples, window_samples, hop_samples)
    if not frames:
        return {"threshold": float(threshold if threshold is not None else absolute_floor), "frames": [], "events": []}
    chosen = float(threshold) if threshold is not None else max(
        float(absolute_floor), median(row["rms"] for row in frames) * baseline_multiplier
    )
    groups: list[list[int]] = []
    for idx, row in enumerate(frames):
        if row["rms"] < chosen:
            continue
        if not groups or idx - groups[-1][-1] > merge_gap_frames + 1:
            groups.append([idx])
        else:
            groups[-1].append(idx)
    events = []
    for event_id, group in enumerate(groups, start=1):
        first, last = frames[group[0]], frames[group[-1]]
        peak = max(frames[i]["peak"] for i in group)
        weighted_energy = sum(frames[i]["rms"] ** 2 * frames[i]["sample_count"] for i in group)
        count = sum(frames[i]["sample_count"] for i in group)
        events.append({
            "event_id": event_id,
            "onset_sample": first["start_sample"],
            "end_sample_exclusive": last["end_sample_exclusive"],
            "duration_samples": last["end_sample_exclusive"] - first["start_sample"],
            "peak": peak,
            "rms": math.sqrt(weighted_energy / max(1, count)),
            "frame_indices": group,
            "frame_count": len(group),
            "classification": "energy_activity_candidate",
            "confidence": None,
        })
    return {"threshold": chosen, "frames": frames, "events": events}


class StreamingEnergyEventDetector:
    """Incrementally merge active windows without retaining frame records."""

    def __init__(self, threshold: float, merge_gap_frames: int = 1) -> None:
        _validate_detector_parameters(threshold, 1.0, 0.0, merge_gap_frames)
        self.threshold = float(threshold)
        self.merge_gap_frames = merge_gap_frames
        self.events: list[dict] = []
        self.current = None
        self.last_active_index = -1
        self.frame_count = 0
        self._finished = False

    def _finish_current(self) -> None:
        if self.current is None:
            return
        count = self.current.pop("_energy_sample_count")
        energy = self.current.pop("_energy_sum")
        self.current["event_id"] = len(self.events) + 1
        self.current["duration_samples"] = self.current["end_sample_exclusive"] - self.current["onset_sample"]
        self.current["rms"] = math.sqrt(energy / max(1, count))
        self.current["classification"] = "energy_activity_candidate"
        self.current["confidence"] = None
        self.events.append(self.current)
        self.current = None

    def feed(self, frame: dict) -> None:
        if self._finished:
            raise RuntimeError("Cannot feed a finished event detector")
        index = self.frame_count
        self.frame_count += 1
        if float(frame["rms"]) < self.threshold:
            return
        if self.current is None or index - self.last_active_index - 1 > self.merge_gap_frames:
            self._finish_current()
            self.current = {
                "onset_sample": int(frame["start_sample"]),
                "end_sample_exclusive": int(frame["end_sample_exclusive"]),
                "peak": int(frame["peak"]),
                "frame_count": 1,
                "_energy_sample_count": int(frame["sample_count"]),
                "_energy_sum": float(frame["rms"]) ** 2 * int(frame["sample_count"]),
            }
        else:
            self.current["end_sample_exclusive"] = int(frame["end_sample_exclusive"])
            self.current["peak"] = max(self.current["peak"], int(frame["peak"]))
            self.current["frame_count"] += 1
            self.current["_energy_sample_count"] += int(frame["sample_count"])
            self.current["_energy_sum"] += float(frame["rms"]) ** 2 * int(frame["sample_count"])
        self.last_active_index = index

    def finish(self) -> dict:
        if not self._finished:
            self._finish_current()
            self._finished = True
        return {"threshold": self.threshold, "frame_count": self.frame_count, "events": self.events}


def detect_energy_events_streaming(
    frames: Iterable[dict],
    threshold: float,
    merge_gap_frames: int = 1,
) -> dict:
    """Convenience wrapper for iterable frame features."""
    detector = StreamingEnergyEventDetector(threshold, merge_gap_frames)
    for frame in frames:
        detector.feed(frame)
    return detector.finish()

