import unittest
from krm_stage12 import Config, run_stage12, rollback_stage12, canonical_result_hash, replay_stage12


def fixture(grid):
    cells = {}
    for (f, b), state in grid.items():
        cells[f"{f},{b}"] = {"state": state, "power": 1e-3, "delta_db": 10.0, "local_floor_power": 1e-4}
    return {
        "schema_version": "krm-stage11-normalized-1.0",
        "input_manifest": {
            "input_id": "integration-fixture", "sample_rate": 44100, "fft_size": 2048,
            "hop_size": 512, "window": "hann", "center_padding": "centered",
            "frame_timestamp_convention": "center", "frequency_bin_convention": "rfft",
            "stage11_version": "fixture-1", "channel_id": 0,
            "resolution_id": "stft-2048-512", "frame_count": 8, "bin_count": 32,
        },
        "cells": cells,
    }


class Stage12IntegrationTests(unittest.TestCase):
    def test_canonical_hash_repeatable(self):
        data = fixture({(0, 4): "S2", (1, 4): "S2", (2, 4): "S2"})
        a = run_stage12(data)
        b = replay_stage12(data)
        self.assertEqual(canonical_result_hash(a), canonical_result_hash(b))
        self.assertEqual(a["run_manifest"]["canonical_result_hash"], b["run_manifest"]["canonical_result_hash"])

    def test_full_rollback_restores_original_regions(self):
        data = fixture({(0, 4): "S2", (1, 4): "S2", (2, 4): "S2"})
        result = run_stage12(data)
        rolled = rollback_stage12(data, result)
        self.assertEqual(len(rolled["merged_regions"]), len(result["original_regions"]))
        self.assertEqual(rolled["rollback_history"][-1]["action"], "full_rollback")
        self.assertFalse(rolled["rollback_history"][-1]["raw_pcm_mutated"])

    def test_partial_rollback_restores_only_selected_region_members(self):
        data = fixture({(0, 2): "S2", (1, 1): "S0", (1, 2): "S0", (1, 3): "S0", (2, 2): "S2", (5, 20): "S2"})
        result = run_stage12(data)
        target = next(r for r in result["merged_regions"] if len(r.get("member_original_ids", [])) > 1)
        rolled = rollback_stage12(data, result, target["region_id"])
        self.assertEqual(rolled["rollback_history"][-1]["action"], "partial_region_rollback")
        self.assertTrue(any(r["region_id"].startswith("OR-") for r in rolled["merged_regions"]))
        self.assertEqual(len(rolled["merged_regions"]), 3)

    def test_config_rejects_nonfinite_and_boolean_values(self):
        with self.assertRaises(ValueError):
            Config(bridge_score_min=float("nan")).validate()
        with self.assertRaises(ValueError):
            Config(max_time_gap_frames=True).validate()

    def test_invalid_numeric_metadata_rejected(self):
        data = fixture({(0, 1): "S2"})
        data["cells"]["0,1"]["delta_db"] = float("inf")
        with self.assertRaises(ValueError):
            run_stage12(data)


if __name__ == "__main__":
    unittest.main()
