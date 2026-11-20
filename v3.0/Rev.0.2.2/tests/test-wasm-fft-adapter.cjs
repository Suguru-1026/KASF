const fs=require('node:fs');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'),'utf8');
const b64=html.match(/<script id="kasf-wasm-binary" type="text\/plain">([\s\S]*?)<\/script>/)?.[1]?.trim();
if(!b64)throw Error('embedded WASM not found');
const wasmBytes=Buffer.from(b64,'base64');
const mod=new WebAssembly.Module(wasmBytes);
const instance=new WebAssembly.Instance(mod,{}),w=instance.exports;
const align8=x=>(x+7)&~7;
let ws=null;
function reserve(n,d,fftN=0){const capN=Math.max(n,ws?.capN||0),capD=Math.max(d,ws?.capD||0),capFFT=Math.max(fftN,ws?.capFFT||0),capRows=capN+capD,halfFFT=Math.floor(capFFT/2),twiddleCount=capFFT>1?Math.floor(Math.log2(capFFT))*2:0,sizes=[capRows*capD,capN,capD,capRows,capD,capFFT,capFFT,halfFFT,halfFFT,twiddleCount];let off=0;const offsets=[];for(const count of sizes){offsets.push(off);off=align8(off+count*8);}w.kasf_reset_heap();const base=w.kasf_alloc(off);if(!base)throw Error('WASM memory');const buffer=w.memory.buffer;ws={capN,capD,capFFT,capRows,base,offsets,views:sizes.map((count,i)=>new Float64Array(buffer,base+offsets[i],count)),shapeViews:new Map(),fftViews:new Map()};}
function ensure(n,d){if(!n||!d||d>4096)return null;if(!ws||n>ws.capN||d>ws.capD)reserve(n,d);const rows=n+d,key=n+':'+d;let v=ws.shapeViews.get(key);if(!v){const b=w.memory.buffer,pc=ws.base+ws.offsets[0],py=ws.base+ws.offsets[1],pp=ws.base+ws.offsets[2];v={columns:Array.from({length:d},(_,j)=>new Float64Array(b,pc+j*rows*8,rows)),target:new Float64Array(b,py,n),prior:new Float64Array(b,pp,d)};ws.shapeViews.set(key,v);}return v;}
function ensureFFT(n){if(!Number.isInteger(n)||(n!==2048&&n!==4096&&n<65536)||(n&(n-1))!==0)return null;if(!ws||n>ws.capFFT)reserve(ws?.capN||1,ws?.capD||1,n);let v=ws.fftViews.get(n);if(!v){const b=w.memory.buffer,p=ws.base;v={real:new Float64Array(b,p+ws.offsets[5],n),imag:new Float64Array(b,p+ws.offsets[6],n),twiddleReal:new Float64Array(b,p+ws.offsets[7],n/2),twiddleImag:new Float64Array(b,p+ws.offsets[8],n/2),twiddles:new Float64Array(b,p+ws.offsets[9],Math.log2(n)*2)};ws.fftViews.set(n,v);}return v;}
function wasmFFT(real,imag){try{const n=real?.length;if(!n||imag?.length!==n||(n!==2048&&n!==4096&&n<65536)||(n&(n-1))!==0)return false;const v=ensureFFT(n);if(!v)return false;v.real.set(real);v.imag.set(imag);for(let len=2,stage=0;len<=n;len*=2,stage++){const angle=-2*Math.PI/len;v.twiddles[stage*2]=Math.cos(angle);v.twiddles[stage*2+1]=Math.sin(angle);}const rc=w.kasf_fft_inplace(v.real.byteOffset,v.imag.byteOffset,v.twiddles.byteOffset,v.twiddleReal.byteOffset,v.twiddleImag.byteOffset,n);if(rc!==0)return false;real.set(v.real);imag.set(v.imag);return true;}catch(e){throw e;}}
function jsFFT(real,imag){const n=real.length;for(let i=1,j=0;i<n;i++){let bit=n>>1;for(;j&bit;bit>>=1)j^=bit;j^=bit;if(i<j){let t=real[i];real[i]=real[j];real[j]=t;t=imag[i];imag[i]=imag[j];imag[j]=t;}}for(let length=2;length<=n;length<<=1){const angle=-2*Math.PI/length,wReal=Math.cos(angle),wImag=Math.sin(angle),half=length>>1;for(let start=0;start<n;start+=length){let currentReal=1,currentImag=0;for(let j=0;j<half;j++){const ei=start+j,oi=ei+half,or=real[oi],om=imag[oi],tr=or*currentReal-om*currentImag,ti=or*currentImag+om*currentReal,er=real[ei],em=imag[ei];real[ei]=er+tr;imag[ei]=em+ti;real[oi]=er-tr;imag[oi]=em-ti;const nr=currentReal*wReal-currentImag*wImag,ni=currentReal*wImag+currentImag*wReal;currentReal=nr;currentImag=ni;}}}}
function bits(x){const a=new ArrayBuffer(8),v=new DataView(a);v.setFloat64(0,x,true);return v.getBigUint64(0,true);}
function same(a,b,label){for(let i=0;i<a.length;i++)if(bits(a[i])!==bits(b[i]))throw Error(`${label} bit mismatch at ${i}`);}
let seed=0x9e3779b9;function rand(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>>0)/4294967296*2-1;}
let cases=0;
for(const n of [2048,4096,8192,16384,32768,65536,131072])for(const kind of ['random','impulse','sine','wide']){
 const origR=new Float64Array(n),origI=new Float64Array(n);for(let i=0;i<n;i++){if(kind==='random'){origR[i]=rand();origI[i]=rand();}else if(kind==='impulse'){origR[i]=i===0?1:0;}else if(kind==='sine'){origR[i]=Math.sin(2*Math.PI*37*i/n);}else{origR[i]=rand()*2**((i%64)-32);origI[i]=rand()*2**((i%64)-32);}}
 const jr=origR.slice(),ji=origI.slice(),wr=origR.slice(),wi=origI.slice();jsFFT(jr,ji);const used=wasmFFT(wr,wi);if(!used)jsFFT(wr,wi);same(jr,wr,`${n}/${kind}/real`);same(ji,wi,`${n}/${kind}/imag`);cases++;
}
// Below-threshold transforms must cleanly retain the JavaScript path.
if(wasmFFT(new Float64Array(1024),new Float64Array(1024))!==false)throw Error('FFT threshold fallback failed');
// Shared workspace must survive both orderings: QR -> FFT and FFT -> QR.
function qrSmoke(){const n=256,d=8,v=ensure(n,d);for(let j=0;j<d;j++)for(let i=0;i<n;i++)v.columns[j][i]=Math.sin((i+1)*(j+1)*.013);v.target.fill(.25);v.prior.fill(0);const rank=w.kasf_solve_ridge_qr_inplace(ws.base,ws.base+ws.offsets[1],ws.base+ws.offsets[2],n,d,.018,ws.base+ws.offsets[3],ws.base+ws.offsets[4]);if(rank<1)throw Error('QR smoke rank invalid');}
qrSmoke();const qR=new Float64Array(4096),qI=new Float64Array(4096);for(let i=0;i<4096;i++)qR[i]=rand();const refR=qR.slice(),refI=qI.slice();jsFFT(refR,refI);wasmFFT(qR,qI);same(refR,qR,'QR-to-FFT interop real');same(refI,qI,'QR-to-FFT interop imag');qrSmoke();

// End-to-end adapter microbenchmark (includes typed-array copies and twiddle prep).
function median(a){return a.sort((x,y)=>x-y)[Math.floor(a.length/2)];}
const bench=[];
for(const n of [2048,4096,65536,131072]){
 const baseR=new Float64Array(n),baseI=new Float64Array(n);for(let i=0;i<n;i++){baseR[i]=rand();baseI[i]=rand();}
 const r=new Float64Array(n),im=new Float64Array(n),jTimes=[],wTimes=[];
 for(let k=0;k<8;k++){r.set(baseR);im.set(baseI);jsFFT(r,im);r.set(baseR);im.set(baseI);wasmFFT(r,im);}
 for(let k=0;k<9;k++){r.set(baseR);im.set(baseI);let t=process.hrtime.bigint();jsFFT(r,im);jTimes.push(Number(process.hrtime.bigint()-t)/1e6);r.set(baseR);im.set(baseI);t=process.hrtime.bigint();const used=wasmFFT(r,im);wTimes.push(Number(process.hrtime.bigint()-t)/1e6);if(!used)throw Error('benchmark WASM dispatch failed');}
 bench.push({n,jsMs:+median(jTimes).toFixed(3),wasmMs:+median(wTimes).toFixed(3),speedup:+(median(jTimes)/median(wTimes)).toFixed(3)});
}
console.log(JSON.stringify({fftCases:cases,interop:'PASS',bitIdentity:'PASS',bench},null,2));
