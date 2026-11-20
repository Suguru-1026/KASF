const fs=require('fs'),vm=require('vm');
function scripts(file){return [...fs.readFileSync(file,'utf8').matchAll(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);}
function pick(file,needle){const s=scripts(file).find(x=>x.includes(needle));if(!s)throw Error('missing '+needle);return s;}
function context(){const c={postMessage:()=>{},console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,performance:{now:()=>0}};c.self=c;c.globalThis=c;return vm.createContext(c);}
function load(file){const c=context();const list=[pick(file,'root.KASF_TVS = api'),pick(file,'root.KASF05_Reader={parameters,componentValue,render'),pick(file,'root.KASF05_VP={solveQR')];for(const src of [...new Set(list)])vm.runInContext(src,c);return c;}
const old=load(require('path').join(__dirname,'../comparison/KASF-2.0-Evolution-Rev0.9.10-Workspace-Optimized.html')),neu=load(require('path').join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'));
function attachWasm(c){
 const html=fs.readFileSync(require('path').join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'),'utf8');
 const b64=html.match(/<script id="kasf-wasm-binary" type="text\/plain">([\s\S]*?)<\/script>/)[1].trim();
 const w=new WebAssembly.Instance(new WebAssembly.Module(Buffer.from(b64,'base64'))).exports;let ws=null;
 const align8=x=>(x+7)&~7;
 function reserve(n,d){const capN=Math.max(n,ws?.capN||0),capD=Math.max(d,ws?.capD||0),capRows=capN+capD,sizes=[capRows*capD,capN,capD,capRows,capD];let off=0;const offsets=[];for(const count of sizes){offsets.push(off);off=align8(off+count*8);}w.kasf_reset_heap();const base=w.kasf_alloc(off);if(!base)throw Error('WASM allocation failed');ws={capN,capD,base,offsets,views:sizes.map((count,i)=>new Float64Array(w.memory.buffer,base+offsets[i],count))};}
 c.__KASF_WASM_SOLVE=(columns,target,lambda,prior)=>{const d=columns.length,n=target.length;if(!ws||n>ws.capN||d>ws.capD)reserve(n,d);const rows=n+d,pc=ws.base,py=ws.base+ws.offsets[1],pp=ws.base+ws.offsets[2],pb=ws.base+ws.offsets[3],po=ws.base+ws.offsets[4];for(let j=0;j<d;j++)new Float64Array(w.memory.buffer,pc+j*rows*8,rows).set(columns[j]);new Float64Array(w.memory.buffer,py,n).set(target);new Float64Array(w.memory.buffer,pp,d).set(prior);const rank=w.kasf_solve_ridge_qr_inplace(pc,py,pp,n,d,lambda,pb,po);return {beta:new Float64Array(w.memory.buffer,po,d).slice(),rank};};
}
attachWasm(old);attachWasm(neu);
let seed=0xabcddcba;function rnd(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
const rate=48000,fd=.02,frames=[],source=Float64Array.from({length:24000},()=>rnd()*.4-.2);
for(let m=0;m<10;m++){const list=[];for(let j=0;j<40;j++)list.push({frequency:80+rnd()*15000,amplitude:.001+rnd()*.12,phase:rnd()*Math.PI*2});frames.push([list]);}
const selected=[];for(let m=2;m<=6;m++)for(let j=0;j<2;j++)selected.push({m,index:j+3,amp:frames[m][0][j+3].amplitude});
const args={frames,channel:0,selected,source,start:2000,end:18000,step:1,rate,frameDuration:fd,attackTime:.1,lambda:.025};
const oldResult=old.KASF05_VP.fit({...args,frequencyOffsets:selected.map((_,i)=>(i%3-1)*.65)});
const cache=neu.KASF05_VP.prepareFitCache(args);
for(const offsets of [selected.map((_,i)=>(i%3-1)*.65),selected.map((_,i)=>(i%2?1:-1)*1.2),selected.map(()=>0)]){
 const fresh=neu.KASF05_VP.fit({...args,frequencyOffsets:offsets});
 const fast=neu.KASF05_VP.fit({...args,frequencyOffsets:offsets,cache});
 if(fresh.rank!==fast.rank)throw Error('rank mismatch');
 for(let i=0;i<fresh.components.length;i++)for(const k of ['frequency','amplitude','phase'])if(!Object.is(fresh.components[i][k],fast.components[i][k]))throw Error(`cache mismatch ${i} ${k}: ${fresh.components[i][k]} ${fast.components[i][k]}`);
 console.log('WASM cached fit equals uncached',offsets[0]);
}
for(let i=0;i<oldResult.components.length;i++)for(const k of ['frequency','amplitude','phase'])if(!Object.is(oldResult.components[i][k],neu.KASF05_VP.fit({...args,frequencyOffsets:selected.map((_,i)=>(i%3-1)*.65)}).components[i][k]))throw Error('old/new fit mismatch');
console.log('VP CACHE ALL PASS');
