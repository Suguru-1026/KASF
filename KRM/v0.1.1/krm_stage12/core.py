"""KRM Stage12 v1 reference implementation (Draft 0.5 baseline).

Input is a normalized Stage11 cell-map JSON. This module deliberately does not
infer an unknown Stage11 file format and never mutates source/residual PCM.
Python standard library only.
"""
from __future__ import annotations
import csv, hashlib, json, math, statistics, time
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

Cell = Tuple[int, int]  # (frame, bin)

@dataclass
class Config:
    max_time_gap_frames: int = 2
    time_gap_hard_limit_frames: int = 8
    max_frequency_gap_bins: int = 2
    frequency_gap_hard_limit_bins: int = 8
    temporal_support_overlap_min: float = 0.50
    frequency_temporal_overlap_min: float = 0.50
    boundary_median_delta_db_max: float = 12.0
    temporal_bridge_frequency_tolerance_bins: int = 1
    s1_bridge_enabled: bool = True
    s1_max_bridge_frames: int = 2
    s1_max_bridge_bins: int = 2
    s1_max_bridge_cells: int = 4
    s1_min_median_normalized_activity: float = 1.0/3.0
    bridge_score_min: float = 0.60
    max_area_growth_ratio: float = 3.0
    max_duration_growth_ratio: float = 4.0
    max_bandwidth_growth_ratio: float = 3.0
    schema_version: str = "krm-stage12-config-1.0"

    def validate(self):
        integer_limits = {
            "max_time_gap_frames": self.max_time_gap_frames,
            "time_gap_hard_limit_frames": self.time_gap_hard_limit_frames,
            "max_frequency_gap_bins": self.max_frequency_gap_bins,
            "frequency_gap_hard_limit_bins": self.frequency_gap_hard_limit_bins,
            "temporal_bridge_frequency_tolerance_bins": self.temporal_bridge_frequency_tolerance_bins,
            "s1_max_bridge_frames": self.s1_max_bridge_frames,
            "s1_max_bridge_bins": self.s1_max_bridge_bins,
            "s1_max_bridge_cells": self.s1_max_bridge_cells,
        }
        for name, value in integer_limits.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.max_time_gap_frames > self.time_gap_hard_limit_frames:
            raise ValueError("max_time_gap_frames exceeds hard safety cap")
        if self.max_frequency_gap_bins > self.frequency_gap_hard_limit_bins:
            raise ValueError("max_frequency_gap_bins exceeds hard safety cap")
        if self.time_gap_hard_limit_frames > 8 or self.frequency_gap_hard_limit_bins > 8:
            raise ValueError("Draft 0.5 hard safety caps cannot be raised in v1")
        if self.s1_max_bridge_cells > 4 or self.s1_max_bridge_frames > 2 or self.s1_max_bridge_bins > 2:
            raise ValueError("S1 bridge exceeds Draft 0.5 fixed safety limits")
        for name in ("temporal_support_overlap_min", "frequency_temporal_overlap_min", "s1_min_median_normalized_activity", "bridge_score_min"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and in [0,1]")
        for name in ("boundary_median_delta_db_max", "max_area_growth_ratio", "max_duration_growth_ratio", "max_bandwidth_growth_ratio"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not isinstance(self.s1_bridge_enabled, bool):
            raise ValueError("s1_bridge_enabled must be boolean")


def _canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
def _sha(obj) -> str: return hashlib.sha256(_canonical(obj)).hexdigest()
def _clip(x, lo=0.0, hi=1.0): return max(lo, min(hi, x))


def load_input(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f: data = json.load(f)
    validate_input(data)
    return data


def validate_input(data: dict) -> None:
    required = {"schema_version", "input_manifest", "cells"}
    missing = required - set(data)
    if missing: raise ValueError(f"missing top-level keys: {sorted(missing)}")
    schema = data["schema_version"]
    if schema not in {"krm-stage11-normalized-1.0", "krm-stage11-normalized-1.1"}:
        raise ValueError("unsupported normalized Stage11 schema_version")
    m = data["input_manifest"]
    if not isinstance(m, dict) or not isinstance(data["cells"], dict):
        raise ValueError("input_manifest and cells must be JSON objects")
    if schema == "krm-stage11-normalized-1.1":
        if m.get("grid_complete") is not True:
            raise ValueError("normalized 1.1 requires input_manifest.grid_complete=true")
        if m.get("implicit_cell_state") not in {"S0", "INVALID"}:
            raise ValueError("normalized 1.1 currently supports implicit_cell_state S0 or INVALID only")
    for k in ("input_id", "sample_rate", "fft_size", "hop_size", "window", "center_padding", "frame_timestamp_convention", "frequency_bin_convention", "stage11_version", "channel_id", "resolution_id", "frame_count", "bin_count"):
        if k not in m: raise ValueError(f"input_manifest missing {k}")
    for name in ("sample_rate", "fft_size", "hop_size", "frame_count", "bin_count", "channel_id"):
        value = m[name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"input_manifest.{name} must be an integer")
    if m["sample_rate"] <= 0 or m["fft_size"] <= 0 or m["hop_size"] <= 0:
        raise ValueError("invalid sample_rate/fft_size/hop_size")
    if m["frame_count"] < 0 or m["bin_count"] < 0 or m["channel_id"] < 0:
        raise ValueError("negative grid size or channel_id")
    if schema == "krm-stage11-normalized-1.1" and len(data["cells"]) > m["frame_count"] * m["bin_count"]:
        raise ValueError("sparse cell count exceeds declared complete grid")
    for key, c in data["cells"].items():
        try: f, b = map(int, key.split(","))
        except Exception: raise ValueError(f"invalid cell key {key!r}; expected 'frame,bin'")
        if key != f"{f},{b}": raise ValueError(f"non-canonical cell key: {key!r}")
        if not (0 <= f < m["frame_count"] and 0 <= b < m["bin_count"]): raise ValueError(f"cell out of bounds: {key}")
        if not isinstance(c, dict) or c.get("state") not in {"S0", "S1", "S2", "S3", "INVALID"}:
            raise ValueError(f"invalid cell record: {key}")
        for field in ("power", "local_floor_power", "delta_db"):
            value = c.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError(f"invalid {field} at {key}")
        if c.get("power") is not None and c["power"] < 0:
            raise ValueError(f"negative power at {key}")
        if c.get("local_floor_power") is not None and c["local_floor_power"] < 0:
            raise ValueError(f"negative local_floor_power at {key}")


class _CellFieldView:
    """Tuple-coordinate view over sparse JSON cells; avoids duplicating maps."""
    def __init__(self, cells: dict, field: str, missing_value=None):
        self.cells = cells
        self.field = field
        self.missing_value = missing_value

    def get(self, cell, default=None):
        f, b = cell
        record = self.cells.get(f"{f},{b}")
        if record is None:
            return self.missing_value
        return record.get(self.field, self.missing_value)

    def __getitem__(self, cell):
        value = self.get(cell)
        if value is None:
            raise KeyError(cell)
        return value

    def items(self):
        for key, record in self.cells.items():
            f, b = map(int, key.split(","))
            value = record.get(self.field, self.missing_value)
            if value is not None:
                yield (f, b), value


def _state_map_from_input(data: dict):
    # Schema 1.0 keeps the historical omitted=INVALID rule. Only schema 1.1
    # has an explicit complete-grid implicit-state contract.
    if data.get("schema_version") == "krm-stage11-normalized-1.1":
        missing = data["input_manifest"]["implicit_cell_state"]
    else:
        missing = "INVALID"
    return _CellFieldView(data["cells"], "state", missing_value=missing)


def rle_encode(cells: Iterable[Cell]) -> List[List[int]]:
    by_frame = defaultdict(list)
    for f,b in set(cells): by_frame[f].append(b)
    out=[]
    for f in sorted(by_frame):
        bins=sorted(set(by_frame[f]))
        if not bins: continue
        s=prev=bins[0]
        for b in bins[1:]:
            if b == prev+1: prev=b
            else: out.append([f,s,prev+1]); s=prev=b
        out.append([f,s,prev+1])
    return out


def rle_decode(runs: Iterable[Iterable[int]]) -> Set[Cell]:
    out=set()
    for f,s,e in runs:
        if not (isinstance(f,int) and isinstance(s,int) and isinstance(e,int) and s < e):
            raise ValueError("invalid RLE run")
        for b in range(s,e):
            cell=(f,b)
            if cell in out: raise ValueError("overlapping RLE runs")
            out.add(cell)
    return out


def _connected_components(cells: Set[Cell]):
    # Deterministic O(N log N) seed order and streaming component emission.
    # Repeated min(unseen) is quadratic for many singleton components; storing
    # every component at once also duplicates large portions of the active map.
    unseen=set(cells)
    for seed in sorted(cells):
        if seed not in unseen:
            continue
        unseen.remove(seed); q=[seed]; comp={seed}
        while q:
            f,b=q.pop()
            for nb in ((f-1,b),(f+1,b),(f,b-1),(f,b+1)):
                if nb in unseen: unseen.remove(nb); comp.add(nb); q.append(nb)
        yield comp


def _region_record(rid: str, cells: Set[Cell], state_map: dict, manifest_hash: str) -> dict:
    fs=[x[0] for x in cells]; bs=[x[1] for x in cells]
    return {"region_id":rid,"frame_start":min(fs),"frame_end_exclusive":max(fs)+1,
            "bin_start":min(bs),"bin_end_exclusive":max(bs)+1,"cell_count":len(cells),
            "shape_rle":rle_encode(cells),"input_manifest_hash":manifest_hash,
            "s3_counts":{"S2":sum(state_map[x]=="S2" for x in cells),"S3":sum(state_map[x]=="S3" for x in cells)}}


def _bbox(regions: List[dict]) -> Tuple[int,int,int,int]:
    return (min(r["frame_start"] for r in regions), max(r["frame_end_exclusive"] for r in regions),
            min(r["bin_start"] for r in regions), max(r["bin_end_exclusive"] for r in regions))
def _rect_union_area(regions: List[dict]) -> int:
    # Exact rectangle union for the two-parent growth check without expanding
    # potentially huge bounding boxes into individual grid cells.
    if not regions: return 0
    if len(regions) == 1:
        r=regions[0]; return (r["frame_end_exclusive"]-r["frame_start"]) * (r["bin_end_exclusive"]-r["bin_start"])
    if len(regions) == 2:
        a,b=regions
        aa=(a["frame_end_exclusive"]-a["frame_start"]) * (a["bin_end_exclusive"]-a["bin_start"])
        ab=(b["frame_end_exclusive"]-b["frame_start"]) * (b["bin_end_exclusive"]-b["bin_start"])
        of=max(0,min(a["frame_end_exclusive"],b["frame_end_exclusive"])-max(a["frame_start"],b["frame_start"]))
        ob=max(0,min(a["bin_end_exclusive"],b["bin_end_exclusive"])-max(a["bin_start"],b["bin_start"]))
        return aa+ab-of*ob
    # General fallback: sweep frame slabs and merge bin intervals.
    points=sorted({x for r in regions for x in (r["frame_start"],r["frame_end_exclusive"])})
    total=0
    for lo,hi in zip(points,points[1:]):
        intervals=sorted((r["bin_start"],r["bin_end_exclusive"]) for r in regions if r["frame_start"]<hi and r["frame_end_exclusive"]>lo)
        covered=0; end=None
        for a,b in intervals:
            if end is None or a>end: covered+=b-a
            elif b>end: covered+=b-end
            end=max(end or b,b)
        total+=(hi-lo)*covered
    return total
def _growth_ok(a: dict,b: dict,cfg: Config) -> Tuple[bool,str]:
    f0=min(a["frame_start"],b["frame_start"]); f1=max(a["frame_end_exclusive"],b["frame_end_exclusive"])
    b0=min(a["bin_start"],b["bin_start"]); b1=max(a["bin_end_exclusive"],b["bin_end_exclusive"])
    merged=(f1-f0)*(b1-b0)
    parent_union=_rect_union_area([a,b])
    if parent_union <= 0: return False,"zero_parent_bbox_union"
    dur=max(1,f1-f0)/max(1,a["frame_end_exclusive"]-a["frame_start"],b["frame_end_exclusive"]-b["frame_start"])
    bw=max(1,b1-b0)/max(1,a["bin_end_exclusive"]-a["bin_start"],b["bin_end_exclusive"]-b["bin_start"])
    if merged/parent_union > cfg.max_area_growth_ratio: return False,"bbox_area_growth"
    if dur > cfg.max_duration_growth_ratio: return False,"duration_growth"
    if bw > cfg.max_bandwidth_growth_ratio: return False,"bandwidth_growth"
    return True,"passed"


def _merge_record(a: dict,b: dict, bridge: dict, next_id: int, generation: int) -> dict:
    parents=sorted([a["region_id"],b["region_id"]])
    members=sorted(set(a["member_original_ids"]+b["member_original_ids"]))
    active=set(a["observed_cells"]) | set(b["observed_cells"])
    s1=set(a["s1_cells"]) | set(b["s1_cells"]) | set(bridge.get("s1_cells",[]))
    connectors=list(a["connectors"])+list(b["connectors"])
    if bridge.get("connector"): connectors.append(bridge["connector"])
    return {"region_id":f"MR-{next_id:06d}","generation":generation,"parent_region_ids":parents,
            "member_original_ids":members,"observed_cells":active,"s1_cells":s1,"connectors":connectors,
            "integration_stage":bridge["stage"],"status":"active"}


def _candidate_bridge(a:dict,b:dict,stage:str,cfg:Config,state_map:dict,activity:dict) -> Optional[dict]:
    if a["region_id"] == b["region_id"]: return None
    ca=a["observed_cells"]; cb=b["observed_cells"]
    if not ca or not cb: return None
    if stage=="12-B2":
        if a["frame_end_exclusive"] > b["frame_start"]:
            a,b=b,a; ca,cb=cb,ca
        gap=b["frame_start"]-a["frame_end_exclusive"]
        if not (1 <= gap <= cfg.max_time_gap_frames): return None
        fa=a["frame_end_exclusive"]-1; fb=b["frame_start"]
        sa={x[1] for x in ca if x[0]==fa}; sb={x[1] for x in cb if x[0]==fb}
        if not sa or not sb: return None
        # True one-bin dilation of the observed support; do not fill internal holes.
        sa2={x for v in sa for x in (v-1,v,v+1)}; sb2={x for v in sb for x in (v-1,v,v+1)}
        # INVALID is not a bridgeable gap. Check the actual intervening time-frequency corridor.
        corridor=sa2 | sb2
        gap_states=[state_map.get((f,b), "INVALID") for f in range(fa+1,fb) for b in corridor]
        if any(x in ("INVALID","S1") for x in gap_states): return None
        overlap=len(sa2&sb2)/min(len(sa2),len(sb2))
        if overlap < cfg.temporal_support_overlap_min: return None
        pa=[activity.get(x) for x in ca if x[0]==fa and activity.get(x) is not None]
        pb=[activity.get(x) for x in cb if x[0]==fb and activity.get(x) is not None]
        if not pa or not pb: return None
        delta=abs(statistics.median(pa)-statistics.median(pb))
        if delta > cfg.boundary_median_delta_db_max: return None
        score=_clip(.5*overlap+.5*math.exp(-delta/12))
        if score < cfg.bridge_score_min: return None
        return {"stage":stage,"gap":gap,"score":score,"support_overlap":overlap,"median_delta_db":delta,
                "connector":{"kind":"temporal","from_frame":fa,"to_frame":fb,"virtual":True}}
    if stage=="12-B3":
        if a["bin_end_exclusive"] > b["bin_start"]:
            a,b=b,a; ca,cb=cb,ca
        gap=b["bin_start"]-a["bin_end_exclusive"]
        if not (1 <= gap <= cfg.max_frequency_gap_bins): return None
        ta={x[0] for x in ca}; tb={x[0] for x in cb}
        if not ta or not tb: return None
        overlap=len(ta&tb)/min(len(ta),len(tb))
        if overlap < cfg.frequency_temporal_overlap_min: return None
        # Compare closest frequency-edge cells over shared frames.
        shared=ta&tb; da=[]
        # INVALID cells in the frequency gap are never treated as bridgeable silence.
        gap_states=[state_map.get((f,gap_bin), "INVALID") for f in shared
                    for gap_bin in range(a["bin_end_exclusive"], b["bin_start"])]
        if any(x in ("INVALID","S1") for x in gap_states): return None
        for f in shared:
            xa=[x for x in ca if x[0]==f and x[1]==a["bin_end_exclusive"]-1]
            xb=[x for x in cb if x[0]==f and x[1]==b["bin_start"]]
            if xa and xb:
                va=activity.get(xa[0]); vb=activity.get(xb[0])
                if va is not None and vb is not None: da.append(abs(va-vb))
        if not da: return None
        delta=statistics.median(da)
        if delta > cfg.boundary_median_delta_db_max: return None
        score=_clip(.5*overlap+.5*math.exp(-delta/12))
        if score < cfg.bridge_score_min: return None
        return {"stage":stage,"gap":gap,"score":score,"support_overlap":overlap,"median_delta_db":delta,
                "connector":{"kind":"frequency","from_bin":a["bin_end_exclusive"]-1,"to_bin":b["bin_start"],"virtual":True}}
    return None


def _apply_bridge_pass(regions: List[dict], stage: str, cfg: Config, state_map:dict, activity:dict,
                       events:list, next_id:int) -> Tuple[List[dict],int]:
    # Freeze snapshot and enumerate only geometrically eligible pairs.
    # This replaces the former all-pairs O(N^2) scan with bounded-gap buckets.
    snapshot=list(regions); candidates=[]
    if stage == "12-B2":
        by_start = defaultdict(list)
        for r in snapshot: by_start[r["frame_start"]].append(r)
        pairs=[]
        for a in snapshot:
            for gap in range(1, cfg.max_time_gap_frames + 1):
                for b in by_start.get(a["frame_end_exclusive"] + gap, ()):
                    pairs.append((a,b))
    elif stage == "12-B3":
        by_start = defaultdict(list)
        for r in snapshot: by_start[r["bin_start"]].append(r)
        pairs=[]
        for a in snapshot:
            for gap in range(1, cfg.max_frequency_gap_bins + 1):
                for b in by_start.get(a["bin_end_exclusive"] + gap, ()):
                    pairs.append((a,b))
    else:
        pairs=[]
    for a,b in pairs:
        c=_candidate_bridge(a,b,stage,cfg,state_map,activity)
        if c:
            c.update({"a":a["region_id"],"b":b["region_id"]})
            candidates.append(c)
    candidates.sort(key=lambda c:(-c["score"],c["gap"],stage,tuple(sorted((c["a"],c["b"])))) )
    byid={r["region_id"]:r for r in snapshot}; parent={k:k for k in byid}; members={k:[k] for k in byid}
    def find(x):
        while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
        return x
    merged_new=[]; rejected=[]
    for c in candidates:
        ra,rb=find(c["a"]),find(c["b"])
        if ra==rb:
            rejected.append((c,"already_connected")); continue
        # Aggregate each provisional component into a temporary region for growth checks.
        aa=[byid[x] for x in members[ra]]; bb=[byid[x] for x in members[rb]]
        ca=set().union(*(x["observed_cells"] for x in aa)); cb=set().union(*(x["observed_cells"] for x in bb))
        temp_a=_aggregate_temp(aa,ca); temp_b=_aggregate_temp(bb,cb)
        ok,reason=_growth_ok(temp_a,temp_b,cfg)
        if not ok:
            rejected.append((c,reason)); continue
        # Union-find deterministic root.
        root,child=sorted((ra,rb)); parent[child]=root; members[root]=sorted(members[ra]+members[rb]); members.pop(child,None)
        c["accepted_component_edge"]=True
        events.append({"stage":stage,"input_region_ids":sorted((c["a"],c["b"])),"status":"accepted_edge","reason_code":"bridge_passed",
                       "bridge_score":c["score"],"validation_metrics":{"growth":"passed","support_overlap":c.get("support_overlap"),"median_delta_db":c.get("median_delta_db")}})
    for c,reason in rejected:
        events.append({"stage":stage,"input_region_ids":sorted((c["a"],c["b"])),"status":"rejected","reason_code":reason,"bridge_score":c["score"]})
    # Emit one derived region for every component with >1 member; preserve unmerged snapshots too.
    out=[]; used=set()
    for root,ids in sorted(members.items()):
        rs=[byid[x] for x in ids]
        if len(rs)==1: out.append(rs[0]); continue
        cells=set().union(*(r["observed_cells"] for r in rs))
        bridges=[c for c in candidates if c.get("accepted_component_edge") and c["a"] in ids and c["b"] in ids]
        # Use all bridge metadata for this derived component.
        for c in bridges:
            next_id+=1
            br={"stage":stage,"connector":c.get("connector")}
            # Build from aggregate parents while keeping lineage.
            temp=_merge_record(rs[0],rs[1],br,next_id,max(r.get("generation",0) for r in rs)+1)
            temp["parent_region_ids"]=sorted(ids)
            temp["member_original_ids"]=sorted(set().union(*(set(r["member_original_ids"]) for r in rs)))
            temp["observed_cells"]=cells
            temp.update(_aggregate_temp(rs, cells))
            temp["s1_cells"]=set().union(*(r["s1_cells"] for r in rs))
            temp["connectors"]=sum((r["connectors"] for r in rs),[])+[c["connector"] for c in bridges if c.get("connector")]
            temp["integration_stage"]=stage; temp["status"]="active"
            break
        if not bridges:
            # Should not occur, but preserve data safely.
            out.extend(rs); continue
        out.append(temp)
        events.append({"stage":stage,"input_region_ids":sorted(ids),"output_region_id":temp["region_id"],"status":"derived_region_created","reason_code":"component_union"})
    return sorted(out,key=lambda r:r["region_id"]),next_id


def _aggregate_temp(rs,cells):
    f=[x[0] for x in cells]; b=[x[1] for x in cells]
    return {"frame_start":min(f),"frame_end_exclusive":max(f)+1,"bin_start":min(b),"bin_end_exclusive":max(b)+1,"observed_cells":cells}


def _apply_s1(regions:list,cfg:Config,state_map:dict,power_map:dict,local_floor:dict,events:list,next_id:int):
    if not cfg.s1_bridge_enabled: return regions,next_id
    snapshot=list(regions); s1={cell for cell,state in state_map.items() if state=="S1"}
    # Enumerate short 4-neighbour S1 paths between exactly two distinct region boundaries.
    boundary=defaultdict(set)
    for r in snapshot:
        for f,b in r["observed_cells"]:
            for n in ((f-1,b),(f+1,b),(f,b-1),(f,b+1)):
                if n in s1: boundary[n].add(r["region_id"])
    candidates=[]
    for start in sorted(s1):
        initial=tuple(sorted(boundary.get(start,set())))
        q=deque([(start,[start],initial)]); seen={(start,initial)}
        while q:
            cell,path,endpoint_ids=q.popleft()
            endpoints=tuple(sorted(set(endpoint_ids) | boundary.get(cell,set())))
            if len(endpoints)>=2:
                ids=list(endpoints)
                if len(ids)==2 and len(path)<=cfg.s1_max_bridge_cells:
                    fs=[x[0] for x in path]; bs=[x[1] for x in path]
                    if max(fs)-min(fs)+1<=cfg.s1_max_bridge_frames and max(bs)-min(bs)+1<=cfg.s1_max_bridge_bins:
                        us=[]
                        for x in path:
                            p=power_map.get(x); floor=local_floor.get(x)
                            if p is None or floor is None or p<=0 or floor<=0: us=[]; break
                            db=10*math.log10(p/floor); us.append(_clip((db-6)/6))
                        if us and statistics.median(us)>=cfg.s1_min_median_normalized_activity:
                            candidates.append({"ids":ids,"path":path,"median_u":statistics.median(us),"score":_clip(.5*statistics.median(us)+.5*(1-(len(path)-1)/4))})
                continue
            if len(path)>=cfg.s1_max_bridge_cells: continue
            f,b=cell
            for n in sorted(((f-1,b),(f+1,b),(f,b-1),(f,b+1))):
                state=(n,tuple(sorted(set(endpoints)|boundary.get(n,set()))))
                if n in s1 and state not in seen:
                    seen.add(state); q.append((n,path+[n],state[1]))
    # Deterministic conflict selection; each cell and each region at most once.
    candidates.sort(key=lambda x:(len(x["path"]),-x["median_u"],x["ids"]))
    accepted=[]; used_cells=set(); used_regions=set()
    for c in candidates:
        if c["score"]<cfg.bridge_score_min or used_cells.intersection(c["path"]) or used_regions.intersection(c["ids"]):
            events.append({"stage":"12-B4","input_region_ids":c["ids"],"status":"rejected","reason_code":"competing_or_low_score","bridge_score":c["score"]}); continue
        a,b=[next(r for r in snapshot if r["region_id"]==rid) for rid in c["ids"]]
        ok,reason=_growth_ok(a,b,cfg)
        if not ok:
            events.append({"stage":"12-B4","input_region_ids":c["ids"],"status":"rejected","reason_code":reason,"bridge_score":c["score"]}); continue
        accepted.append((a,b,c)); used_cells.update(c["path"]); used_regions.update(c["ids"])
    out=[r for r in snapshot if r["region_id"] not in used_regions]
    for a,b,c in accepted:
        next_id+=1; rec=_merge_record(a,b,{"stage":"12-B4","s1_cells":c["path"],"connector":{"kind":"s1_observed_path","virtual":False}},next_id,max(a.get("generation",0),b.get("generation",0))+1)
        rec["s1_cells"]=set(c["path"]); out.append(rec)
        events.append({"stage":"12-B4","input_region_ids":c["ids"],"output_region_id":rec["region_id"],"status":"accepted","reason_code":"s1_bridge_passed","bridge_score":c["score"],"s1_cells":[list(x) for x in c["path"]]})
    return sorted(out,key=lambda r:r["region_id"]),next_id


def extract_features(region:dict,state_map:dict,power_map:dict,manifest:dict) -> dict:
    cells=region["observed_cells"]; f0,f1,b0,b1=_bbox([_aggregate_temp([region],cells)])
    nt=f1-f0; nf=b1-b0; nobs=len(cells); bbox=nt*nf
    frames=defaultdict(list); bins=defaultdict(list)
    for f,b in cells: frames[f].append(b); bins[b].append(f)
    valid=sum(1 for f in range(f0,f1) for b in range(b0,b1) if state_map.get((f,b),"INVALID")!="INVALID")
    invalid=bbox-valid
    powers=[v for x in cells if (v:=power_map.get(x)) is not None]
    freqs=[]; weights=[]
    for f,b in cells:
        p=power_map.get((f,b),0.0); freqs.append(b*manifest["sample_rate"]/manifest["fft_size"]); weights.append(p)
    centroid=(sum(x*w for x,w in zip(freqs,weights))/sum(weights)) if sum(weights)>0 else None
    frame_centroids=[]; frame_rms=[]
    for f,bs in sorted(frames.items()):
        vals=[power_map.get((f,b),0.0) for b in bs]; sw=sum(vals)
        if sw>0: frame_centroids.append(sum((b*manifest["sample_rate"]/manifest["fft_size"])*p for b,p in zip(bs,vals))/sw)
        frame_rms.append(math.sqrt(statistics.mean(vals)) if vals else 0.0)
    temporal=[]
    for f in range(f0,f1-1):
        a=set(frames.get(f,[])); b=set(frames.get(f+1,[])); u=a|b
        if u: temporal.append(len(a&b)/len(u))
    frequency=[]
    for b in range(b0,b1-1):
        a=set(bins.get(b,[])); z=set(bins.get(b+1,[])); u=a|z
        if u: frequency.append(len(a&z)/len(u))
    mean_rms=math.sqrt(statistics.mean(powers)) if powers else None
    med_rms=math.sqrt(statistics.median(powers)) if powers else None
    peak_rms=math.sqrt(max(powers)) if powers else None
    mean_fr=statistics.mean(frame_rms) if frame_rms else 0
    intensity_cv=(statistics.pstdev(frame_rms)/mean_fr) if len(frame_rms)>1 and mean_fr else None
    return {"region_id":region["region_id"],"duration_s":nt*manifest["hop_size"]/manifest["sample_rate"],
      "bandwidth_hz":nf*manifest["sample_rate"]/manifest["fft_size"],"frequency_centroid_hz":centroid,
      "mean_cell_rms":mean_rms,"median_cell_rms":med_rms,"peak_cell_rms":peak_rms,"observed_cell_count":nobs,
      "s1_bridge_cell_count":len(region["s1_cells"]),"connector_count":len(region["connectors"]),
      "occupancy_density":nobs/bbox if bbox else 0.0,"temporal_continuity":statistics.mean(temporal) if temporal else None,
      "frequency_continuity":statistics.mean(frequency) if frequency else None,"aspect_ratio":nt/max(1,nf),
      "centroid_variation_hz":statistics.pstdev(frame_centroids) if len(frame_centroids)>=2 else None,
      "intensity_variation_cv":intensity_cv,"feature_completeness":valid/bbox if bbox else 0.0,
      "invalid_fraction":invalid/bbox if bbox else 0.0,"bbox_frames":nt,"bbox_bins":nf}


def classify(features:dict,manifest:dict) -> dict:
    D=features["duration_s"]; W=features["bandwidth_hz"]; fc=features["frequency_centroid_hz"]
    df=manifest["sample_rate"]/manifest["fft_size"]
    Ct=features["temporal_continuity"]; rho=features["occupancy_density"]; sigma=features["centroid_variation_hz"]
    fallback=False
    if Ct is None: Ct=0.0; fallback=True
    st=math.exp(-D/.15)*(.5+.5*(1-Ct))
    if fc is None or W is None: ston=sd=None
    else:
        rel=W/max(abs(fc),df); narrow=math.exp(-rel/.08)
        # Draft 0.5 permits Ct=0 fallback only for Transient; do not invent
        # temporal continuity for Tonal when the feature is undefined.
        ston=None if sigma is None or features["temporal_continuity"] is None else (narrow*math.exp(-sigma/max(W,df))*(.5+.5*Ct))**(1/3)
        broad=1-math.exp(-rel/.20); long=1-math.exp(-D/.25)
        sd=(broad*(.5+.5*rho)*(.5+.5*long))**(1/3)
    scores={"Transient":_clip(st),"Tonal":None if ston is None else _clip(ston),"Diffuse":None if sd is None else _clip(sd)}
    labels=[k for k,v in scores.items() if v is not None and v>=.60]
    if features["feature_completeness"]<.80 or not labels: labels=["Unclassified"]
    return {"region_id":features["region_id"],"labels":labels,"scores":scores,"score_semantics":"heuristic_fit_score_not_probability",
            "threshold":.60,"fallback_used":fallback,"formula_version":"KRM-S12-D-0.5"}


def run_stage12(data:dict,config:Optional[Config]=None) -> dict:
    validate_input(data); cfg=config or Config(); cfg.validate()
    start=time.perf_counter(); manifest=data["input_manifest"]
    cells_data=data["cells"]
    state_map=_state_map_from_input(data)
    power_map=_CellFieldView(cells_data, "power")
    activity=_CellFieldView(cells_data, "delta_db")
    local_floor=_CellFieldView(cells_data, "local_floor_power")
    manifest_hash=_sha(manifest)
    active_cells={(int(k.split(",")[0]),int(k.split(",")[1])) for k,v in cells_data.items() if v.get("state") in ("S2","S3")}
    orig=[]; original_owner={}
    # 12-A: frame-local contiguous frequency runs, immutable original records.
    byframe=defaultdict(list)
    for f,b in active_cells: byframe[f].append(b)
    for f in sorted(byframe):
        bins=sorted(byframe[f]); s=p=bins[0]
        runs=[]
        for b in bins[1:]:
            if b==p+1: p=b
            else: runs.append((s,p+1)); s=p=b
        runs.append((s,p+1))
        for lo,hi in runs:
            cells={(f,b) for b in range(lo,hi)}; rid=f"OR-{len(orig)+1:06d}"
            rec=_region_record(rid,cells,state_map,manifest_hash); rec["frame_index"]=f; rec["observed_cells"]=cells; rec["s1_cells"]=set(); rec["connectors"]=[]; rec["member_original_ids"]=[rid]; rec["generation"]=0
            orig.append(rec)
            for cell in cells: original_owner[cell]=rid
    events=[]; next_id=0
    # B1: exact 4-neighbour connected components over active cells.
    orig_by_id={r["region_id"]:r for r in orig}
    b1=[]
    for comp in _connected_components(active_cells):
        parents=sorted({original_owner[cell] for cell in comp})
        if len(parents)==1: base=orig_by_id[parents[0]]; b1.append(base)
        else:
            next_id+=1; rec={"region_id":f"MR-{next_id:06d}","generation":1,"parent_region_ids":parents,"member_original_ids":parents,
              "observed_cells":comp,"s1_cells":set(),"connectors":[],"integration_stage":"12-B1","status":"active"}
            rec.update(_aggregate_temp([], comp)); b1.append(rec)
            events.append({"stage":"12-B1","input_region_ids":parents,"output_region_id":rec["region_id"],"status":"accepted","reason_code":"four_neighbour_component"})
    # B1 singletons/runs remain original; normalize records to runtime shape.
    current=[]
    for r in b1:
        if "observed_cells" not in r: continue
        current.append(r)
    current,next_id=_apply_bridge_pass(current,"12-B2",cfg,state_map,activity,events,next_id)
    current,next_id=_apply_bridge_pass(current,"12-B3",cfg,state_map,activity,events,next_id)
    current,next_id=_apply_s1(current,cfg,state_map,power_map,local_floor,events,next_id)
    run_id = "RUN-" + _sha({"input":manifest_hash,"config":asdict(cfg),"software":"KRM-Stage12-1.1.0"})[:16]
    config_hash = _sha(asdict(cfg))
    for index, event in enumerate(events, 1):
        event["event_id"] = f"ME-{index:06d}"
        event["run_id"] = run_id
        event["parameters_snapshot_hash"] = config_hash
        event["created_from_snapshot"] = _sha({"stage":event.get("stage"),"input_region_ids":event.get("input_region_ids",[])})
    # 12-B5: validate lineage, cell conservation, and disjoint active observed ownership.
    seen=set()
    for r in current:
        if seen & r["observed_cells"]: raise AssertionError("overlapping active observed-cell ownership")
        seen |= r["observed_cells"]
        if not set(r["member_original_ids"]): raise AssertionError("merged region has no original lineage")
    if seen != active_cells: raise AssertionError("observed active cells were lost or added")
    features=[]; classifications=[]
    for r in current:
        f=extract_features(r,state_map,power_map,manifest); features.append(f); classifications.append(classify(f,manifest))
    # Stable serialization: runtime sets become sorted arrays/RLE.
    def serial_region(r):
        cells=sorted(r["observed_cells"]); s1=sorted(r["s1_cells"])
        return {k:v for k,v in r.items() if k not in ("observed_cells","s1_cells")} | {
          "observed_shape_rle":rle_encode(cells),"observed_cell_count":len(cells),"s1_cells":[list(x) for x in s1],
          "connectors":r["connectors"]}
    original_out=[]
    for r in orig:
        original_out.append({k:v for k,v in r.items() if k not in ("observed_cells","s1_cells","connectors","member_original_ids","generation")} )
    elapsed=time.perf_counter()-start
    result = {"schema_version":"krm-stage12-output-1.0","run_manifest":{"run_id":run_id,"input_manifest_hash":manifest_hash,"config":asdict(cfg),
      "config_hash":config_hash,"software_version":"KRM-Stage12-1.1.0","started_unix":None,"elapsed_seconds":elapsed,
      "channel_id":manifest["channel_id"],"resolution_id":manifest["resolution_id"]},
      "original_regions":original_out,"merged_regions":[serial_region(r) for r in current],"merge_events":events,
      "features":features,"classifications":classifications,
      "validation":{"active_input_cells":len(active_cells),"active_output_cells":len(seen),"cell_conservation":seen==active_cells,
       "original_region_count":len(orig),"active_region_count":len(current),"rle_roundtrip":all(rle_decode(rle_encode(x))==x for x in [active_cells]),
       "raw_pcm_mutated":False,
       "stage11_adapter_status":("stage11-source-replay" if data.get("schema_version") == "krm-stage11-normalized-1.1" and "stage11_source_sha256" in manifest else ("sparse-complete-grid-input" if data.get("schema_version") == "krm-stage11-normalized-1.1" else "normalized-input")),
       "input_grid_complete":data.get("input_manifest", {}).get("grid_complete", False),
       "implicit_cell_state":data.get("input_manifest", {}).get("implicit_cell_state", None)}}
    result["run_manifest"]["canonical_result_hash"] = canonical_result_hash(result)
    return result


def canonical_result_hash(result: dict) -> str:
    """Hash deterministic analytical outputs, excluding wall-clock timing."""
    payload = {
        "schema_version": result.get("schema_version"),
        "input_manifest_hash": result.get("run_manifest", {}).get("input_manifest_hash"),
        "config_hash": result.get("run_manifest", {}).get("config_hash"),
        "software_version": result.get("run_manifest", {}).get("software_version"),
        "original_regions": result.get("original_regions", []),
        "merged_regions": result.get("merged_regions", []),
        "merge_events": result.get("merge_events", []),
        "features": result.get("features", []),
        "classifications": result.get("classifications", []),
        "validation": result.get("validation", {}),
    }
    return _sha(payload)


def rollback_stage12(data: dict, result: dict, target_region_id: str | None = None) -> dict:
    """Return a rollback view without mutating the original run.

    target_region_id=None performs full rollback to immutable 12-A regions.
    A target ID performs partial rollback of that active merged region to its
    original 12-A members. This is region-level rollback; event-branch rollback
    below an intermediate, non-active generation is intentionally not exposed.
    """
    validate_input(data)
    originals = {r["region_id"]: r for r in result["original_regions"]}
    active = list(result["merged_regions"])
    if target_region_id is not None and not any(r["region_id"] == target_region_id for r in active):
        raise KeyError(f"active region not found: {target_region_id}")
    selected = [r for r in active if target_region_id is None or r["region_id"] == target_region_id]
    keep = [r for r in active if r not in selected]
    restore_ids = sorted(set().union(*(set(r.get("member_original_ids", [r["region_id"]])) for r in selected))) if selected else []
    state_map = _state_map_from_input(data)
    power_map = {tuple(map(int, k.split(","))): v["power"] for k, v in data["cells"].items() if v.get("power") is not None}
    restored = []
    for rid in restore_ids:
        src = originals[rid]
        restored.append({
            "region_id": rid, "generation": 0, "parent_region_ids": [],
            "member_original_ids": [rid], "observed_shape_rle": src["shape_rle"],
            "observed_cell_count": src["cell_count"], "s1_cells": [], "connectors": [],
            "integration_stage": "12-A", "status": "active",
        })
    merged = sorted(keep + restored, key=lambda r: r["region_id"])
    manifest = data["input_manifest"]
    def to_runtime(r):
        return {**r, "observed_cells": rle_decode(r.get("observed_shape_rle", r.get("shape_rle", []))),
                "s1_cells": {tuple(x) for x in r.get("s1_cells", [])}, "connectors": r.get("connectors", [])}
    feats=[]; classes=[]
    for r in merged:
        rr=to_runtime(r)
        feats.append(extract_features(rr, state_map, power_map, manifest))
        classes.append(classify(feats[-1], manifest))
    out = dict(result)
    out["merged_regions"] = merged
    out["features"] = feats
    out["classifications"] = classes
    out["rollback_history"] = list(result.get("rollback_history", [])) + [{
        "event_id": f"RB-{len(result.get('rollback_history', []))+1:06d}",
        "action": "full_rollback" if target_region_id is None else "partial_region_rollback",
        "target_region_id": target_region_id,
        "restored_original_region_ids": restore_ids,
        "source_run_hash": result.get("run_manifest", {}).get("canonical_result_hash"),
        "raw_pcm_mutated": False,
    }]
    out["run_manifest"] = dict(result["run_manifest"])
    out["run_manifest"]["canonical_result_hash"] = canonical_result_hash(out)
    out["validation"] = dict(result["validation"])
    out["validation"]["active_region_count"] = len(merged)
    out["validation"]["rollback_applied"] = True
    out["validation"]["rollback_scope"] = "full" if target_region_id is None else "active-region"
    return out


def replay_stage12(data: dict, config: Optional[Config] = None) -> dict:
    """Clean deterministic replay from the immutable normalized input."""
    return run_stage12(data, config)


def write_bundle(result:dict,outdir:str|Path):
    out=Path(outdir); out.mkdir(parents=True,exist_ok=True)
    def dump(name,obj):
        (out/name).write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    dump("run_manifest.json",result["run_manifest"]); dump("validation_report.json",result["validation"])
    if "rollback_history" in result: dump("rollback_history.json", result["rollback_history"])
    for name,key in (("original_regions.jsonl","original_regions"),("merged_regions.jsonl","merged_regions"),("merge_events.jsonl","merge_events"),("classification_results.jsonl","classifications")):
        (out/name).write_text("".join(json.dumps(x,ensure_ascii=False,sort_keys=True,allow_nan=False)+"\n" for x in result[key]),encoding="utf-8")
    rows=result["features"]
    if rows:
        with open(out/"region_features.csv","w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    files=sorted(p for p in out.iterdir() if p.is_file() and p.name!="SHA256SUMS.txt")
    (out/"SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files),encoding="utf-8")
