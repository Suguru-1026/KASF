const fs=require('fs'),vm=require('vm');
function scripts(file){return [...fs.readFileSync(file,'utf8').matchAll(/<script(?:\s+[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);}
function pick(file,needle){const s=scripts(file).find(x=>x.includes(needle));if(!s)throw Error('missing '+needle);return s;}
function context(){const c={postMessage:()=>{},console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise,performance:{now:()=>0}};c.self=c;c.globalThis=c;return vm.createContext(c);}
const old=require('path').join(__dirname,'../comparison/KASF-2.0-Evolution-Rev0.9.10-Workspace-Optimized.html');
const neu=require('path').join(__dirname,'../KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html');
for(const file of [old,neu]){
 const c=context();
 const unique=[...new Set([pick(file,'root.KASF_TVS = api'),pick(file,'root.KASF05_Reader={parameters,componentValue,render'),pick(file,'root.KASF05_Loss={fft,spectral')])];
 for(const src of unique)vm.runInContext(src,c);
 if(file===old)global.oldC=c;else global.newC=c;
}
const O=global.oldC,N=global.newC;
function bits(a,b){if(a.length!==b.length)return false;const x=new Float64Array(a),y=new Float64Array(b);const u=new BigUint64Array(x.buffer),v=new BigUint64Array(y.buffer);for(let i=0;i<u.length;i++)if(u[i]!==v[i])return false;return true;}
let seed=0x12345678;const rnd=()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>>0)/4294967296;};
for(const len of [512,2048,5000,12000,25000]){
 const x=Float64Array.from({length:len},()=>rnd()*2-1),y=Float64Array.from({length:len},()=>rnd()*2-1),sizes=[256,1024,4096,8192];
 const a=O.KASF05_Loss.spectral(x,y,sizes,44100),prep=N.KASF05_Loss.prepareSpectralReference(x,sizes,44100),b=N.KASF05_Loss.spectral(x,y,sizes,44100,prep);
 for(const k of ['linear','log','balanced'])if(!Object.is(a[k],b[k]))throw Error(`spectral mismatch ${len} ${k}: ${a[k]} ${b[k]}`);
 const m1=O.KASF05_Loss.measure(x,y,44100,1,.2,0,{extreme:true}),m2=N.KASF05_Loss.measure(x,y,44100,1,.2,0,{extreme:true,referenceSpectra:prep,referenceEnvelope:N.KASF05_Loss.prepareEnvelopeReference(x,44100),referenceEnergy:N.KASF05_Loss.referenceEnergy(x)});
 for(const k of ['score','nmse','envShape','envFlux'])if(!Object.is(m1[k],m2[k]))throw Error(`measure mismatch ${len} ${k}: ${m1[k]} ${m2[k]}`);
 if(JSON.stringify(m1.onset)!==JSON.stringify(m2.onset))throw Error('onset mismatch');
 console.log('metrics bit-identical',len);
}
// Reader rendering exact equality
const rate=48000,fd=.02,o=O.KASF05_Reader.parameters(rate,fd),frames=[];
for(let m=0;m<12;m++){const ch=[];for(let c=0;c<2;c++){const a=[];for(let j=0;j<60;j++)a.push({frequency:30+rnd()*18000,amplitude:rnd()*.3,phase:rnd()*Math.PI*2});ch.push(a);}frames.push(ch);}
for(const [start,end,step] of [[0,20000,1],[123,8000,2],[10000,45000,3]]){
 const a=O.KASF05_Reader.render(frames,0,o,start,end,step),b=N.KASF05_Reader.render(frames,0,o,start,end,step);
 if(!bits(a,b))throw Error('Reader output mismatch');console.log('Reader bit-identical',start,end,step);
}
console.log('ALL PASS');
