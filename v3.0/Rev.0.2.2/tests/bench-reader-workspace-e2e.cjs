const fs=require('fs'),vm=require('vm'),path=require('path'),{performance}=require('perf_hooks');
function scripts(file){return [...fs.readFileSync(file,'utf8').matchAll(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);}
function pick(file,needle){const s=scripts(file).find(x=>x.includes(needle));if(!s)throw Error('missing '+needle);return s;}
function load(file){const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,WeakMap,Promise,postMessage:()=>{},setTimeout,clearTimeout,Blob,TextEncoder,TextDecoder,document:{getElementById:()=>({value:'',textContent:'',innerHTML:'',checked:false})}};c.self=c;c.globalThis=c;const x=vm.createContext(c);for(const src of [...new Set([pick(file,'root.KASF_TVS = api'),pick(file,'root.KASF05_Reader={parameters,componentValue,render')])])vm.runInContext(src,x);return x.KASF05_Reader;}
const old=load(path.join(__dirname,'../comparison/KASF-2.0-Evolution-Rev0.9.16-WASM-GVP-HAAR-Optimized.html'));
const neu=load(path.join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'));
let seed=0x73a911;function rnd(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
const rate=48000,fd=.042666666666666665,o=old.parameters(rate,fd),n=neu.parameters(rate,fd),frames=[];
for(let m=0;m<9;m++){const chs=[];for(let ch=0;ch<2;ch++){const list=[];for(let k=0;k<96;k++)list.push({frequency:35+rnd()*21000,amplitude:.002+rnd()*.2,phase:rnd()*Math.PI*2});chs.push(list);}frames.push(chs);}
const start=2048,end=6144,step=1,cycles=9;
const slots=[];for(let ch=0;ch<2;ch++)for(let m=2;m<=6;m++)for(let i=0;i<2;i++)slots.push({ch,m,i:i+5,original:frames[m][ch][i+5]});
function swapCandidate(ch,k){const changed=[];for(const s of slots)if(s.ch===ch){frames[s.m][ch][s.i]={frequency:s.original.frequency+(k+1)*.17,amplitude:s.original.amplitude*(1+.0003*(k+1)),phase:s.original.phase+(k+1)*.001};changed.push(s);}return ()=>{for(const s of changed)frames[s.m][ch][s.i]=s.original;};}
function runOld(){let sink=0;const t=performance.now();for(let k=0;k<cycles;k++)for(let ch=0;ch<2;ch++){const restore=k===0?()=>{}:swapCandidate(ch,k);const y=old.render(frames,ch,o,start,end,step);sink+=y[(k*31)%y.length];restore();}return {ms:performance.now()-t,sink};}
function runNew(){let sink=0;const ws=[neu.createRenderWorkspace(),neu.createRenderWorkspace()];const t=performance.now();for(let k=0;k<cycles;k++)for(let ch=0;ch<2;ch++){const restore=k===0?()=>{}:swapCandidate(ch,k);const y=neu.render(frames,ch,n,start,end,step,ws[ch]);sink+=y[(k*31)%y.length];restore();if(k===0)ws[ch].cacheWaves=false;}return {ms:performance.now()-t,sink,bytes:ws.reduce((s,w)=>s+w.waveCacheBytes,0)};}
// Warm up the JS engine with disposable contexts.
for(let i=0;i<2;i++){runOld();runNew();}
const A=[],B=[];let mem=0;for(let i=0;i<7;i++){const a=runOld(),b=runNew();if(!Object.is(a.sink,b.sink))throw Error('output sink mismatch');A.push(a.ms);B.push(b.ms);mem=Math.max(mem,b.bytes);}
A.sort((a,b)=>a-b);B.sort((a,b)=>a-b);
console.log(JSON.stringify({fixture:`${cycles} full Reader passes (baseline + multi-start-like repeated candidate measurements), 9 frames x 2 channels x 96 components x 4096 samples`,oldMedianMs:+A[3].toFixed(2),workspaceMedianMs:+B[3].toFixed(2),speedup:+(A[3]/B[3]).toFixed(3),maxCachedWaveBytes:mem,perChannelCap:4*1024*1024,oldRuns:A.map(x=>+x.toFixed(2)),workspaceRuns:B.map(x=>+x.toFixed(2))},null,2));
