'use strict';
const fs=require('node:fs'),path=require('node:path'),{performance}=require('node:perf_hooks');
const w=new WebAssembly.Instance(new WebAssembly.Module(fs.readFileSync(path.join(__dirname,'../build/kasf-core-clang-validation.wasm'))),{}).exports;
const bits=x=>{const b=Buffer.allocUnsafe(8);b.writeDoubleLE(x);return b.toString('hex');};
const same=(a,b,label)=>{if(bits(a)!==bits(b))throw Error(`${label}: ${a} != ${b}`);};
function jsMatrix(N,NW){const W=NW/N,M=new Float64Array(N*N);for(let i=0;i<N;i++)for(let j=0;j<N;j++){const d=i-j;M[i*N+j]=d===0?2*W:Math.sin(2*Math.PI*W*d)/(Math.PI*d);}return M;}
function wasmMatrix(N,NW){const W=NW/N,kernel=new Float64Array(N);for(let d=0;d<N;d++)kernel[d]=d===0?2*W:Math.sin(2*Math.PI*W*d)/(Math.PI*d);w.kasf_reset_heap();const base=w.kasf_alloc((N*N+N)*8);if(!base)throw Error('allocation failed');const mem=w.memory.buffer,k=new Float64Array(mem,base,N),m=new Float64Array(mem,base+N*8,N*N);k.set(kernel);const rc=w.kasf_dpss_build_toeplitz(k.byteOffset,m.byteOffset,N);if(rc!==0)throw Error(`toeplitz build failed: ${rc}`);return {matrix:m.slice(),kernel};}
for(const [N,NW] of [[128,2.5],[256,2.5],[256,3.5],[512,2.5],[512,3.5]]){const a=jsMatrix(N,NW),b=wasmMatrix(N,NW).matrix;for(let i=0;i<a.length;i++)same(a[i],b[i],`matrix ${N}/${NW} @${i}`);console.log(`PASS DPSS Toeplitz matrix bit-identical N=${N} NW=${NW}`);}
function median(a){return a.sort((x,y)=>x-y)[a.length>>1];}
function bench(N,NW,reps=40){function js(){return jsMatrix(N,NW);}function wasm(){return wasmMatrix(N,NW).matrix;}js();wasm();const jt=[],wt=[];for(let r=0;r<7;r++){let t=performance.now();for(let i=0;i<reps;i++)js();jt.push(performance.now()-t);t=performance.now();for(let i=0;i<reps;i++)wasm();wt.push(performance.now()-t);}return {N,NW,reps,jsMs:+median(jt).toFixed(2),wasmMs:+median(wt).toFixed(2),speedup:+(median(jt)/median(wt)).toFixed(2)};}
console.log('BENCH DPSS matrix construction median of 7',JSON.stringify([bench(128,2.5),bench(256,2.5),bench(512,2.5)]));
