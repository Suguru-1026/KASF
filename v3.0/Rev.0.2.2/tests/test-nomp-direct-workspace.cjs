const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{performance}=require('node:perf_hooks');
const currentName='KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html';
const previousName='KASF-2.0-Evolution-Rev0.9.14-WASM-QRP-DPSS-Optimized.html';
const html=fs.readFileSync(path.join(__dirname,'../'+currentName),'utf8');
const prev=fs.readFileSync(path.join(__dirname,'../comparison/'+previousName),'utf8');
function grab(src,id){const m=src.match(new RegExp(`<script id="${id}"[^>]*>([\\s\\S]*?)<\\/script>`,'i'));if(!m)throw Error('missing '+id);return m[1];}
function bootCode(src){const b64=src.match(/<script id="kasf-wasm-binary" type="text\/plain">([\s\S]*?)<\/script>/)?.[1]?.trim();if(!b64)throw Error('WASM binary missing');const a=src.indexOf('const wasmBoot=useWasm?`')+'const wasmBoot=useWasm?`'.length,b=src.indexOf('`:`self.__KASF_WASM_SOLVE=null',a);if(a<0||b<a)throw Error('bootstrap template missing');return new Function('b64',`return \`${src.slice(a,b)}\`;`)(b64);}
const currentWorker=grab(html,'embedded-worker-b'),previousWorker=grab(prev,'embedded-worker-b');
function context(worker,boot){const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,performance,setTimeout,clearTimeout,postMessage:()=>{},Blob,TextEncoder,TextDecoder,WebAssembly,atob,URL,Date,RegExp,Error,BigInt,DataView,ArrayBuffer,Intl,JSON,parseInt,parseFloat,isFinite,isNaN};c.self=c;c.globalThis=c;c.document={getElementById:()=>({value:'',textContent:'',innerHTML:'',checked:false,style:{},addEventListener(){}})};c.addEventListener=()=>{};c.removeEventListener=()=>{};c.close=()=>{};const ctx=vm.createContext(c);if(boot)vm.runInContext(boot,ctx,{timeout:15000});vm.runInContext(worker,ctx,{timeout:60000});return c;}
const old=context(previousWorker,bootCode(prev)),wasm=context(currentWorker,bootCode(html)),fallback=context(currentWorker,null);
const same=(a,b,label)=>{if(!Object.is(a,b))throw Error(`${label}: ${a} != ${b}`);};
function compareFit(a,b,label){if(!a||!b)throw Error(`${label}: null fit`);for(const k of ['sse','energy'])same(a[k],b[k],label+'.'+k);if(a.coefficients.length!==b.coefficients.length)throw Error(label+'.coeff length');for(let i=0;i<a.coefficients.length;i++)same(a.coefficients[i],b.coefficients[i],label+`.coef${i}`);for(let i=0;i<a.components.length;i++){for(const k of ['frequency','amplitude','phase','source'])same(a.components[i][k],b.components[i][k],label+`.component${i}.${k}`);}for(let i=0;i<a.frequencies.length;i++)same(a.frequencies[i],b.frequencies[i],label+`.freq${i}`);}
let preserveCalls=0,copyCalls=0;const rawReady=wasm.__KASF_WASM_SOLVE_READY,rawCopy=wasm.__KASF_WASM_SOLVE;wasm.__KASF_WASM_SOLVE_READY=(...args)=>{if(args[3]===true)preserveCalls++;return rawReady(...args);};wasm.__KASF_WASM_SOLVE=(...args)=>{copyCalls++;return rawCopy(...args);};
let seed=0x15f00d;function rand(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
function makeSignal(n,sr){const x=new Float64Array(n),fs=[173.25,440.125,997.75,1811.5],amps=[.21,.12,.071,.033],ph=[.31,1.4,-.8,2.1];for(let i=0;i<n;i++){let t=i/sr,v=(rand()-.5)*.001;for(let k=0;k<fs.length;k++)v+=amps[k]*Math.sin(2*Math.PI*fs[k]*t+ph[k]);x[i]=v;}return x;}
for(const [n,fs] of [[256,[173.25,440.125]],[512,[173.25,440.125,997.75]],[2048,[173.25,440.125,997.75,1811.5]],[4096,[173.25,440.125,997.75,1811.5]],[8192,[173.25,440.125,997.75,1811.5]]]){
 const samples=makeSignal(n,48000),a=old.KASF097_Research.fitFrequencySet(samples,48000,fs),b=wasm.KASF097_Research.fitFrequencySet(samples,48000,fs),c=fallback.KASF097_Research.fitFrequencySet(samples,48000,fs);
 compareFit(a,b,`old-wasm vs direct-wasm N=${n}`);
 if(!c||!Number.isFinite(c.sse))throw Error(`JS fallback failed N=${n}`);
}
if(preserveCalls!==5||copyCalls!==0)throw Error(`direct workspace path not used as expected: preserve=${preserveCalls}, wrapperCopy=${copyCalls}`);
console.log('PASS NOMP-GVP direct basis workspace: 5 sizes, old WASM vs new direct-to-WASM results bit-identical; wrapper column-copy calls=0');
// Full NOMP-GVP regression on a deterministic signal.
const n=2048,sr=48000,samples=makeSignal(n,sr);
const a=old.KASF097_Research.nompGVP(samples,sr,[173.25,440.125],3),b=wasm.KASF097_Research.nompGVP(samples,sr,[173.25,440.125],3);
if(!a||!b)throw Error('NOMP-GVP full fit returned null');
compareFit(a,b,'full NOMP-GVP');for(const k of ['initialSse','relativeReduction','componentsAdded','refinements','rejectedByBIC','method'])same(a[k],b[k],'NOMP metric '+k);
console.log(`PASS full NOMP-GVP: ${b.components.length} components / ${b.refinements} refinements, exact match`);
function median(xs){return xs.sort((a,b)=>a-b)[xs.length>>1];}
function timed(c,x,fs){const t=performance.now();c.KASF097_Research.fitFrequencySet(x,sr,fs);return performance.now()-t;}
const benchN=4096,benchFs=[173.25,440.125,997.75,1811.5],benchX=makeSignal(benchN,sr);for(let i=0;i<4;i++){timed(old,benchX,benchFs);timed(wasm,benchX,benchFs);timed(fallback,benchX,benchFs);}const oldT=[],newT=[],jsT=[];for(let i=0;i<13;i++){oldT.push(timed(old,benchX,benchFs));newT.push(timed(wasm,benchX,benchFs));jsT.push(timed(fallback,benchX,benchFs));}
const om=median(oldT),nm=median(newT),jm=median(jsT);console.log(`BENCH direct basis fit N=${benchN}, d=8, median(13): old-WASM-copy=${om.toFixed(3)}ms direct-WASM=${nm.toFixed(3)}ms cached-JS=${jm.toFixed(3)}ms; direct-vs-old=${(om/nm).toFixed(3)}x, direct-vs-cached-JS=${(jm/nm).toFixed(3)}x`);
