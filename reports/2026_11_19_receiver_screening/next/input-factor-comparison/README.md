# Accuracy with capture-era and ordinary GLRT factors

On these four recordings, compact five-refresh v5 stayed within 10% of original no-repair v5 in both calibration arms when it used the original capture-era factors. Changing to complete ordinary GLRT factors with the same five-refresh computation left one of four within 10% in each arm. The original capture-era factors are the accuracy reference for this panel. A separate same-implementation comparison reproduced the factor-source change on every recording. [Scored pairs](scores.csv) · [Both-arm chart](plots/index.html) · [Checked comparison](comparison.json)

## Geographic error

Positive deltas indicate greater error. The fixed-factor delta subtracts original full no-repair v5 from capture-era compact secant. The changed-factor delta subtracts capture-era compact secant from ordinary compact secant. Within 10% means error at most 1.10 times the comparator on that recording. [Exact scores](scores.csv)

| Recording | Arm | Original v5 (km) | Capture-era secant (km) | Ordinary secant (km) | Fixed-factor change (m) | Changed-factor change (km) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 | `c = 0` | 1.278 | 1.260 | 0.218 | −18.4 | −1.042 |
| DS26-0036 | Fitted `c` | 1.208 | 1.196 | 0.180 | −11.8 | −1.016 |
| DS26-0237 | `c = 0` | 0.362 | 0.353 | 0.889 | −8.8 | +0.536 |
| DS26-0237 | Fitted `c` | 0.271 | 0.262 | 0.814 | −9.5 | +0.552 |
| DS29-0082 | `c = 0` | 0.567 | 0.568 | 2.789 | +1.2 | +2.221 |
| DS29-0082 | Fitted `c` | 0.517 | 0.516 | 2.654 | −1.4 | +2.138 |
| DS29-0174 | `c = 0` | 0.885 | 0.886 | 1.161 | +0.5 | +0.275 |
| DS29-0174 | Fitted `c` | 0.917 | 0.918 | 1.224 | +0.7 | +0.306 |

The four positions come from one physical roof. Switching factor sources improved both arms on DS26-0036 and increased error in both arms on the other three. The largest fixed-factor geographic change was 18.4 m, versus a largest increase of 2.221 km across factor sources. Changing factors includes every difference in detector candidate output and its effect on observation preparation and association.

## Doppler fit

The original no-repair receipt reports its own residual RMS. Both compact versions report conditional Doppler RMS. Changing the factor source changes the observations and fitted track associations underlying the conditional metric. Ordinary conditional RMS rose in every pair, including DS26-0036 where the position improved. [RF columns](scores.csv)

| Recording | Original residual RMS, zero / fitted (Hz) | Capture-era conditional RMS, zero / fitted (Hz) | Ordinary conditional RMS, zero / fitted (Hz) |
| --- | ---: | ---: | ---: |
| DS26-0036 | 106.989 / 91.934 | 74.760 / 74.682 | 102.253 / 102.289 |
| DS26-0237 | 102.892 / 91.742 | 80.670 / 80.608 | 110.246 / 110.117 |
| DS29-0082 | 97.004 / 96.684 | 97.003 / 96.684 | 106.672 / 106.588 |
| DS29-0174 | 123.187 / 105.213 | 95.404 / 95.518 | 113.047 / 113.147 |

## Native factor differences

Session, raw input authority, capture exclusions, first clock anchor, last sample counter and each visit/RX/sample-counter row matched. Both sets used adaptive 20 ms probes at 10 MS/s. The recorded pass flag agreed with the same `fractional_margin >= 0.025` predicate on every candidate. The capture-era headers bind original fast-scan run and analysis identities and omit a detector binary digest. The ordinary headers bind the replay run, new analysis identity and prepared-fractional library digest. The optimized ordinary library is independently byte-equivalent to the stock ordinary native science after lineage normalization. The comparison changes a complete detector result. It cannot identify the effect of one detector submodule or threshold. [Headers, exact counts and native digests](comparison.json) · [Whole ordinary parity](../complete-four/comparison.json)

| Recording | Probe rows / excluded visits | Total candidates, capture → ordinary | Gate passes, capture → ordinary | Prepared observations, capture → ordinary | Prepared tracks, capture → ordinary |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0036 | 13,530 / 4 | 59,973 → 59,622 | 9,488 → 15,073 | 3,395 → 3,610 | 94 → 104 |
| DS26-0237 | 13,532 / 2 | 60,306 → 60,148 | 10,243 → 15,823 | 3,740 → 3,927 | 103 → 107 |
| DS29-0082 | 9,736 / 1,904 | 42,162 → 43,375 | 4,582 → 7,962 | 1,868 → 2,044 | 61 → 70 |
| DS29-0174 | 13,408 / 70 | 61,128 → 63,485 | 12,428 → 19,262 | 4,018 → 4,134 | 128 → 127 |

In each recording, the complete candidate list differed in all but one RX probe row. The ordinary detector returned more empty probe rows and more candidates passing the fractional margin gate in each recording. The prepared observation counts rose by 116–215 points. These measurements describe inputs and their preparation, with no single-factor ablation among the changes.

## Checked controls and new bridge

The original no-repair executions matched the frozen reference coordinates and residual RMS. The compact drivers share the recorded source hashes for the five-refresh v5 core, bounded secant solver and compiled projector. The checked requests retain the original truth-free policy, 25 km tile, visible-sky screen center, track configuration and paired calibration arms. All 38, 47, 45 and 45 causal TLE snapshots, respectively, passed membership and byte checks, including each current and preceding catalogue. The request changes are limited to native lineage and filesystem bindings. [Original execution bindings](../../secant-full/original-v5-inputs.json) · [Full comparison ledger](comparison.json)

- **DS26-0036 and DS29-0082.** An archived ordinary factor-only run of the original secant implementation produced exactly the same paired coordinates and RMS as the full optimized ordinary replay. Both secant versions recorded five initial refreshes in each of three branches. [Direct lifetime and secant receipt](../direct-lifetime/receipt.json)
- **DS29-0174.** The same direct lifetime worker used in the ordinary replay had already run on complete capture-era factors, matching the capture-era five-refresh secant in both arms exactly. [Capture-era lifetime receipt](../../integration/cavity-lifetime/direct-lock.json)
- **DS26-0237.** Two new factor-only executions used the same released 78-source standalone code, binaries and CPU 18 under a 512 MiB zero-swap cgroup. Capture-era and ordinary runs took 78.462 and 83.191 s, used 77.762 and 82.691 cgroup CPU-seconds, and peaked at 315,334,656 and 361,033,728 bytes. Each reproduced its corresponding sealed coordinates and conditional RMS exactly. Both met the predeclared 165 second limit. [Prospective protocol](PROTOCOL.md) · [Service results](bridge-positions.jsonl.gz) · [Bridge lock](bridge-lock.json)

The first score export stopped because the resolved capture-era request relocates its output directory. The checked exporter now permits this recorded filesystem difference. The sealed predictions and service runs were unchanged.
