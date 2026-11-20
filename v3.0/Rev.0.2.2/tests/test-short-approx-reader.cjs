const fs=require('fs'),vm=require('vm'),path=require('path');
function scripts(file){return [...fs.readFileSync(file,'utf8').matchAll(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);}
function pick(file,needle){const s=scripts(file).find(x=>x.includes(needle));if(!s)throw Error('missing '+needle+' in '+file);return s;}
function context(){const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,WeakMap,performance:{now:()=>0},postMessage:()=>{},setTimeout,clearTimeout,Blob,TextEncoder,TextDecoder,document:{getElementById:()=>({value:'',textContent:'',innerHTML:'',checked:false})}};c.self=c;c.globalThis=c;return vm.createContext(c);}
function load(file){const c=context();for(const src of [...new Set([pick(file,'root.KASF_TVS = api'),pick(file,'root.KASF05_Reader={parameters,componentValue,render')])])vm.runInContext(src,c);return c.KASF05_Reader;}
function maxDiff(a,b){let max=0,sum=0;for(let i=0;i<a.length;i++){const d=Math.abs(a[i]-b[i]);max=Math.max(max,d);sum+=d*d;}return {max,rms:Math.sqrt(sum/Math.max(1,a.length))};}
const base=path.join(__dirname,'../comparison/KASF-2.0-Evolution-Rev0.9.17-Reader-Workspace-Optimized.html');
const next=path.join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html');
const O=load(base),N=load(next);
let seed=0x83a192e1;function rnd(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
const rate=48000,fd=0.02,o=O.parameters(rate,fd),n=N.parameters(rate,fd),frames=[];
for(let m=0;m<9;m++){const channels=[];for(let ch=0;ch<2;ch++){const list=[];for(let k=0;k<128;k++)list.push({frequency:20+rnd()*23900,amplitude:rnd()*.12,phase:rnd()*Math.PI*2});channels.push(list);}frames.push(channels);}
const ws=N.createRenderWorkspace(),start=0,end=19000,step=1;
// Prime the exact baseline: all unchanged component objects are remembered.
for(let ch=0;ch<2;ch++)N.render(frames,ch,n,start,end,step,ws);
ws.captureBaseline=false;ws.cacheWaves=false;
// Replace a few components, as VP does. Their new identities must be the only
// components sent through the approximate oscillator path.
for(const [m,ch,k,df,da,dp] of [[2,0,4,1.371,1.0002,.00017],[3,0,8,-2.711,.9997,-.00029],[4,1,3,.811,1.0001,.00011],[5,1,7,-1.213,.9998,-.00009]]){
 const c=frames[m][ch][k];frames[m][ch][k]={frequency:c.frequency+df,amplitude:c.amplitude*da,phase:c.phase+dp};
}
const results=[];
for(let ch=0;ch<2;ch++){
 ws.approximate=true;const approx=N.render(frames,ch,n,start,end,step,ws).slice();
 ws.approximate=false;const exact=N.render(frames,ch,n,start,end,step,ws).slice();
 const legacy=O.render(frames,ch,o,start,end,step);
 const d=maxDiff(approx,legacy),dx=maxDiff(exact,legacy);
 if(dx.max!==0)throw Error(`exact workspace changed legacy result ch=${ch}: ${dx.max}`);
 if(d.max>1e-9)throw Error(`approx error exceeds 1e-9 ch=${ch}: ${d.max}`);
 results.push({channel:ch,maxAbsError:d.max,rmsError:d.rms,exactMaxDiff:dx.max});
}
// The maximum short approximation range is intentionally hard-limited by the
// Hybrid caller (<=5 frames, <=0.4 s, <=24,000 samples); render itself remains opt-in.
if(ws.waveCacheBytes>ws.waveCacheLimit)throw Error('wave cache memory cap exceeded');
console.log(JSON.stringify({test:'short approximate re-synthesis',results,cacheBytes:ws.waveCacheBytes,cacheLimit:ws.waveCacheLimit,reseedInterval:256},null,2));
console.log('SHORT APPROX READER PASS');
