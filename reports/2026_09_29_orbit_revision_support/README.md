# Causal GP revisions provide a feasible orbit-sensitivity experiment

**A 24-hour revision comparison has sufficient coverage to test orbital-input
sensitivity across DS7–DS9. A six-hour comparison provides no changed DS9
elements.** No precision ephemeris or independently verified satellite identity
has been established by this inventory. These archived GP revisions are external
to our RF fit but are not independent orbital truth or a calibrated covariance.

| Dataset | Eligible cases | Latest whole-snapshot median element age | Changed at 6-hour snapshot lag | Present at 24-hour lag | Changed at 24-hour lag |
|---|---:|---:|---:|---:|---:|
| DS7 | 1,346 | 16.12 h | 653 | 1,346 | 1,335 |
| DS8 | 1,311 | 20.63 h | 223 | 1,307 | 1,273 |
| DS9 | 1,326 | 28.46 h | 0 | 1,322 | 794 |
| Total | 3,983 | 20.89 h | 876 | 3,975 | 3,402 |

Cases are conditional track/candidate assignments from the existing nine
eight-scan panels: 72 scans and 1,693 distinct scan/catalogue-number pairs.
Receivers and tracks repeat candidate numbers, so counts are not independent
orbit solutions. The latest snapshots cover all cases; eight cases lack the
candidate in the 24-hour-old snapshot and remain explicit missing support.

## Selection and provenance

The [protocol](PROTOCOL.md) preceded execution. For every scan, select the latest
Space-Track archive snapshot collected strictly before capture start minus
505 seconds. Select comparator snapshots at least 6 and 24 hours earlier than
that snapshot's collection time. These are collection-time lags; they do not
guarantee equally spaced element epochs. Every selected snapshot is causal.

The read-only `TleArchiveReader` verified all 23 selected snapshot digests.
The installed textual parser validated element records without propagation.
Compare the exact two orbital element lines, separately from the epoch field.
Of 876 six-hour changed cases, 838 have changed epochs and 38 have changed bytes
at equal epoch. All 3,402 changed 24-hour cases have changed epochs. Repeated
snapshots of identical elements do not count as new orbit information.

Latest whole-snapshot element ages range from 4.87 to 97.58 hours; the 24-hour
comparator reaches 181.23 hours. No selected candidate has a future epoch.
These ages describe the selected **whole snapshots**, not necessarily the exact
per-object element source of the existing all-archive numerical banks. A future
comparison must verify each bank's baseline element provenance before treating
this latest snapshot as its zero-change control.

The earlier [orbit inventory](../2026_09_27_ds7_wave1/orbits/README.md) documented
GP/3LE feeds and no SupGP/provider-ephemeris port or historical precise bytes.
This follow-up uses that supported GP archive; it does not claim an exhaustive
search of external orbit providers or reinterpret the second feed as independent
precision evidence. It also does not repeat the earlier near-zero first-scan
newest-whole versus all-archive comparison: the new comparison concerns older,
changed element versions across all nine panels.

## Verification and reproduction

Two tests pass for strict causal/lag selection and fractional-day epoch parsing.
The runner verifies the prior residual experiment's input/source hashes. The
summarizer verifies all new bindings, 3,983 unique case keys, causal cutoff and
both lag requirements. `results.json` retains snapshot metadata, element-line
digests, epochs, missing entries, and installed parser/reader source digests;
it does not publish provider element bytes. `summary.json` retains counts and
age ranges. Ruff lint and formatting pass.

The archive requires read access unavailable to the ordinary workspace user;
the existing installed release was used with `sudo -n`. Output redirection runs
as the workspace user. The reader only reads archive paths. No RF, archive write,
provider download, propagation, model fit or geographic scoring occurred.

```bash
.venv/bin/python -m unittest discover -s reports/2026_09_29_orbit_revision_support -p 'test_*.py'
sudo -n timeout 120 /opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python reports/2026_09_29_orbit_revision_support/inventory.py > reports/2026_09_29_orbit_revision_support/results.json
.venv/bin/python reports/2026_09_29_orbit_revision_support/summarize.py
```

## Next experiment

Freeze candidate assignments, fitted position/time and all observation masks.
First reproduce the exact bank baseline from its declared elements; then replace
only orbital elements with the causal older versions. Compare predicted
frequency-shape changes and held residuals without fitting a correction to those
held data. Keep missing and unchanged cases visible. Use the 24-hour comparison
as the broad primary sensitivity assay and six-hour comparison as a separate
limited-support control. Older-versus-newer differences can expose sensitivity
and model dependence, but cannot by themselves justify choosing an orbit by
reference-position error or assigning an orbit-error prior. Reliable short-window
sub-km accuracy remains unresolved.
