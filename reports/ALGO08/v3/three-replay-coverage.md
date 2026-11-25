# How much of the first 65 recordings' accuracy gap do the three measured corrections close?

The frequency correction improved both calibration arms on all three saved recordings. Only DS30-0218 crossed the 1 km threshold. DS30-0019 and DS30-0274 already had fitted errors under 1 km. Substituting just those three measured corrections into the 65-pair panel changes fitted coverage from **27 to 28 of 65**, against **38 of 65** for ALGO08v3. The other 62 candidate outcomes keep their original measured values. The full-field results continue to use the original workers. [Replays on 0019](held-shrink-0019-ram.md) · [0274](held-shrink-0274.md) · [0218](masked-cfo-0218-prospective.md)

| First 65, all attempts in the denominator | ALGO08v3 | Original candidate | Candidate with three measured replacements |
|---|---:|---:|---:|
| Fixes, both calibrations | 59 | 61 | 61 |
| Within 1 km, fixed zero | 34 | 27 | 28 |
| Within 1 km, fitted | 38 | 27 | 28 |
| Largest count below the ALGO08v3 cumulative curve, fixed zero | 0 | 12 | 12 |
| Largest count below the ALGO08v3 cumulative curve, fitted | 0 | 12 | 11 |

The same three changes also affect the runtime target for a hypothetical chooser. Give it advance knowledge of every position and time, allow it to run either build on each recording at zero selection cost, and require it to match or exceed ALGO08v3’s fix count and cumulative coverage at every finite threshold in both arms. Using the original outcomes, the fastest such selection achieves **1.402×** summed wall speedup. Substituting the three corrected positions while still charging the original candidate times raises the ceiling to **1.425×**. The extra cost of a raw-to-exit corrected worker has not been measured on these three recordings. No gain is assumed on the other 62. [Per-arm counts, exact timing certificates and source digests](measurements/three-replay-coverage.json.gz)

If every candidate clock could additionally shrink by the same fraction, the smallest cut needed to reach 2× overall drops from **50.88% to 46.07%**. At both boundaries the selected route also passes the paired-median timing gate. This calculation prices a uniform compute improvement under fixed outcomes and perfect selection. Operational fixes that improve additional recordings can change the requirement. All 65 recordings came from the same roof. [Clock-scaling method](ds30-routing-clock-fraction.md) · [Replay substitution and verification](three_replay_coverage.py)

Reproduce the calculation with the sealed 65-pair combined export on Gauss.

```sh
python -m reports.ALGO08.v3.three_replay_coverage /tmp/leo-transfer65-3fb2f299/rows-with-relocations.jsonl
```
