import unittest
from krm_stage12 import rle_encode,rle_decode,run_stage12,Config

class Stage12Tests(unittest.TestCase):
 def test_rle_roundtrip_holes(self):
  cells={(0,1),(0,2),(0,4),(2,2),(2,3)}
  self.assertEqual(rle_decode(rle_encode(cells)),cells)
 def fixture(self,grid):
  cells={}
  for (f,b),state in grid.items(): cells[f"{f},{b}"]={"state":state,"power":1e-3,"delta_db":10.0,"local_floor_power":1e-4}
  return {"schema_version":"krm-stage11-normalized-1.0","input_manifest":{"input_id":"synthetic","sample_rate":44100,"fft_size":2048,"hop_size":512,"window":"hann","center_padding":"centered","frame_timestamp_convention":"center","frequency_bin_convention":"rfft","stage11_version":"fixture-1","channel_id":0,"resolution_id":"stft-2048-512","frame_count":8,"bin_count":32},"cells":cells}
 def test_silence_zero_regions(self):
  r=run_stage12(self.fixture({}))
  self.assertEqual(r["validation"]["active_region_count"],0)
  self.assertTrue(r["validation"]["cell_conservation"])
 def test_direct_four_neighbour(self):
  g={(0,4):"S2",(1,4):"S2",(2,4):"S3",(2,5):"S2"}
  r=run_stage12(self.fixture(g))
  self.assertEqual(r["validation"]["active_region_count"],1)
 def test_diagonal_not_connected(self):
  g={(0,1):"S2",(1,2):"S2"}
  r=run_stage12(self.fixture(g))
  self.assertEqual(r["validation"]["active_region_count"],2)
 def test_invalid_not_active_or_bridge(self):
  g={(0,1):"S2",(1,1):"INVALID",(2,1):"S2"}
  r=run_stage12(self.fixture(g))
  self.assertEqual(r["validation"]["active_region_count"],2)
  self.assertTrue(r["validation"]["cell_conservation"])
 def test_temporal_bridge_requires_valid_gap_cells(self):
  g={(0,5):"S2",(1,4):"S0",(1,5):"S0",(1,6):"S0",(2,5):"S2"}
  r=run_stage12(self.fixture(g))
  self.assertEqual(r["validation"]["active_region_count"],1)
  self.assertTrue(any(e.get("stage")=="12-B2" and e.get("status")=="accepted_edge" for e in r["merge_events"]))
 def test_frequency_bridge_requires_valid_gap_cells(self):
  g={(0,5):"S2",(0,6):"S0",(0,7):"S2"}
  r=run_stage12(self.fixture(g))
  self.assertEqual(r["validation"]["active_region_count"],1)
  self.assertTrue(any(e.get("stage")=="12-B3" and e.get("status")=="accepted_edge" for e in r["merge_events"]))
 def test_frequency_bridge_rejects_invalid_gap(self):
  g={(0,5):"S2",(0,7):"S2"}
  r=run_stage12(self.fixture(g))
  self.assertEqual(r["validation"]["active_region_count"],2)
 def test_s1_bridge_keeps_s1_separate(self):
  g={(0,5):"S2",(0,6):"S1",(0,7):"S2"}
  r=run_stage12(self.fixture(g))
  # S1 can only bridge if its normalized activity is sufficiently high.
  self.assertEqual(r["validation"]["active_output_cells"],2)
  self.assertEqual(r["validation"]["active_region_count"],1)
  self.assertEqual(r["merged_regions"][0]["s1_bridge_cell_count"] if "s1_bridge_cell_count" in r["merged_regions"][0] else len(r["merged_regions"][0]["s1_cells"]),1)
  self.assertTrue(r["validation"]["cell_conservation"])
 def test_originals_preserved(self):
  g={(0,1):"S2",(0,2):"S2",(1,1):"S2"}
  r=run_stage12(self.fixture(g))
  self.assertEqual(len(r["original_regions"]),2)
  self.assertEqual(sum(x["cell_count"] for x in r["original_regions"]),3)
 def test_config_safety(self):
  with self.assertRaises(ValueError): Config(max_time_gap_frames=9).validate()

if __name__=="__main__": unittest.main()
