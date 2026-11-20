const fs=require('node:fs'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'),'utf8');
const b64=html.match(/<script id="kasf-wasm-binary" type="text\/plain">([\s\S]*?)<\/script>/)?.[1]?.trim();
// Use the just-built module until the final HTML payload is embedded.
const wasmBytes=fs.readFileSync(path.join(__dirname,'../build/kasf-core-clang-validation.wasm'));
const w=new WebAssembly.Instance(new WebAssembly.Module(wasmBytes),{}).exports;
function jsDpss(N=256,NW=2.5,K=3){
 const W=NW/N,Kmat=new Float64Array(N*N);
 for(let i=0;i<N;i++)for(let j=0;j<N;j++){const d=i-j;Kmat[i*N+j]=d===0?2*W:Math.sin(2*Math.PI*W*d)/(Math.PI*d);}
 const out=[];
 for(let q=0;q<K;q++){
  let v=new Float64Array(N);for(let i=0;i<N;i++)v[i]=Math.cos(Math.PI*(q+1)*(i+.5)/N)+.37*Math.sin(Math.PI*(q+2)*(i+.5)/N);
  const orth=()=>{for(const u of out){let d=0;for(let i=0;i<N;i++)d+=v[i]*u[i];for(let i=0;i<N;i++)v[i]-=d*u[i];}let z=Math.sqrt(v.reduce((a,b)=>a+b*b,0))||1;for(let i=0;i<N;i++)v[i]/=z;};orth();
  for(let it=0;it<88;it++){const z=new Float64Array(N);for(let i=0;i<N;i++){let a=0,base=i*N;for(let j=0;j<N;j++)a+=Kmat[base+j]*v[j];z[i]=a;}v=z;orth();}
  let peak=0;for(let i=0;i<N;i++)if(Math.abs(v[i])>Math.abs(v[peak]))peak=i;if(v[peak]<0)for(let i=0;i<N;i++)v[i]=-v[i];out.push(v);
 }
 return out;
}
function wasmDpss(N=256,NW=2.5,K=3){
 const W=NW/N,Kmat=new Float64Array(N*N);
 for(let i=0;i<N;i++)for(let j=0;j<N;j++){const d=i-j;Kmat[i*N+j]=d===0?2*W:Math.sin(2*Math.PI*W*d)/(Math.PI*d);}
 const out=[];w.kasf_reset_heap();let off=0;const alloc=(n)=>{off=(off+7)&~7;const p=base+off;off+=n*8;return new Float64Array(w.memory.buffer,p,n);};const bytes=8*(N*N+N*4+K*N);const base=w.kasf_alloc(bytes);if(!base)throw Error('WASM allocation failed');off=0;
 const matrix=alloc(N*N),initial=alloc(N),basis=alloc(K*N),result=alloc(N),scratch=alloc(N);matrix.set(Kmat);
 for(let q=0;q<K;q++){
  for(let i=0;i<N;i++)initial[i]=Math.cos(Math.PI*(q+1)*(i+.5)/N)+.37*Math.sin(Math.PI*(q+2)*(i+.5)/N);
  for(let p=0;p<q;p++)basis.set(out[p],p*N);
  const rc=w.kasf_dpss_power_iteration(matrix.byteOffset,initial.byteOffset,basis.byteOffset,q,result.byteOffset,scratch.byteOffset,N,88);if(rc!==0)throw Error('DPSS kernel '+rc);
  let peak=0;for(let i=0;i<N;i++)if(Math.abs(result[i])>Math.abs(result[peak]))peak=i;if(result[peak]<0)for(let i=0;i<N;i++)result[i]=-result[i];out.push(result.slice());
 }
 return out;
}
function same(a,b,label){for(let q=0;q<a.length;q++)for(let i=0;i<a[q].length;i++)if(!Object.is(a[q][i],b[q][i]))throw Error(`${label} mismatch q=${q} i=${i}: ${a[q][i]} != ${b[q][i]}`);}
for(const [N,NW,K] of [[128,2.5,3],[256,2.5,3],[256,3.5,4],[512,2.5,3]]){const a=jsDpss(N,NW,K),b=wasmDpss(N,NW,K);same(a,b,`${N}/${NW}/${K}`);console.log(`PASS DPSS ${N}/${NW}/${K} bit-identical`);}
function median(a){return a.sort((x,y)=>x-y)[Math.floor(a.length/2)];}
for(const [N,NW,K] of [[256,2.5,3],[512,2.5,3]]){
 for(let i=0;i<2;i++){jsDpss(N,NW,K);wasmDpss(N,NW,K);}
 const j=[],v=[];for(let i=0;i<7;i++){let t=process.hrtime.bigint();jsDpss(N,NW,K);j.push(Number(process.hrtime.bigint()-t)/1e6);t=process.hrtime.bigint();wasmDpss(N,NW,K);v.push(Number(process.hrtime.bigint()-t)/1e6);}
 console.log(`BENCH DPSS ${N}/${NW}/${K}: JS ${median(j).toFixed(2)} ms / WASM+copy ${median(v).toFixed(2)} ms / ${(median(j)/median(v)).toFixed(2)}x`);
}
