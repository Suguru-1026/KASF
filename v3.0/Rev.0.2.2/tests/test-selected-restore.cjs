const {performance}=require('perf_hooks');
const make=()=>Array.from({length:5},(_,m)=>Array.from({length:2},(_,ch)=>Array.from({length:512},(_,i)=>({frequency:80+i*2+m,amplitude:.01+i*.00001,phase:(i%100)/100,tag:`${m}-${ch}-${i}`}))));
const clone=frames=>frames.map((channels,m)=>({m,channels:channels.map(a=>a.map(c=>({...c})))}));
const fullRestore=(frames,snap)=>{for(const e of snap)frames[e.m]=e.channels.map(a=>a.map(c=>({...c})));};
const selectedRestore=(frames,snap,selected)=>{const first=snap[0]?.m??0;for(let ch=0;ch<selected.length;ch++)for(const item of selected[ch]){const f=snap[item.m-first];if(f&&f.m===item.m&&f.channels[ch]&&f.channels[ch][item.index]!==undefined)frames[item.m][ch][item.index]=f.channels[ch][item.index];}};
const selected=Array.from({length:2},(_,ch)=>Array.from({length:18},(_,i)=>({m:1+(i%3),index:ch*7+i*13})));
const original=make(),snap=clone(original);
let full=make(),partial=make();
for(let ch=0;ch<2;ch++)for(const x of selected[ch]){full[x.m][ch][x.index]={changed:1};partial[x.m][ch][x.index]={changed:1};}
fullRestore(full,snap);selectedRestore(partial,snap,selected);
const norm=x=>JSON.stringify(x);
if(norm(full)!==norm(partial))throw Error('selected restore differs from full restore');
console.log('PASS selected restore exact equivalence');
const loops=1000;full=make();partial=make();let t=performance.now();for(let i=0;i<loops;i++)fullRestore(full,snap);const tf=performance.now()-t;t=performance.now();for(let i=0;i<loops;i++)selectedRestore(partial,snap,selected);const ts=performance.now()-t;
console.log({loops,fullRestoreMs:+tf.toFixed(2),selectedRestoreMs:+ts.toFixed(2),speedup:+(tf/ts).toFixed(2),restoredSlotsPerLoop:selected.reduce((a,x)=>a+x.length,0),totalSlotsPerLoop:5*2*512});
