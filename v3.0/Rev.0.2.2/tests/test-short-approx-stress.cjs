const fs=require('fs'),vm=require('vm'),path=require('path');
function scripts(file){return [...fs.readFileSync(file,'utf8').matchAll(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);}
function pick(file,needle){const s=scripts(file).find(x=>x.includes(needle));if(!s)throw Error('missing '+needle+' in '+file);return s;}
function context(){const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,WeakMap,postMessage:()=>{},setTimeout,clearTimeout,Blob,TextEncoder,TextDecoder,document:{getElementById:()=>({value:'',textContent:'',innerHTML:'',checked:false})}};c.self=c;c.globalThis=c;return vm.createContext(c);}
function load(file){const c=context();for(const src of [...new Set([pick(file,'root.KASF_TVS = api'),pick(file,'root.KASF05_Reader={parameters,componentValue,render')])])vm.runInContext(src,c);return c.KASF05_Reader;}
function maxDiff(a,b){let max=0,sum=0;for(let i=0;i<a.length;i++){const d=Math.abs(a[i]-b[i]);max=Math.max(max,d);sum+=d*d;}return {max,rms:Math.sqrt(sum/Math.max(1,a.length))};}
const oldPath=path.join(__dirname,'../comparison/KASF-2.0-Evolution-Rev0.9.17-Reader-Workspace-Optimized.html');
const newPath=path.join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html');
const O=load(oldPath),N=load(newPath);let seed=0x1918beef;function rnd(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
const reports=[];
for(const rate of [44100,48000,96000]){
 const fd=.02,o=O.parameters(rate,fd),n=N.parameters(rate,fd),frames=[];
 for(let m=0;m<32;m++){const chs=[];for(let ch=0;ch<2;ch++){const list=[];for(let k=0;k<48;k++)list.push({frequency:10+rnd()*(rate*.499),amplitude:rnd()*.1,phase:rnd()*Math.PI*2});chs.push(list);}frames.push(chs);}
 const start=137,end=12000,step=1,ws=N.createRenderWorkspace();
 for(let ch=0;ch<2;ch++)N.render(frames,ch,n,start,end,step,ws);
 ws.cacheWaves=false;
 for(let m=7;m<=12;m++)for(let ch=0;ch<2;ch++)for(let k=0;k<5;k++){const c=frames[m][ch][k];frames[m][ch][k]={frequency:c.frequency+(k%2?-.37:.51),amplitude:c.amplitude*(1.0001+(k%3)*.0001),phase:c.phase+(k+1)*.000013};}
 for(let ch=0;ch<2;ch++){
  ws.approximate=true;const approx=N.render(frames,ch,n,start,end,step,ws).slice();
  ws.approximate=false;const exact=N.render(frames,ch,n,start,end,step,ws).slice();
  const reference=O.render(frames,ch,o,start,end,step),ed=maxDiff(exact,reference),ad=maxDiff(approx,reference);
  if(ed.max!==0)throw Error(`exact path mismatch rate=${rate} ch=${ch} max=${ed.max}`);
  if(ad.max>1e-9)throw Error(`approx error too high rate=${rate} ch=${ch} max=${ad.max}`);
  reports.push({rate,ch,maxAbsError:ad.max,rmsError:ad.rms,exactMaxDiff:ed.max});
 }
 if(ws.waveCacheBytes>ws.waveCacheLimit)throw Error('cache cap exceeded');
}
console.log(JSON.stringify({cases:reports.length,reports,maxApproxError:Math.max(...reports.map(x=>x.maxAbsError)),exactPathsBitIdentical:true},null,2));
console.log('SHORT APPROX STRESS PASS');
