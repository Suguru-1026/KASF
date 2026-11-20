const fs=require('fs'),vm=require('vm'),path=require('path');
function scripts(file){return [...fs.readFileSync(file,'utf8').matchAll(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);}
function pick(file,needle){const s=scripts(file).find(x=>x.includes(needle));if(!s)throw Error('missing '+needle);return s;}
const file=path.join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html'),html=fs.readFileSync(file,'utf8');
const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,WeakMap,Promise,postMessage:()=>{},setTimeout,clearTimeout,Blob,TextEncoder,TextDecoder,document:{getElementById:()=>({value:'',textContent:'',innerHTML:'',checked:false})}};c.self=c;c.globalThis=c;const x=vm.createContext(c);
for(const src of [...new Set([pick(file,'root.KASF_TVS = api'),pick(file,'root.KASF05_Reader={parameters,componentValue,render')])])vm.runInContext(src,x);
const R=c.KASF05_Reader,rate=96000,fd=.02,o=R.parameters(rate,fd),frames=[];let seed=987654321;
function rnd(){seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return(seed>>>0)/4294967296;}
for(let m=0;m<30;m++){const list=[];for(let k=0;k<128;k++){let f;if(k%5===0)f=rate/2-.01-(k%3);else if(k%5===1)f=rate*.499-rnd()*100;else f=rnd()*rate*.5;list.push({frequency:f,amplitude:.35*rnd(),phase:rnd()*Math.PI*2});}frames.push([list]);}
const ws=R.createRenderWorkspace(),start=0,end=24000;R.render(frames,0,o,start,end,1,ws);ws.cacheWaves=false;ws.approximate=true;
const approx=R.render(frames,0,o,start,end,1,ws).slice();ws.approximate=false;const exact=R.render(frames,0,o,start,end,1,ws).slice();
let max=0,sum=0;for(let i=0;i<exact.length;i++){const d=Math.abs(exact[i]-approx[i]);max=Math.max(max,d);sum+=d*d;}
if(max>2e-12)throw Error('high-frequency approximation error too high: '+max);
console.log(JSON.stringify({sampleRate:rate,amplitudeMax:.35,componentsPerFrame:128,regionSamples:end,maxAbsoluteError:max,rmsError:Math.sqrt(sum/end),exactCacheBytes:ws.waveCacheBytes},null,2));
console.log('SHORT APPROX HIGH-FREQUENCY PASS');
