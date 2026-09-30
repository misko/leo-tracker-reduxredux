# Additional carriers do not strengthen the current identity lead

The existing wider-carrier experiment uses 709 qualified 10 MS/s entries from
DS7–DS10, of which 121 have conditional satellite labels. It compares the same
early six-symbol region using four core carriers versus 26 common non-pilot
carriers. The matched identity effect weakens when widened; there is no
supported cross-session positive comparison in this subset.

## Matched comparisons

Only one of eight scope/tier combinations has matched positive and negative
controls. It contains **14 same-candidate pairs, all within a session**. The
other seven combinations abstain. On those matched pairs, the real-sign
excess falls from **.1036 for four carriers to .0224 for 26 carriers**. The
wide phase and relative-phase excesses are .0245 and −.0053. None survives
the trajectory-preserving maximum-statistic reference; all four ranks are 1.

This is a carrier-support comparison on the same 10 MS/s subset, **not a
controlled experiment comparing recordings acquired at different sample rates**.
It neither establishes a satellite signature nor shows that more bandwidth
cannot reveal message bits. Wider features can dilute a narrow effect, combine
different signal components or increase estimation variance.

## Are the extra carriers simply worse?

The prior reliability benchmark infers the known state from symbols 194–257
and measures disagreement on separate symbols 258–289. Training weights use
the first reserved frame; held results use the second. The present audit
independently sums the stored per-carrier errors and decision counts:

| Edge | Held frames | Four core carriers | Additional 22 carriers |
|---|---:|---:|---:|
| Lower | 375 | 18.079% | 18.250% |
| Upper | 131 | 19.191% | 19.254% |

These reproduce the original aggregate values exactly. The saved recording-group
resampling intervals for additional-minus-core disagreement include zero.
Thus a broad degradation of the additional carriers on this **late known-waveform
benchmark** is not supported. This does not measure early-header error rate:
selection requires a recovered T-state, and its reference is inferred rather
than independently known payload bits.

## Lower-edge profile transfer

The complementary profile test uses 24 common carriers across DS9-middle and
DS10-F010-v1085/v1150/v1162, with discovery/held splits of 22/23, 22/23, 9/9
and 10/11 frames. Its 32 comparisons include same-excerpt and cross-excerpt
profiles, complex and real-valued metrics. None passes its family correction.
The audit verifies the correction arithmetic and preserves every comparison
in the ledger without rerunning an already unsuccessful profile search.

Profile transfer concerns averages across frames; it is distinct from the
recent positive simultaneous RX0/RX1 variation in early symbols 3/4/6. Real
same-frame structure can coexist with poorly estimated or visit-dependent
average profiles. Neither observation currently maps to a firmware field.

## Firmware interpretation

The audited role settings and threshold-mask tables still supply no verified
RF address/field placement. Their counts must not be used to label these
carrier groups. The evidence ranks comparable late known-waveform recovery
above a broad outer-carrier failure explanation, while leaving early coding,
interleaving, scrambling and field semantics unresolved.

```sh
uv run --no-project --with numpy python reports/2026_09_29_firmware_cluster_reaudit/bandwidth_receipt_audit.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with matplotlib python reports/2026_09_29_firmware_cluster_reaudit/association_ledger.py
```

Ignored `local/bandwidth-receipt-audit.json` records independently recomputed
disagreement rates, complete source experiments and hashes. The ledger adds
42 entries, reaching 430. All 23 component tests pass. No new RF or source
fixture changes were made. The full investigation remains active.
