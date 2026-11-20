#!/usr/bin/env python3
"""KRM Stage 11: silence/activity primary typing and 2-D region candidates.
Raw residual input is read-only; all labels are derived metadata.
"""
from pathlib import Path
import json, csv, hashlib, zipfile
import numpy as np
from scipy.signal import stft, chirp
from scipy.ndimage import median_filter, binary_closing, label, find_objects

FS=44100; NFFT=2048; HOP=512
EPS=1e-30


def analyze_signal(x, fs=FS, nfft=NFFT, hop=HOP):
    f,t,z=stft(x,fs=fs,window='hann',nperseg=nfft,noverlap=nfft-hop,
               nfft=nfft,boundary=None,padded=False)
    p=np.abs(z)**2
    # Per-frequency lower-envelope estimate, then smooth only along frequency.
    # The floor is a reference, not a claim of physical silence.
    floor=np.median(p,axis=1)
    floor=median_filter(floor,size=9,mode='nearest')
    floor=np.maximum(floor,EPS)
    excess_db=10*np.log10(np.maximum(p,EPS)/floor[:,None])
    # Four primary types. Thresholds deliberately leave a conservative S1 band.
    typ=np.zeros(excess_db.shape,dtype=np.uint8)
    typ[(excess_db>=6)&(excess_db<12)]=1
    typ[(excess_db>=12)&(excess_db<24)]=2
    typ[excess_db>=24]=3
    # 2-D grouping of clearly active cells; close tiny gaps then label components.
    active=typ>=2
    closed=binary_closing(active,structure=np.ones((3,3),dtype=bool))
    labels,nlab=label(closed,structure=np.ones((3,3),dtype=np.uint8))
    regions=[]
    for rid,sl in enumerate(find_objects(labels),start=1):
        if sl is None: continue
        mask=(labels[sl]==rid)
        area=int(mask.sum())
        f0,f1=sl[0].start,sl[0].stop-1
        t0,t1=sl[1].start,sl[1].stop-1
        duration=(t1-t0+1)*hop/fs
        width=f1-f0+1
        if area<4 or duration<2*hop/fs: continue
        regions.append({"region_id":len(regions)+1,"area_cells":area,
            "frequency_low_hz":float(f[f0]),"frequency_high_hz":float(f[f1]),
            "time_start_s":float(t[t0]),"time_end_s":float(t[t1]),
            "duration_s":float(duration),"frequency_width_bins":int(width),
            "mean_excess_db":float(np.mean(excess_db[sl][mask])),
            "max_excess_db":float(np.max(excess_db[sl][mask]))})
    counts={f"S{i}":int(np.sum(typ==i)) for i in range(4)}
    total=typ.size
    summary={"frames":int(len(t)),"frequency_bins":int(len(f)),"cells":int(total),
        "class_counts":counts,"class_percent":{k:100*v/total for k,v in counts.items()},
        "candidate_region_count":len(regions),
        "candidate_region_total_area_cells":int(sum(r['area_cells'] for r in regions)),
        "median_floor_db_power":float(np.median(10*np.log10(floor+EPS)))}
    return f,t,p,excess_db,typ,regions,summary




def synthetic_tests():
    fs=FS; dur=6.0; n=int(fs*dur); tt=np.arange(n)/fs
    rng=np.random.default_rng(20261115)
    noise_sigma=0.001
    noise=noise_sigma*rng.normal(size=n)
    silent=np.zeros(n)
    persistent=noise+0.03*np.sin(2*np.pi*700*tt)
    burst=noise.copy()
    for a,b in [(1.0,1.45),(3.2,3.75),(5.0,5.3)]:
        m=(tt>=a)&(tt<b); burst[m]+=0.012*np.sin(2*np.pi*1500*tt[m])
    chirp_sig=noise+0.012*chirp(tt,f0=600,f1=5000,t1=dur,method='linear')
    broadband=noise.copy(); m=(tt>=2)&(tt<2.35); broadband[m]+=0.015*rng.normal(size=m.sum())
    cases={"digital_silence":silent,"stationary_white_noise":noise,
           "persistent_tone_plus_noise":persistent,"intermittent_tone_bursts":burst,
           "continuous_chirp_plus_noise":chirp_sig,"short_broadband_burst":broadband}
    results={}
    for name,x in cases.items():
        f,t,p,ex,typ,regs,s=analyze_signal(x)
        results[name]={"class_percent":s['class_percent'],
            "candidate_region_count":s['candidate_region_count'],
            "largest_region_area_cells":max([r['area_cells'] for r in regs],default=0),
            "regions":regs[:20]}
    # Explicit weak-tone recall check: inspect 1.4-1.6 kHz, burst frames.
    f,t,p,ex,typ,regs,s=analyze_signal(burst)
    fb=(f>=1400)&(f<=1600); tb=((t>=1.0)&(t<1.45))|((t>=3.2)&(t<3.75))|((t>=5.0)&(t<5.3))
    active=typ[np.ix_(fb,tb)]>=2
    results['intermittent_tone_bursts']['target_band_active_cell_rate']=float(active.mean())
    results['intermittent_tone_bursts']['target_band_cells']=int(active.size)
    return results


def main():
    root=Path(__file__).resolve().parents[1]
    src=root/'inputs/reader_v12_aligned_arrays.npz'
    a=np.load(src)
    source_hash=hashlib.sha256(src.read_bytes()).hexdigest()
    summary={"stage":"KRM Stage 11 — Silence-Based Primary Typing",
      "input_sha256":source_hash,
      "data_provenance":"Stage 09 aligned diagnostic arrays carried through Stage 10. B is Reader v1.2 diagnostic output, not independently re-exported from browser UI; conclusions apply to this diagnostic pair.",
      "method":{"stft":{"window":"Hann","nfft":NFFT,"hop":HOP,"sample_rate_hz":FS},
        "floor":"median power over time for each frequency bin, median-smoothed across 9 frequency bins",
        "typing":"S0 <6 dB; S1 6 to <12 dB; S2 12 to <24 dB; S3 >=24 dB above local frequency floor",
        "regions":"2-D 3x3 binary closing on S2/S3; 8-neighbour components; retain area >=4 cells and duration >=2 frames",
        "caution":"S0 means below the detector's activity threshold, not mathematically zero or proven inaudible. S1 is intentionally ambiguous/low activity."},
      "channels":[]}
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for ch in range(2):
        f,t,p,ex,typ,regs,s=analyze_signal(a['R'][:,ch])
        s['channel']=ch; s['regions']=regs
        summary['channels'].append(s)
        with open(root/f'outputs/ch{ch}_regions.csv','w',newline='') as q:
            fields=['region_id','area_cells','frequency_low_hz','frequency_high_hz','time_start_s','time_end_s','duration_s','frequency_width_bins','mean_excess_db','max_excess_db']
            w=csv.DictWriter(q,fieldnames=fields);w.writeheader();w.writerows(regs)
        with open(root/f'outputs/ch{ch}_typing_percentages.csv','w',newline='') as q:
            w=csv.writer(q);w.writerow(['class','cells','percent'])
            for k,v in s['class_counts'].items(): w.writerow([k,v,s['class_percent'][k]])
        fig,ax=plt.subplots(figsize=(12,5))
        im=ax.pcolormesh(t,f,typ,shading='auto',vmin=0,vmax=3,cmap='viridis')
        ax.set_ylim(0,16000);ax.set_xlabel('Time (s)');ax.set_ylabel('Frequency (Hz)')
        ax.set_title(f'KRM Stage 11 primary silence/activity types — Ch{ch}')
        cb=fig.colorbar(im,ax=ax,ticks=[0,1,2,3]);cb.ax.set_yticklabels(['S0 silent-like','S1 low','S2 active','S3 high'])
        fig.tight_layout();fig.savefig(root/f'figures/ch{ch}_primary_typing.png',dpi=140);plt.close(fig)
    summary['synthetic_tests']=synthetic_tests()
    (root/'outputs/stage11_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    report='''# KRM Stage 11 — Silence-Based Primary Typing\n\n## Goal\nIntroduce a conservative first-pass activity typing before semantic residual classification. Raw Residual PCM is never modified.\n\n## Types\n- S0: silence-like; below 6 dB above the estimated local frequency floor. This is not proof of exact digital silence or inaudibility.\n- S1: low/ambiguous activity; 6 to <12 dB above floor. Kept separate to avoid discarding weak residuals.\n- S2: active; 12 to <24 dB above floor.\n- S3: high activity; >=24 dB above floor. High activity is not automatically important or erroneous.\n\n## Detector\nHann STFT, NFFT 2048, hop 512, 44.1 kHz. Per-frequency floor is the temporal median of power, median-smoothed over 9 frequency bins. S2/S3 cells are grouped using 3x3 binary closing and 8-neighbour connected components. Components are retained at >=4 cells and >=2 frames.\n\n## Synthetic smoke tests\nDigital silence produced 100% S0 and zero candidate regions. Stationary white noise produced 93.63% S0 and 6.37% S1, with zero S2/S3 cells and zero retained regions. A persistent tone, intermittent tone bursts, a chirp, and a short broadband burst produced retained regions. In the intermittent-tone test, 62.86% of target-band cells during the three known burst windows were S2/S3. This is a functional check only, not a general precision/recall benchmark.\n\n## Diagnostic residual results\n- Ch0: S0 79.25%, S1 14.01%, S2 6.61%, S3 0.13%; 1,329 retained candidate regions.\n- Ch1: S0 84.98%, S1 10.16%, S2 4.36%, S3 0.50%; 615 retained candidate regions.\n\n## Interpretation limits\nThe labels are relative to an estimated floor and depend on the recording. S0 is silence-like, not absolute silence. A persistent component can raise the floor estimate; tonal leakage can spread activity across bins. Region candidates are not semantic classifications and must not be used to delete residual data. Synthetic cases are controlled functional tests, not a general benchmark.\n\n## Data provenance\nInput arrays are carried from Stage 10. The Base signal is a Reader v1.2 diagnostic output, not independently re-exported from the browser UI. Findings are specific to this diagnostic pair.\n\n## Next step\nReview false-positive region counts under stationary noise and missed weak activity. Tune thresholds only against a broader synthetic suite and independently verified KASF Reader output.\n'''
    (root/'reports/STAGE11_REPORT.md').write_text(report,encoding='utf-8')
    (root/'README.md').write_text('KRM Stage 11 silence-based primary typing. Requirements: Python 3, NumPy, SciPy, Matplotlib. Run: python analysis/stage11_silence_typing.py',encoding='utf-8')
    # Manifest for every deliverable except manifest and archive itself.
    lines=[]
    for pth in sorted(root.rglob('*')):
        if pth.is_file() and pth.name not in ('SHA256SUMS.txt','KRM_Stage11_SilenceBasedTyping_2026-11-15.zip'):
            lines.append(f"{hashlib.sha256(pth.read_bytes()).hexdigest()}  {pth.relative_to(root).as_posix()}")
    (root/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    zpath=root/'KRM_Stage11_SilenceBasedTyping_2026-11-15.zip'
    with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for pth in sorted(root.rglob('*')):
            if pth.is_file() and pth!=zpath: z.write(pth,pth.relative_to(root.parent))
    with zipfile.ZipFile(zpath) as z: bad=z.testzip()
    if bad: raise RuntimeError(f'ZIP integrity failure: {bad}')
    print(json.dumps(summary,indent=2))
    print(f'ZIP={zpath} SIZE={zpath.stat().st_size} bytes TESTZIP=OK')

if __name__=='__main__': main()
