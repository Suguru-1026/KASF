const fs=require('fs');
const path=require('path');
const root=path.join(__dirname,'..');
function wasm(file){
 const html=fs.readFileSync(file,'utf8');
 const b64=html.match(/<script id="kasf-wasm-binary" type="text\/plain">([\s\S]*?)<\/script>/)[1].trim();
 return new WebAssembly.Instance(new WebAssembly.Module(Buffer.from(b64,'base64'))).exports;
}
const oldW=wasm(path.join(root,'comparison/KASF-2.0-Evolution-Rev0.9.11-Performance-Optimized.html'));
const newW=wasm(path.join(root,'KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'));
if(typeof newW.kasf_solve_ridge_qr_inplace!=='function')throw Error('in-place QR export missing');
let seed=0x4a5b6c7d;
function rnd(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
function alloc(w,counts){let off=0,ptrs=[];for(const n of counts){off=(off+7)&~7;ptrs.push(off);off+=n*8;}w.kasf_reset_heap();const base=w.kasf_alloc(off);if(!base)throw Error('WASM allocation failed');return {base,ptrs};}
function check(n,d,lambda,degenerate=false){
 const rows=n+d, cols=Array.from({length:d},()=>new Float64Array(n)),target=Float64Array.from({length:n},()=>rnd()-.5),prior=Float64Array.from({length:d},()=>rnd()-.5);
 for(let j=0;j<d;j++)for(let i=0;i<n;i++)cols[j][i]=degenerate?(j%3===0?0:(j%3===1?cols[Math.max(0,j-1)][i]:cols[Math.max(0,j-1)][i])):(rnd()-.5)*.08;
 const old=alloc(oldW,[n*d,n,d,rows*d,rows,d]),newer=alloc(newW,[rows*d,n,d,rows,d]);
 const oldA=old.base+old.ptrs[0],oldY=old.base+old.ptrs[1],oldP=old.base+old.ptrs[2],oldScratchA=old.base+old.ptrs[3],oldScratchB=old.base+old.ptrs[4],oldBeta=old.base+old.ptrs[5];
 const newA=newer.base+newer.ptrs[0],newY=newer.base+newer.ptrs[1],newP=newer.base+newer.ptrs[2],newScratchB=newer.base+newer.ptrs[3],newBeta=newer.base+newer.ptrs[4];
 const oldMatrix=new Float64Array(oldW.memory.buffer,oldA,n*d),newMatrix=new Float64Array(newW.memory.buffer,newA,rows*d);
 for(let j=0;j<d;j++){oldMatrix.set(cols[j],j*n);newMatrix.set(cols[j],j*rows);}
 new Float64Array(oldW.memory.buffer,oldY,n).set(target);new Float64Array(oldW.memory.buffer,oldP,d).set(prior);
 new Float64Array(newW.memory.buffer,newY,n).set(target);new Float64Array(newW.memory.buffer,newP,d).set(prior);
 const oldRank=oldW.kasf_solve_ridge_qr(oldA,oldY,oldP,n,d,lambda,oldScratchA,oldScratchB,oldBeta);
 const newRank=newW.kasf_solve_ridge_qr_inplace(newA,newY,newP,n,d,lambda,newScratchB,newBeta);
 const oldOut=new Float64Array(oldW.memory.buffer,oldBeta,d),newOut=new Float64Array(newW.memory.buffer,newBeta,d);
 if(oldRank!==newRank)throw Error(`rank mismatch ${n}x${d} ${oldRank}/${newRank}`);
 for(let i=0;i<d;i++)if(!Object.is(oldOut[i],newOut[i]))throw Error(`bit mismatch ${n}x${d} lambda=${lambda} i=${i}: ${oldOut[i]} vs ${newOut[i]}`);
 console.log(`PASS ${n}x${d} lambda=${lambda} degenerate=${degenerate} rank=${newRank}`);
}
for(const [n,d] of [[128,4],[512,10],[2048,16],[4096,24],[8192,32],[12000,40],[300,40]]){
 check(n,d,.025,false);
}
check(256,8,0,true);
console.log('ALL IN-PLACE QR OUTPUTS BIT-IDENTICAL TO REV.0.9.11');
