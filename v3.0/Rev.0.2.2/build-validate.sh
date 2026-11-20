#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

: "${CLANGXX:=clang++}"
: "${KASF_HTML:=$ROOT/KASF-v3.0-Rev0.2.2.html}"
: "${KASF_WASM_OUT:=$ROOT/build/kasf-core-clang-validation.wasm}"

command -v "$CLANGXX" >/dev/null || { echo "Clang compiler not found: $CLANGXX" >&2; exit 127; }
[[ -f "$KASF_HTML" ]] || { echo "Target HTML not found: $KASF_HTML" >&2; exit 2; }
mkdir -p "$(dirname "$KASF_WASM_OUT")"

"$CLANGXX" "$ROOT/src/kasf_wasm.cpp" --target=wasm32-unknown-unknown -O3 -msimd128 -ffp-contract=off -fno-exceptions -fno-rtti -nostdlib \
  -Wl,--no-entry -Wl,--export-memory \
  -Wl,--export=kasf_reset_heap -Wl,--export=kasf_alloc -Wl,--export=kasf_simd_enabled \
  -Wl,--export=kasf_solve_ridge_qr -Wl,--export=kasf_solve_ridge_qr_inplace \
  -Wl,--export=kasf_fft_inplace_scalar -Wl,--export=kasf_fft_inplace \
  -Wl,--export=kasf_dpss_power_iteration \
  -Wl,--export=kasf_qrp_exact_gate -Wl,--export=kasf_gpo_component_sse \
  -Wl,--export=kasf_dpss_build_toeplitz \
  -Wl,--export=kasf_haar_best_update -Wl,--export=kasf_haar_residual_energy \
  -Wl,--initial-memory=16777216 -Wl,--max-memory=268435456 -Wl,--strip-all \
  -o "$KASF_WASM_OUT"

python3 tools/embed_wasm.py "$KASF_WASM_OUT" "$KASF_HTML"
python3 tools/embed_wasm.py "$KASF_WASM_OUT" "$KASF_HTML" --check
printf 'Validation build complete: %s -> %s\n' "$KASF_WASM_OUT" "$KASF_HTML"
