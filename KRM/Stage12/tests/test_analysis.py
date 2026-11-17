import unittest
from krm_proto.candidates import ComponentProposal, FrequencyCandidate
from krm_proto.events import (
    P2Quantile,
    detect_energy_events,
    detect_energy_events_streaming,
    frame_features,
    iter_frame_features_from_chunks,
)


class AnalysisTests(unittest.TestCase):
    def test_energy_event_probe(self):
        signal = [0] * 64 + [20] * 64 + [0] * 64
        result = detect_energy_events(signal, window_samples=16, hop_samples=16, threshold=5)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["onset_sample"], 64)

    def test_candidate_validation(self):
        candidate = FrequencyCandidate(
            candidate_id=1,
            start_sample=100,
            end_sample_exclusive=300,
            center_freq_hz=1000.0,
            amplitude=0.1,
            phase_rad=0.0,
            chirp_rate_hz_s=12.0,
            bandwidth_hz=30.0,
            confidence=0.8,
            phase_reference_sample=100,
            component_proposals=(
                ComponentProposal(100, 0, 990.0, 0.08, 0.0, 0.9),
                ComponentProposal(200, 0, 1010.0, 0.07, 0.1, 0.8),
            ),
        )
        candidate.validate(sample_rate_hz=48000, total_samples=1000)
        self.assertEqual(len(candidate.to_dict()["component_proposals"]), 2)
        invalid = FrequencyCandidate(2, 0, 100, 30000, 0.1, 0, 0, 0, 0.5)
        with self.assertRaises(ValueError):
            invalid.validate(sample_rate_hz=48000, total_samples=1000)

    def test_component_proposals_must_be_sorted_and_in_range(self):
        candidate = FrequencyCandidate(
            1, 10, 100, 1000, 0.1, 0, 0, 0, 0.8,
            component_proposals=(
                ComponentProposal(20, 0, 1000, 0.1, 0, 0.8),
                ComponentProposal(20, 0, 1010, 0.1, 0, 0.8),
            ),
        )
        with self.assertRaisesRegex(ValueError, "uniquely sorted"):
            candidate.validate(48000, 1000)

    def test_streamed_frames_match_in_memory_across_chunk_edges(self):
        signal = [((i * 73) % 101) - 50 for i in range(103)]
        for window, hop in ((16, 8), (17, 17), (9, 23), (31, 7)):
            chunks = [signal[:3], signal[3:29], signal[29:30], signal[30:77], signal[77:]]
            streamed = list(iter_frame_features_from_chunks(chunks, window, hop))
            reference = frame_features(signal, window, hop)
            self.assertEqual(streamed, reference)

    def test_streaming_events_match_reference_summary(self):
        signal = [0] * 64 + [20] * 64 + [0] * 64 + [0] * 32 + [30] * 64
        reference = detect_energy_events(signal, 16, 16, threshold=5, merge_gap_frames=1)
        streamed_frames = iter_frame_features_from_chunks([signal[:33], signal[33:96], signal[96:]], 16, 16)
        streamed = detect_energy_events_streaming(streamed_frames, threshold=5, merge_gap_frames=1)
        self.assertEqual(len(streamed["events"]), len(reference["events"]))
        for actual, expected in zip(streamed["events"], reference["events"]):
            for key in ("onset_sample", "end_sample_exclusive", "duration_samples", "peak", "frame_count"):
                self.assertEqual(actual[key], expected[key])
            self.assertAlmostEqual(actual["rms"], expected["rms"])

    def test_p2_median_estimate_is_reasonable(self):
        estimator = P2Quantile(0.5)
        values = list(range(1, 10_002))
        for value in values:
            estimator.add(value)
        self.assertLess(abs(estimator.value - 5001.5), 100)


if __name__ == "__main__":
    unittest.main()
