const fs=require('fs'),vm=require('vm'),{performance}=require('perf_hooks');
function worker(file){const h=fs.readFileSync(file,'utf8');const m=h.match(/<script id="embedded-worker-a"[^>]*>([\s\S]*?)<\/script>/i);if(!m)throw Error('worker A missing');const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,performance,setTimeout,clearTimeout,postMessage:()=>{},Blob,TextEncoder,TextDecoder};c.self=c;c.globalThis=c;c.document={getElementById:()=>({value:'',textContent:'',innerHTML:'',checked:false})};const ctx=vm.createContext(c);vm.runInContext(m[1],ctx,{timeout:30000});
 const b64=h.match(/<script id=\"kasf-wasm-binary\" type=\"text\/plain\">([\s\S]*?)<\/script>/i)[1].trim();
 const w=new WebAssembly.Instance(new WebAssembly.Module(Buffer.from(b64,'base64'))).exports;let ws=null;const align8=x=>(x+7)&~7;
 if(typeof w.kasf_solve_ridge_qr_inplace==='function'){
  function reserve(n,d){const capN=Math.max(n,ws?.capN||0),capD=Math.max(d,ws?.capD||0),capRows=capN+capD,sizes=[capRows*capD,capN,capD,capRows,capD];let off=0;const offsets=[];for(const count of sizes){offsets.push(off);off=align8(off+count*8);}w.kasf_reset_heap();const base=w.kasf_alloc(off);if(!base)throw Error('WASM allocation failed');ws={capN,capD,base,offsets,views:sizes.map((count,i)=>new Float64Array(w.memory.buffer,base+offsets[i],count)),shapeViews:new Map()};}
  function ensure(n,d){if(!n||!d||d>4096)return null;if(!ws||n>ws.capN||d>ws.capD)reserve(n,d);const rows=n+d,key=n+':'+d;let v=ws.shapeViews.get(key);if(!v){const buffer=w.memory.buffer,pc=ws.base+ws.offsets[0],py=ws.base+ws.offsets[1],pp=ws.base+ws.offsets[2];v={columns:Array.from({length:d},(_,j)=>new Float64Array(buffer,pc+j*rows*8,rows)),target:new Float64Array(buffer,py,n),prior:new Float64Array(buffer,pp,d)};ws.shapeViews.set(key,v);}return v;}
  c.__KASF_WASM_ACQUIRE=(n,d)=>{try{return ensure(n,d);}catch(e){c.__KASF_WASM_ERROR=String(e&&e.message||e);return null;}};
  c.__KASF_WASM_SOLVE_READY=(n,d,lambda)=>{try{if(!ws||n>ws.capN||d>ws.capD)return null;const rank=w.kasf_solve_ridge_qr_inplace(ws.base,ws.base+ws.offsets[1],ws.base+ws.offsets[2],n,d,lambda,ws.base+ws.offsets[3],ws.base+ws.offsets[4]);return {beta:ws.views[4].slice(0,d),rank};}catch(e){c.__KASF_WASM_ERROR=String(e&&e.message||e);return null;}};
  c.__KASF_WASM_SOLVE=(columns,target,lambda,prior)=>{const v=ensure(target.length,columns.length);if(!v)return null;for(let j=0;j<columns.length;j++)v.columns[j].set(columns[j].subarray?columns[j].subarray(0,target.length):columns[j]);v.target.set(target);if(prior)v.prior.set(prior);else v.prior.fill(0);const rank=w.kasf_solve_ridge_qr_inplace(ws.base,ws.base+ws.offsets[1],ws.base+ws.offsets[2],target.length,columns.length,lambda,ws.base+ws.offsets[3],ws.base+ws.offsets[4]);return {beta:ws.views[4].slice(0,columns.length),rank};};
 }else{
  function reserve(n,d){const capN=Math.max(n,ws?.capN||0),capD=Math.max(d,ws?.capD||0),capRows=capN+capD,sizes=[capN*capD,capN,capD,capRows*capD,capRows,capD];let off=0;const offsets=[];for(const count of sizes){offsets.push(off);off=align8(off+count*8);}w.kasf_reset_heap();const base=w.kasf_alloc(off);if(!base)throw Error('WASM allocation failed');ws={capN,capD,base,offsets,views:sizes.map((count,i)=>new Float64Array(w.memory.buffer,base+offsets[i],count)),shapeViews:new Map()};}
  function ensure(n,d){if(!n||!d||d>4096)return null;if(!ws||n>ws.capN||d>ws.capD)reserve(n,d);const key=n+':'+d;let v=ws.shapeViews.get(key);if(!v){const buffer=w.memory.buffer,pc=ws.base+ws.offsets[0],py=ws.base+ws.offsets[1],pp=ws.base+ws.offsets[2];v={columns:Array.from({length:d},(_,j)=>new Float64Array(buffer,pc+j*n*8,n)),target:new Float64Array(buffer,py,n),prior:new Float64Array(buffer,pp,d)};ws.shapeViews.set(key,v);}return v;}
  c.__KASF_WASM_SOLVE=(columns,target,lambda,prior)=>{const v=ensure(target.length,columns.length);if(!v)return null;for(let j=0;j<columns.length;j++)v.columns[j].set(columns[j]);v.target.set(target);if(prior)v.prior.set(prior);else v.prior.fill(0);const rank=w.kasf_solve_ridge_qr(ws.base,ws.base+ws.offsets[1],ws.base+ws.offsets[2],target.length,columns.length,lambda,ws.base+ws.offsets[3],ws.base+ws.offsets[4],ws.base+ws.offsets[5]);return {beta:ws.views[5].slice(0,columns.length),rank};};
 }
 return ctx;}
function randGen(seed){return()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;};}
async function run(file){const c=worker(file),r=randGen(1234),rate=12000,fd=.02,channels=[[]],frames=[];
 for(let ch=0;ch<1;ch++)channels[ch]=Float64Array.from({length:9000},(_,i)=>.12*Math.sin(2*Math.PI*440*i/rate)+.04*Math.sin(2*Math.PI*880*i/rate)+(.003*(r()-.5)));
 const o=c.KASF05_Reader.parameters(rate,fd);
 for(let m=0;m<15;m++){const by=[];for(let ch=0;ch<1;ch++){const list=[];for(let j=0;j<16;j++)list.push({frequency:200+j*370+r()*20,amplitude:.01+r()*.04,phase:r()*Math.PI*2});by.push(list);}frames.push(by);}
 
 const attacks=[{time:.12,confidence:.9,reliable:true,score:1,classes:{dominant:'harmonic',transient:.2,decay:.1}}];
 const out=await c.KASF05_Hybrid.optimize({frames,channels,rate,frameDuration:fd,attacks,level:'extreme'});
 return {frames:out.frames,metrics:out.metrics};}
(async()=>{const a=await run(require('path').join(__dirname,'../comparison/KASF-2.0-Evolution-Rev0.9.17-Reader-Workspace-Optimized.html')),b=await run(require('path').join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'));
 function canonical(x){return JSON.stringify(x);}if(canonical(a.frames)!==canonical(b.frames))throw Error('hybrid frame output mismatch');
 for(const k of Object.keys(a.metrics))if(typeof a.metrics[k]!=='object'&&a.metrics[k]!==b.metrics[k])throw Error('metric mismatch '+k+' '+a.metrics[k]+' '+b.metrics[k]);
 if(!b.metrics.shortApproxRegions||!b.metrics.shortApproxEvaluations)throw Error('short approximation path was not exercised');
 console.log('HYBRID OUTPUT EXACT MATCH; approximate path exercised',b.metrics.shortApproxRegions,b.metrics.shortApproxEvaluations,a.metrics.evaluations,a.metrics.quantTrials,a.metrics.finalScore);
})().catch(e=>{console.error(e);process.exit(1)});
