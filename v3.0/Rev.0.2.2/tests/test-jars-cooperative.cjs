const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const htmlPath=process.argv[2]||path.join(__dirname,'..','KASF-v3.0-Rev0.2.2.html');
const html=fs.readFileSync(htmlPath,'utf8');
const start='/* Rev0.7 JARS - Joint Adaptive Residual Synthesis',end='/* KASF Evolution Rev.0.8';
const a=html.indexOf(start),b=html.indexOf(end,a+start.length);
assert(a>=0&&b>a,'JARS module boundary missing');
const ctx={console,Math,Float64Array,Float32Array,Uint8Array,Int32Array,Array,Map,Set,Number,Object,String,Boolean,Promise};
ctx.self=ctx;ctx.globalThis=ctx;ctx.KASF083_Budget={cap:(v)=>v};
vm.createContext(ctx);
vm.runInContext(html.slice(a,b),ctx);
let discoverySawUnmodified=false;
ctx.KASF05_Reader={
 parameters:()=>({N:8,H:4}),
 render:(frames,ch,o,start,end)=>{
  const out=new Float64Array(end-start);
  for(const c of frames[0][ch])out[0]+=.1;
  return out;
 }
};
ctx.KASF06_Detail={
 chooseFrames:()=>[{m:0,kind:'tail'}],
 spectrumCandidates:()=>[{frequency:100,mag:.01}],
 propose:(residual,frequency)=>({frequency,amplitude:.01,phase:0}),
 contribution:()=>new Float64Array([.1,0,0,0,0,0,0,0]),
 exactGate:()=>({accept:true,gain:1})
};
ctx.KASF07_HPSS={analyze:()=>({dominant:[],frames:[],window:{left:0},hop:256}),at:()=>({percussiveRatio:0,highPercussiveRatio:0,highPercussiveEnergy:0})};
ctx.KASF07_Kalman={discover:(frames)=>{
 discoverySawUnmodified=frames[0][0].length===0;
 return {tracks:1,matched:2,gaps:[{m:0,frequency:110,amplitude:.01,confidence:.9}]};
}};
ctx.KASF05_Loss={spectral:()=>({linear:1,balanced:1}),contour:()=>[0,0]};
(async()=>{
 const frames=[[[]]],channels=[new Float64Array([.1,0,0,0,0,0,0,0])];
 const result=await ctx.KASF07_JARS.run({frames,channels,rate:48000,frameDuration:.01,level:'optimized',mode:'jars',maxComponents:16});
 assert(discoverySawUnmodified,'Kalman cue discovery ran after candidate mutation');
 assert(result.jars&&result.jars.frames===1,'cooperative frame accounting missing');
 assert(result.hpss.accepted===1,'cooperative candidate was not accepted');
 assert(result.kalman.recovered===1&&result.kalman.gapsFound===1,'Kalman cue was not jointly accepted/accounted');
 assert(frames[0][0].length===1,'accepted component was not committed exactly once');
 console.log('PASS: JARS cooperative cue collection / non-mutating discovery / exact-gated commit / Kalman attribution');
 // A second fixture proves each candidate sees the newly committed Reader state.
 const observedBaselines=[];
 ctx.KASF05_Reader={parameters:()=>({N:1024,H:512}),render:(f,ch,o,s,e)=>{
  const out=new Float64Array(e-s);for(const c of f[0][ch])out[0]+=.1;return out;
 }};
 ctx.KASF06_Detail={
  chooseFrames:()=>[{m:0,kind:'attack'}],
  spectrumCandidates:()=>[{frequency:100,mag:2},{frequency:300,mag:1}],
  propose:(residual,frequency)=>({frequency,amplitude:.01,phase:0}),
  contribution:()=>{const d=new Float64Array(1024);d[0]=.1;return d;},
  exactGate:({recon})=>{observedBaselines.push(recon[0]);return {accept:true,gain:1};}
 };
 ctx.KASF07_HPSS={analyze:()=>({dominant:[{frequency:600,energy:.25},{frequency:900,energy:.1}],frames:[],window:{left:0},hop:256}),at:()=>({percussiveRatio:.7,highPercussiveRatio:.7,highPercussiveEnergy:.01})};
 ctx.KASF07_Kalman={discover:()=>({tracks:1,matched:3,gaps:[{m:0,frequency:1200,amplitude:.01,confidence:.9}]})};
 ctx.KASF05_Loss={spectral:()=>({linear:1,balanced:1}),contour:()=>[0,0]};
 const frames2=[[[]]],source2=new Float64Array(1024);source2[0]=.6;
 const result2=await ctx.KASF07_JARS.run({frames:frames2,channels:[source2],rate:48000,frameDuration:.01,level:'optimized',mode:'jars',maxComponents:16});
 assert(result2.hpss.accepted===3,'attack-frame cooperative candidate budget was not used');
 assert.deepStrictEqual(observedBaselines,[0,.1,.2],'candidate gates did not use the latest Reader reconstruction');
 assert(frames2[0][0].length===3,'cooperative additions were not committed sequentially');
 console.log('PASS: JARS re-renders the latest accepted state before each subsequent candidate gate');
})().catch(e=>{console.error(e);process.exitCode=1;});
