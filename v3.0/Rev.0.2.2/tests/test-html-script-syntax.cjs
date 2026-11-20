const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const htmlPath = process.argv[2] ? path.resolve(process.argv[2]) : path.join(__dirname, '../KASF-2.0-Evolution-Rev0.9.19-Three-Worker.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const re = /<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi;
let match;
let checked = 0;
while ((match = re.exec(html))) {
  const attrs = match[1];
  const body = match[2];
  const id = attrs.match(/\bid=["']([^"']+)["']/i)?.[1] || `inline-${checked + 1}`;
  const type = attrs.match(/\btype=["']([^"']+)["']/i)?.[1]?.toLowerCase() || 'text/javascript';
  if (id === 'kasf-wasm-binary') continue;
  if (type !== 'text/javascript' && id !== 'embedded-worker-a' && id !== 'embedded-worker-b') continue;
  const result = spawnSync(process.execPath, ['--check', '-'], { input: body, encoding: 'utf8' });
  if (result.status !== 0) {
    process.stderr.write(`Syntax error in ${id}:\n${result.stderr || result.stdout}`);
    process.exit(result.status || 1);
  }
  checked++;
}
if (checked !== 6) throw new Error(`Expected 6 executable script blocks; checked ${checked}`);
console.log(`PASS: ${checked} executable script blocks parse`);
