#!/usr/bin/env node
'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const html = fs.readFileSync(process.argv[2] || path.join(__dirname, '../KASF-v3.0-Rev0.2.2.html'), 'utf8');
const match = html.match(/<script id="embedded-worker-a" type="text\/plain">([\s\S]*?)<\/script>/);
if (!match) throw new Error('embedded Worker A not found');
const source = match[1];
const start = source.indexOf('const KASF0920_TemporalGuards = (() => {');
const endMarker = '})();';
const end = source.indexOf(endMarker, start);
if (start < 0 || end < 0) throw new Error('Temporal guard module not found');
const code = source.slice(start, end + endMarker.length) + '\nthis.__guards = KASF0920_TemporalGuards;';
const sandbox = { Math, Number, Uint8Array, Map, Set };
vm.runInNewContext(code, sandbox, { timeout: 5000 });
const g = sandbox.__guards;
const assert = (v, m) => { if (!v) throw new Error(m); };
const near = (a, b, e=1e-8) => Math.abs(a-b) <= e;

// Stable sustained track: large phase innovation is limited in conservative mode.
let stats = {checked:0, detected:0, limited:0, attackBypassed:0, unstableBypassed:0, clippedRadians:0, maxClippedRadians:0};
let v = g.limitPhaseInnovation(1.4, 'conservative', true, false, stats);
assert(near(v, 0.62), 'conservative phase limit');
assert(stats.detected === 1 && stats.limited === 1, 'phase limit counters');
// Attack and unstable tracks are never clipped.
assert(near(g.limitPhaseInnovation(1.4, 'balanced', true, true, stats), 1.4), 'attack bypass');
assert(near(g.limitPhaseInnovation(1.4, 'balanced', false, false, stats), 1.4), 'unstable bypass');
assert(near(g.limitPhaseInnovation(1.4, 'off', true, false, stats), 1.4), 'off bypass');
assert(g.attackMask(4, [{time: 0.1}], 0).every(v => v === 0), 'invalid hop produces safe empty attack mask');

// Construct a three-frame, stable sinusoid with a one-frame phase spike.
const TAU = Math.PI*2, hop = 0.01, f = 440;
const p0 = 0.2, advance = TAU*f*hop, spike = 1.35;
const frames = [
  [[{frequency:f, amplitude:.20, phase:p0}]],
  [[{frequency:f, amplitude:.205, phase:p0+advance+spike}]],
  [[{frequency:f, amplitude:.202, phase:p0+2*advance}]]
];
const phaseStats = g.applyPhaseSpikeGuard(frames, 1, 48000, .02, [], 'conservative');
assert(phaseStats.spikesDetected === 1 && phaseStats.corrected === 1, 'single-frame phase spike detected/corrected');
const wrap = x => Math.atan2(Math.sin(x), Math.cos(x));
const residual = wrap(frames[1][0][0].phase - (frames[0][0][0].phase + advance));
assert(Math.abs(residual) < spike*.30, 'phase spike substantially reduced');

// Attack protection prevents spike correction.
const attackFrames = [
  [[{frequency:f, amplitude:.20, phase:p0}]],
  [[{frequency:f, amplitude:.205, phase:p0+advance+spike}]],
  [[{frequency:f, amplitude:.202, phase:p0+2*advance}]]
];
const protectedStats = g.applyPhaseSpikeGuard(attackFrames, 1, 48000, .02, [{time:.01, confidence:.9, reliable:true}], 'balanced');
assert(protectedStats.corrected === 0 && protectedStats.attackProtected > 0, 'attack-adjacent phase preserved');

// Weak isolated, non-harmonic component is softly attenuated, never deleted.
const noiseFrames = Array.from({length:5}, (_,i) => [
  i === 2
    ? [{frequency:440, amplitude:.40, phase:i*.1}, {frequency:733.2, amplitude:.012, phase:0.2}]
    : [{frequency:440, amplitude:.40, phase:i*.1}]
]);
const noiseStats = g.applyMusicalNoiseGuard(noiseFrames, 1, .02, [], 'conservative');
assert(noiseStats.candidates === 1 && noiseStats.attenuated === 1, 'isolated weak component detected');
assert(noiseFrames[2][0].length === 2 && noiseFrames[2][0][1].amplitude < .012, 'component softly attenuated, not deleted');
const conservativeAttenuation = 1 - noiseFrames[2][0][1].amplitude / .012;
assert(conservativeAttenuation <= .18 + 1e-9, 'conservative attenuation cap');
const balancedNoiseFrames = Array.from({length:5}, (_,i) => [
  i === 2
    ? [{frequency:440, amplitude:.40, phase:i*.1}, {frequency:733.2, amplitude:.012, phase:0.2}]
    : [{frequency:440, amplitude:.40, phase:i*.1}]
]);
g.applyMusicalNoiseGuard(balancedNoiseFrames, 1, .02, [], 'balanced');
const balancedAttenuation = 1 - balancedNoiseFrames[2][0][1].amplitude / .012;
assert(balancedAttenuation > conservativeAttenuation && balancedAttenuation <= .30 + 1e-9, 'balanced attenuation bounded and stronger');

// Persistent and harmonic components are protected in the middle of a longer segment.
const protectedNoiseFrames = Array.from({length:5}, (_,i) => [[
  {frequency:220, amplitude:.45, phase:i*.1},
  {frequency:440, amplitude:.015, phase:i*.1+.2},
  {frequency:1600, amplitude:.40, phase:i*.1+.3},
  {frequency:733.2, amplitude:.015, phase:i*.1+.25}
]]);
const before440 = protectedNoiseFrames[2][0][1].amplitude;
const before733 = protectedNoiseFrames[2][0][3].amplitude;
const safeStats = g.applyMusicalNoiseGuard(protectedNoiseFrames, 1, .02, [], 'conservative');
assert(near(protectedNoiseFrames[2][0][1].amplitude, before440), 'harmonic component preserved');
assert(near(protectedNoiseFrames[2][0][3].amplitude, before733), 'persistent component preserved');
assert(safeStats.harmonicProtected > 0 && safeStats.persistentProtected > 0, 'harmonic/persistence protection counters');

// Attack protection: the isolated weak component at the attack frame is unchanged.
const attackOnlyFrames = Array.from({length:9}, (_,i) => [
  i === 4
    ? [{frequency:1600, amplitude:.40, phase:i*.1}, {frequency:2600, amplitude:.014, phase:.4}]
    : [{frequency:1600, amplitude:.40, phase:i*.1}]
]);
const before2600 = attackOnlyFrames[4][0][1].amplitude;
const attackOnlyStats = g.applyMusicalNoiseGuard(attackOnlyFrames, 1, .02, [{time:.04, confidence:.9, reliable:true}], 'conservative');
assert(near(attackOnlyFrames[4][0][1].amplitude, before2600), 'attack-adjacent component preserved');
assert(attackOnlyStats.attackProtected > 0, 'attack protection counter');

// OFF mode is a strict no-op.
const offFrames = [[[{frequency:700, amplitude:.01, phase:0}]], [[{frequency:700, amplitude:.01, phase:.1}]]];
const offBefore = offFrames[0][0][0].amplitude;
const offStats = g.applyMusicalNoiseGuard(offFrames, 1, .02, [], 'off');
assert(offFrames[0][0][0].amplitude === offBefore && offStats.attenuated === 0, 'MNG off no-op');
console.log('PASS: phase jump clamp, isolated phase spike correction, attack bypass, invalid-hop safety, musical-noise persistence guard, harmonic protection, attenuation caps, no-delete behavior, and OFF no-op');
