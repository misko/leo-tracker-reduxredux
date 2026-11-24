# The all-visit shorter timing scout loses weak physical factors

On the signed first DS30-0016 member, two timing lags and four carrier rows cut guarded 12 ms native CPU by **27.55%** and authenticated acquisition by **27.40–28.22 ms elapsed**. Both antennas still ran on every admitted visit. The shorter path lost **12 of 34 short-primary factors**, including 9 of 20 on antenna 0 and 3 of 14 on antenna 1. All 11 full-anchor factors matched byte for byte. The result failed the prespecified per-antenna gate before North. [Frozen protocol](all-visit-timing-protocol.md) · [Exact paired member receipt](measurements/all-visit-timing-0016.json.gz)

## How the shortlist was frozen

The earlier archive contains original and candidate factors, both antennas, and repeated native clocks. The screen requires a counterpart for at least five sixths of original qualifying short factors in every development case and antenna, and all 12 signed synthetic plants. Among passing arms it takes the lowest dense scheduled short native CPU. It uses no geographic results or observation owners. [Prior native receipt](measurements/short-timing-lags.json.gz)

| Prior scout | Dense short native CPU | Dense antenna 0 / 1 matched | Weak antenna 0 / 1 matched |
|---|---:|---:|---:|
| One lag, four rows | 53.679 ms | 20/25, 8/10 | 5/6, 5/6 |
| Two lags, four rows | 56.236 ms | 21/25, 9/10 | 6/6, 5/6 |
| Two lags, eight rows | 60.874 ms | 21/25, 9/10 | 6/6, 5/6 |

The native build kept the actual 12 ms short ABI and original guarded verifier and relinked its ordinary guarded short reference byte for byte. It only evaluates lag 28 and 44 and sends four timing rows to signed carrier search. Original signed eligibility, full-rate refinement, independent confirmation and fractional verifier still determine accepted factors. Its PGO training uses deterministic pilots on both edges and carrier signs. The final object matched the ordinary guarded reference exactly on 12 positive and four noise plants. The real full-anchor and signed cancellation library and fixed-epoch CFO retry bundle came from the original pack. [Build and verified binding](all_visit_timing.py)

## One original physical member through detection seal

The matched prefix has 64 issued visits, 58 admitted stereo visits and six excluded visits. Both routes used precisely the same case, capture clocks, ordered original IQ digests, and full/short schedule. They paid for **16 full and 100 short native antenna calls** each. The scopes verified the original 78,554,951 compressed bytes and complete 102.4 MB decoded member from the existing tmpfs recording. The original IQ and index pages were resident before and after. All four child processes observed zero input blocks and zero major faults. [Prior guarded acquisition](continued-cfo-first-0016.md)

| Order | Short native CPU, ordinary / shorter | Authenticated acquisition elapsed, ordinary / shorter | Process elapsed through selected detection seal, ordinary / shorter |
|---|---:|---:|---:|
| Ordinary then shorter | 94.21 / 67.97 ms | 288.00 / 259.78 ms | 652.74 / 622.67 ms |
| Shorter then ordinary | 92.05 / 66.96 ms | 284.52 / 257.12 ms | 645.19 / 614.51 ms |

Each lost factor became an empty lane. There were **zero new or replaced factors**, and every retained factor was byte-identical before CFO. Original exact-minus-control margins on lost factors ranged from **0.04774 to 0.13187**, with seven above 0.1. All nine antenna 0 misses had negative signed CFO. The other antenna lost three positive carriers. The five-sixths gate required at least 17 of 20 and 12 of 14 original short factors. Both antennas retained only 11. Both held-cycle decisions were `unfiltered`, leaving **33 instead of 45 factors**. The shorter run paid six instead of seven original 20 ms CFO attempts. Both made six edits. Tail CPU moved from **5.38 to 4.24 ms** and **4.94 to 4.22 ms**, with the missing attempt on visit 61, antenna 0. Faster acquisition includes work avoided by missing detections. The experiment provides no position, RF fit or numerical publication comparison for the alternate scout.

## Opt-in and reproduction

The combined raw CLI accepts `--short-timing-scout PACK --short-timing-scout-sha256 SHA256` only with its original `--anchored-cfo-pack`. It verifies the binary and source-bound `short-scout.json` and includes the alternative short object in the canonical detector recipe. The original region, causal archive, periodic full anchors and held-history selector retain their ordinary bindings. No North replay was launched after the physical gate failed. [Combined entry](combined_raw_research.py)

The existing local pack is `/dev/shm/leo-v3-all-visit-timing-pack01`. Its manifest digest is `e7f5584a3f2ea8033a05e4c238b0ba44db7b231dd879fe024644d84a89f2cc5e` and its `short.so` digest is `ad2bd4b05516b195c68d23a790e007cbea33734c55d1015903196568f6140228`. From the isolated checkout, use the installed release interpreter under the normal shared Gauss lock on CPU2 as the original fixture owner. Set `PYTHONPATH` to the checkout, `reports/ALGO08/v3`, release `src` and release root. Run `python -Bm reports.ALGO08.v3.all_visit_timing build PACK RELEASE_ASSETS`, then `python -Bm reports.ALGO08.v3.all_visit_timing_trial OUTPUT PACK PACK_DIGEST`. The uncompressed receipt SHA-256 is `b1a7727ffb35afe91e6e6886b2ea35654f7a4eea4847a0ce85adf9cc22c9b333`. Twelve focused and adjacent tests passed. [Tests](../../../tests/pipeline_eval/test_all_visit_timing.py)
