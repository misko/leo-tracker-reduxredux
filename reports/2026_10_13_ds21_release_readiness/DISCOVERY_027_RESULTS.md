# DS21-027 baseline discovery

The next previously unprocessed development recording completed the original fitted-c discovery stage: **100 points, 300 fits, 298 stationary**, in **378.986940 seconds**. No held observations or reference coordinates entered this stage. This is initialization evidence, not a final position estimate or a sub-0.5 km result.

The original selection chose these three centers, in east/north kilometers relative to the configured prior:

1. (-131.25, -31.25)
2. (-87.5, -87.5)
3. (-75, -75)

Their selected satellite union contains 38 candidates. The two nonstationary point fits remain in the outcome inventory; they were not retried. The stage completed in its first numbered slice under the unchanged 480-second internal / 495-second TERM / 500-second KILL limits.

This baseline uses the original initialization protocol and search rule, not the DS21-039 all-first selector intervention. The original whole-block partition remains fixed, with held blocks 0, 4 and 6 under seed 20261012. No reference-derived starts or candidate choices were introduced.

The five remaining initialization stages and final A/B/C comparisons are still outstanding for DS21-027. Ten development recordings have complete initialization; DS21-027 is an additional partially completed case. The 20 locked evaluation recordings remain untouched. Full DS21 performance and the 0.5 km acceptance requirement remain unverified.

Local namespace: `reports/2026_10_13_ds21_release_readiness/local/initialization-v1/DS21-027/discovery`.

| Receipt | SHA-256 |
| --- | --- |
| Discovery protocol | `6f2bfa101f51d55a8f48a447f8fb83d9e1f56b460bd2950f2212e0c5007049de` |
| Discovery terminal | `7668d744d7b36071511daf1a600296dab77a0f294baa794fd194daee85f624a1` |
