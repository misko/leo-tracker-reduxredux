# Portable compact v5 with a held Doppler gate

All three stock replays of the original incomplete queries reached conservative recovery and were still inside that stage at the 188-second profiling cap. The workers received the exact native and causal-history packets from the original results. They used the original mounted solver bytes and one CPU each. The reported active-stage durations are approximate time remaining after entry, because the workers were interrupted before the stage could report a final elapsed time. [Original portable results](../../portable-v5/README.md) · [Instrumented traces](original-profiles.json) · [Packet bindings and replay commands](profile-reproduction.json)

| Historical profiling query | Native preparation (s) | Initial selection (s) | Time after entering conservative recovery (s, approx.) | Profiling result |
|---|---:|---:|---:|---|
| Site 1, omitted | 13.3 | 53.8 | 121 | Timeout |
| Site 2, containing | 13.6 | 33.1 | 141 | Timeout |
| Site 2, omitted | 14.5 | 69.0 | 104 | Timeout |

The candidate tests native Doppler from time blocks excluded from track fitting. It runs the same compact-v5 search for a supported offer, retains the stable paired exclusion/refit result, and omits the exhaustive search over rejected track prefixes and suffixes. The candidate can lose tracks stock would salvage. A denial from the held-Doppler gate withholds coordinates before the fit. A wall timeout remains a separate outcome. Both calibration arms share the admission decision and paired downstream evidence. The offer packet preserves its identifier for digest comparisons. The solver reads only its center and width, and site coordinates used for scoring stay in the supervisor. [Protocol](PROTOCOL.md) · [Candidate source lock](source-lock.json)

On an additional exact replay of Site 2's containing packet, the original paired exclusion/refit completed in 11.4 s. Exhaustive `salvage` was still running roughly 99 s later at the 150-second diagnostic cap. The measured input digest and original scientific source remain bound. [Detailed conservative trace](conservative-detail.json)

## Bounded recovery with the first held gate

The first gate recovered the historical containing query that twice timed out. It also falsely published at both historical omitted offers. The four fresh containing arm runs returned, but the two fresh omitted queries produced a timeout and a frozen orbit-interpolation error. Those outcomes provide no evidence of successful omitted-region rejection. The attempted shuffle withheld after yielding only one eligible development arc. [Candidate and original scores](scores.json) · [Pre-score prediction lock](prediction-lock.json) · [Original retries](../../portable-v5/retry.json)

| Query | Original portable | Candidate status (s) | Published error in km, zero / fitted | Conditional RF RMS on retained tracks in Hz, zero / fitted |
|---|---|---|---:|---:|
| Historical Site 1, containing | Returned at 86 s | Returned (83.1) | 0.527 / 0.483 | 23.746 / 23.744 |
| Historical Site 2, containing | Timed out at 180 s and 195 s | Returned (157.9) | 0.728 / 0.594 | 24.045 / 24.051 |
| Historical Site 1, omitted | Timed out at 180 s and 195 s | False publication (132.5) | 93.728 / 93.728 | 23.422 / 23.421 |
| Historical Site 2, omitted | Timed out at 180 s | False publication (174.9) | 89.786 / 89.786 | 25.006 / 25.006 |
| Fresh Site 1, containing | — | Returned (107.1) | 0.549 / 0.395 | 23.912 / 23.908 |
| Fresh Site 2, containing | — | Returned (67.4) | 0.441 / 0.123 | 23.882 / 23.877 |
| Fresh Site 1, omitted | — | Timed out (195.1) | — | — |
| Fresh Site 2, omitted | — | Interpolation error (43.7) | — | — |
| Fresh shuffle | — | Withheld (24.5) | — | — |

The wrong Site 1 solution had lower in-fit RF RMS than every correct solution. The retained paired fit dropped about 4,400 of 5,300 winning detector observations before salvage would begin at each wrong offer. The held gate saw six and seven supporting satellite families at the wrong offers, versus 12 on each containing query. On the same matched native packets, fitted calibration reduced conditional RF RMS by less than 0.006 Hz in three cases and increased it by 0.006 Hz at historical Site 2. Position error fell at all four containing offers by 0.043–0.318 km. [Historical predictions](historical.jsonl.gz) · [Fresh predictions](fresh.jsonl.gz)

The [outside-region comparison](halo/README.md) and [held-arc coverage follow-up](coverage/README.md) use their own source locks and fresh draws.

The bounded solver removed the observed conservative-recovery bottleneck for the historical containing case. Geographic publication remained unresolved. The outside comparison rejected every omitted offer and yielded zero containing fixes. Counting a supermajority of physical time–frequency arcs retained the containing fixes and rejected both historical omissions, but still produced a false position on its independent omitted offer.

## Reproduce

Use the authenticated frozen numerical sources, portable archive mount and original detector and TLE receipts from the [portable adapter](../../portable-v5/README.md). The commands below place new results in a separate directory. An explicit `--fresh-seed-hex` from the sealed `labels.json` reproduces the fresh candidates and offers. Without a seed override, the inference command draws new sites after it binds the sources. Stock profiling uses the archived source environment described in the older report. The retained profile wrapper has the exact measured import layout. The live wrapper reorders imports for Ruff. [Measured profiling wrapper](as-profiled-worker.py.txt)

```sh
mkdir -p /tmp/portable-gate-report
.venv/bin/python -m tools.pipeline_eval.qualification.portable_gate_trials \
  --phase infer --scratch /tmp/portable-gate-infer --report /tmp/portable-gate-report
.venv/bin/python -m tools.pipeline_eval.qualification.portable_gate_trials \
  --phase score --scratch /tmp/portable-gate-infer --report /tmp/portable-gate-report
```

For stock profiling, use `--phase profile` and the original portable report's `LEO_PORTABLE_V5_SOURCE_SNAPSHOT` setting. The live profiler includes the paired refit and salvage substage spans. The original replay commands in `profile-reproduction.json` mount the measured top-level profiler instead.
