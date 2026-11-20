# KASF WASM Source Build Pipeline

## Source of truth

- C++ source: `src/kasf_wasm.cpp`
- Primary executable HTML: `KASF-v3.0-Rev0.2.2.html`
- Embedded payload marker: `<script id="kasf-wasm-binary" type="text/plain">`
- Clang validation output: `build/kasf-core-clang-validation.wasm`
- Emscripten production output: `build/kasf-core.wasm`

The source package contains one current primary executable and historical comparison HTML files. The build scripts must target the primary executable, not the Rev0.9.16 comparison file.

## Clang validation build

```bash
bash build-validate.sh
```

This compiles `src/kasf_wasm.cpp` for `wasm32-unknown-unknown`, embeds the result into the primary HTML, and performs a byte-for-byte embed verification.

Compiler and paths can be overridden:

```bash
CLANGXX=clang++ \
KASF_HTML="$PWD/KASF-v3.0-Rev0.2.2.html" \
KASF_WASM_OUT="$PWD/build/kasf-core-clang-validation.wasm" \
bash build-validate.sh
```

## Emscripten production build

```bash
bash build-emscripten.sh
```

This uses `em++` and the same exported-function set, SIMD128 setting, floating-point contraction setting, and memory limits as the source package's established build configuration. `EMXX`, `KASF_HTML`, and `KASF_WASM_OUT` are overrideable.

Emscripten is not installed in the validation environment used for this repair. Therefore, the Emscripten production command is repaired and statically inspected, but has not been executed here.

## Embed verification

```bash
python3 tools/embed_wasm.py build/kasf-core-clang-validation.wasm \
  KASF-v3.0-Rev0.2.2.html --check
```

`tools/embed_wasm.py` requires exactly one marker, validates the WASM magic header, writes through a temporary file plus atomic replacement, and supports `--check` for byte-for-byte comparison without modifying the HTML.

## Verified result in this repair

- Clang compilation: PASS.
- WASM output: 17,706 bytes.
- SHA-256: `2a7724def5d3026d08d03a5c0fc0e958d9c627e1266f60e62e35dd06431d4bd4`.
- Embedded payload in the primary HTML: byte-identical to the Clang output.
- The binary hash matches the package's existing validated WASM payload; no WASM algorithm change was made.
