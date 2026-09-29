# Fused proposal and final-reuse search prototype

This research prototype runs the full-resolution lag-1/3/5/power FP32 proposal
and the preferred fine-frame-2, raw-conditioned, radius-2 final-reuse search in
one process. Both workspaces persist across all 22 receiver/windows. Proposal
centres pass through a narrow in-memory API and are clipped, deduplicated and
sorted before search. `--top=3` is optional; top four is the default.

The proposal already reads interleaved CI16 directly. Search retains its one
CI16-to-FP64-complex conversion for each 20 ms receiver/window because its
existing scientific kernels consume that representation. Per-row
`fused_total` is proposal CPU plus search CPU; template loading and workspace
planning happen before these timers. This is still saved-IQ research timing,
not concurrent capture or production integration.

Run `python3 build.py`. Host and sanitizer component tests execute during the
build. The ARM binaries are cross-built only; physical ARM execution is owned
by the serialized benchmark operator.

`../../.venv/bin/python test_parity.py --all-rates` compares the fused binary
against the original proposal and search executables. `parity.json` records
exact candidate parity for eight saved dwells: two template edges at each of
2.5, 5, 7.5 and 10 MS/s, with 22 windows and 176 candidate objects per dwell.

The ARM link combines two previously separate FFTW users under LTO. GCC 7
reports a cross-translation-unit FFTW declaration warning, so that target also
uses `-fno-strict-aliasing`; the warning and exact command remain in the build
receipt. Physical-ARM parity remains required before using its fused timing.

## V2 measured fused interval

V1's `fused_total` was an arithmetic stage sum and is retained unchanged in
`builds/`. V2 is isolated in `sources-v2/` and `builds-v2/`. Its single outer
`CLOCK_PROCESS_CPUTIME_ID` interval begins immediately before the proposal and
ends after region construction, CI16-to-FP64-complex conversion and search.
It reports the old arithmetic value as `stage_sum` and the outer measurement as
`fused_total`. Input/template reads, workspace and FFT planning, and JSON
printing remain outside the measured interval. Build with `python3 build_v2.py`
and validate with `../../.venv/bin/python test_parity_v2.py --all-rates`.

## V3 omit-power proposal

V3 is isolated in `sources-v3/` and `builds-v3/`. It defines
`LEO_PROPOSAL_OMIT_POWER=1`, so the proposal folds, correlates and ranks only
lag-1, lag-3 and lag-5 features. Build receipts and the matrix record that
feature mask. Search and the V2 outer timing boundary are unchanged.
`../../.venv/bin/python test_parity_v3.py --all-rates` compares it with the
standalone feature-ablation proposal invoked with `--omit=power`, followed by
the original preferred final-reuse search. `parity-v3.json` records exact
candidate parity across both template edges at all four rates. Physical ARM
execution remains required before reporting the fused V3 runtime.

## V4 omit-power plus NEON conditioned moments

V4 is isolated in `sources-v4/` and `builds-v4/`. It keeps V3's three-feature
proposal and outer timer, and replaces only `full_search.c` with the qualified
NEON conditioned-moments V2 implementation. The build defines
`LEO_NEON_CONDITIONED_MOMENTS=1` and runs its moment-accuracy component test.
`test_parity_v4.py --all-rates` compares candidates against the standalone
omit-power proposal feeding the standalone NEON-moments V2 search.

The fused ARM link exposes an FFTW LTO declaration mismatch: proposal code sees
`fftwf_complex` as a two-float array while a C-complex search translation unit
sees `_Complex float`. V1-V3 added `-fno-strict-aliasing`, which may explain
part of their measured search regression. V4 compiles the proposal object
without LTO and does not disable strict aliasing globally; GCC 7 still reports
the mismatch against linked FFTW code, so only `lto-type-mismatch` is downgraded
from an error. The exact warning is preserved in the ARM build receipt. ARM
candidate parity is required before accepting timing.
