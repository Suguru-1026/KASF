const fs=require('node:fs');
const path=require('node:path');
const wasmBytes=fs.readFileSync(path.join(__dirname,'../build/kasf-core-clang-validation.wasm'));
const instance=new WebAssembly.Instance(new WebAssembly.Module(wasmBytes),{});
const w=instance.exports;
const align8=x=>(x+7)&~7;
function allocDoubles(count){const p=w.kasf_alloc(count*8);if(!p)throw Error('WASM alloc failed');return new Float64Array(w.memory.buffer,p,count);}
function jsFFT(real,imag){
 const n=real.length;
 for(let i=1,j=0;i<n;i++){let bit=n>>1;for(;j&bit;bit>>=1)j^=bit;j^=bit;if(i<j){let t=real[i];real[i]=real[j];real[j]=t;t=imag[i];imag[i]=imag[j];imag[j]=t;}}
 for(let length=2;length<=n;length<<=1){const angle=-2*Math.PI/length,wReal=Math.cos(angle),wImag=Math.sin(angle),half=length>>1;
  for(let start=0;start<n;start+=length){let currentReal=1,currentImag=0;
   for(let j=0;j<half;j++){const evenIndex=start+j,oddIndex=evenIndex+half,oddReal=real[oddIndex],oddImag=imag[oddIndex],tr=oddReal*currentReal-oddImag*currentImag,ti=oddReal*currentImag+oddImag*currentReal,evenReal=real[evenIndex],evenImag=imag[evenIndex];real[evenIndex]=evenReal+tr;imag[evenIndex]=evenImag+ti;real[oddIndex]=evenReal-tr;imag[oddIndex]=evenImag-ti;const nr=currentReal*wReal-currentImag*wImag,ni=currentReal*wImag+currentImag*wReal;currentReal=nr;currentImag=ni;}
  }
 }
}
function bits(x){const a=new ArrayBuffer(8);new DataView(a).setFloat64(0,x,true);return new DataView(a).getBigUint64(0,true);}
function assertSame(a,b,label){if(a.length!==b.length)throw Error(label+' length mismatch');for(let i=0;i<a.length;i++){if(bits(a[i])!==bits(b[i]))throw Error(`${label} mismatch @${i}: ${a[i]} !== ${b[i]}`);}}
let seed=0x12345678;function rnd(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>>0)/4294967296*2-1;}
let cases=0;
for(const n of [2,4,8,16,64,256,512,1024,2048,4096,8192,16384,32768,65536,131072]){
 for(const fixture of ['random','impulse','sine','wide']){
  const re=new Float64Array(n),im=new Float64Array(n);
  for(let i=0;i<n;i++){
   if(fixture==='random'){re[i]=rnd();im[i]=rnd();}
   else if(fixture==='impulse'){re[i]=i===0?1:0;im[i]=0;}
   else if(fixture==='sine'){re[i]=Math.sin(2*Math.PI*17*i/n);im[i]=0;}
   else {re[i]=rnd()*Math.pow(2,(i%80)-40);im[i]=rnd()*Math.pow(2,(i%80)-40);}
  }
  const jr=re.slice(),ji=im.slice();jsFFT(jr,ji);
  w.kasf_reset_heap();const wr=allocDoubles(n),wi=allocDoubles(n),tw=allocDoubles(2*Math.log2(n));wr.set(re);wi.set(im);
  let s=0;for(let len=2;len<=n;len<<=1,s++){const a=-2*Math.PI/len;tw[s*2]=Math.cos(a);tw[s*2+1]=Math.sin(a);}
  const rc=w.kasf_fft_inplace_scalar(wr.byteOffset,wi.byteOffset,tw.byteOffset,n);if(rc!==0)throw Error('WASM FFT returned '+rc);
  assertSame(jr,wr,`${n}/${fixture}/real`);assertSame(ji,wi,`${n}/${fixture}/imag`);cases++;
 }
}
console.log(`PASS: ${cases} FFT fixtures; bit-identical real/imag outputs`);
