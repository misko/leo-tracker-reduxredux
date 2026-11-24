# Bound the remaining track score in the regional veto

The bounded scalar scorer halved dense receiver-1 track evaluations, from **3,050 to 1,490**, while preserving the original decision. It still took **767 ms CPU** after shared geometry setup, versus **699 ms** for the current guarded fused scorer. Medium and the near-missing South offer saved 24 and 13 ms. The valid South far withholding paid a 15 ms overhead and reproduced all 96 original fallback rows. These four saved assays do not support replacing the current fused proof with this adapter. [Frozen protocol](regional-decision-bound-protocol.md) · [Measured receipts](measurements/regional-decision-bound.json.gz)

| Saved offer | Current guarded fused CPU | Prior full scalar receiver-1 precheck CPU | Bounded CPU | Certified / attempted eligible exteriors | Released outcome |
|---|---:|---:|---:|---:|---|
| Dense DS30-0008 | 699.2 ms | 977.3 ms | 767.1 ms | 24 / 24 | No veto |
| Medium DS30-0057 | 180.6 ms | 178.8 ms | 156.5 ms | 24 / 24 | No veto |
| South far missing | 179.7 ms | 213.3 ms | 194.3 ms | 3 / 4, then fallback | Valid veto |
| South near missing | 51.2 ms | 39.2 ms | 37.9 ms | 24 / 24 | No veto |

The three no-veto offers scored the first interior point and projected all 24 eligible exterior points on the original geometry. The positive far-veto offer abandoned the shortcut after its fourth exterior, then ran the released full diagnostic. Both precheck modes paid the original fallback when inconclusive. The near-missing offer remains a known false publication in the original full pipeline. This assay preserves its decision and supplies no new localization or region-accuracy result. [Prior full regional controls](regional-track-scores.md) · [Earlier one-receiver check](bilateral-veto-disproof.md)

Every contrast's Gaussian quadratic and log determinant are nonnegative. Its maximum before those penalties is the original length-dependent peak \(b\). The number visible at the first and last measurements, \(K\), is an upper bound on the number visible across the entire track. With full causal catalogue size \(N\), equal prior weights, and the original outlier term, the real-arithmetic cap is \(\log(1+\exp(b)K/N)\). The prototype rounds this further upward and guards positive accumulation before comparing strictly against the witness. The fixed order uses longest tracks first, then original order on ties. Unsupported cases, unresolved points and ties defer to the current bilateral diagnostic. Full native scoring outside the measured decision observed zero violations of any used track cap or strict certificate on all four fixtures. [Bound and tie handling](regional_decision_bound.py)

| Saved offer | Original catalogue / projected orbits | Median endpoint-visible upper count | Initial normalized receptor-1 sum cap | Interior witness | Largest audited actual exterior score |
|---|---:|---:|---:|---:|---:|
| Dense DS30-0008 | 11,177 / 774 | 453 | 5.3490 | 3.7755 | 3.6877 |
| Medium DS30-0057 | 10,953 / 715 | 517 | 5.2673 | 4.5536 | 4.3399 |
| South far missing | 10,937 / 856 | 494.5 | 4.2175 | 2.6957 | 3.2812 |
| South near missing | 10,937 / 855 | 492 | 4.2175 | 3.6450 | 3.3262 |

The coarse dyadic prior caps were constant across the measured exteriors within each case. They exceeded the interior witness at every initial check. Dense stopped after 24–104 of 122 tracks per exterior, medium after 8–24 of 29, and South near after 8 of 13. South far paid all 13 on every attempted exterior. The cap audit covers the four attempted far exteriors before fallback. The unchanged diagnostic covers all 96 far points. [Per-point caps and native witness values](measurements/regional-decision-bound.json.gz)

| Bounded route CPU before fallback | Shared causal geometry setup, all modes | Actual per-probe projection | Original track calls | Cap tests |
|---|---:|---:|---:|---:|
| Dense | 2,007.2 ms | 488.1 ms | 265.2 ms | 11.0 ms |
| Medium | 452.1 ms | 117.3 ms | 35.0 ms | 2.8 ms |
| South far | 171.7 ms | 4.4 ms | 2.1 ms | 0.3 ms |
| South near | 173.2 ms | 28.1 ms | 7.5 ms | 1.4 ms |

The dense bounded adapter projected all **80,457,300** satellite-time cells before any track-score savings. With that measured projection fixed, even removing every other cost in the bounded route would leave at most **211 ms** against the concurrent 699 ms fused stage. The fused control interleaves projection and mixture evaluation, so its inclusive time cannot also be counted as removable track work. The shared all-location geometry setup remains charged independently in all modes. [Current fused kernel](regional-probe-block.md) · [Separated measurements](measurements/regional-decision-bound.json.gz)

## Unique projection support of the observed prefixes

| Offer | Actually computed cells | Cells required if projection were lazy | Avoidable cells | Of those, attributable to stopping beyond receiver-1 geometry alone |
|---|---:|---:|---:|---:|
| Dense | 80,457,300 | 52,869,618 | 27,587,682 (34.3%) | 17,893,332 |
| Medium | 20,502,625 | 10,399,675 | 10,102,950 (49.3%) | 6,170,450 |
| South far, failed precheck only | 1,078,560 | 1,078,560 | 0 | 0 |
| South near | 5,386,500 | 4,032,180 | 1,354,320 (25.1%) | 1,354,320 |

Each exterior counts the union of every receiver-1 track endpoint needed for the cap and every retained measurement time in its actual stopped prefix. The complete interior witness counts every receiver-1 time. The number of projected orbits stays fixed. Dense had 4,158 original times, 3,657 receiver-1 times, 244 endpoint times and 1,780–3,518 required times per exterior. Medium had 1,147, 927, 58 and 473–877, respectively. Tracks were matched to signed observation counters from existing physical traces. The two South offers share track supports recovered through the released Graph on their exact saved detector packet. No projection or regional scoring was retimed for this census. [Cell inventory and checks](measurements/regional-lazy-geometry.json) · [Counter](regional_lazy_geometry.py)

The current fused kernel is orbit-first. It projects all times and immediately updates every track before moving to the next orbit. It cannot consume the completed-track cap without changing that work order. A lazy projection port would have to keep selected columns across successive track batches. The table grants no fallback, propagation, input or time credit. [Fused loop](regional_probe_block.c)

Each fixture ran one fixed-order stage comparison on the same prepared geometry under the shared Gauss CPU 2 lock, nice 15, I/O priority 7 and one numerical thread. Small deltas remain subject to order and timing variation. An initial import-order error stopped before the proof ran. The corrected invocation ran all four staged cases, with no waveform reads or position fits. Six focused tests passed. The uncompressed receipt SHA-256 is `2a9da8107bf494e6c6d3155ff8c790fb8f236b9cb1d3970b822361ba2b33e1c7`. [Driver](regional_decision_bound_trial.py) · [Tests](../../../tests/pipeline_eval/test_regional_decision_bound.py)
