"""Draft 0.5 acceptance-oriented synthetic cases (behavioral, not quality proof)."""
import unittest
from krm_stage12 import run_stage12, rle_decode


def make_input(states, frames=16, bins=32):
    cells = {}
    for (f, b), state in states.items():
        rec = {"state": state}
        if state in {"S1", "S2", "S3"}:
            rec.update(power=1e-3, local_floor_power=1e-4, delta_db=10.0)
        elif state == "S0":
            rec.update(power=1e-8, local_floor_power=1e-4, delta_db=-40.0)
        cells[f"{f},{b}"] = rec
    return {"schema_version":"krm-stage11-normalized-1.0", "input_manifest":{
        "input_id":"acceptance-synthetic", "sample_rate":44100, "fft_size":2048,
        "hop_size":512, "window":"hann", "center_padding":"centered",
        "frame_timestamp_convention":"center", "frequency_bin_convention":"rfft",
        "stage11_version":"synthetic-ground-truth-1", "channel_id":0,
        "resolution_id":"stft-2048-512", "frame_count":frames, "bin_count":bins}, "cells":cells}


class Stage12AcceptanceCases(unittest.TestCase):
    def test_01_digital_silence(self):
        r=run_stage12(make_input({}))
        self.assertEqual(r["validation"]["active_region_count"],0)
        self.assertTrue(r["validation"]["cell_conservation"])

    def test_02_stationary_noise_is_conserved_and_bounded(self):
        s={(f,b):"S2" for f in range(8) for b in range(0,24) if (f*7+b*11)%5 in (0,1)}
        r=run_stage12(make_input(s))
        self.assertEqual(r["validation"]["active_input_cells"],r["validation"]["active_output_cells"])
        self.assertLessEqual(r["validation"]["active_region_count"],len(s))

    def test_03_persistent_tone_is_tonal_candidate(self):
        s={(f,12):"S2" for f in range(12)}
        r=run_stage12(make_input(s))
        labels=r["classifications"][0]["labels"]
        self.assertIn("Tonal",labels)

    def test_04_short_impulse_is_transient_candidate(self):
        s={(5,b):"S3" for b in range(8,16)}
        r=run_stage12(make_input(s))
        self.assertIn("Transient",r["classifications"][0]["labels"])

    def test_05_chirp_like_track_stays_connected_when_4_neighbour_path_exists(self):
        s={}
        for f in range(8):
            b=5+f//2
            s[(f,b)]="S2"
            if f % 2 == 1 and f < 7:
                s[(f,b+1)]="S2"
        r=run_stage12(make_input(s))
        self.assertEqual(r["validation"]["active_region_count"],1)

    def test_06_intermittent_tone_temporal_bridge(self):
        s={(0,12):"S2",(2,12):"S2"}
        for b in (11,12,13): s[(1,b)]="S0"
        r=run_stage12(make_input(s))
        self.assertEqual(r["validation"]["active_region_count"],1)
        self.assertTrue(any(e["stage"]=="12-B2" and e["status"]=="accepted_edge" for e in r["merge_events"]))

    def test_07_nearby_distinct_tones_outside_gap_limit_do_not_merge(self):
        s={(f,8):"S2" for f in range(8)} | {(f,12):"S2" for f in range(8)}
        for f in range(8):
            for b in (9,10,11): s[(f,b)]="S0"
        r=run_stage12(make_input(s))
        self.assertEqual(r["validation"]["active_region_count"],2)

    def test_08_s1_bridge_uses_linear_power_not_delta_db_as_power(self):
        s={(4,10):"S2",(4,11):"S1",(4,12):"S2"}
        data=make_input(s)
        data["cells"]["4,11"]["power"]=1e-3
        data["cells"]["4,11"]["local_floor_power"]=1e-4
        r=run_stage12(data)
        e=[e for e in r["merge_events"] if e["stage"]=="12-B4" and e["status"]=="accepted"]
        self.assertEqual(len(e),1)
        self.assertEqual(e[0]["s1_cells"],[[4,11]])

    def test_09_broadband_burst_has_diffuse_or_transient_structure(self):
        s={(5,b):"S3" for b in range(2,25)}
        r=run_stage12(make_input(s))
        labels=r["classifications"][0]["labels"]
        self.assertTrue("Diffuse" in labels or "Transient" in labels)

    def test_10_ring_shape_preserves_hole(self):
        s={(f,b):"S2" for f in range(3) for b in range(3) if (f,b)!=(1,1)}
        r=run_stage12(make_input(s,frames=4,bins=4))
        shape=set()
        for run in r["merged_regions"][0]["observed_shape_rle"]:
            f,a,z=run
            shape.update((f,b) for b in range(a,z))
        self.assertEqual(len(shape),8)
        self.assertNotIn((1,1),shape)

    def test_11_l_shape_connects_but_diagonal_only_does_not(self):
        l=run_stage12(make_input({(0,0):"S2",(1,0):"S2",(1,1):"S2"},frames=3,bins=3))
        d=run_stage12(make_input({(0,0):"S2",(1,1):"S2"},frames=3,bins=3))
        self.assertEqual(l["validation"]["active_region_count"],1)
        self.assertEqual(d["validation"]["active_region_count"],2)

    def test_12_frequency_bridge_requires_temporal_overlap(self):
        s={(0,4):"S2",(0,6):"S2",(0,5):"S0"}
        r=run_stage12(make_input(s))
        self.assertEqual(r["validation"]["active_region_count"],1)

    def test_13_competing_s1_paths_choose_one_deterministically(self):
        s={(2,2):"S2",(3,3):"S2",(2,3):"S1",(3,2):"S1"}
        r=run_stage12(make_input(s,frames=5,bins=5))
        accepted=[e for e in r["merge_events"] if e["stage"]=="12-B4" and e["status"]=="accepted"]
        self.assertEqual(len(accepted),1)
        self.assertEqual(len(accepted[0]["s1_cells"]),1)

    def test_14_invalid_gap_is_never_bridgeable(self):
        s={(0,8):"S2",(1,7):"S0",(1,8):"INVALID",(1,9):"S0",(2,8):"S2"}
        r=run_stage12(make_input(s))
        self.assertEqual(r["validation"]["active_region_count"],2)

    def test_15_rle_roundtrip_and_observed_cell_conservation(self):
        s={(f,b):"S2" for f in range(4) for b in range(2,6) if (f,b)!=(2,4)}
        r=run_stage12(make_input(s))
        self.assertTrue(r["validation"]["rle_roundtrip"])
        self.assertEqual(r["validation"]["active_input_cells"],r["validation"]["active_output_cells"])
        for reg in r["merged_regions"]:
            self.assertEqual(len(rle_decode(reg["observed_shape_rle"])),reg["observed_cell_count"])

    def test_16_events_have_stable_ids_and_lineage(self):
        s={(0,5):"S2",(1,4):"S0",(1,5):"S0",(1,6):"S0",(2,5):"S2"}
        r=run_stage12(make_input(s))
        ids=[e["event_id"] for e in r["merge_events"]]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(all(e["run_id"]==r["run_manifest"]["run_id"] for e in r["merge_events"]))
        self.assertTrue(all(reg["member_original_ids"] for reg in r["merged_regions"]))


if __name__=="__main__": unittest.main()
