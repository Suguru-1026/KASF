const fs=require('fs'),vm=require('vm'),path=require('path'),{performance}=require('perf_hooks');
function scripts(file){return [...fs.readFileSync(file,'utf8').matchAll(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);}
function pick(file,needle){const s=scripts(file).find(x=>x.includes(needle));if(!s)throw Error('missing '+needle);return s;}
function load(file){const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,WeakMap,Promise,postMessage:()=>{},setTimeout,clearTimeout,Blob,TextEncoder,TextDecoder,document:{getElementById:()=>({value:'',textContent:'',innerHTML:'',checked:false})}};c.self=c;c.globalThis=c;const x=vm.createContext(c);for(const src of [...new Set([pick(file,'root.KASF_TVS = api'),pick(file,'root.KASF05_Reader={parameters,componentValue,render')])])vm.runInContext(src,x);return x.KASF05_Reader;}
const old=load(path.join(__dirname,'../comparison/KASF-2.0-Evolution-Rev0.9.16-WASM-GVP-HAAR-Optimized.html'));
const neu=load(path.join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'));
let seed=0x73a911;function rnd(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
const rate=48000,fd=.042666666666666665,o=old.parameters(rate,fd),n=neu.parameters(rate,fd),frames=[];
for(let m=0;m<9;m++){const chs=[];for(let ch=0;ch<2;ch++){const list=[];for(let k=0;k<96;k++)list.push({frequency:35+rnd()*21000,amplitude:.002+rnd()*.2,phase:rnd()*Math.PI*2});chs.push(list);}frames.push(chs);}
const start=2048,end=6144,step=1,ws=neu.createRenderWorkspace();
function run(fn,reps){let sink=0;const t=performance.now();for(let i=0;i<reps;i++){for(let ch=0;ch<2;ch++){const y=fn(ch);sink+=y[(i*31)%y.length];}}return {ms:performance.now()-t,sink};}
// Warm each path before collecting medians.
for(let i=0;i<3;i++){old.render(frames,0,o,start,end,step);neu.render(frames,0,n,start,end,step,ws);}
const oldTimes=[],newTimes=[];for(let r=0;r<9;r++){const a=run(ch=>old.render(frames,ch,o,start,end,step),4);const b=run(ch=>neu.render(frames,ch,n,start,end,step,ws),4);oldTimes.push(a.ms);newTimes.push(b.ms);if(!Object.is(a.sink,b.sink))throw Error('benchmark sink mismatch '+a.sink+' '+b.sink);}
oldTimes.sort((a,b)=>a-b);newTimes.sort((a,b)=>a-b);const ratio=oldTimes[4]/newTimes[4];
console.log(JSON.stringify({fixture:'9 frames x 2 channels x 96 components, 4096 samples/channel, 4 repeats x 9 runs',oldMedianMs:+oldTimes[4].toFixed(3),workspaceMedianMs:+newTimes[4].toFixed(3),speedup:+ratio.toFixed(3),oldRuns:oldTimes.map(x=>+x.toFixed(2)),workspaceRuns:newTimes.map(x=>+x.toFixed(2))},null,2));
