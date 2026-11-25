# Optional signed owner residuals for DS30-0218

The installed `tools.algo08_position.selected_packet` calls
`leo.presentation.localization_v3.prepare_packet` at the selected state.
For each of `c0` and `fitted_c`, the packet already contains an ordered
row keyed by native observation ID, NORAD and role. The selected route
has no phase-mixture families. Each owner has one published role and one
residual. Conditional rows come from the history-position likelihood
with its fitted nuisance. Predictive rows use the event prediction's
raw signed residual before per-track bias profiling. The observer
exports each row's measured CFO, residual and prediction in Hz. The
sign is measured minus prediction under the original lifts. The
published prediction is the Graph CFO minus that signed residual.

At 01:29 UTC on 2026-11-25 the field ledger had no attempt for either
DS30-0218 role and no pair file. We selected the observer at commit
`116a98cc26915e095d11d79de6cc0facc0c13171` for both saved roles
before either field result was available. Use the original plans,
isolation, shared lease and caps with the two entries below.
The [registered position and timing comparisons](masked-cfo-0218-readiness.md)
use their original verified-output boundary. Report the full observed
exit times as well.

```bash
python -IB reports/ALGO08/v3/masked_cfo_0218_owner_residuals.py ordinary CELL --pin PLAN_SHA --lease-fd FD
python -IB reports/ALGO08/v3/masked_cfo_0218_owner_residuals.py corrected CELL --pin PLAN_SHA --lease-fd FD
```

The timed solve retains one reference to the existing rows when
`selected_packet` returns. The wrapper returns the original packet.
The ordinary arm never derives CFO features. The original solver,
figures, publication verifier, receipt and in-worker clock boundary are
unchanged. The measured primary interval includes the small tap wrapper
and reference assignment if enabled. After the original observation
witness closes, the optional entry checks the installed presentation
source, verifies each ordered owner triple against the publication
witness and writes a separate `owner-residuals.json`. A genuine withhold
has an empty row map. The artifact binds the original native bytes and
selected terminal, plan and receipt hashes. Its digest and separate
post-closure measurement go in `owner-residual-export-clock.json`.
Whole-process timing also includes the optional setup/export and its
clock file. Preserve that elapsed time as observed and report the
primary verified-output interval separately. A missing export receipt
leaves the supplemental comparison unverified.

The two exports describe their respective selected states. A later
fixed-state arithmetic check can add the signed CFO edit to the
ordinary residual only for the same native observation with the
ordinary predictor, assignment and alias lift held fixed. The
difference between the two selected-state residuals alone includes any
changes in the fitted geometry or nuisance. No residual comparison,
survey join or numerical replay has been run for DS30-0218.
