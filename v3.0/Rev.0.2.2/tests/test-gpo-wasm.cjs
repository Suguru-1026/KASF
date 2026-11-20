const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{performance}=require('node:perf_hooks');
const currentName='KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html';
const previousName='KASF-2.0-Evolution-Rev0.9.14-WASM-QRP-DPSS-Optimized.html';
const html=fs.readFileSync(path.join(__dirname,'../'+currentName),'utf8');
const prev=fs.readFileSync(path.join(__dirname,'../comparison/'+previousName),'utf8');
function grab(src,id){const m=src.match(new RegExp(`<script id="${id}"[^>]*>([\\s\\S]*?)<\\/script>`,'i'));if(!m)throw Error('missing '+id);return m[1];}
function bootCode(src){const b64=src.match(/<script id="kasf-wasm-binary" type="text\/plain">([\s\S]*?)<\/script>/)?.[1]?.trim();if(!b64)throw Error('WASM binary missing');const a=src.indexOf('const wasmBoot=useWasm?`')+'const wasmBoot=useWasm?`'.length,b=src.indexOf('`:`self.__KASF_WASM_SOLVE=null',a);if(a<0||b<a)throw Error('bootstrap template missing');return new Function('b64',`return \`${src.slice(a,b)}\`;`)(b64);}
const workerNew=grab(html,'embedded-worker-a'),workerOld=grab(prev,'embedded-worker-a'),boot=bootCode(html);
function context(worker,withWasm){
 const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,performance,setTimeout,clearTimeout,postMessage:()=>{},Blob,TextEncoder,TextDecoder,WebAssembly,atob,URL,Date,RegExp,Error,BigInt,DataView,ArrayBuffer,Intl,JSON,parseInt,parseFloat,isFinite,isNaN};
 c.self=c;c.globalThis=c;c.document={getElementById:()=>({value:'',textContent:'',innerHTML:'',checked:false,style:{},addEventListener(){}})};c.addEventListener=()=>{};c.removeEventListener=()=>{};c.close=()=>{};
 const ctx=vm.createContext(c);if(withWasm)vm.runInContext(boot,ctx,{timeout:15000});vm.runInContext(worker,ctx,{timeout:45000});return c;
}
const wasm=context(workerNew,true),js=context(workerOld,false),newJs=context(workerNew,false);
const bits=x=>{const b=Buffer.allocUnsafe(8);b.writeDoubleLE(x);return b.toString('hex');};
function same(a,b,label){if(!Object.is(a,b))throw Error(`${label}: ${a} != ${b} (${bits(a)} != ${bits(b)})`);}
let seed=0x15a0c5;function rand(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
for(const n of [1,2,7,128,240,480,4096,12000])for(let k=0;k<20;k++){
 const residual=Float64Array.from({length:n},()=>rand()*.4-.2),old=Float64Array.from({length:n},()=>rand()*.1-.05),next=Float64Array.from({length:n},()=>rand()*.1-.05);
 const work=wasm.__KASF_WASM_QRP_ACQUIRE(n);work.original.set(residual);work.recon.set(old);work.delta.set(next);
 const expected=(()=>{let s=0;for(let i=0;i<n;i++){const d=next[i]-old[i],r=residual[i]-d;s+=r*r;}return s;})();
 const actual=wasm.__KASF_WASM_GPO_SCORE(0,n);same(expected,actual,`GPO kernel N=${n} case=${k}`);
}
console.log('PASS GPO WASM kernel: 160 deterministic cases bit-identical to JS scalar accumulation');
let gpoWasmCalls=0;const rawGpoScore=wasm.__KASF_WASM_GPO_SCORE;wasm.__KASF_WASM_GPO_SCORE=(...args)=>{gpoWasmCalls++;return rawGpoScore(...args);};

function fixture(frameDuration=.08,windows=4){
 const rate=48000,N=Math.round(rate*frameDuration),H=Math.round(N/2),F=120,length=(F-1)*H+N,frequency=440.1,baseFrequency=440.24,amplitude=.12;
 const source=new Float64Array(length);for(let i=0;i<length;i++)source[i]=amplitude*Math.sin(2*Math.PI*frequency*i/rate);
 const frames=Array.from({length:F},(_,m)=>[[{frequency:baseFrequency,amplitude,phase:2*Math.PI*baseFrequency*m*H/rate,source:'test'}]]);
 return {frames,channels:[source],rate,frameDuration,windows,perFrame:1};
}
async function run(c,frameDuration=.08,windows=4){const f=fixture(frameDuration,windows);const metrics=await c.KASF097_GJRF.run(f);return {frames:f.frames,metrics};}
(async()=>{
 gpoWasmCalls=0;const [a,b,c]=await Promise.all([run(wasm),run(js),run(newJs)]);
 if(gpoWasmCalls<=0)throw Error('Large-window GPO failed to route through WASM');
 const ma=a.metrics,mb=b.metrics;
 for(const k of Object.keys(mb)){const x=ma[k],y=mb[k];if(typeof y==='number'||typeof y==='string'||typeof y==='boolean')same(x,y,`GPO metric ${k}`);}
 if(a.frames.length!==b.frames.length||a.frames.length!==c.frames.length)throw Error('GPO frame count mismatch');
 let changed=0;
 for(let m=0;m<a.frames.length;m++)for(let ch=0;ch<a.frames[m].length;ch++){
  const x=a.frames[m][ch],y=b.frames[m][ch],z=c.frames[m][ch];if(x.length!==y.length||x.length!==z.length)throw Error(`component count frame=${m}`);
  for(let i=0;i<x.length;i++)for(const k of Object.keys(y[i])){same(x[i][k],y[i][k],`frame ${m}/${ch}/${i}/${k}`);same(x[i][k],z[i][k],`fallback frame ${m}/${ch}/${i}/${k}`);}
  if(x.length&&Math.abs(x[0].frequency-440.24)>1e-8)changed++;
 }
 if(mb.evaluations<=0)throw Error('GPO fixture did not evaluate candidates');
 console.log(`PASS integrated GPO: ${mb.windowsTested} windows / ${mb.componentsTested} components / ${mb.evaluations} candidate scores / ${mb.componentsAdjusted} adjusted; frames and metrics bit-identical; WASM calls=${gpoWasmCalls}; modified frames=${changed}`);
 const beforeSmall=gpoWasmCalls;for(const frameDuration of [.01,.04]){const [smallW,smallJ]=await Promise.all([run(wasm,frameDuration,4),run(js,frameDuration,4)]);if(gpoWasmCalls!==beforeSmall)throw Error(`GPO ${frameDuration*1000}ms should stay on JS fallback`);for(const k of Object.keys(smallJ.metrics)){const x=smallW.metrics[k],y=smallJ.metrics[k];if(typeof y==='number'||typeof y==='string'||typeof y==='boolean')same(x,y,`small fallback metric ${frameDuration}/${k}`);}for(let m=0;m<smallW.frames.length;m++)for(let ch=0;ch<smallW.frames[m].length;ch++)for(let i=0;i<smallW.frames[m][ch].length;i++)for(const k of Object.keys(smallJ.frames[m][ch][i]))same(smallW.frames[m][ch][i][k],smallJ.frames[m][ch][i][k],`small fallback frame ${frameDuration}/${m}/${i}/${k}`);}console.log('PASS GPO routing threshold: 10/40 ms windows use JS; 80 ms windows use WASM; exact output matches');
 // End-to-end GPO module timing, including the preparation and WASM boundary.
 function median(a){return a.sort((x,y)=>x-y)[a.length>>1];}
 async function timed(c){const t=performance.now();await run(c);return performance.now()-t;}
 await timed(wasm);await timed(js);await timed(newJs);const tw=[],tj=[],tn=[];for(let r=0;r<5;r++){tw.push(await timed(wasm));tj.push(await timed(js));tn.push(await timed(newJs));}
 const wm=median(tw),jm=median(tj),nm=median(tn);console.log(`BENCH GPO run median(5): WASM=${wm.toFixed(2)}ms JS-new=${nm.toFixed(2)}ms JS-old=${jm.toFixed(2)}ms; WASM vs old=${(jm/wm).toFixed(3)}x, cache-only=${(jm/nm).toFixed(3)}x, WASM vs cache-JS=${(nm/wm).toFixed(3)}x`);
})().catch(e=>{console.error(e);process.exitCode=1;});
