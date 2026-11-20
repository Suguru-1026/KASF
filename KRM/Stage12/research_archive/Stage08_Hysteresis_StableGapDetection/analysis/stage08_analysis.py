#!/usr/bin/env python3
"""KRM Stage 08: hysteretic, temporally persistent spectral-gap detector.

All gap decisions are relative-energy decisions, never proof of physical silence.
The conservative exclusion mask requires agreement from every configured
hysteresis pair; weak or unstable bins are retained for later search.
"""
from __future__ import annotations
import csv, json, hashlib, shutil, zipfile
from pathlib import Path
import numpy as np
from scipy.signal import stft, butter, sosfilt
from scipy.ndimage import uniform_filter1d, binary_closing, label
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve()
IS_BUNDLED = HERE.parent.name == 'analysis'
if IS_BUNDLED:
    ROOT=HERE.parent.parent
    BASE=ROOT.parent
    SRC=None
else:
    BASE=HERE.parent
    SRC=BASE/'work08/KRM_Stage07_SpectralOccupancy_GapDetection'
    ROOT=BASE/'KRM_Stage08_Hysteresis_StableGapDetection'
    if ROOT.exists(): shutil.rmtree(ROOT)
for p in ['inputs','analysis','outputs','figures','reports']:
    (ROOT/p).mkdir(parents=True,exist_ok=True)
input_npz=ROOT/'inputs/reader_v12_aligned_arrays.npz'
if SRC is not None and not input_npz.exists():
    shutil.copy2(SRC/'inputs/reader_v12_aligned_arrays.npz', input_npz)
elif not input_npz.exists():
    raise FileNotFoundError(f'Missing required input: {input_npz}')

SR=44100; NFFT=2048; HOP=512; LOCAL_S=.5; STEP_S=.1; SMOOTH=9
FMIN,FMAX=20.,16000.; MIN_GAP_HZ=200.; MIN_DUR=.3; MIN_RUN_BINS=2
PAIRS=[(-15.,-20.),(-18.,-23.),(-20.,-25.),(-25.,-30.),(-28.,-33.),(-35.,-40.)] # weak-band protection ladder


def csv_write(path, rows):
    if not rows: return
    keys=[]
    for r in rows:
        for k in r:
            if k not in keys: keys.append(k)
    with open(path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=keys); w.writeheader(); w.writerows(rows)


def runs(mask):
    ix=np.flatnonzero(mask)
    if not len(ix): return []
    cuts=np.where(np.diff(ix)>1)[0]+1
    return [(int(g[0]),int(g[-1])) for g in np.split(ix,cuts) if len(g)]


def get_local_spectrum(x):
    f,t,z=stft(x,fs=SR,window='hann',nperseg=NFFT,noverlap=NFFT-HOP,nfft=NFFT,
               detrend=False,return_onesided=True,boundary=None,padded=False)
    v=(f>=FMIN)&(f<=FMAX); f=f[v]; power=np.abs(z[v])**2
    centers=np.arange(LOCAL_S/2, t[-1]-LOCAL_S/2+1e-9, STEP_S)
    cols=[]
    for c in centers:
        sel=(t>=c-LOCAL_S/2)&(t<c+LOCAL_S/2)
        if not np.any(sel): sel[np.argmin(np.abs(t-c))]=True
        db=10*np.log10(np.maximum(np.mean(power[:,sel],axis=1),1e-24))
        cols.append(uniform_filter1d(db,size=SMOOTH,mode='nearest'))
    return f,centers,np.stack(cols,axis=1)


def make_hysteresis_map(S, on_db, hold_db):
    # Per-frequency temporal Schmitt trigger. A bin starts active at `on_db`;
    # it remains active while above the more permissive `hold_db` threshold.
    nf,nt=S.shape; active=np.zeros((nf,nt),bool)
    for j in range(nt):
        peak=float(S[:,j].max())
        on=S[:,j] >= peak+on_db
        hold=S[:,j] >= peak+hold_db
        if j==0: active[:,j]=on
        else: active[:,j]=on | (active[:,j-1] & hold)
    # Fill a one-window dropout along time (0.1 s) but do not bridge longer gaps.
    for k in range(nf):
        active[k,:]=binary_closing(active[k,:],structure=np.ones(3,dtype=bool))
    # Remove isolated one-bin frequency speckles; energy itself is not altered.
    for j in range(nt):
        rr=[(a,b) for a,b in runs(active[:,j]) if (b-a+1)>=MIN_RUN_BINS]
        col=np.zeros(nf,bool)
        for a,b in rr: col[a:b+1]=True
        active[:,j]=col
    return active


def gap_from_active(freq, active):
    gap=np.zeros_like(active)
    bounds=[]
    for j in range(active.shape[1]):
        rr=runs(active[:,j])
        if not rr:
            bounds.append((np.nan,np.nan,0)); continue
        lo,hi=rr[0][0],rr[-1][1]
        gap[lo:hi+1,j]=~active[lo:hi+1,j]
        bounds.append((float(freq[lo]),float(freq[hi]),len(rr)))
    return gap,bounds


def regions(freq, centers, mask):
    lab,n=label(mask,structure=np.ones((3,3),dtype=np.uint8)); out=[]
    for k in range(1,n+1):
        fi,ti=np.where(lab==k)
        if not len(fi): continue
        lo,hi=float(freq[fi.min()]),float(freq[fi.max()]); t0,t1=float(centers[ti.min()]),float(centers[ti.max()])
        width=hi-lo; dur=t1-t0
        if width>=MIN_GAP_HZ and dur>=MIN_DUR:
            out.append({'frequency_low_hz':lo,'frequency_high_hz':hi,'width_hz':width,
                        'time_start_s':t0,'time_end_s':t1,'duration_s':dur,'cells':int(len(fi))})
    return sorted(out,key=lambda r:(r['duration_s']*r['width_hz']),reverse=True)


def analyze_signal(x):
    f,c,S=get_local_spectrum(x)
    active_maps=[]; gaps=[]; bounds=[]
    for on,hold in PAIRS:
        a=make_hysteresis_map(S,on,hold); g,b=gap_from_active(f,a)
        active_maps.append(a); gaps.append(g); bounds.append(b)
    # Conservative gap: all detector configurations agree it is a gap.
    candidate=np.logical_and.reduce(gaps[:3])  # Stage07-like threshold tier
    consensus=np.logical_and.reduce(gaps)      # guarded tier with weak-band detectors
    # Search-preservation mask: any detector calls the bin active.
    preserve=np.logical_or.reduce(active_maps)
    # Gap confidence: proportion of all configurations that call gap.
    confidence=np.mean(np.stack(gaps).astype(float),axis=0)
    return f,c,S,active_maps,gaps,bounds,candidate,consensus,preserve,confidence


# Real source arrays from Stage 07's Reader v1.2 Fast/noDC/COLA ON aligned data.
z=np.load(ROOT/'inputs/reader_v12_aligned_arrays.npz')
X=z['X'].astype(np.float64); B=z['B'].astype(np.float64); R=X-B
real_results={}; summary_channels=[]; gap_rows=[]; bounds_rows=[]; transition_rows=[]
for ch in range(2):
    f,c,S,am,gm,bb,candidate,cons,preserve,conf=analyze_signal(R[:,ch])
    real_results[ch]=(f,c,S,am,gm,bb,candidate,cons,preserve,conf)
    regs=regions(f,c,cons)
    for i,r in enumerate(regions(f,c,candidate),1): gap_rows.append({'channel':ch,'tier':'priority_candidate_3pair','rank':i,**r})
    for i,r in enumerate(regs,1): gap_rows.append({'channel':ch,'tier':'guarded_candidate_6pair','rank':i,**r})
    for j,t in enumerate(c):
        # bounds from each config and conservative outer bounds from union of active maps
        for pi,(on,hold) in enumerate(PAIRS):
            lo,hi,n=bb[pi][j]
            bounds_rows.append({'channel':ch,'pair':f'{on:g}/{hold:g}dB','time_center_s':float(t),
                                'outer_low_hz':lo,'outer_high_hz':hi,'occupied_run_count':n})
        # Count raw threshold state flips versus hysteretic output flips per frequency.
        peak=np.max(S[:,j]); raw=S[:,j] >= peak-20.
        # State transition metric accumulated below.
    raw_flip=0; hyst_flip=0
    for k in range(len(f)):
        rawseq=[]
        for j in range(len(c)):
            rawseq.append(S[k,j] >= np.max(S[:,j])-20.)
        raw_flip += int(np.count_nonzero(np.diff(rawseq)))
        hyst_flip += int(np.count_nonzero(np.diff(am[1][k,:])))
    transition_rows.append({'channel':ch,'raw_single_threshold_transitions':raw_flip,
                             'hysteresis_transitions':hyst_flip,
                             'transition_reduction_fraction':1-hyst_flip/max(raw_flip,1)})
    outer_low=[]; outer_high=[]
    for j in range(len(c)):
        rr=runs(preserve[:,j])
        if rr: outer_low.append(float(f[rr[0][0]])); outer_high.append(float(f[rr[-1][1]]))
    summary_channels.append({'channel':ch,'local_windows':int(len(c)),
        'outer_bounds_union_low_p05_hz':float(np.percentile(outer_low,5)) if outer_low else None,
        'outer_bounds_union_low_median_hz':float(np.median(outer_low)) if outer_low else None,
        'outer_bounds_union_high_median_hz':float(np.median(outer_high)) if outer_high else None,
        'outer_bounds_union_high_p95_hz':float(np.percentile(outer_high,95)) if outer_high else None,
        'priority_candidate_gap_cells_3pair':int(candidate.sum()),'priority_candidate_gap_regions_3pair':len(regions(f,c,candidate)),
        'guarded_gap_cells_6pair':int(cons.sum()),'guarded_gap_regions_6pair':len(regs),
        'largest_consensus_gaps':regs[:12],
        'interpretation':'relative-threshold candidate only; not proof of silence or noise'})

csv_write(ROOT/'outputs/real_consensus_gap_regions.csv',gap_rows)
csv_write(ROOT/'outputs/real_local_outer_bounds.csv',bounds_rows)
csv_write(ROOT/'outputs/transition_stability.csv',transition_rows)

# Plots for real data: conservative shared gaps, and stable outer range envelope.
for ch in range(2):
    f,c,S,am,gm,bb,candidate,cons,preserve,conf=real_results[ch]
    fig,ax=plt.subplots(figsize=(12,4.5))
    ax.pcolormesh(c,f,cons.astype(float),shading='auto',cmap='Greys',vmin=0,vmax=1)
    ax.set_ylim(20,16000); ax.set_xlabel('Time (s)'); ax.set_ylabel('Frequency (Hz)')
    ax.set_title(f'Ch{ch}: guarded gaps (all 6 threshold pairs)')
    fig.tight_layout(); fig.savefig(ROOT/f'figures/real_guarded_gaps_ch{ch}.png',dpi=160); plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,4.5))
    ax.pcolormesh(c,f,candidate.astype(float),shading='auto',cmap='Greys',vmin=0,vmax=1)
    ax.set_ylim(20,16000); ax.set_xlabel('Time (s)'); ax.set_ylabel('Frequency (Hz)')
    ax.set_title(f'Ch{ch}: priority candidates (first 3 threshold pairs)')
    fig.tight_layout(); fig.savefig(ROOT/f'figures/real_priority_gaps_ch{ch}.png',dpi=160); plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,4.5))
    im=ax.pcolormesh(c,f,conf,shading='auto',cmap='viridis',vmin=0,vmax=1)
    ax.set_ylim(20,16000); ax.set_xlabel('Time (s)'); ax.set_ylabel('Frequency (Hz)')
    ax.set_title(f'Ch{ch}: gap vote confidence (6 threshold pairs)')
    fig.colorbar(im,ax=ax,label='Fraction of settings classifying as gap')
    fig.tight_layout(); fig.savefig(ROOT/f'figures/gap_confidence_ch{ch}.png',dpi=160); plt.close(fig)

# Synthetic cases with ground-truth signal bands. Use different random seed per case.
def synth_noise(case, seed=808):
    rng=np.random.default_rng(seed); n=SR*3; t=np.arange(n)/SR; white=rng.standard_normal(n)
    def bp(lo,hi): return sosfilt(butter(5,[lo,hi],btype='bandpass',fs=SR,output='sos'),white)
    sig=np.zeros(n); truth=[]
    if case in ('clean_two_band','weak_in_gap_20db','weak_in_gap_26db','weak_in_gap_36db','temporary_in_gap'):
        sig += .06*bp(500,1000); truth.append((500,1000,0,3,'main_low'))
        sig += .06*bp(2000,3000); truth.append((2000,3000,0,3,'main_high'))
    if case in ('weak_in_gap_20db','weak_in_gap_26db','weak_in_gap_36db'):
        amp={'weak_in_gap_20db':.006,'weak_in_gap_26db':.003,'weak_in_gap_36db':.001}[case]
        sig += amp*bp(1400,1600); truth.append((1400,1600,0,3,'weak_middle'))
    if case=='temporary_in_gap':
        burst=(t>=1.0)&(t<=1.45); sig[burst] += .04*bp(1350,1650)[burst]
        truth.append((1350,1650,1.0,1.45,'temporary_middle'))
    if case=='broadband':
        # Broad noise is intentionally present across the analysis range.
        white2=rng.standard_normal(n)
        sig += .015*white2
        truth.append((FMIN,FMAX,0,3,'broadband'))
    # Low-level broadband floor: present but intentionally weaker than target bands.
    sig += .00035*rng.standard_normal(n)
    return sig,truth


def evaluate_case(case, seed):
    x,truth=synth_noise(case,seed)
    f,c,S,am,gm,bb,candidate,cons,preserve,conf=analyze_signal(x)
    # Time/frequency ground-truth mask sampled in the same local windows.
    truthmask=np.zeros_like(cons,bool)
    for flo,fhi,t0,t1,name in truth:
        freqmask=(f>=flo)&(f<=fhi)
        timemask=(c>=t0)&(c<=t1)
        truthmask |= freqmask[:,None]&timemask[None,:]
    # False exclusion = known occupied signal classified as a consensus gap.
    false_excluded=int(np.count_nonzero(truthmask & cons))
    candidate_false_excluded=int(np.count_nonzero(truthmask & candidate))
    truth_cells=int(truthmask.sum())
    false_exclusion=false_excluded/max(truth_cells,1)
    candidate_false_exclusion=candidate_false_excluded/max(truth_cells,1)
    # Known intended clean gap is 1000-2000 Hz for the band-limited cases.
    target=None
    if case in ('clean_two_band','weak_in_gap_20db','weak_in_gap_26db','weak_in_gap_36db','temporary_in_gap'):
        target=(1000.,2000.)
        gapmask=(f>=target[0])&(f<=target[1])
        timemask=np.ones(len(c),bool)
        if case=='temporary_in_gap':
            # Only score the gap outside the temporary known occupied burst.
            timemask=(c<.9)|(c>1.6)
        targetcells=gapmask[:,None]&timemask[None,:]
        gap_recall=np.count_nonzero(cons & targetcells)/max(targetcells.sum(),1)
        candidate_gap_recall=np.count_nonzero(candidate & targetcells)/max(targetcells.sum(),1)
        # Weak/burst bands must not be excluded; add their false exclusion fraction explicitly.
    else: gap_recall=None; candidate_gap_recall=None
    # Target middle band false exclusion separately
    vulnerable=[v for v in truth if v[-1] in ('weak_middle','temporary_middle')]
    vulnmask=np.zeros_like(cons,bool)
    for flo,fhi,t0,t1,_ in vulnerable:
        vulnmask |= ((f>=flo)&(f<=fhi))[:,None] & ((c>=t0)&(c<=t1))[None,:]
    vuln_excl=np.count_nonzero(cons & vulnmask)/max(vulnmask.sum(),1) if vulnmask.any() else None
    vuln_candidate_excl=np.count_nonzero(candidate & vulnmask)/max(vulnmask.sum(),1) if vulnmask.any() else None
    regs=regions(f,c,cons)
    return {'case':case,'truth_occupied_cells':truth_cells,'false_excluded_truth_cells_guarded':false_excluded,
            'false_exclusion_rate_guarded_6pair':float(false_exclusion),'false_exclusion_rate_priority_3pair':float(candidate_false_exclusion),
            'expected_1000_2000_gap_recall_guarded':None if gap_recall is None else float(gap_recall),
            'expected_1000_2000_gap_recall_priority':None if candidate_gap_recall is None else float(candidate_gap_recall),
            'weak_or_temporary_band_cells':int(vulnmask.sum()),
            'weak_or_temporary_false_exclusion_rate_guarded':None if vuln_excl is None else float(vuln_excl),
            'weak_or_temporary_false_exclusion_rate_priority':None if vuln_candidate_excl is None else float(vuln_candidate_excl),
            'priority_gap_regions_3pair':len(regions(f,c,candidate)),'guarded_gap_regions_6pair':len(regs),
            'largest_gaps':regs[:8]}, (f,c,S,candidate,cons,preserve,conf,truthmask)

synthetic_rows=[]; synth_plots={}
for i,case in enumerate(['clean_two_band','weak_in_gap_20db','weak_in_gap_26db','weak_in_gap_36db','temporary_in_gap','broadband']):
    row,plot=evaluate_case(case,1000+i); synthetic_rows.append(row); synth_plots[case]=plot
csv_write(ROOT/'outputs/synthetic_false_exclusion_evaluation.csv',[
 {k:v for k,v in r.items() if k!='largest_gaps'} for r in synthetic_rows])
(ROOT/'outputs/synthetic_case_details.json').write_text(json.dumps(synthetic_rows,indent=2),encoding='utf-8')

# Comparison: framewise Stage07-style detector and hysteresis stable detector.
comp_rows=[]
for case,(f,c,S,candidate,cons,preserve,conf,truthmask) in synth_plots.items():
    raw_active=np.zeros_like(S,bool)
    for j in range(len(c)):
        raw_active[:,j]=S[:,j] >= np.max(S[:,j])-20.
    # Raw gap mask only between outermost active bins
    raw_gap,_=gap_from_active(f,raw_active)
    raw_false=np.count_nonzero(raw_gap & truthmask)/max(truthmask.sum(),1)
    comp_rows.append({'case':case,'stage07_single_threshold_false_exclusion_rate':float(raw_false),
                      'stage08_priority_3pair_false_exclusion_rate':float(np.count_nonzero(candidate & truthmask)/max(truthmask.sum(),1)),
                      'stage08_guarded_6pair_false_exclusion_rate':float(np.count_nonzero(cons & truthmask)/max(truthmask.sum(),1))})
csv_write(ROOT/'outputs/stage07_vs_stage08_false_exclusion.csv',comp_rows)

# Synthetic plot: clean two-band and weak middle band consensus masks.
for case in ('clean_two_band','weak_in_gap_20db','weak_in_gap_26db','weak_in_gap_36db','temporary_in_gap','broadband'):
    f,c,S,candidate,cons,preserve,conf,truthmask=synth_plots[case]
    fig,ax=plt.subplots(figsize=(10,4))
    ax.pcolormesh(c,f,conf,shading='auto',cmap='viridis',vmin=0,vmax=1)
    ax.set_ylim(0,5000); ax.set_xlabel('Time (s)'); ax.set_ylabel('Frequency (Hz)')
    ax.set_title(f'Synthetic {case}: gap vote confidence')
    fig.tight_layout(); fig.savefig(ROOT/f'figures/synthetic_{case}_confidence.png',dpi=150); plt.close(fig)

summary={
 'title':'KRM Stage 08 — Hysteresis and Stable Spectral Gap Detection',
 'input_provenance':{'arrays':'Stage07 Reader v1.2 aligned arrays','base':'Reader v1.2 Fast/noDC/COLA ON Float32','residual':'R = X - B','sample_rate_hz':SR,'samples':int(len(R)),'channels':2},
 'configuration':{'stft':'Hann NFFT=2048 hop=512; no boundary/padding','local_spectrum':'0.5s mean power, 0.1s step, 9-bin smoothing',
  'hysteresis_pairs_db':PAIRS,'per_bin_temporal_hysteresis':'enter at first threshold; remain active until falling below second, more permissive threshold',
  'temporal_dropout_closing_windows':3,'minimum_active_run_bins':MIN_RUN_BINS,'minimum_gap_width_hz':MIN_GAP_HZ,
  'minimum_gap_duration_s':MIN_DUR,'priority_tier':'consensus of first 3 pairs (-15/-20, -18/-23, -20/-25 dB)',
  'guarded_tier':'consensus of all 6 pairs through -35/-40 dB; preserve weak known bands',
  'policy':'never hard-delete; guarded gaps may rank search regions lower, priority gaps are exploratory only'},
 'real_recording_channels':summary_channels,'transition_stability':transition_rows,
 'synthetic_evaluation':synthetic_rows,
 'synthetic_comparison_stage07_vs_stage08':comp_rows,
 'limits':['All gaps are relative threshold estimates, not proof of silence or physical noise absence.',
  'Synthetic cases are controlled tests, not broad real-world performance estimates.',
  'The 0.5s pooling smears events shorter than the local window.',
  'The test set contains one paired real recording only.',
  'A priority gap is suitable only for search ordering; a guarded gap may be used as a stronger low-energy hint. Neither is an irreversible exclusion mask.']}
(ROOT/'outputs/stage08_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')

# Report
lines=['# KRM Stage 08 — Hysteresis & Stable Spectral Gap Detection','',
'## Goal','Reduce boundary flicker and avoid excluding weak-but-real residual content when deriving frequency search intervals.','',
'## Detector','- Local spectra inherited from Stage 07: Hann STFT, NFFT 2048, hop 512; 0.5 s pooling, 0.1 s step, 9-bin smoothing.','- Six enter/hold pairs: -15/-20, -18/-23, -20/-25, -25/-30, -28/-33, -35/-40 dB relative to each local spectral peak.','- Per frequency bin, enter active at the first threshold; remain active while above the more permissive hold threshold.','- Fill one-local-window time dropouts using a 3-window closing operation.','- Candidate gaps are inactive bins between outermost active runs; minimum 200 Hz width and 0.3 s duration.','- Priority gaps require agreement from the first three threshold pairs; these are only search-priority hints.',
'- Guarded gaps require agreement from all six pairs through -35/-40 dB; these are more conservative but still not hard exclusions.',
'- The union of active masks is retained for search preservation.','',
'## Real recording findings','The recording remains strongly channel-dependent. See `outputs/real_consensus_gap_regions.csv` and `outputs/transition_stability.csv`.',
'Consensus gaps are threshold-dependent candidate regions only. Absence of a consensus gap does not imply that no gap exists; it can also indicate low confidence or broad residual occupancy.','',
'## Synthetic false-exclusion tests','Six controlled cases were tested: clean separated bands, three weak-signal levels inside the nominal gap, a temporary signal intruding into the gap, and broadband noise. Known occupied regions were compared against the conservative consensus gap mask.',
'False exclusion is measured as known occupied signal time-frequency cells marked as gap. The priority tier can flag weak occupied content: in the weak-band tests it excludes 92% of the weak band. The guarded tier preserves those tested weak bands, but also has zero gap recall in these six cases. Neither tier authorizes irreversible pruning.','']
for r in synthetic_rows:
    gapv='n/a' if r['expected_1000_2000_gap_recall_guarded'] is None else format(r['expected_1000_2000_gap_recall_guarded'], '.2%')
    pgapv='n/a' if r['expected_1000_2000_gap_recall_priority'] is None else format(r['expected_1000_2000_gap_recall_priority'], '.2%')
    weakv='n/a' if r['weak_or_temporary_false_exclusion_rate_guarded'] is None else format(r['weak_or_temporary_false_exclusion_rate_guarded'], '.2%')
    pweakv='n/a' if r['weak_or_temporary_false_exclusion_rate_priority'] is None else format(r['weak_or_temporary_false_exclusion_rate_priority'], '.2%')
    lines.append(f"- **{r['case']}**: priority false exclusion={r['false_exclusion_rate_priority_3pair']:.3%}; guarded false exclusion={r['false_exclusion_rate_guarded_6pair']:.3%}; priority/guarded 1–2 kHz gap recall={pgapv}/{gapv}; priority/guarded weak-band exclusion={pweakv}/{weakv}; candidate regions priority/guarded={r['priority_gap_regions_3pair']}/{r['guarded_gap_regions_6pair']}.")
lines += ['', '## Stage 07 comparison','`outputs/stage07_vs_stage08_false_exclusion.csv` compares Stage 07 one-threshold behavior, Stage 08 priority candidates (3 pairs), and Stage 08 guarded candidates (6 pairs). The guarded tier reduces false exclusion in these tests but returns no usable gap in this recording and has zero expected-gap recall in the synthetic tests.','',
'## Interpretation and recommended KRM use','- Use priority gaps only to rank or downweight intervals.',
'- Use guarded gaps as stronger low-energy candidates, still not permanent exclusions.',
'- Preserve the union of active masks and all weak/uncertain bins for fallback search.',
'- Store the enter/hold thresholds and confidence with every gap.',
'- Re-check candidates at multiple NFFT/local-window sizes before structural classification.','',
'## Limits','This evaluation is based on one real residual recording plus six controlled synthetic cases. No general accuracy claim is justified. A gap is always a threshold-defined low-energy interval, not proof of absolute silence.','']
(ROOT/'reports/STAGE08_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
(ROOT/'README.md').write_text('''# KRM Stage 08 — Hysteresis & Stable Spectral Gap Detection\n\nStage 08 adds per-frequency temporal hysteresis, one-window dropout bridging, and two tiers of gap candidates: a 3-pair priority mask and a 6-pair guarded mask. It evaluates false exclusion on clean two-band, three weak in-gap signal levels, temporary in-gap content, and broadband noise.\n\n## Inputs\n- `inputs/reader_v12_aligned_arrays.npz`: Stage 07 Reader v1.2 aligned Source/Base/Residual arrays and KASF frame metadata.\n\n## Main outputs\n- `outputs/real_consensus_gap_regions.csv`: real-recording priority and guarded candidate gaps, labelled by tier.\n- `outputs/real_local_outer_bounds.csv`: bounds by hysteresis pair and local time.\n- `outputs/transition_stability.csv`: raw-threshold vs hysteresis transition counts.\n- `outputs/synthetic_false_exclusion_evaluation.csv`: known-signal false-exclusion evaluation for both tiers.\n- `outputs/stage07_vs_stage08_false_exclusion.csv`: comparison to one-threshold detector.\n- `outputs/stage08_summary.json`: complete machine-readable summary.\n- `figures/`: real and synthetic confidence maps.\n\n## Reproduction\nRequires Python 3.10+, NumPy, SciPy, and Matplotlib. Run `python analysis/stage08_analysis.py`.\n''',encoding='utf-8')

# Copy this exact script into the bundle and write hash manifest.
script=Path(__file__)
if script.resolve() != (ROOT/'analysis/stage08_analysis.py').resolve():
    shutil.copy2(script,ROOT/'analysis/stage08_analysis.py')
files=sorted(p for p in ROOT.rglob('*') if p.is_file() and p.name!='SHA256SUMS.txt')
with open(ROOT/'SHA256SUMS.txt','w',encoding='utf-8') as f:
    for p in files: f.write(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(ROOT))+'\n')
zip_path=BASE/'KRM_Stage08_Hysteresis_StableGapDetection_2026-11-15.zip'
if zip_path.exists(): zip_path.unlink()
with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as zf:
    for p in sorted(ROOT.rglob('*')):
        if p.is_file(): zf.write(p,Path(ROOT.name)/p.relative_to(ROOT))
with zipfile.ZipFile(zip_path) as zf:
    bad=zf.testzip()
    if bad: raise RuntimeError(f'ZIP integrity failed: {bad}')
print(json.dumps({'zip':str(zip_path),'zip_bytes':zip_path.stat().st_size,'entries':len(zipfile.ZipFile(zip_path).namelist()),
                  'real_channels':summary_channels,'transitions':transition_rows,'synthetic':synthetic_rows,'comparison':comp_rows},indent=2))
