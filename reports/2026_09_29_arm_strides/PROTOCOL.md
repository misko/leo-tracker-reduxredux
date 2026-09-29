# ARM stride promotion and saved-IQ comparison

This experiment adds a separately identified, opt-in native GLRT analysis
component. It does not replace the deployed adaptive fractional detector or
the live native-presence capture worker. Existing contracts, capture behavior,
and the dense default remain unchanged. No RF collection is authorized.

The measured engine must be built from maintained `src/leo` component sources,
not from a report runner or another repository. Its public RAM API processes
dual-receiver CI16 input. The saved-file command is an adapter to that API.
Supported rates are 2.5, 5, 7.5 and 10 MS/s; valid dwell lengths are 120, 240
and 360 ms. Every probe is 20 ms. Strides are 10 (default), 20 and 120 ms.

For each receiver, the schedule is all starts `k * stride` for which the full
20 ms probe lies within the supplied dwell. Expected dual-RX window counts:

| Dwell | 10 ms stride | 20 ms stride | 120 ms stride |
|---|---:|---:|---:|
| 120 ms | 22 | 12 | 2 |
| 240 ms | 46 | 24 | 4 |
| 360 ms | 70 | 36 | 6 |

Sparse schedules must actually omit unscheduled searches. The 20 ms anchor
windows use independent proposals; dense odd windows reuse neighboring anchor
proposals with the existing fallback. Shared starts should therefore yield
identical scientific candidate values, but this is a hypothesis to test, not
an assumed result. Candidate rank and probe index are distinct from time.

## Comparison panel and timing

Freeze a deterministic whole-dwell selection from the existing DS7 materialized
CI16 corpus before examining new outputs. Use 32 primary-rate dwells and eight
dwells per other rate, selected with seed 20260929. The same 56 saved dwells,
templates, and executable must run at each stride on PLUTO+ 192.168.1.15 CPU0.
Record input, source, template, binary, configuration and output hashes.
No report-side implementation substitutes for the packaged runtime.

Use at least two serial measurement rounds with a seeded mode ordering to
reduce order bias. Report detector CPU time including preparation, proposals,
and search. Label setup, file I/O, serialization, and capture exclusions
explicitly. No host measurement may populate an ARM timing column. Report
mean, median, P95 and maximum, with counts below the 120 ms budget; a mean below
that budget does not establish capture headroom or a real-time guarantee.

Compare raw positive candidates against both the same native dense run and the
frozen original GLRT reference where available. Report two denominators:
same scheduled windows, and the full dense inventory (which includes omitted
windows). Match individually within the same receiver and absolute probe start,
using the frozen two-sample/8 kHz matching tolerances and margin >=0.025.
Do not substitute positive-window counts or track counts for candidate recall.

Replay the unchanged production overlap-selection policy on the new outputs.
Compare selected observation values separately from provenance identifiers.
If an adapter supplies zero fractional offsets for integer ARM estimates, label
that replay explicitly as a tracking-policy diagnostic; do not publish those
objects as deployed fractional-detector products or claim production parity.

The DS7 panel has 120 ms saved dwells. Synthetic inputs may qualify geometry,
failure handling, bounded memory and shared-window parity at 240/360 ms, but
must not be described as real longer-dwell scientific validation. Any new PGO
build must train its own compatible profiles and disclose training overlap;
the historical Wave8 profiles must not silently be reused after extraction.
