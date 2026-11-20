"""KRM-FC metadata and frame-level KASF component proposal validation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math


def _integer(value, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _finite(value, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


@dataclass(frozen=True)
class ComponentProposal:
    """One frame/channel proposal; this is not yet a serialized KASF Component."""

    frame_start_sample: int
    channel_index: int
    frequency_hz: float
    amplitude_linear: float
    phase_rad: float
    confidence: float = 0.5

    def validate(self, sample_rate_hz: int, total_samples: int, channel_count: int, candidate_start: int, candidate_end: int) -> None:
        _integer(self.frame_start_sample, "frame_start_sample")
        _integer(self.channel_index, "channel_index")
        if not candidate_start <= self.frame_start_sample < candidate_end <= total_samples:
            raise ValueError("Component proposal frame is outside its candidate interval")
        if self.channel_index >= channel_count:
            raise ValueError("Component proposal channel is outside the signal")
        frequency = _finite(self.frequency_hz, "frequency_hz")
        amplitude = _finite(self.amplitude_linear, "amplitude_linear")
        phase = _finite(self.phase_rad, "phase_rad")
        confidence = _finite(self.confidence, "confidence")
        if not 0.0 <= frequency <= sample_rate_hz / 2:
            raise ValueError("Proposal frequency must be within Nyquist range")
        if amplitude < 0:
            raise ValueError("Proposal amplitude must be non-negative")
        if not -math.pi - 1e-9 <= phase <= math.pi + 1e-9:
            raise ValueError("Proposal phase must be in [-pi, pi]")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("Proposal confidence must be between 0 and 1")


@dataclass(frozen=True)
class FrequencyCandidate:
    candidate_id: int
    start_sample: int
    end_sample_exclusive: int
    center_freq_hz: float
    amplitude: float
    phase_rad: float
    chirp_rate_hz_s: float
    bandwidth_hz: float
    confidence: float
    source_event_id: int | None = None
    parent_kasf_revision: str | None = None
    parent_residual_revision: str | None = None
    phase_reference_sample: int | None = None
    component_proposals: tuple[ComponentProposal, ...] = field(default_factory=tuple)

    def validate(self, sample_rate_hz: int, total_samples: int, channel_count: int = 1) -> None:
        _integer(self.candidate_id, "candidate_id")
        _integer(sample_rate_hz, "sample_rate_hz", 1)
        _integer(total_samples, "total_samples")
        _integer(channel_count, "channel_count", 1)
        _integer(self.start_sample, "start_sample")
        _integer(self.end_sample_exclusive, "end_sample_exclusive", 1)
        if not (0 <= self.start_sample < self.end_sample_exclusive <= total_samples):
            raise ValueError("Candidate sample interval is outside the signal")
        center = _finite(self.center_freq_hz, "center_freq_hz")
        amplitude = _finite(self.amplitude, "amplitude")
        phase = _finite(self.phase_rad, "phase_rad")
        _finite(self.chirp_rate_hz_s, "chirp_rate_hz_s")
        bandwidth = _finite(self.bandwidth_hz, "bandwidth_hz")
        confidence = _finite(self.confidence, "confidence")
        nyquist = sample_rate_hz / 2
        if not 0.0 <= center <= nyquist:
            raise ValueError("Center frequency must be within Nyquist range")
        if amplitude < 0 or bandwidth < 0 or bandwidth > 2 * nyquist:
            raise ValueError("Amplitude or bandwidth is outside its valid range")
        if center - bandwidth / 2 < 0 or center + bandwidth / 2 > nyquist:
            raise ValueError("Candidate bandwidth extends outside the Nyquist interval")
        if not -math.pi - 1e-9 <= phase <= math.pi + 1e-9:
            raise ValueError("Phase must be in [-pi, pi]")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("Confidence must be between 0 and 1")
        if self.source_event_id is not None:
            _integer(self.source_event_id, "source_event_id")
        if self.phase_reference_sample is not None:
            _integer(self.phase_reference_sample, "phase_reference_sample")
            if not self.start_sample <= self.phase_reference_sample < self.end_sample_exclusive:
                raise ValueError("Phase reference must lie within the candidate interval")
        for name, value in (("parent_kasf_revision", self.parent_kasf_revision), ("parent_residual_revision", self.parent_residual_revision)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string when supplied")

        previous_key = None
        for proposal in self.component_proposals:
            if not isinstance(proposal, ComponentProposal):
                raise ValueError("component_proposals must contain ComponentProposal records")
            proposal.validate(sample_rate_hz, total_samples, channel_count, self.start_sample, self.end_sample_exclusive)
            key = (proposal.frame_start_sample, proposal.channel_index)
            if previous_key is not None and key <= previous_key:
                raise ValueError("Component proposals must be uniquely sorted by frame and channel")
            previous_key = key

    def to_dict(self) -> dict:
        return asdict(self)
