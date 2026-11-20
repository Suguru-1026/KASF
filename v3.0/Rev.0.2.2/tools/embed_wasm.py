#!/usr/bin/env python3
"""Safely embed a standalone WASM binary into a KASF HTML marker."""
from pathlib import Path
import base64
import hashlib
import os
import sys
import tempfile

OPEN = '<script id="kasf-wasm-binary" type="text/plain">'
CLOSE = '</script>'


def extract_region(html: str):
    if html.count(OPEN) != 1:
        raise ValueError(f"expected exactly one WASM marker, found {html.count(OPEN)}")
    start = html.index(OPEN) + len(OPEN)
    end = html.find(CLOSE, start)
    if end < 0:
        raise ValueError("WASM marker has no closing </script>")
    return start, end


def main():
    if len(sys.argv) not in (3, 4) or (len(sys.argv) == 4 and sys.argv[3] != '--check'):
        raise SystemExit("usage: embed_wasm.py input.wasm output.html [--check]")

    wasm_path, html_path = map(Path, sys.argv[1:3])
    check_only = len(sys.argv) == 4
    wasm = wasm_path.read_bytes()
    if not wasm.startswith(b'\0asm'):
        raise SystemExit("input is not a WebAssembly binary")
    encoded = base64.b64encode(wasm).decode('ascii')
    html = html_path.read_text(encoding='utf-8')
    start, end = extract_region(html)
    current = ''.join(html[start:end].split())

    if check_only:
        if current != encoded:
            raise SystemExit("embedded WASM does not match input binary")
        print(f"Verified {len(wasm):,} bytes; SHA-256 {hashlib.sha256(wasm).hexdigest()}")
        return

    updated = html[:start] + encoded + html[end:]
    fd, temp_name = tempfile.mkstemp(prefix=html_path.name + '.', suffix='.tmp', dir=html_path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, html_path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    print(f"Embedded {len(wasm):,} bytes into {html_path}; SHA-256 {hashlib.sha256(wasm).hexdigest()}")


if __name__ == '__main__':
    main()
