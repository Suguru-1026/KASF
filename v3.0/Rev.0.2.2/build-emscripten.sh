#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

: "${EMXX:=em++}"
: "${KASF_HTML:=$ROOT/KASF-v3.0-Rev0.2.2.html}"
: "${KASF_WASM_OUT:=$ROOT/build/kasf-core.wasm}"

command -v "$EMXX" >/dev/null || { echo "Emscripten compiler not found: $EMXX" >&2; exit 127; }
[[ -f "$KASF_HTML" ]] || { echo "Target HTML not found: $KASF_HTML" >&2; exit 2; }
mkdir -p "$(dirname "$KASF_WASM_OUT")"

"$EMXX" src/kasf_wasm.cpp -O3 -msimd128 -ffp-contract=off -fno-exceptions -fno-rtti \
  -s STANDALONE_WASM=1 -s ALLOW_MEMORY_GROWTH=1 \
  -s INITIAL_MEMORY=16777216 -s MAXIMUM_MEMORY=268435456 \
  -s FILESYSTEM=0 \
  -s EXPORTED_FUNCTIONS='["_kasf_reset_heap","_kasf_alloc","_kasf_simd_enabled","_kasf_solve_ridge_qr","_kasf_solve_ridge_qr_inplace","_kasf_fft_inplace_scalar","_kasf_fft_inplace","_kasf_dpss_power_iteration","_kasf_qrp_exact_gate","_kasf_gpo_component_sse","_kasf_dpss_build_toeplitz","_kasf_haar_best_update","_kasf_haar_residual_energy"]' \
  -o "$KASF_WASM_OUT"

python3 tools/embed_wasm.py "$KASF_WASM_OUT" "$KASF_HTML"
python3 tools/embed_wasm.py "$KASF_WASM_OUT" "$KASF_HTML" --check
printf 'Build complete: %s -> %s\n' "$KASF_WASM_OUT" "$KASF_HTML"
