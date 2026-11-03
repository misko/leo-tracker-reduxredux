# Same-scan receiver/RF correction lacks overlapping donor support

**The declared contemporaneous receiver correction cannot be evaluated on this
exported corpus: zero of 3,983 target cases have three usable other-candidate
donors on the same receiver and RF.** This is a coverage result, not evidence
that receiver drift is absent or that a well-supported correction would fail.

The input comprises all nine early/middle/late eight-scan panels from DS7–DS9:
72 scans, 4,328 original bank tracks, and 3,983 conditional residual cases retained
by the preceding donor export. Candidate identities are model assignments,
not independently verified satellite labels. No production or geographic fit
changed, and no new RF was collected.

| Dataset | Eligible target cases | At least 3 other numbers on same scan/RX/RF, ignoring time | At least 1 usable overlapping number | At least 3 usable overlapping numbers |
|---|---:|---:|---:|---:|
| DS7 | 1,346 | 1,336 | 258 | 0 |
| DS8 | 1,311 | 1,279 | 228 | 0 |
| DS9 | 1,326 | 1,310 | 205 | 0 |
| Total | 3,983 | 3,925 | 691 | 0 |

There are usually other candidate numbers somewhere in the scan, but their
training intervals do not overlap enough. Only 33 targets have two usable
same-receiver donor numbers. Pooling the whole scan would conceal this timing
limitation and impose an additional assumption of drift stability across it.
This experiment deliberately leaves that assumption unmade.

## Method and controls

The [protocol](PROTOCOL.md) was written before execution. Exclude the target's
candidate number and track from every donor. Require the same scan and exact RF,
at least 50% overlap of the target training span, and at least five donor training
points spanning five seconds inside that span. Fit donor slopes on those points;
median within each candidate number, then across at least three numbers. Thus
multiple tracks assigned to the same number cannot inflate donor diversity.

Every prediction uses the target's training-only residual/time means. Evaluate
median absolute residual on inherited held points; masks are interleaved, so
this is interpolation validation, not causal forecasting. Times are relative
to recording start, as explicitly checked in `tools/ds7_export_baseline.py`.
Residual Hz are normalized to the existing 11.2-GHz convention. Conditional
residuals inherit the previously fitted location, recording time and association.

An opposite-receiver control qualifies on only two targets, both in the same
DS7 early scan. One held median improves from 572.16 to 564.62 Hz; the other
worsens from 151.57 to 218.78 Hz. No target supports both controls. These two
dependent cases cannot establish an RX comparison or a general correction.

The target's own training slope improves held median residual on 3,053/3,983
cases (DS7 1,016; DS8 1,019; DS9 1,018), with median paired reduction 22.04 Hz.
This confirms predictable within-track structure. It does **not** identify
receiver drift: a target's slope can absorb geometry, orbit, association and
other errors. Earlier [geographic slope experiments](../2026_09_28_pooled_receiver_slope/README.md)
and [differential drift allocations](../2026_09_29_drift_geographic/README.md)
already show that better residual prediction need not improve position.

Unsupported corrections fall back to zero slope and remain in all-population
accounting. The resulting zero overall change for the same-RX arm is a fallback
identity, not a tested null effect. No threshold was relaxed after seeing this.

## Verification and next decision

Three synthetic tests cover exact slope recovery, candidate exclusion and minimum
diversity, held-data isolation/order invariance, receiver/RF separation and temporal
support. Lint and formatting pass. The bounded numerical replay completed in
about one second. `results.json` binds all nine input files, the protocol and
estimator source by SHA-256; `audit.py` verifies those bindings and independently
reconstructs support counts in `coverage.json`. `summary.json` retains all nine
panel summaries and empty matched comparisons explicitly. The coverage audit
was added after seeing zero support; it changes no estimator or threshold.

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m unittest discover -s reports/2026_09_29_contemporaneous_residual -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 90 .venv/bin/python reports/2026_09_29_contemporaneous_residual/study.py
OPENBLAS_NUM_THREADS=1 .venv/bin/python reports/2026_09_29_contemporaneous_residual/audit.py
```

Do not launch a geographic refit with this unsupported correction. The next
useful corpus check is whether cross-band observations provide contemporaneous
candidate diversity, with RF dependence made explicit. A common receiver-clock
model across RF would be a new physical assumption to test, not permission to
silently pool lanes. If those observations are also sparse, independent clock
or orbit evidence is more useful than adding free per-track slopes. Reliable
short-window sub-km accuracy remains unresolved.
