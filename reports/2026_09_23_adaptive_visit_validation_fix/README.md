# Sparse adaptive visit UI validation

`scan-fw-55ba04c1ea8e1d02` returned valid schema-7 detail over HTTP 200, but the
web UI raised `Adaptive visit evidence is invalid`. The 15 MS/s recording has
2,230 started visits and 1,621 retained visits. Visit 11 is not retained, while
visit 12 is retained. Retained IQ duty is 64.84%; this fix does not fill gaps or
change the recording's qualification state.

The backend `AdaptiveHopSessionDetailV1._bound` explicitly allows sparse retained
indices for history schemas 3 and 7. The frontend permitted them only for schema
3, incorrectly imposing the legacy retained-prefix rule on schema 7. The fix
aligns that predicate with the backend while retaining count, ordering, counter,
timing, and target-mask validation.

Commit `11d3367bb913daf618f890b281fe83152deed9b5` is merged to remote main and was
activated for the API/UI on September 23 at 14:32 UTC. The analysis workers remain
on `fb152566148e662dc22d7948607fd65998f033a9`; the intervening runtime change is
frontend-only, so their analysis implementation is current. Prior commits between
that worker release and this fix added rollout reports only.

Validation: 27 adaptive-panel tests passed, including sparse schema-7 acceptance,
retained-count mismatch rejection, and legacy-prefix rejection. The web test/build
deployment gates and immutable release qualification passed, including 16 Chromium
tests. Replaying the exact saved API response through the previous validator fails;
the corrected validator accepts all 2,230 visit records.

After deployment, normal production Scanner navigation opened this exact scan.
The browser rendered visit 11 as `Incomplete; not retained` and visit 12 as
`120 ms retained`; the original error was absent and there were no JavaScript
page errors. No IQ, source manifest, firmware, or capture configuration was changed.

- [Browser verification](scan55-fixed-browser.json)
- [Browser screenshot](scan55-fixed-browser.png)
- [Deployment receipt](deployment.json)
- [Release qualification](release-qualification.json)
