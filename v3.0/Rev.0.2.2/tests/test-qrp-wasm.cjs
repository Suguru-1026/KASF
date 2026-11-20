const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{performance}=require('node:perf_hooks');
const html=fs.readFileSync(path.join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'),'utf8');
const b64=html.match(/<script id="kasf-wasm-binary" type="text\/plain">([\s\S]*?)<\/script>/)?.[1]?.trim();
if(!b64)throw Error('WASM binary missing');
const bootStart=html.indexOf('const wasmBoot=useWasm?`')+'const wasmBoot=useWasm?`'.length;
const bootEnd=html.indexOf('`:`self.__KASF_WASM_SOLVE=null',bootStart);if(bootStart<0||bootEnd<bootStart)throw Error('WASM bootstrap missing');
const boot=new Function('b64',`return \`${html.slice(bootStart,bootEnd)}\`;`)(b64);
const worker=html.match(/<script id="embedded-worker-a"[^>]*>([\s\S]*?)<\/script>/)?.[1];if(!worker)throw Error('Worker A missing');
function context(useWasm){const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,performance,setTimeout,clearTimeout,postMessage:()=>{},Blob,TextEncoder,TextDecoder,WebAssembly,atob,URL,Date,RegExp,Error,BigInt,DataView,ArrayBuffer,Intl,JSON,parseInt,parseFloat,isFinite,isNaN};c.self=c;c.globalThis=c;const ctx=vm.createContext(c);if(useWasm)vm.runInContext(boot,ctx,{timeout:10000});vm.runInContext(worker,ctx,{timeout:30000});return c;}
const fast=context(true),plain=context(false);
const bits=x=>{const b=Buffer.allocUnsafe(8);b.writeDoubleLE(x);return b.toString('hex');};
function same(a,b,label){if(a!==b)throw Error(`${label}: ${a} != ${b} (${bits(a)} != ${bits(b)})`);}
let accepts=0,rejects=0,seed=0x91a2b3c4;function rand(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
for(const n of [128,240,256,480,2048,4096,8192,12000])for(const kind of ['attack','tail'])for(let trial=0;trial<12;trial++){
 const original=Float64Array.from({length:n},()=> (rand()*2-1)*.3),recon=Float64Array.from(original,x=>x+(rand()*2-1)*.03),delta=Float64Array.from({length:n},(_,i)=>trial%3===0?(original[i]-recon[i])*.05:(rand()*2-1)*(trial%4===0?.08:.002));
 const work=n>=240?fast.__KASF_WASM_QRP_ACQUIRE(n):null;
 if(work){work.original.set(original);work.recon.set(recon);}
 const a=plain.KASF06_Detail.exactGate({original,recon,delta,kind});
 const b=fast.KASF06_Detail.exactGate({original,recon,delta,kind,wasmWork:work});
 if(a.accept!==b.accept)throw Error(`accept mismatch ${n}/${kind}/${trial}`);
 same(a.gain,b.gain,`gain ${n}/${kind}/${trial}`);
 if(a.fraction!==undefined)same(a.fraction,b.fraction,`fraction ${n}/${kind}/${trial}`);
 if(a.accept)accepts++;else rejects++;
}
console.log(`PASS QRP exactGate: ${accepts} accepted / ${rejects} rejected, decisions and accumulated values bit-identical`);

// Verify the cached Hann basis preserves the original per-sample proposal.
function oldPropose(residual,frequency,o,globalPeak,reader){let aa=0,bb=0,ab=0,ra=0,rb=0;for(let n=0;n<o.N;n++){const w=.5-.5*Math.cos(2*Math.PI*n/o.N),theta=2*Math.PI*frequency*n/o.rate,u=w*Math.sin(theta),v=w*Math.cos(theta),e=residual[n];aa+=u*u;bb+=v*v;ab+=u*v;ra+=e*u;rb+=e*v;}const ridge=Math.max(1e-9,(aa+bb)*.00001),det=(aa+ridge)*(bb+ridge)-ab*ab;if(det<=1e-18)return null;const sinPart=(ra*(bb+ridge)-rb*ab)/det,cosPart=(rb*(aa+ridge)-ra*ab)/det,amp=Math.hypot(sinPart,cosPart);if(!Number.isFinite(amp)||amp<2/16383||amp>Math.min(.35,Math.max(.045,globalPeak*.75)))return null;return reader.quant({frequency,amplitude:amp,phase:Math.atan2(cosPart,sinPart)});}
for(const n of [240,480,1024,2048,4096]){const o={N:n,rate:48000},r=Float64Array.from({length:n},()=>rand()*.2-.1),freq=330.25,old=oldPropose(r,freq,o,.25,plain.KASF05_Reader),now=fast.KASF06_Detail.propose(r,freq,o,.25);if((old===null)!==(now===null))throw Error(`proposal null mismatch N=${n}`);if(old){for(const k of ['frequency','amplitude','phase'])same(old[k],now[k],`proposal ${n} ${k}`);}console.log(`PASS NOMP propose cached-window N=${n}`);}

// Full QRP recovery integration: compare the real Worker A recovery pass with
// and without WASM on a deterministic transient-rich synthetic source.
async function runRecover(c){
 const rate=48000,frameDuration=.005,N=Math.round(rate*frameDuration),H=Math.round(N/2),length=rate*2.5;
 const source=new Float64Array(length);
 for(let i=0;i<length;i++){const t=i/rate;source[i]=.105*Math.sin(2*Math.PI*3000*t)+.012*Math.sin(2*Math.PI*6200*t);}
 const frames=Array.from({length:Math.ceil(length/H)},()=>[[]]);
 const result=await c.KASF06_Detail.recover({frames,channels:[source],rate,frameDuration,attacks:[{time:1.2,confidence:1,reliable:true}],level:'precision'});
 return {result,frames};
}
(async()=>{
 const [a,b]=await Promise.all([runRecover(fast),runRecover(plain)]);
 const ka=a.result,kb=b.result;
 for(const k of Object.keys(kb)){const x=ka[k],y=kb[k];if(typeof y==='number'||typeof y==='string'||typeof y==='boolean'){if(!Object.is(x,y))throw Error(`QRP recover metric mismatch ${k}: ${x} != ${y}`);}}
 if(a.frames.length!==b.frames.length)throw Error('QRP frame count mismatch');
 for(let m=0;m<a.frames.length;m++)for(let ch=0;ch<a.frames[m].length;ch++){
  const x=a.frames[m][ch],y=b.frames[m][ch];if(x.length!==y.length)throw Error(`QRP component count mismatch frame ${m}`);
  for(let i=0;i<x.length;i++)for(const k of ['frequency','amplitude','phase'])same(x[i][k],y[i][k],`QRP recover ${m}/${i}/${k}`);
 }
 console.log(`PASS integrated QRP recover: ${ka.framesExamined} frames / ${ka.proposals} proposals / ${ka.added} components; WASM and JS output identical`);
})().catch(e=>{console.error(e);process.exitCode=1;});

// Gate benchmark includes the exact adapter transfer cost: fixed original and
// reconstruction per frame, one delta transfer per proposal.
function jsGate(original,recon,delta,kind){let gain=0,sourceEnergy=0,addedEnergy=0,initial=0;const hop=Math.max(1,Math.round(original.length/7));for(let start=0;start<original.length;start+=hop){let srcE=0,baseE=0,afterE=0;for(let i=start;i<Math.min(original.length,start+hop);i++){const e=original[i]-recon[i],d=delta[i];gain+=2*e*d-d*d;srcE+=original[i]*original[i];baseE+=recon[i]*recon[i];afterE+=(recon[i]+d)**2;sourceEnergy+=original[i]*original[i];addedEnergy+=d*d;initial+=e*e;}const src=Math.sqrt(srcE),base=Math.sqrt(baseE),after=Math.sqrt(afterE);if(after>Math.max(src*1.40,base*1.12)+.0001&&after>src+.01)return {accept:false,gain};}const fraction=gain/Math.max(1e-15,initial),minFrac=kind==='attack'?.0015:.00065,energyLimit=kind==='attack'?.40:.20;return {accept:gain>0&&fraction>minFrac&&addedEnergy<sourceEnergy*energyLimit,gain,fraction};}
function median(a){return a.sort((x,y)=>x-y)[a.length>>1];}
function bench(n,candidates=10,reps=100){const original=Float64Array.from({length:n},()=>rand()*.3-.15),recon=Float64Array.from({length:n},()=>rand()*.3-.15),deltas=Array.from({length:candidates},()=>Float64Array.from({length:n},()=>rand()*.001-.0005)),v=fast.__KASF_WASM_QRP_ACQUIRE(n);v.original.set(original);v.recon.set(recon);
 function j(){let z=0;for(const d of deltas){const g=jsGate(original,recon,d,'tail');z+=g.gain+(g.accept?1:0);}return z;}
 function w(){let z=0;for(const d of deltas){v.delta.set(d);const g=fast.__KASF_WASM_QRP_GATE(n,Math.max(1,Math.round(n/7)),.00065,.20);if(!g)throw Error('WASM gate failed');z+=g.gain+(g.accept?1:0);}return z;}
 j();w();const jt=[],wt=[];for(let r=0;r<7;r++){let t=performance.now();for(let i=0;i<reps;i++)j();jt.push(performance.now()-t);t=performance.now();for(let i=0;i<reps;i++)w();wt.push(performance.now()-t);}return {n,candidates,reps,jsMs:+median(jt).toFixed(2),wasmMs:+median(wt).toFixed(2),speedup:+(median(jt)/median(wt)).toFixed(3)};}
const benchResults=[128,240,256,480,512,1024,2048,4096,8192,12000].map(n=>bench(n));console.log('BENCH QRP exactGate median of 7',JSON.stringify(benchResults));
