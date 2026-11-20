const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const begin = html.indexOf('const KASF_CHUNKS=(()=>{');
if (begin < 0) throw new Error('KASF_CHUNKS start not found');
const endMarker = 'if(typeof module!==\'undefined\'&&module.exports)module.exports=KASF_CHUNKS;';
const end = html.indexOf(endMarker, begin);
if (end < 0) throw new Error('KASF_CHUNKS end not found');
const code = html.slice(begin, end + endMarker.length);
const sandbox = { module: { exports: {} }, exports: {}, console, Uint8Array, Float32Array, Float64Array, DataView, ArrayBuffer, Math, Number, Map, Set, BigInt };
vm.runInNewContext(code, sandbox, { timeout: 5000 });
const K = sandbox.module.exports;
function makeKASf(channels, frames, seed) {
  let total = 32;
  const rows = [];
  for (let f = 0; f < frames; f++) {
    const row=[];
    for (let c=0;c<channels;c++) {
      const b = new Uint8Array(14); // count + one component
      const v = new DataView(b.buffer);
      v.setBigUint64(0, 1n, true);
      for(let i=0;i<6;i++) b[8+i]=(seed+f*17+c*31+i)&255;
      row.push(b); total += b.length;
    }
    rows.push(row);
  }
  const out = new Uint8Array(total), v = new DataView(out.buffer);
  v.setUint32(0,0x4653414b,true);v.setUint32(4,1,true);
  v.setBigUint64(8,BigInt(channels),true);v.setBigUint64(16,BigInt(frames),true);v.setFloat64(24,.01,true);
  let pos=32;for(const row of rows)for(const b of row){out.set(b,pos);pos+=b.length;}
  return out.buffer;
}
function assert(ok,msg){if(!ok)throw new Error(msg);}
const plan=K.plan(48000*8+137,48000,48000,10,30);
const part=plan.chunks[0];
const mid=part.first+Math.floor((part.last-part.first)/2);
const a=K.subPart(plan,part,part.first,mid);
const b=K.subPart(plan,part,mid,part.last);
for (const sub of [a,b]) {
  const expected=sub.analysisLast-sub.analysisFirst;
  const samples=sub.sampleLast-sub.sampleFirst;
  const frameSize=plan.size, frames=samples<=frameSize?1:Math.ceil((samples-frameSize)/plan.hop)+1;
  assert(frames===expected,`subrange frame count mismatch: ${frames} != ${expected}`);
}
const bodyA=K.keepChunk(makeKASf(1,a.analysisLast-a.analysisFirst,10),a,plan,1);
const bodyB=K.keepChunk(makeKASf(1,b.analysisLast-b.analysisFirst,90),b,plan,1);
const mono=K.concatBodies([bodyA,bodyB]);
assert(mono.length===14*(part.last-part.first), 'mono concatenation length incorrect');
// Stereo channel merge must restore channel 0 from B and channel 1 from A.
const left=K.keepChunk(makeKASf(1,part.analysisLast-part.analysisFirst,20),part,plan,1);
const right=K.keepChunk(makeKASf(1,part.analysisLast-part.analysisFirst,120),part,plan,1);
const stereo=K.mergeChannelBodies([{body:right,channels:[1]},{body:left,channels:[0]}],2,part.last-part.first);
assert(stereo.length===28*(part.last-part.first), 'stereo merge length incorrect');
const v=new DataView(stereo.buffer,stereo.byteOffset,stereo.byteLength);
assert(v.getBigUint64(0,true)===1n, 'first merged block missing');
assert(stereo[8]===20, 'channel 0 (left) order was not restored');
assert(v.getBigUint64(14,true)===1n, 'second merged block missing');
assert(stereo[22]===120, 'channel 1 (right) order was not restored');
// Verify malformed and incomplete mappings are rejected.
let rejected=false;try{K.mergeChannelBodies([{body:left,channels:[0]}],2,part.last-part.first);}catch(_){rejected=true;}
assert(rejected, 'incomplete channel mapping accepted');
console.log(`PASS: mono subrange frame counts, guarded KASF trimming, mono concatenation, stereo channel order and merge validation (${part.last-part.first} frames)`);
