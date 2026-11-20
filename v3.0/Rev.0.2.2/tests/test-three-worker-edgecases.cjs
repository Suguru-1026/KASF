const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const begin = html.indexOf('const KASF_CHUNKS=(()=>{');
const marker = "if(typeof module!=='undefined'&&module.exports)module.exports=KASF_CHUNKS;";
const end = html.indexOf(marker, begin);
if (begin < 0 || end < 0) throw new Error('KASF_CHUNKS source not found');
const sandbox = { module: { exports: {} }, exports: {}, Uint8Array, Float32Array, Float64Array,
  DataView, ArrayBuffer, Math, Number, Map, Set, BigInt };
vm.runInNewContext(html.slice(begin, end + marker.length), sandbox, { timeout: 5000 });
const K = sandbox.module.exports;
function assert(ok, message) { if (!ok) throw new Error(message); }
function makeBody(channels, frames, sampleSeed = 0) {
  const bytesPerChannel = 14, out = new Uint8Array(frames * channels * bytesPerChannel);
  const view = new DataView(out.buffer); let pos = 0;
  for (let frame = 0; frame < frames; frame++) for (let ch = 0; ch < channels; ch++) {
    view.setBigUint64(pos, 1n, true);
    for (let i = 0; i < 6; i++) out[pos + 8 + i] = (sampleSeed + frame * 13 + ch * 29 + i) & 255;
    pos += bytesPerChannel;
  }
  return out;
}
function makeKASF(channels, frames, seed = 0, frameMs = 10) {
  const body = makeBody(channels, frames, seed), out = new Uint8Array(32 + body.length), v = new DataView(out.buffer);
  v.setUint32(0, 0x4653414b, true); v.setUint32(4, 1, true);
  v.setBigUint64(8, BigInt(channels), true); v.setBigUint64(16, BigInt(frames), true);
  v.setFloat64(24, frameMs / 1000, true); out.set(body, 32); return out.buffer;
}
// Verify all supported frame lengths and rates, including odd 44.1-kHz sample sizes.
let cases = 0;
for (const rate of [44100, 48000, 96000]) for (const frameMs of [5, 10, 20, 30, 40]) {
  const samples = Math.round(rate * 5.137) + 37;
  const plan = K.plan(samples, rate, rate, frameMs, 2.1);
  for (const parent of plan.chunks) {
    const mid = parent.first + Math.floor((parent.last - parent.first) / 2);
    if (mid <= parent.first || mid >= parent.last) continue;
    const a = K.subPart(plan, parent, parent.first, mid);
    const b = K.subPart(plan, parent, mid, parent.last);
    for (const sub of [a, b]) {
      const sampleCount = sub.sampleLast - sub.sampleFirst;
      const expected = sampleCount <= plan.size ? 1 : Math.ceil((sampleCount - plan.size) / plan.hop) + 1;
      assert(expected === sub.analysisLast - sub.analysisFirst, `frame count mismatch rate=${rate} frame=${frameMs}`);
      assert(sub.sampleFirst >= parent.sampleFirst && sub.sampleLast <= parent.sampleLast, 'subrange escapes parent chunk');
    }
    const bodyA = K.keepChunk(makeKASF(1, a.analysisLast - a.analysisFirst, 1, frameMs), a, plan, 1);
    const bodyB = K.keepChunk(makeKASF(1, b.analysisLast - b.analysisFirst, 2, frameMs), b, plan, 1);
    const joined = K.concatBodies([bodyA, bodyB]);
    assert(joined.length === 14 * (parent.last - parent.first), 'joined mono body frame count mismatch');
    cases++;
  }
}
// Subrange PCM slices must equal independently prepared ranges, including resampling.
for (const [sourceRate, targetRate] of [[48000, 44100], [96000, 48000]]) {
  const samples = sourceRate * 3 + 113;
  const source = new Float32Array(samples);
  for (let i = 0; i < samples; i++) source[i] = Math.fround(Math.sin(i * .013) * .3 + Math.cos(i * .071) * .05);
  const audio = { numberOfChannels: 1, getChannelData: () => source };
  for (const coherent of [false, true]) {
    const plan = K.plan(samples, sourceRate, targetRate, 10, 2.4);
    const parent = plan.chunks[0], mid = parent.first + Math.floor((parent.last - parent.first) / 2);
    const sub = K.subPart(plan, parent, mid, parent.last);
    const parentData = new Float32Array(K.makeBuffers(audio, plan, parent, coherent)[0]);
    const subData = new Float32Array(K.makeBuffers(audio, plan, sub, coherent)[0]);
    const offset = sub.sampleFirst - parent.sampleFirst;
    const expected = parentData.subarray(offset, offset + subData.length);
    assert(expected.length === subData.length, 'PCM subrange length mismatch');
    for (let i = 0; i < subData.length; i++) assert(expected[i] === subData[i], `PCM resample slice mismatch coherent=${coherent} i=${i}`);
  }
}
// Multichannel interleave: A carries odd channels, B carries even channels.
{
  const rate = 48000, frameMs = 10, plan = K.plan(rate * 2, rate, rate, frameMs, 3), parent = plan.chunks[0], frames = parent.last - parent.first;
  const sources = [];
  for (const group of [[1, 3], [0, 2, 4]]) {
    const localBody = makeBody(group.length, frames, group[0] * 31);
    sources.push({ body: localBody, channels: group });
  }
  const merged = K.mergeChannelBodies(sources, 5, frames);
  assert(merged.length === 14 * 5 * frames, '5-channel merge byte length mismatch');
  const v = new DataView(merged.buffer, merged.byteOffset, merged.byteLength);
  for (let f = 0; f < frames; f++) for (let ch = 0; ch < 5; ch++) {
    const pos = (f * 5 + ch) * 14;
    assert(v.getBigUint64(pos, true) === 1n, 'multichannel block missing');
    const group = ch % 2 === 1 ? [1, 3] : [0, 2, 4];
    const expectedSeed = ch % 2 === 1 ? 31 : 0;
    assert(merged[pos + 8] === ((expectedSeed + group.indexOf(ch) * 29 + f * 13) & 255), `channel order mismatch ch=${ch}`);
  }
}
// Phase-join test: the first B frame has a deliberately discontinuous phase.
function oneComponentBody(phases, rate = 48000, hop = 240) {
  const out = new Uint8Array(phases.length * 14), v = new DataView(out.buffer);
  const fq = Math.round(440 / 96000 * 0xffffff), aq = Math.round(.5 * 16383);
  let p = 0;
  for (const phase of phases) {
    v.setBigUint64(p, 1n, true);
    out[p + 8] = fq & 255; out[p + 9] = (fq >>> 8) & 255; out[p + 10] = (fq >>> 16) & 255;
    out[p + 11] = aq & 255; out[p + 12] = (aq >>> 8) & 0x3f;
    const q = Math.round(((phase % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI)) * 1024 / (2 * Math.PI)) % 1024;
    out[p + 12] |= (q & 3) << 6; out[p + 13] = q >>> 2; p += 14;
  }
  return out;
}
{
  const rate = 48000, hop = 240, freq = 440, step = 2 * Math.PI * hop / rate, start = .3;
  const left = oneComponentBody([start, start + step * freq, start + 2 * step * freq]);
  const right = oneComponentBody([0, step * freq]);
  const tail = K.connectPhases(left, null, 1, hop, rate).tail;
  const linked = K.connectPhases(right, tail, 1, hop, rate);
  assert(linked.stats.linked === 1, 'mono seam did not find matching sinusoidal track');
  assert(linked.stats.adjusted >= 1, 'mono seam did not correct the first B frame');
}
// Broken body / malformed channel map must be rejected.
{
  let rejected = false;
  try { K.mergeChannelBodies([{ body: makeBody(1, 2), channels: [0] }], 2, 2); } catch (_) { rejected = true; }
  assert(rejected, 'incomplete mapping accepted');
}
console.log(`PASS: ${cases} mono split cases across 3 rates × 5 frame lengths; 5-channel ordering; internal mono phase seam; validation`);
