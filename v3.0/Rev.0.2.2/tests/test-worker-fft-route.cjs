const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{performance}=require('node:perf_hooks');
const html=fs.readFileSync(path.join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'),'utf8');
const b64=html.match(/<script id="kasf-wasm-binary" type="text\/plain">([\s\S]*?)<\/script>/)[1].trim();
function grab(id){const re=new RegExp(`<script id="${id}"[^>]*>([\\s\\S]*?)<\\/script>`,'i');const m=html.match(re);if(!m)throw Error('missing '+id);return m[1];}
const bootStart=html.indexOf('const wasmBoot=useWasm?`')+'const wasmBoot=useWasm?`'.length;
const bootEnd=html.indexOf('`:`self.__KASF_WASM_SOLVE=null',bootStart);
const bootTemplate=html.slice(bootStart,bootEnd);
const boot=new Function('b64',`return \`${bootTemplate}\`;`)(b64);
const workerA=grab('embedded-worker-a');
const workerB=grab('embedded-worker-b');
function context(withWasm){
 const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,performance,setTimeout,clearTimeout,postMessage:()=>{},Blob,TextEncoder,TextDecoder,WebAssembly,atob,URL,Date,RegExp,Error,BigInt,DataView,ArrayBuffer,Intl,JSON,parseInt,parseFloat,isFinite,isNaN};
 c.self=c;c.globalThis=c;c.document={getElementById:()=>({value:'',textContent:'',innerHTML:'',checked:false,style:{},addEventListener(){}})};c.addEventListener=()=>{};c.removeEventListener=()=>{};c.close=()=>{};
 const ctx=vm.createContext(c);if(withWasm)vm.runInContext(boot,ctx,{timeout:10000});vm.runInContext(workerA,ctx,{timeout:30000});return c;
}
function rng(seed){return()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296*2-1;};}
function equal(a,b){for(let i=0;i<a.length;i++)if(!Object.is(a[i],b[i]))throw Error('FFT output mismatch at '+i);}
const fast=context(true),plain=context(false);
for(const n of [2048,4096,8192,65536]){
 const r=rng(n),x=Float64Array.from({length:n},r),y=Float64Array.from({length:n},r),a=x.slice(),ai=y.slice(),b=x.slice(),bi=y.slice();
 fast.KASF05_Loss.fft(a,ai);plain.KASF05_Loss.fft(b,bi);equal(a,b);equal(ai,bi);
 const should=n===2048||n===4096||n>=65536;if(!!fast.__KASF_WASM_FFT_ERROR)throw Error(fast.__KASF_WASM_FFT_ERROR);
 console.log(`PASS Worker A FFT N=${n} route=${should?'WASM':'JS'} outputs=bit-identical`);
}

function contextB(withWasm){
 const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,performance,setTimeout,clearTimeout,postMessage:()=>{},Blob,TextEncoder,TextDecoder,WebAssembly,atob,URL,Date,RegExp,Error,BigInt,DataView,ArrayBuffer,Intl,JSON,parseInt,parseFloat,isFinite,isNaN};
 c.self=c;c.globalThis=c;const ctx=vm.createContext(c);if(withWasm)vm.runInContext(boot,ctx,{timeout:10000});vm.runInContext(workerB+'\n;globalThis.__testFFT=fft;globalThis.__testDPSS=dpssTapers;',ctx,{timeout:30000});return c;
}
const fastB=contextB(true),plainB=contextB(false);
for(const n of [2048,4096,8192,16384]){
 const r=rng(n+77),x=Float64Array.from({length:n},r),y=Float64Array.from({length:n},r),a=x.slice(),ai=y.slice(),b=x.slice(),bi=y.slice();
 fastB.__testFFT(a,ai);plainB.__testFFT(b,bi);equal(a,b);equal(ai,bi);
 const should=n===2048||n===4096;console.log(`PASS Worker B FFT N=${n} route=${should?'WASM':'JS'} outputs=bit-identical`);
}

const fastD=contextB(true),plainD=contextB(false);
for(const [N,NW,K] of [[128,2.5,3],[256,2.5,3],[256,3.5,4],[512,2.5,3]]){
 const a=fastD.__testDPSS(N,NW,K),b=plainD.__testDPSS(N,NW,K);
 if(a.length!==b.length)throw Error('Worker B DPSS count mismatch');
 for(let q=0;q<a.length;q++)for(let i=0;i<a[q].length;i++)if(!Object.is(a[q][i],b[q][i]))throw Error(`Worker B DPSS mismatch N=${N} q=${q} i=${i}`);
 console.log(`PASS Worker B DPSS N=${N} K=${K} WASM vs JS bit-identical`);
}

// Shared Worker B memory must remain valid across FFT -> DPSS -> FFT -> DPSS growth/reuse.
const interopA=fastB.__testDPSS(256,2.5,3);
const interopRef=plainB.__testDPSS(256,2.5,3);
for(let q=0;q<interopA.length;q++)for(let i=0;i<interopA[q].length;i++)if(!Object.is(interopA[q][i],interopRef[q][i]))throw Error('FFT-to-DPSS workspace interop mismatch');
const ir=Float64Array.from({length:4096},(_,i)=>Math.sin(i*.019)),ii=new Float64Array(4096),jr=ir.slice(),ji=ii.slice();
fastB.__testFFT(ir,ii);plainB.__testFFT(jr,ji);equal(ir,jr);equal(ii,ji);
const interopB=fastB.__testDPSS(128,3.0,3),interopBR=plainB.__testDPSS(128,3.0,3);
for(let q=0;q<interopB.length;q++)for(let i=0;i<interopB[q].length;i++)if(!Object.is(interopB[q][i],interopBR[q][i]))throw Error('DPSS-to-FFT-to-DPSS workspace reuse mismatch');
console.log('PASS Worker B shared WASM workspace FFT/DPSS interop');
