const fs=require('fs'),vm=require('vm'),path=require('path');
const file=path.join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html');
const html=fs.readFileSync(file,'utf8'),match=html.match(/<script id="embedded-worker-a"[^>]*>([\s\S]*?)<\/script>/i);
if(!match)throw Error('embedded Worker A missing');
const c={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,performance:{now:()=>0},setTimeout,clearTimeout,postMessage:()=>{},Blob,TextEncoder,TextDecoder,document:{getElementById:()=>({value:'',textContent:'',innerHTML:'',checked:false})}};c.self=c;c.globalThis=c;const ctx=vm.createContext(c);vm.runInContext(match[1],ctx,{timeout:30000});
const rate=12000,channels=[Float64Array.from({length:9000},(_,i)=>.1*Math.sin(2*Math.PI*440*i/rate))];
const frames=Array.from({length:32},(_,m)=>[Array.from({length:16},(_,k)=>({frequency:200+k*300+m,amplitude:.01+k*.001,phase:.1*k}))]);
function check(fd){const o=c.KASF05_Reader.parameters(rate,fd),center=Math.round(.12*rate/o.H),ids=[];for(let m=Math.max(0,center-2);m<=Math.min(frames.length-1,center+2);m++)ids.push(m);return c.KASF05_Hybrid.makeContext(frames,channels,{time:.12,classes:{transient:.2,decay:.1}},ids,rate,fd,'optimized');}
const short=check(.02),long=check(.12);
if(!short.approximationEnabled)throw Error('short local window did not enable approximation');
if(long.approximationEnabled)throw Error('long local window unexpectedly enabled approximation');
console.log(JSON.stringify({short:{samples:short.approximationSamples,frames:short.ids.length,enabled:short.approximationEnabled},long:{samples:long.approximationSamples,frames:long.ids.length,enabled:long.approximationEnabled}},null,2));
console.log('SHORT APPROX RANGE GATE PASS');
