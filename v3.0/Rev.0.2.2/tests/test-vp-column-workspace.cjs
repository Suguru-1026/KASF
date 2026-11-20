const fs=require('fs'),vm=require('vm'),path=require('path');
function scripts(file){return [...fs.readFileSync(file,'utf8').matchAll(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);}
function pick(file,needle){const s=scripts(file).find(x=>x.includes(needle));if(!s)throw Error('missing '+needle);return s;}
function context(){const c={postMessage:()=>{},console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,performance:{now:()=>0}};c.self=c;c.globalThis=c;return vm.createContext(c);}
function load(file){const c=context();vm.runInContext(pick(file,'root.KASF_TVS = api'),c);return c;}
function attachWasm(c,file,zeroCopy=false){
 const html=fs.readFileSync(file,'utf8'),b64=html.match(/<script id="kasf-wasm-binary" type="text\/plain">([\s\S]*?)<\/script>/)[1].trim();
 const w=new WebAssembly.Instance(new WebAssembly.Module(Buffer.from(b64,'base64'))).exports;let ws=null;const align8=x=>(x+7)&~7;
 if(!zeroCopy){
  function reserve(n,d){const capN=Math.max(n,ws?.capN||0),capD=Math.max(d,ws?.capD||0),capRows=capN+capD,sizes=[capN*capD,capN,capD,capRows*capD,capRows,capD];let off=0;const offsets=[];for(const count of sizes){offsets.push(off);off=align8(off+count*8);}w.kasf_reset_heap();const base=w.kasf_alloc(off);if(!base)throw Error('WASM allocation failed');ws={capN,capD,base,offsets,views:sizes.map((count,i)=>new Float64Array(w.memory.buffer,base+offsets[i],count)),shapeViews:new Map()};}
  function ensure(n,d){if(!n||!d||d>4096)return null;if(!ws||n>ws.capN||d>ws.capD)reserve(n,d);const key=n+':'+d;let v=ws.shapeViews.get(key);if(!v){const buffer=w.memory.buffer,pc=ws.base+ws.offsets[0],py=ws.base+ws.offsets[1],pp=ws.base+ws.offsets[2];v={columns:Array.from({length:d},(_,j)=>new Float64Array(buffer,pc+j*n*8,n)),target:new Float64Array(buffer,py,n),prior:new Float64Array(buffer,pp,d)};ws.shapeViews.set(key,v);}return v;}
  c.__KASF_WASM_SOLVE=(columns,target,lambda,prior)=>{const d=columns.length,n=target.length,v=ensure(n,d);if(!v)return null;for(let j=0;j<d;j++)v.columns[j].set(columns[j]);v.target.set(target);if(prior)v.prior.set(prior.subarray?prior.subarray(0,d):prior);else v.prior.fill(0);const rank=w.kasf_solve_ridge_qr(ws.base,ws.base+ws.offsets[1],ws.base+ws.offsets[2],n,d,lambda,ws.base+ws.offsets[3],ws.base+ws.offsets[4],ws.base+ws.offsets[5]);return {beta:ws.views[5].slice(0,d),rank};};
  return;
 }
 function reserve(n,d){const capN=Math.max(n,ws?.capN||0),capD=Math.max(d,ws?.capD||0),capRows=capN+capD,sizes=[capRows*capD,capN,capD,capRows,capD];let off=0;const offsets=[];for(const count of sizes){offsets.push(off);off=align8(off+count*8);}w.kasf_reset_heap();const base=w.kasf_alloc(off);if(!base)throw Error('WASM allocation failed');ws={capN,capD,base,offsets,views:sizes.map((count,i)=>new Float64Array(w.memory.buffer,base+offsets[i],count)),shapeViews:new Map()};}
 function ensure(n,d){if(!n||!d||d>4096)return null;if(!ws||n>ws.capN||d>ws.capD)reserve(n,d);const rows=n+d,key=n+':'+d;let v=ws.shapeViews.get(key);if(!v){const buffer=w.memory.buffer,pc=ws.base+ws.offsets[0],py=ws.base+ws.offsets[1],pp=ws.base+ws.offsets[2];v={columns:Array.from({length:d},(_,j)=>new Float64Array(buffer,pc+j*rows*8,rows)),target:new Float64Array(buffer,py,n),prior:new Float64Array(buffer,pp,d)};ws.shapeViews.set(key,v);}return v;}
 c.__KASF_WASM_ACQUIRE=(n,d)=>{try{return ensure(n,d);}catch(e){c.__KASF_WASM_ERROR=String(e&&e.message||e);return null;}};
 c.__KASF_WASM_SOLVE_READY=(n,d,lambda)=>{try{if(!ws||n>ws.capN||d>ws.capD)return null;const rank=w.kasf_solve_ridge_qr_inplace(ws.base,ws.base+ws.offsets[1],ws.base+ws.offsets[2],n,d,lambda,ws.base+ws.offsets[3],ws.base+ws.offsets[4]);return {beta:ws.views[4].slice(0,d),rank};}catch(e){c.__KASF_WASM_ERROR=String(e&&e.message||e);return null;}};
 c.__KASF_WASM_SOLVE=(columns,target,lambda,prior)=>{try{const d=columns.length,n=target.length,v=ensure(n,d);if(!v)return null;for(let j=0;j<d;j++)v.columns[j].set(columns[j].subarray?columns[j].subarray(0,n):columns[j]);v.target.set(target);if(prior)v.prior.set(prior.subarray?prior.subarray(0,d):prior);else v.prior.fill(0);return c.__KASF_WASM_SOLVE_READY(n,d,lambda);}catch(e){c.__KASF_WASM_ERROR=String(e&&e.message||e);return null;}};
}

const dir=path.join(__dirname,'..'),oldFile=path.join(dir,'comparison/KASF-2.0-Evolution-Rev0.9.11-Performance-Optimized.html'),newFile=path.join(dir,'KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html');
const old=load(oldFile),neo=load(newFile);attachWasm(old,oldFile,false);attachWasm(neo,newFile,true);
let seed=0x1248ab;function rnd(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
const rate=48000,fd=.02,source=Float64Array.from({length:24000},()=>rnd()*.4-.2),base=[];
for(let m=0;m<12;m++){const list=[];for(let j=0;j<64;j++)list.push({frequency:50+rnd()*18000,amplitude:.001+rnd()*.12,phase:rnd()*Math.PI*2});base.push([list]);}
const selected=[];for(let m=2;m<=8;m++)for(let j=0;j<3;j++)selected.push({m,index:j+5,amp:base[m][0][j+5].amplitude});
const framesOld=JSON.parse(JSON.stringify(base)),framesNew=JSON.parse(JSON.stringify(base));
const argsOld={frames:framesOld,channel:0,selected,source,start:1000,end:21000,step:1,rate,frameDuration:fd,attackTime:.1,lambda:.025};
const argsNew={...argsOld,frames:framesNew};
const cacheOld=old.KASF05_VP.prepareFitCache(argsOld),cacheNew=neo.KASF05_VP.prepareFitCache(argsNew);
if(cacheNew.columns!==null)throw Error('WASM path should not allocate JS QR columns');
const wasmShape=neo.__KASF_WASM_ACQUIRE(cacheNew.n,selected.length*2),innerRefs=wasmShape.columns.slice();
const offsetsList=[0,selected.map((_,i)=>(i%3-1)*.65),selected.map((_,i)=>(i%2?1:-1)*1.2),selected.map((_,i)=>(i%5-2)*.37),selected.map(()=>0)];
for(let r=0;r<offsetsList.length;r++){
 const offsets=Array.isArray(offsetsList[r])?offsetsList[r]:selected.map(()=>0);
 const a=old.KASF05_VP.fit({...argsOld,frequencyOffsets:offsets,cache:cacheOld});
 const b=neo.KASF05_VP.fit({...argsNew,frequencyOffsets:offsets,cache:cacheNew});
 if(cacheNew.columns!==null)throw Error('WASM path unexpectedly allocated JavaScript QR columns');
 if(a.rank!==b.rank)throw Error('rank mismatch');
 for(let i=0;i<a.components.length;i++)for(const k of ['frequency','amplitude','phase'])if(!Object.is(a.components[i][k],b.components[i][k]))throw Error(`fit mismatch r${r} ${i} ${k}`);
 const nextShape=neo.__KASF_WASM_ACQUIRE(cacheNew.n,selected.length*2);if(nextShape.columns.length!==innerRefs.length||nextShape.columns.some((x,i)=>x!==innerRefs[i]))throw Error('WASM column views were replaced');
}
const jsOld=load(oldFile),jsNew=load(newFile),jsFramesOld=JSON.parse(JSON.stringify(base)),jsFramesNew=JSON.parse(JSON.stringify(base)),jsArgsOld={...argsOld,frames:jsFramesOld},jsArgsNew={...argsNew,frames:jsFramesNew},jsCacheOld=jsOld.KASF05_VP.prepareFitCache(jsArgsOld),jsCacheNew=jsNew.KASF05_VP.prepareFitCache(jsArgsNew),jsColumns=jsCacheNew.columns.slice();
for(let r=0;r<offsetsList.length;r++){const offsets=Array.isArray(offsetsList[r])?offsetsList[r]:selected.map(()=>0),a=jsOld.KASF05_VP.fit({...jsArgsOld,frequencyOffsets:offsets,cache:jsCacheOld}),b=jsNew.KASF05_VP.fit({...jsArgsNew,frequencyOffsets:offsets,cache:jsCacheNew});if(a.rank!==b.rank)throw Error('JS fallback rank mismatch');for(let i=0;i<a.components.length;i++)for(const k of ['frequency','amplitude','phase'])if(!Object.is(a.components[i][k],b.components[i][k]))throw Error(`JS fallback mismatch r${r} ${i} ${k}`);}
if(jsCacheNew.columns.some((x,i)=>x!==jsColumns[i]))throw Error('JS fallback column buffers were replaced');
console.log('VP WASM ZERO-COPY + JS FALLBACK EXACT MATCH; WASM views and JS fallback buffers reused across',offsetsList.length,'proposals; dimension',selected.length*2);
