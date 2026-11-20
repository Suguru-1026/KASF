const fs=require('fs'),vm=require('vm'),path=require('path'),{performance}=require('perf_hooks');
function scripts(file){return [...fs.readFileSync(file,'utf8').matchAll(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);}
function pick(file,needle){const s=scripts(file).find(x=>x.includes(needle));if(!s)throw Error('missing '+needle);return s;}
function load(file){const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,WeakMap,Promise,postMessage:()=>{},setTimeout,clearTimeout,Blob,TextEncoder,TextDecoder,document:{getElementById:()=>({value:'',textContent:'',innerHTML:'',checked:false})}};c.self=c;c.globalThis=c;const x=vm.createContext(c);for(const src of [...new Set([pick(file,'root.KASF_TVS = api'),pick(file,'root.KASF05_Reader={parameters,componentValue,render')])])vm.runInContext(src,x);return x.KASF05_Reader;}
const file=path.join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'),R=load(file);
let seed=0x8711cba1;function rnd(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
const rate=48000,fd=.02,o=R.parameters(rate,fd),frames=[];
for(let m=0;m<9;m++){const channels=[];for(let ch=0;ch<2;ch++){const list=[];for(let k=0;k<128;k++)list.push({frequency:20+rnd()*23000,amplitude:.002+rnd()*.12,phase:rnd()*Math.PI*2});channels.push(list);}frames.push(channels);}
const start=0,end=19000,step=1,ws=[R.createRenderWorkspace(),R.createRenderWorkspace()];
for(let ch=0;ch<2;ch++)R.render(frames,ch,o,start,end,step,ws[ch]);
for(const w of ws){w.captureBaseline=false;w.cacheWaves=false;}
for(let m=2;m<=6;m++)for(let ch=0;ch<2;ch++)for(let k=0;k<8;k++){const c=frames[m][ch][k];frames[m][ch][k]={frequency:c.frequency+(k%2?-.93:1.17),amplitude:c.amplitude*(1.0001+(k%3)*.0001),phase:c.phase+.00013*(k+1)};}
function run(approx){let sink=0;for(let ch=0;ch<2;ch++){ws[ch].approximate=approx;const y=R.render(frames,ch,o,start,end,step,ws[ch]);sink+=y[1234]+y[7654]+y[12345];ws[ch].approximate=false;}return sink;}
for(let i=0;i<5;i++){run(false);run(true);}
const A=[],B=[];for(let i=0;i<11;i++){let t=performance.now();const a=run(false);A.push(performance.now()-t);t=performance.now();const b=run(true);B.push(performance.now()-t);if(!Number.isFinite(a+b))throw Error('bad sink');}
A.sort((a,b)=>a-b);B.sort((a,b)=>a-b);
console.log(JSON.stringify({fixture:'2 channels, 5 affected frames, 128 components/frame/channel, 19,000-sample region, 8 replaced components/frame/channel',exactMedianMs:+A[5].toFixed(3),approxMedianMs:+B[5].toFixed(3),speedup:+(A[5]/B[5]).toFixed(3),exactRuns:A.map(x=>+x.toFixed(3)),approxRuns:B.map(x=>+x.toFixed(3))},null,2));
