'use strict';
const fs = require('fs');
const vm = require('vm');
const [htmlPath, kasfPath, outPath, rateText, countText] = process.argv.slice(2);
if (!htmlPath || !kasfPath || !outPath || !rateText || !countText) {
  console.error('Usage: node compare_reader_node.cjs REV0920.html input.kasf output.f64 SAMPLE_RATE SAMPLE_COUNT');
  process.exit(2);
}
const html = fs.readFileSync(htmlPath, 'utf8');
const marker = '/* KASF Rev0.5 — exact KASF v1 local (pre global peak normalization) synthesis. */';
const start = html.indexOf(marker);
if (start < 0) throw new Error('Could not find KASF05_Reader source marker');
const close = "})(typeof self!=='undefined'?self:globalThis);";
const endAt = html.indexOf(close, start);
if (endAt < 0) throw new Error('Could not find KASF05_Reader source closure');
const source = html.slice(start, endAt + close.length);
const TAU = 2 * Math.PI;
globalThis.KASF_TVS = {
  quantizedComponent(c) {
    const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
    const qf = clamp(Math.round(c.frequency / 96000 * 0xFFFFFF), 0, 0xFFFFFF);
    const qa = clamp(Math.round(c.amplitude * 0x3FFF), 0, 0x3FFF);
    let phase = c.phase % TAU; if (phase < 0) phase += TAU;
    const qp = clamp(Math.round(phase / TAU * 1024), 0, 1023);
    return {frequency: qf / 0xFFFFFF * 96000, amplitude: qa / 0x3FFF, phase: qp * TAU / 1024};
  }
};
vm.runInThisContext(source, {filename: 'KASF-Rev0.9.20-KASF05_Reader-extract.js'});
const r = fs.readFileSync(kasfPath);
if (r.subarray(0,4).toString('ascii') !== 'KASF') throw new Error('Wrong magic; expected KASF');
if (r.readUInt32LE(4) !== 1) throw new Error('Unsupported KASF version');
const channels = Number(r.readBigUInt64LE(8));
const frameCount = Number(r.readBigUInt64LE(16));
const frameDuration = r.readDoubleLE(24);
const frames = [];
let p = 32;
for (let m=0; m<frameCount; m++) {
  const row=[];
  for (let ch=0; ch<channels; ch++) {
    if (p+8>r.length) throw new Error('Truncated component count');
    const count = Number(r.readBigUInt64LE(p)); p += 8;
    if (!Number.isSafeInteger(count) || p+count*6>r.length) throw new Error('Invalid component payload length');
    const list=[];
    for (let i=0; i<count; i++) {
      const b0=r[p], b1=r[p+1], b2=r[p+2], b3=r[p+3], b4=r[p+4], b5=r[p+5]; p+=6;
      const qf=b0|(b1<<8)|(b2<<16);
      const qa=b3|((b4&0x3F)<<8);
      const qp=(b4>>6)|(b5<<2);
      list.push({frequency:qf/0xFFFFFF*96000, amplitude:qa/0x3FFF, phase:qp*TAU/1024});
    }
    row.push(list);
  }
  frames.push(row);
}
if (p!==r.length) throw new Error('Trailing bytes in KASF file');
const rate=Number(rateText), sampleCount=Number(countText);
const params=globalThis.KASF05_Reader.parameters(rate,frameDuration);
const out=Buffer.alloc(sampleCount*channels*8);
for (let ch=0; ch<channels; ch++) {
  const pcm=globalThis.KASF05_Reader.render(frames,ch,params,0,sampleCount,1,null);
  for (let i=0; i<sampleCount; i++) out.writeDoubleLE(pcm[i],(i*channels+ch)*8);
}
fs.writeFileSync(outPath,out);
console.log(JSON.stringify({channels,frameCount,frameDuration,rate,sampleCount,outputBytes:out.length}));
