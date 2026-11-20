"""Lossless integer prediction experiments; these do not compress data."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PredictedChannel:
    sample_count: int
    seed: list[int]
    innovations: list[int]
    order: int


def encode_predictive_channel(samples: list[int], order: int = 2) -> PredictedChannel:
    """Encode with an integer linear predictor and exact innovations.

    order=1: prediction is previous sample.
    order=2: prediction is 2*previous - second_previous.

    The innovations remain signed Python integers. This is a predictor demo,
    not entropy coding or compression.
    """
    if order not in (1, 2):
        raise ValueError("Prototype predictor supports order 1 or 2")
    seed_count = min(order, len(samples))
    seed = [int(x) for x in samples[:seed_count]]
    innovations: list[int] = []
    for i in range(seed_count, len(samples)):
        if order == 1:
            prediction = int(samples[i - 1])
        else:
            prediction = 2 * int(samples[i - 1]) - int(samples[i - 2])
        innovations.append(int(samples[i]) - prediction)
    return PredictedChannel(len(samples), seed, innovations, order)


def decode_predictive_channel(encoded: PredictedChannel) -> list[int]:
    if encoded.order not in (1, 2):
        raise ValueError("Unsupported predictor order")
    if len(encoded.seed) != min(encoded.order, encoded.sample_count):
        raise ValueError("Invalid predictor seed")
    expected_innovations = encoded.sample_count - len(encoded.seed)
    if len(encoded.innovations) != expected_innovations:
        raise ValueError("Innovation count mismatch")
    output = list(encoded.seed)
    for innovation in encoded.innovations:
        if encoded.order == 1:
            prediction = output[-1]
        else:
            prediction = 2 * output[-1] - output[-2]
        output.append(prediction + int(innovation))
    return output


class StreamingPredictorVerifier:
    """Carry exact integer predictor state across arbitrary chunk boundaries."""

    def __init__(self, order: int = 2) -> None:
        if order not in (1, 2):
            raise ValueError("Prototype predictor supports order 1 or 2")
        self.order = order
        self.history: list[int] = []
        self.sample_count = 0
        self.innovation_count = 0
        self.max_abs_innovation = 0
        self.exact = True
        self._finished = False

    def feed(self, chunk) -> None:
        if self._finished:
            raise RuntimeError("Cannot feed a finished predictor verifier")
        for raw_value in chunk:
            value = int(raw_value)
            self.sample_count += 1
            if len(self.history) < self.order:
                self.history.append(value)
                continue
            if self.order == 1:
                prediction = self.history[-1]
            else:
                prediction = 2 * self.history[-1] - self.history[-2]
            innovation = value - prediction
            reconstructed = prediction + innovation
            self.exact = self.exact and reconstructed == value
            self.max_abs_innovation = max(self.max_abs_innovation, abs(innovation))
            self.innovation_count += 1
            self.history.append(reconstructed)
            if len(self.history) > self.order:
                del self.history[0]

    def finish(self) -> dict:
        self._finished = True
        return {
            "order": self.order,
            "sample_count": self.sample_count,
            "seed_count": min(self.order, self.sample_count),
            "innovation_count": self.innovation_count,
            "max_abs_innovation": self.max_abs_innovation,
            "exact": self.exact,
            "compression": False,
        }


def verify_predictive_chunks(chunks, order: int = 2) -> dict:
    """Verify an integer predictor over a chunk stream without retaining samples."""
    verifier = StreamingPredictorVerifier(order)
    for chunk in chunks:
        verifier.feed(chunk)
    return verifier.finish()
