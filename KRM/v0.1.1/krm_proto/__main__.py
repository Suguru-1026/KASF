from __future__ import annotations

import argparse
import json
from pathlib import Path

from .capture import capture_residual
from .fastgen import generate_kasf, generate_and_capture
from .container import iter_blocks, read_file_header
from .events import (
    P2Quantile,
    StreamingEnergyEventDetector,
    StreamingFrameFeatures,
)
from .predictor import StreamingPredictorVerifier
from .restore import inspect_krmi, restore_krmi, restore_raw_pcm, verify_krmi
from .tea import iter_transient_candidates_from_chunks
from krm_stage12 import Config as Stage12Config, load_input as load_stage12_input
from krm_stage12 import run_stage12, write_bundle as write_stage12_bundle, rollback_stage12
import wave
from .pcm import read_wav_spec, decode_interleaved


def analyze_krmi_streaming(
    path: str | Path,
    window_samples: int,
    hop_samples: int,
    threshold: float | None,
    baseline_multiplier: float,
    absolute_floor: float,
    merge_gap_frames: int,
) -> dict:
    """Analyze all channels with one file scan per pass, bounded by block/window size."""
    with open(path, "rb") as fp:
        manifest, _, _ = read_file_header(fp)
    channels = int(manifest["audio"]["channels"])
    sample_rate = int(manifest["audio"]["sample_rate_hz"])
    extractors = [StreamingFrameFeatures(window_samples, hop_samples) for _ in range(channels)]

    if threshold is None:
        estimators = [P2Quantile(0.5) for _ in range(channels)]
        with open(path, "rb") as fp:
            _, _, _ = read_file_header(fp)
            for block in iter_blocks(fp, manifest):
                for ch in range(channels):
                    for frame in extractors[ch].feed(block.residual[ch]):
                        estimators[ch].add(frame["rms"])
        for ch in range(channels):
            for frame in extractors[ch].finish():
                estimators[ch].add(frame["rms"])
        thresholds = [max(absolute_floor, estimator.value * baseline_multiplier) for estimator in estimators]
        threshold_method = "two-pass P² approximate median"
    else:
        thresholds = [float(threshold)] * channels
        threshold_method = "user-supplied fixed threshold"

    detectors = [StreamingEnergyEventDetector(thresholds[ch], merge_gap_frames) for ch in range(channels)]
    extractors = [StreamingFrameFeatures(window_samples, hop_samples) for _ in range(channels)]
    with open(path, "rb") as fp:
        _, _, _ = read_file_header(fp)
        for block in iter_blocks(fp, manifest):
            for ch in range(channels):
                for frame in extractors[ch].feed(block.residual[ch]):
                    detectors[ch].feed(frame)
    results = []
    for ch in range(channels):
        for frame in extractors[ch].finish():
            detectors[ch].feed(frame)
        result = detectors[ch].finish()
        result.update({
            "channel": ch,
            "threshold_method": threshold_method,
            "window_samples": window_samples,
            "hop_samples": hop_samples,
            "event_semantics": "energy_activity_candidate; not a source-class or MP event label",
        })
        results.append(result)

    return {
        "sample_rate_hz": sample_rate,
        "sample_count_per_channel": int(manifest["audio"]["sample_count"]),
        "channels": results,
        "notice": "Coarse time-domain activity probe only; not MP, HPSS, STN, or source separation. Residual PCM is processed block-by-block.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="krm_proto",
        description="KRM/KRC/KRM-IF research prototype (not production software)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("capture", help="Create a KRM-IF file from Source and Base PCM WAV files")
    p.add_argument("--source", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--chunk-samples", type=int, default=65_536)
    p.add_argument("--resume", action="store_true", help="Resume a checkpointed capture; inputs are replayed from sample zero")

    p = sub.add_parser("restore", help="Restore a PCM WAV from KRM-IF Base + Residual")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)

    p = sub.add_parser("restore-raw", help="Restore interleaved raw PCM (no RIFF/WAV 4 GiB limit)")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)

    p = sub.add_parser("verify", help="Verify checksums and exact reconstructed PCM")
    p.add_argument("--input", required=True)
    p.add_argument("--source", help="Optional original WAV to compare against")

    p = sub.add_parser("inspect", help="Print KRM-IF manifest")
    p.add_argument("--input", required=True)

    p = sub.add_parser("analyze", help="Run bounded-memory residual energy activity analysis")
    p.add_argument("--input", required=True)
    p.add_argument("--window-samples", type=int, default=1024)
    p.add_argument("--hop-samples", type=int, default=512)
    p.add_argument("--threshold", type=float)
    p.add_argument("--baseline-multiplier", type=float, default=3.0)
    p.add_argument("--absolute-floor", type=float, default=1.0)
    p.add_argument("--merge-gap-frames", type=int, default=1)
    p.add_argument("--output-json")

    p = sub.add_parser("predict-demo", help="Run streaming exact integer order-1/order-2 predictor checks")
    p.add_argument("--input", required=True)

    p = sub.add_parser("tea", help="Run the independent time-domain TEA transient-candidate channel on a PCM WAV")
    p.add_argument("--input", required=True)
    p.add_argument("--window-samples", type=int, default=256)
    p.add_argument("--hop-samples", type=int, default=64)
    p.add_argument("--baseline-frames", type=int, default=8)
    p.add_argument("--rise-ratio", type=float, default=3.0)
    p.add_argument("--crest-factor", type=float, default=5.0)
    p.add_argument("--absolute-rms-floor", type=float, default=0.0)
    p.add_argument("--merge-gap-frames", type=int, default=1)
    p.add_argument("--chunk-frames", type=int, default=65536)
    p.add_argument("--output-json")

    p = sub.add_parser("stage12", help="Run Stage12 on a normalized Stage11 cell-map JSON")
    p.add_argument("--input", required=True)
    p.add_argument("--output", default="KRM_STAGE12_OUTPUT")
    p.add_argument("--config", help="optional Stage12 Config JSON")
    p.add_argument("--rollback-all", action="store_true", help="also emit a full-rollback view")
    p.add_argument("--rollback-region", help="also emit a partial rollback view for this active region ID")

    p = sub.add_parser("generate-fast", help="Generate a KASF v1 file with the native C++ spectral-pursuit baseline")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--frame-ms", type=float, default=10.0)
    p.add_argument("--max-components", type=int, default=48)
    p.add_argument("--threshold-db", type=float, default=-58.0)
    p.add_argument("--min-hz", type=float, default=15.0)
    p.add_argument("--no-edge-pad", action="store_true", help="Disable half-window pre/post guard frames")
    p.add_argument("--no-tracking", action="store_true", help="Disable temporal component association metadata")
    p.add_argument("--experimental-track-refine", action="store_true", help="Enable experimental audio-changing phase-derived frequency refinement")
    p.add_argument("--tracker-assignment", choices=("greedy", "hungarian"), default="greedy")
    p.add_argument("--base-wav", help="Also emit experimental local-Reader Base WAV")
    p.add_argument("--force", action="store_true")
    p.add_argument("--binary")

    p = sub.add_parser("bridge-fast", help="FastGen -> KASF Reader -> Base WAV -> KRC/KRM-IF in one run")
    p.add_argument("--source", required=True)
    p.add_argument("--kasf", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--krmi", required=True)
    p.add_argument("--frame-ms", type=float, default=10.0)
    p.add_argument("--max-components", type=int, default=48)
    p.add_argument("--threshold-db", type=float, default=-58.0)
    p.add_argument("--min-hz", type=float, default=15.0)
    p.add_argument("--no-edge-pad", action="store_true", help="Disable half-window pre/post guard frames")
    p.add_argument("--no-tracking", action="store_true", help="Disable temporal component association metadata")
    p.add_argument("--experimental-track-refine", action="store_true", help="Enable experimental audio-changing phase-derived frequency refinement")
    p.add_argument("--tracker-assignment", choices=("greedy", "hungarian"), default="greedy")
    p.add_argument("--chunk-samples", type=int, default=65_536)
    p.add_argument("--resume", action="store_true", help="Resume KRC capture using the saved KASF and Base WAV")
    p.add_argument("--force", action="store_true")
    p.add_argument("--binary")

    args = parser.parse_args()
    if args.command == "capture":
        manifest = capture_residual(args.source, args.base, args.output, args.chunk_samples, resume=args.resume)
        print(json.dumps({"status": "CREATED", "output": args.output, "audio": manifest["audio"], "container": manifest["container"]}, ensure_ascii=False, indent=2))
    elif args.command == "restore":
        result = restore_krmi(args.input, args.output)
        print(json.dumps({"status": "RESTORED", "output": args.output, **result}, ensure_ascii=False, indent=2))
    elif args.command == "restore-raw":
        result = restore_raw_pcm(args.input, args.output)
        print(json.dumps({"status": "RESTORED_RAW_PCM", "output": args.output, **result}, ensure_ascii=False, indent=2))
    elif args.command == "verify":
        print(json.dumps(verify_krmi(args.input, args.source), ensure_ascii=False, indent=2))
    elif args.command == "inspect":
        print(json.dumps(inspect_krmi(args.input), ensure_ascii=False, indent=2))
    elif args.command == "analyze":
        if args.window_samples < 1 or args.hop_samples < 1:
            raise SystemExit("window-samples and hop-samples must be positive")
        if args.baseline_multiplier <= 0 or args.absolute_floor < 0 or args.merge_gap_frames < 0:
            raise SystemExit("Invalid event detector parameters")
        payload = analyze_krmi_streaming(
            args.input, args.window_samples, args.hop_samples, args.threshold,
            args.baseline_multiplier, args.absolute_floor, args.merge_gap_frames,
        )
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.output_json:
            Path(args.output_json).write_text(rendered, encoding="utf-8")
        print(rendered)
    elif args.command == "tea":
        if args.chunk_frames < 1:
            raise SystemExit("chunk-frames must be positive")
        channel_results = []
        with wave.open(args.input, "rb") as wf:
            spec = read_wav_spec(wf)
        for ch in range(spec.channels):
            def channel_chunks(channel_index=ch):
                with wave.open(args.input, "rb") as wf:
                    while True:
                        raw = wf.readframes(args.chunk_frames)
                        if not raw:
                            break
                        decoded = decode_interleaved(raw, spec)
                        yield decoded[channel_index]
            events = list(iter_transient_candidates_from_chunks(
                channel_chunks(), args.window_samples, args.hop_samples,
                baseline_frames=args.baseline_frames,
                rise_ratio_threshold=args.rise_ratio,
                crest_factor_threshold=args.crest_factor,
                absolute_rms_floor=args.absolute_rms_floor,
                merge_gap_frames=args.merge_gap_frames,
            ))
            channel_results.append({"channel": ch, "candidate_count": len(events), "events": events})
        payload = {"schema_version":"krm-tea-wav-report-1.0", "detector":"KRM-TEA-TD-Candidate-v0.2",
                   "input":args.input, "sample_rate_hz":spec.sample_rate, "channels":spec.channels,
                   "sample_count_per_channel":spec.sample_count,
                   "parameters":{"window_samples":args.window_samples,"hop_samples":args.hop_samples,
                     "baseline_frames":args.baseline_frames,"rise_ratio_threshold":args.rise_ratio,
                     "crest_factor_threshold":args.crest_factor,"absolute_rms_floor":args.absolute_rms_floor,
                     "merge_gap_frames":args.merge_gap_frames,"chunk_frames":args.chunk_frames},
                   "channel_results":channel_results,
                   "notice":"Candidates only; not source identity, exact onset truth, or artifact diagnosis. Raw PCM is read-only."}
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.output_json: Path(args.output_json).write_text(rendered, encoding="utf-8")
        print(rendered)
    elif args.command == "stage12":
        cfg = Stage12Config(**json.loads(Path(args.config).read_text(encoding="utf-8"))) if args.config else Stage12Config()
        source = load_stage12_input(args.input)
        result = run_stage12(source, cfg)
        write_stage12_bundle(result, args.output)
        if args.rollback_all and args.rollback_region:
            raise SystemExit("choose only one rollback mode")
        if args.rollback_all:
            rolled = rollback_stage12(source, result)
            write_stage12_bundle(rolled, str(args.output) + "_ROLLBACK_ALL")
        elif args.rollback_region:
            rolled = rollback_stage12(source, result, args.rollback_region)
            write_stage12_bundle(rolled, str(args.output) + "_ROLLBACK_PARTIAL")
        print(json.dumps({"status":"PASS", "validation":result["validation"],
                          "canonical_result_hash":result["run_manifest"]["canonical_result_hash"]}, ensure_ascii=False, indent=2))
    elif args.command == "generate-fast":
        result = generate_kasf(args.input, args.output, frame_ms=args.frame_ms,
            max_components=args.max_components, threshold_db=args.threshold_db,
            min_hz=args.min_hz, edge_pad=not args.no_edge_pad,
            temporal_tracking=not args.no_tracking,
            temporal_refinement=args.experimental_track_refine, tracker_assignment=args.tracker_assignment,
            base_wav=args.base_wav, force=args.force, binary=args.binary)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "bridge-fast":
        result = generate_and_capture(args.source, args.kasf, args.base, args.krmi,
            frame_ms=args.frame_ms, max_components=args.max_components,
            threshold_db=args.threshold_db, min_hz=args.min_hz,
            edge_pad=not args.no_edge_pad, temporal_tracking=not args.no_tracking,
            temporal_refinement=args.experimental_track_refine, tracker_assignment=args.tracker_assignment,
            chunk_samples=args.chunk_samples, force=args.force, resume=args.resume, binary=args.binary)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "predict-demo":
        with open(args.input, "rb") as fp:
            manifest, _, _ = read_file_header(fp)
            channel_count = int(manifest["audio"]["channels"])
            verifiers = [[StreamingPredictorVerifier(order) for order in (1, 2)] for _ in range(channel_count)]
            for block in iter_blocks(fp, manifest):
                for channel in range(channel_count):
                    for verifier in verifiers[channel]:
                        verifier.feed(block.residual[channel])
        reports = []
        for channel in range(channel_count):
            for verifier in verifiers[channel]:
                reports.append(verifier.finish() | {"channel": channel})
        if not all(report["exact"] for report in reports):
            raise SystemExit("Predictor round-trip failed")
        print(json.dumps({"status": "PASS", "reports": reports}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
