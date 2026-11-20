#!/usr/bin/env node
'use strict';
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const root = path.resolve(__dirname, '..');
const htmlPath = path.join(root, 'KASF-v3.0-Rev0.2.2.html');
const wasmPath = path.join(root, 'build/kasf-core-clang-validation.wasm');
const embed = path.join(root, 'tools/embed_wasm.py');
const html = fs.readFileSync(htmlPath, 'utf8');
const wasm = fs.readFileSync(wasmPath);
const marker = '<script id="kasf-wasm-binary" type="text/plain">';
assert.strictEqual((html.match(/<script id="kasf-wasm-binary"/g) || []).length, 1, 'main HTML must have one WASM marker');
assert(wasm.subarray(0, 4).equals(Buffer.from([0, 97, 115, 109])), 'compiled file must be WASM');
const embedded = html.split(marker)[1].split('</script>')[0].replace(/\s/g, '');
const decoded = Buffer.from(embedded, 'base64');
assert(decoded.equals(wasm), 'main HTML embedded WASM must match Clang output byte-for-byte');
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
assert.strictEqual(sha(decoded), '2a7724def5d3026d08d03a5c0fc0e958d9c627e1266f60e62e35dd06431d4bd4');

const emscriptenScript = fs.readFileSync(path.join(root, 'build-emscripten.sh'), 'utf8');
const clangScript = fs.readFileSync(path.join(root, 'build-validate.sh'), 'utf8');
for (const [name, script] of [['Emscripten', emscriptenScript], ['Clang', clangScript]]) {
  assert(script.includes('KASF-v3.0-Rev0.2.2.html'), `${name} default target must be the current primary HTML`);
  assert(script.includes('KASF_HTML'), `${name} target must be overrideable via KASF_HTML`);
  assert(!script.includes('KASF-2.0-Evolution-Rev0.9.16-WASM-GVP-HAAR-Optimized.html'), `${name} must not point to the missing Rev0.9.16 comparison file`);
}

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'kasf-wasm-embed-'));
try {
  const testHtml = path.join(temp, 'test.html');
  const testWasm = path.join(temp, 'test.wasm');
  fs.writeFileSync(testHtml, `<!doctype html>${marker}old</script>`);
  fs.writeFileSync(testWasm, wasm);
  let r = spawnSync('python3', [embed, testWasm, testHtml], { encoding: 'utf8' });
  assert.strictEqual(r.status, 0, `embed should succeed: ${r.stderr}`);
  r = spawnSync('python3', [embed, testWasm, testHtml, '--check'], { encoding: 'utf8' });
  assert.strictEqual(r.status, 0, `embed --check should succeed: ${r.stderr}`);
  fs.writeFileSync(testHtml, fs.readFileSync(testHtml, 'utf8').replace(embedded, 'AAAA'));
  r = spawnSync('python3', [embed, testWasm, testHtml, '--check'], { encoding: 'utf8' });
  assert.notStrictEqual(r.status, 0, 'embed --check must reject a mismatched embedded payload');
  console.log('PASS: current HTML/WASM byte identity, build target routing, atomic embed and mismatch detection');
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}
