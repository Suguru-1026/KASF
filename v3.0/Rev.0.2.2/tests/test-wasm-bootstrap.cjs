const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.join(__dirname,'..');
const html=fs.readFileSync(path.join(root,'KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'),'utf8');
const b64=html.match(/<script id="kasf-wasm-binary" type="text\/plain">([\s\S]*?)<\/script>/)?.[1]?.trim();
if(!b64)throw Error('WASM payload missing');
const token='const wasmBoot=useWasm?`';const a=html.indexOf(token);if(a<0)throw Error('worker boot template missing');
const begin=a+token.length;const end=html.indexOf('`:`self.__KASF_WASM_SOLVE=null',begin);if(end<0)throw Error('worker boot template terminator missing');
const template=html.slice(begin,end);
const boot=new Function('b64',`return \`${template}\`;`)(b64);
const c={atob,WebAssembly,Float64Array,Map,Math,Number,Error,String,Array,BigInt};c.self=c;c.globalThis=c;
vm.createContext(c);vm.runInContext(boot,c,{timeout:10000});
if(typeof c.__KASF_WASM_FFT!=='function'||typeof c.__KASF_WASM_ACQUIRE!=='function')throw Error('WASM worker API not initialized');
function jsFFT(real,imag){const n=real.length;for(let i=1,j=0;i<n;i++){let b=n>>1;for(;j&b;b>>=1)j^=b;j^=b;if(i<j){let t=real[i];real[i]=real[j];real[j]=t;t=imag[i];imag[i]=imag[j];imag[j]=t;}}for(let l=2;l<=n;l*=2){const a=-2*Math.PI/l,wr0=Math.cos(a),wi0=Math.sin(a);for(let p=0;p<n;p+=l){let wr=1,wi=0;for(let j=0;j<l/2;j++){const x=p+j,y=x+l/2,vr=real[y]*wr-imag[y]*wi,vi=real[y]*wi+imag[y]*wr;real[y]=real[x]-vr;imag[y]=imag[x]-vi;real[x]+=vr;imag[x]+=vi;const nr=wr*wr0-wi*wi0;wi=wr*wi0+wi*wr0;wr=nr;}}}}
function same(a,b){if(a.length!==b.length)throw Error('length mismatch');for(let i=0;i<a.length;i++)if(!Object.is(a[i],b[i]))throw Error('value mismatch '+i);}
for(const n of [2048,4096,8192,32768,65536,131072]){
 const x=new Float64Array(n),y=new Float64Array(n);let seed=n;for(let i=0;i<n;i++){seed=(seed*1664525+1013904223)>>>0;x[i]=seed/4294967296-.5;}
 const aR=x.slice(),aI=y.slice(),bR=x.slice(),bI=y.slice();jsFFT(aR,aI);const used=c.__KASF_WASM_FFT(bR,bI);const shouldUse=n===2048||n===4096||n>=65536;if(used!==shouldUse)throw Error(`dispatch mismatch at ${n}: ${used}`);if(!used)jsFFT(bR,bI);same(aR,bR);same(aI,bI);
}
// Exercise QR -> FFT workspace growth -> QR, proving both kernels coexist.
function qr(){const n=128,d=4,v=c.__KASF_WASM_ACQUIRE(n,d);if(!v)throw Error('QR acquire failed');for(let j=0;j<d;j++)for(let i=0;i<n;i++)v.columns[j][i]=Math.sin((i+1)*(j+1)*.017);v.target.fill(.1);v.prior.fill(0);const r=c.__KASF_WASM_SOLVE_READY(n,d,.02);if(!r||r.rank<1||r.beta.length!==d)throw Error('QR solve failed after workspace change');}
qr();const aR=new Float64Array(65536),aI=new Float64Array(65536);for(let i=0;i<aR.length;i++)aR[i]=Math.sin(i*.01);if(!c.__KASF_WASM_FFT(aR,aI))throw Error('large FFT dispatch failed');qr();
console.log('PASS: actual HTML worker bootstrap, FFT routing, JS fallback, QR/FFT workspace interop');
