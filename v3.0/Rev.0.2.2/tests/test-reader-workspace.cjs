const fs=require('fs'),vm=require('vm'),path=require('path');
function scripts(file){return [...fs.readFileSync(file,'utf8').matchAll(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);}
function pick(file,needle){const s=scripts(file).find(x=>x.includes(needle));if(!s)throw Error('missing '+needle+' in '+file);return s;}
function context(){const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,WeakMap,performance:{now:()=>0},postMessage:()=>{},setTimeout,clearTimeout,Blob,TextEncoder,TextDecoder,document:{getElementById:()=>({value:'',textContent:'',innerHTML:'',checked:false})}};c.self=c;c.globalThis=c;return vm.createContext(c);}
function load(file){const c=context();for(const src of [...new Set([pick(file,'root.KASF_TVS = api'),pick(file,'root.KASF05_Reader={parameters,componentValue,render')])])vm.runInContext(src,c);return c;}
function bits(a,b){if(a.length!==b.length)return false;const x=new Float64Array(a),y=new Float64Array(b),u=new BigUint64Array(x.buffer),v=new BigUint64Array(y.buffer);for(let i=0;i<u.length;i++)if(u[i]!==v[i])return false;return true;}
const base=path.join(__dirname,'../comparison/KASF-2.0-Evolution-Rev0.9.16-WASM-GVP-HAAR-Optimized.html');
const next=path.join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html');
const O=load(base).KASF05_Reader,N=load(next).KASF05_Reader;
let seed=0x91a7e2d3;function rnd(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
const frames=[];for(let m=0;m<22;m++){const channels=[];for(let ch=0;ch<2;ch++){const list=[];for(let k=0;k<160;k++)list.push({frequency:25+rnd()*22000,amplitude:rnd()*.35,phase:rnd()*Math.PI*2});channels.push(list);}frames.push(channels);}
const ws=N.createRenderWorkspace();
const cases=[{rate:48000,fd:.02,start:0,end:11000,step:1},{rate:48000,fd:.02,start:123,end:9000,step:2},{rate:44100,fd:.03,start:1500,end:19000,step:3},{rate:96000,fd:.01,start:200,end:12000,step:1}];
// First case primes both quantization and waveform caches; subsequent exact
// comparisons exercise range/step/rate-dependent workspace reconfiguration.
for(let ix=0;ix<cases.length;ix++){const q=cases[ix],o=O.parameters(q.rate,q.fd),n=N.parameters(q.rate,q.fd);for(let ch=0;ch<2;ch++){const a=O.render(frames,ch,o,q.start,q.end,q.step),b=N.render(frames,ch,n,q.start,q.end,q.step,ws);if(!bits(a,b))throw Error(`initial render mismatch case=${ix} ch=${ch}`);}console.log('render bit-identical',ix);}
// Same-range in-place mutation must invalidate both caches even after the
// wave cache is frozen, as it is for normal candidate evaluations.
ws.cacheWaves=false;const q0=cases[3],o0=O.parameters(q0.rate,q0.fd),n0=N.parameters(q0.rate,q0.fd);
for(let ch=0;ch<2;ch++){const a=O.render(frames,ch,o0,q0.start,q0.end,q0.step),b=N.render(frames,ch,n0,q0.start,q0.end,q0.step,ws);if(!bits(a,b))throw Error('pre-mutation render mismatch '+ch);}
frames[7][0][31].frequency+=12.345;frames[7][0][31].amplitude*=.73;frames[7][0][31].phase-=.123;
// Object replacement and list-length changes must also be reflected.
frames[8][1][22]={frequency:1801.25,amplitude:.12345,phase:1.2345};
frames[9][0].push({frequency:9900.1,amplitude:.02,phase:2.2});frames[9][0].splice(4,1);
for(let ch=0;ch<2;ch++){const a=O.render(frames,ch,o0,q0.start,q0.end,q0.step),b=N.render(frames,ch,n0,q0.start,q0.end,q0.step,ws);if(!bits(a,b))throw Error('mutation invalidation mismatch '+ch);}
for(const w of [ws])if(w.waveCacheBytes>w.waveCacheLimit)throw Error('wave cache memory cap exceeded');
console.log('same-range in-place mutation/replacement/list-size invalidation exact; wave cache cap respected');
// Same-size repeated calls reuse the output backing buffer.
const q=cases[0],o=N.parameters(q.rate,q.fd);const a=N.render(frames,0,o,q.start,q.end,q.step,ws),b=N.render(frames,1,o,q.start,q.end,q.step,ws);if(a!==b)throw Error('output buffer was not reused');
console.log('output workspace reused');
console.log('READER WORKSPACE ALL PASS');
