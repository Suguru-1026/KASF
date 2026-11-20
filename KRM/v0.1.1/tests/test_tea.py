import math
import unittest

from krm_proto.tea import detect_transient_candidates, frame_metrics


class TeaTests(unittest.TestCase):
    def test_frame_metrics_known_values(self):
        rows = frame_metrics([3, -4, 0, 0], 4)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["rms"], 2.5)
        self.assertEqual(rows[0]["peak"], 4.0)
        self.assertAlmostEqual(rows[0]["crest_factor"], 1.6)

    def test_impulse_is_candidate(self):
        signal = [0.0] * 64
        signal[32] = 10.0
        result = detect_transient_candidates(
            signal, 8, 8, baseline_frames=2,
            rise_ratio_threshold=2.0, crest_factor_threshold=2.0,
        )
        self.assertTrue(result["events"])
        self.assertIn("high_crest_factor", result["events"][0]["candidate_reasons"])

    def test_constant_tone_has_no_energy_rise_after_initial_frame(self):
        signal = [1.0] * 64
        result = detect_transient_candidates(
            signal, 8, 8, baseline_frames=2,
            rise_ratio_threshold=2.0, crest_factor_threshold=2.0,
        )
        self.assertEqual(result["events"], [])

    def test_zero_signal_is_empty(self):
        result = detect_transient_candidates([0] * 32, 8, 8)
        self.assertEqual(result["events"], [])

    def test_merges_candidates_within_gap(self):
        signal = [0.0] * 64
        signal[16] = 8.0
        signal[32] = 9.0
        result = detect_transient_candidates(
            signal, 8, 8, baseline_frames=1,
            rise_ratio_threshold=2.0, crest_factor_threshold=2.0,
            merge_gap_frames=1,
        )
        self.assertEqual(len(result["events"]), 1)

    def test_rejects_non_finite_samples(self):
        with self.assertRaises(ValueError):
            frame_metrics([0.0, float("nan")], 2)

    def test_rejects_bad_thresholds(self):
        with self.assertRaises(ValueError):
            detect_transient_candidates([0] * 16, 4, rise_ratio_threshold=0)


    def test_streaming_matches_batch_across_irregular_chunks(self):
        from krm_proto.tea import iter_transient_candidates_from_chunks

        signal = [0.0] * 257
        signal[31] = 12.0
        signal[89:121] = [3.0 * ((-1.0) ** i) for i in range(32)]
        signal[198] = -18.0
        kwargs = dict(
            baseline_frames=3,
            rise_ratio_threshold=2.5,
            crest_factor_threshold=4.0,
            absolute_rms_floor=0.1,
            merge_gap_frames=2,
        )
        batch = detect_transient_candidates(signal, 24, 7, **kwargs)["events"]
        chunks = [signal[:1], [], signal[1:19], signal[19:76], signal[76:77], signal[77:203], signal[203:]]
        streamed = list(iter_transient_candidates_from_chunks(chunks, 24, 7, **kwargs))
        self.assertEqual(streamed, batch)

    def test_streaming_matches_batch_when_hop_exceeds_window(self):
        from krm_proto.tea import iter_transient_candidates_from_chunks

        signal = [0] * 100
        signal[30] = 100
        signal[75] = 80
        kwargs = dict(baseline_frames=2, rise_ratio_threshold=2, crest_factor_threshold=2)
        batch = detect_transient_candidates(signal, 8, 13, **kwargs)["events"]
        streamed = list(iter_transient_candidates_from_chunks(
            [signal[:5], signal[5:40], signal[40:41], signal[41:]], 8, 13, **kwargs
        ))
        self.assertEqual(streamed, batch)

    def test_large_finite_samples_do_not_overflow_metrics(self):
        rows = frame_metrics([1e308, -1e308, 1e308, -1e308], 4)
        self.assertTrue(all(
            math.isfinite(rows[0][key])
            for key in ("rms", "peak", "mean_abs", "crest_factor")
        ))
        self.assertAlmostEqual(rows[0]["rms"], 1e308)

    def test_rejects_boolean_geometry_and_thresholds(self):
        with self.assertRaises(ValueError):
            frame_metrics([1, 2], True)
        with self.assertRaises(ValueError):
            detect_transient_candidates([1, 2], 2, rise_ratio_threshold=True)

    def test_streaming_empty_input_has_no_candidates(self):
        from krm_proto.tea import iter_transient_candidates_from_chunks
        self.assertEqual(list(iter_transient_candidates_from_chunks([], 16)), [])


if __name__ == "__main__":
    unittest.main()
