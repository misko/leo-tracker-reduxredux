# PLUTO+ residual predicate comparison

CPU-only tests ran on `192.168.1.15` with firmware
`v0.59-plutoplus-spf-dual-rx-counter-fix`. Both frozen ARM variants passed the
tracking and chosen-point component tests. Four serial full DS9 runs used order
control, candidate, candidate, control, each under a 90-second watchdog.

| Variant | First wall time | Second wall time | Peak RSS range |
| --- | ---: | ---: | ---: |
| Control | 27.832 s | 27.760 s | 22,696–22,764 KiB |
| Predicate pushdown | 26.210 s | 26.215 s | 22,700–22,748 KiB |

The candidate reduces elapsed time by 5.6–5.8% in the two pairs. All four
serialized outputs are byte-identical and contain the same 64 tracks. The
fixture and executable hashes, exact measurements, and qualification scope are
in [receipt.json](receipt.json); logs and outputs are retained beside it.

These are whole-process serial tracking times, including input/output. They do
not measure two-worker publication, detector execution, live capture contention,
or regional location search. No new RF collection occurred. The results support
the small exact production optimization, without closing any remaining
five-second freshness or full-pipeline parity gate.
