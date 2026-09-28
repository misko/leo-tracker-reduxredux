# DS7 direction F: CFO panel preparation

The four-recording panel is frozen in `panel.json`. It spans 2.5, 5, 7.5, and
10 MS/s, strong/weak/failed cached tracking support, and both receivers where
tracking evidence exists. Selection used a strict allowlist projection from the
public tracking-status API for all 88 plan sessions. No raw IQ was read. An
earlier one-process, CPU-1, BLAS-1 numerical reconstruction attempt hit its
120-second cap and produced no inventory; that failed approach remains recorded
in `provenance.json`.

`tools/ds7_cfo_panel.py` rejects observer-site, position, pose, truth, and
reference-score fields recursively. It binds every row to the reference-free
budget plan, selects all four rates with strong/weak/failed coverage, and
requires both receivers. Its matched-epoch validator requires every comparator
to retain an explicit supported, rejected, failed, or inapplicable row at each
baseline epoch.

`handoff-0001.json` append-only binds the frozen 10 MS/s panel member
`scan-fw-a40658642d9ade6a` to the second baseline track export without changing
the original panel receipt. That export provides track-level time, frequency,
receiver, visit, RF lane, channel, and training-mask data. It does not yet make
a same-epoch waveform comparison possible.

Known-pilot applicability requires an actually detected pilot together with
acquisition-qualified frame timing and CFO alias support at each epoch. Sample
rate alone is insufficient. The remaining input contract needs immutable
native-window/sample identities, absolute support times, receiver/visit/probe
identity, detected edge and frame epoch, the acquisition-bound CFO basin,
support/rejection diagnostics, a frozen held-window mapping, and either bounded
read-only samples or equivalently source-bound matched-pilot matrices. The
profile estimators do not acquire timing, choose an OFDM alias, or prove carrier
continuity. No full-band processing claim is valid for the 2.5--10 MHz DS7
recordings.

The panel's 7.5 MS/s member is classified as failed support because its cached
tracking product was unavailable. This does not say that the raw recording
failed, is unreadable, or lacks signal content.
