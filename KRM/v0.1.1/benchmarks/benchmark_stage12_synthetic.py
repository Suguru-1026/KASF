#!/usr/bin/env python3
"""Reproducible Stage12 sparse-grid smoke benchmark; not an acceptance proof."""
import argparse, json, random, time, tracemalloc, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from krm_stage12 import run_stage12


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--frames',type=int,default=80)
    p.add_argument('--bins',type=int,default=192)
    p.add_argument('--active-probability',type=float,default=.12)
    p.add_argument('--seed',type=int,default=20261117)
    p.add_argument('--output',default='stage12_synthetic_benchmark.json')
    a=p.parse_args()
    if a.frames<1 or a.bins<1 or not 0<=a.active_probability<=1: raise SystemExit('invalid benchmark geometry/probability')
    rng=random.Random(a.seed); cells={}
    for f in range(a.frames):
        for b in range(a.bins):
            active=rng.random()<a.active_probability; state='S2' if active else 'S0'
            cells[f'{f},{b}']={'state':state,'power':1e-3 if active else 1e-8,
                'delta_db':10.0 if active else -40.0,'local_floor_power':1e-4}
    data={'schema_version':'krm-stage11-normalized-1.0','input_manifest':{
        'input_id':f'synthetic-{a.frames}x{a.bins}-seed-{a.seed}','sample_rate':44100,
        'fft_size':2048,'hop_size':512,'window':'hann','center_padding':'centered',
        'frame_timestamp_convention':'center','frequency_bin_convention':'rfft',
        'stage11_version':'synthetic-benchmark-1','channel_id':0,
        'resolution_id':'stft-2048-512','frame_count':a.frames,'bin_count':a.bins},'cells':cells}
    tracemalloc.start(); start=time.perf_counter(); result=run_stage12(data); elapsed=time.perf_counter()-start
    current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    report={'benchmark':'KRM-Stage12-sparse-grid-smoke-1.0','seed':a.seed,'frames':a.frames,'bins':a.bins,
        'grid_cells':a.frames*a.bins,'active_probability':a.active_probability,
        'active_cells':result['validation']['active_input_cells'],
        'original_regions':result['validation']['original_region_count'],
        'active_regions':result['validation']['active_region_count'],
        'elapsed_seconds':elapsed,'python_tracemalloc_peak_bytes':peak,
        'python_tracemalloc_peak_mib':peak/1024/1024,
        'cell_conservation':result['validation']['cell_conservation'],
        'canonical_result_hash':result['run_manifest']['canonical_result_hash'],
        'limitations':['tracemalloc is not process RSS','single synthetic seed/config','not a 512 MiB enforcement test','not real-audio accuracy validation']}
    Path(a.output).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__': main()
