# DS9 portable native detector evidence

This directory binds the repository-owned native detector to saved DS9 input.
It contains no device collection and no QNAP write. The portable 80-case cohort
is every saved 2.5 MS/s DS9 dwell in the prior comparison input manifest: 80
dual-receiver 120 ms dwells from 20 scans, always replayed with an explicit
120 ms stride.

`arm-ordinary-control-parity.json` records the published ARM comparison:
ordinary and native-control scientific rows match for all 800 repeated calls
and 2,980 candidate repetitions. All those candidates report the ordinary CFO
lane's `refinement_skipped`; that field is not fractional timing evidence.

`arm-current-regression.json` consumes the current flashed-PLUTO+ replay. The
new ordinary mode matches the published control-qualified ARM ordinary output
for all 80 unique calls. Enabling fractional epoch preserves every ordinary
field. Of 298 retained ordinary candidates, 292 complete the five-cell
fractional epoch calculation and six are explicitly `unbracketed`. At the
deployed baseline fractional-margin gate of 0.025, 286 pass. No unavailable
fractional value is replaced with zero.

The current ARM persistent replay timing is evidence about this saved-input
process, not a per-probe realtime qualification. Ordinary call wall time is
53.798 ms mean and 109.462 ms maximum, with no call over 120 ms. Fractional
call wall time is 106.214 ms mean and 278.057 ms maximum, with 33 of 80 calls
over 120 ms. Queue capacity and average service headroom require a separate
runtime measurement before any deadline claim.

`deployed-fractional-oracle.json` was exported through the public read-only
capture and adaptive-analysis stores. `fractional-server-comparison.json`
matches candidates across the two different acquisition algorithms by circular
integer epoch distance at most two samples and acquired-CFO distance at most
10 kHz. Candidate ranks are local to each algorithm and are not identities.
For the 211 matched 2.5 MS/s candidates, absolute fractional-margin difference
is 0.000669 mean and 0.006003 maximum; all are within 0.01. The five-cell
fractional calculation is therefore close on common hypotheses, but the
detector is not server-parity qualified.

The material gap is upstream candidate coverage. Both algorithms begin with
eight hypotheses per receiver row, 1,280 across the cohort. The frozen native
ordinary coarse gate skips 982 and exposes 298. The deployed server has 880
complete and 400 unavailable fractional candidates. Native matches 210 of 295
server candidates that pass the baseline gate (71.2%). Among the 85 unmatched
server gate candidates, 24 have no native epoch after retention and gating, 38
have the epoch but a different acquired-CFO hypothesis, and 23 have no distinct
native candidate after hypothesis collapse. Changing that gate or acquisition would change the
ordinary detector and is outside an additive fractional refinement.

`server-coverage-comparison.json` evaluates a separate mode that leaves both
ordinary modes intact. It keeps all eight native hypotheses, uses the full
conditioned native CFO path, and then runs fractional confirmation. On host it
produces 1,280 candidates, of which 986 complete fractional confirmation and
524 pass the baseline gate. It matches 252 of 295 deployed baseline-gate
candidates (85.4%), up from 71.2%, at 8.128 ms mean and 11.189 ms maximum host
CPU per dwell. The remaining 43 misses comprise eight absent native epochs, 22
different acquired-CFO hypotheses, and 13 hypotheses without a distinct native
candidate. This mode still uses native proposals rather than the deployed
Python symbolwise acquisition, has low complete-candidate match precision
(25.7%), and remains explicitly unqualified for server parity.

The comparator is now source-owned by
`tools/native_adaptive_ds9_export.py compare-fractional-server`. Earlier detail
rows accidentally repeated the selected pair while their separately accumulated
summary counts remained correct. Schema v4/v2 regenerates every detail row with
unique native and server endpoints and asserts that matched positive counts do
not exceed either positive inventory. The corrected recalls remain 210/295
(71.2%) for additive ordinary and 252/295 (85.4%) for coverage.

`server-reference-comparison.json` evaluates the separately translated FP64
symbolwise kernel using its default zero-center, +/-400 kHz geometry. Its
candidate selection is component-qualified against maintained
`acquire_symbolwise`, but the deployed adaptive wrapper uses per-visit bounded
search geometry and a peer-triggered 22-anchor fallback that this replay does
not yet supply. It matches 111 of 295 server positive candidates (37.6%) and is
explicitly not server-parity qualified. Host call CPU is 165.3 ms mean and
180.6 ms maximum. No full location scan or E3 run uses this mode.

`deployed-server-wrapper-comparison.json` evaluates the new, separate
`deployed-server-wrapper-fractional` research mode. It supplies the actual
per-visit center and observable residual-CFO bounds, retains eight basins with
the deployed 5-sample/10 kHz separation, and repeats a receiver with anchors
2, 16, ..., 296 when its peer passes the 0.025 fractional gate and it does not.
The frozen 80-case host panel has 160 receiver rows and 1,280 candidate ranks:
880 complete and 400 explicitly unbracketed. Direct rank comparison has zero
missing, additional, availability, integer-epoch, gate, or numerical-tolerance
mismatches. All 295 server gate-positive ranks pass natively. The maximum
fractional score delta is 1.263e-13 and the maximum fractional CFO delta is
2.911e-9 Hz. `deployed-server-wrapper-strict-comparison.json` freezes the
acceptance tolerances. The older tolerance matcher reports 38 off-diagonal
pairs because separate coarse basins sometimes converge to identical final
epoch/CFO hypotheses; direct array-index-to-server-rank comparison passes.

The three-case ARM replay in `arm-deployed-wrapper-representative.jsonl`
preserves the same rank/status and numerical result. It also rejects realtime
use of this exact research translation: the two ordinary wrapper calls take
12.85 seconds each and the peer-fallback call takes 23.20 seconds. The scalar
FP64 coarse grid consumes 74.4% of normal search CPU and the FP64 conditioned
scan consumes 19.5%. FFT setup is not the dominant cost. The bounded four-CFO
register accumulation experiment in the isolated FP64 coarse loop preserves
every non-timing call and candidate field exactly across the 80 host cases. It
is not a host optimization: mean call CPU increased from 230.984 to 279.718 ms
and mean coarse CPU increased from 169.469 to 211.269 ms.
`deployed-wrapper-register4-host.json` binds those outputs and the separate ARM
research build. On the same three ARM cases it reduces main-phase wall time
from 49.519 to 39.099 seconds (21.0%). The two normal calls fall from a 12.842
second mean to 10.300 seconds and the fallback call falls from 23.194 to 18.328
seconds. All non-timing call and candidate fields remain exactly equal to the
scalar ARM output; the strict 48-rank server comparison also has zero status,
epoch, gate, or tolerance failures. `arm-deployed-wrapper-register4-performance.json`
binds the build, inputs, scientific differential, and stage timing. The roughly
26.6% coarse-stage reduction explains the gain; conditioned FP64 still costs
about 2.5 seconds per call. The production capability therefore remains
unqualified and the full 80-case ARM replay was not run.

Recreate the host comparison with:

```text
.venv/bin/python tools/native_adaptive_ds9_export.py compare-deployed-wrapper \
  --report reports/2026_09_30_native_adaptive_deployment/ds9
```

The research replay accepts the 12-column schedules under
`portable80/deployed-wrapper-schedules`; the four appended numerical columns
are receiver-0 center, receiver-1 center, residual minimum, and residual
maximum. These inputs are explicit per visit and remain owned by the detector
context. `arm-deployed-wrapper-representative.tsv` binds the three measured ARM
cases to the existing read-only saved-IQ fixture paths.

The fractional implementation caches identical `(integer epoch, acquired CFO
bits)` work within a receiver row. The 80 cases contain 81 duplicate candidates,
reducing the possible six-GLRT sequence from 1,788 to 1,302 calls. Host output
was scientifically identical before and after this cache; mean host CPU time
was 85.3% of the uncached run. `arm-cache-regression.json` consumes the cached
ARM rerun: all 80 scientific outputs are identical, mean wall time falls from
106.214 to 90.071 ms, the maximum falls from 278.057 to 242.173 ms, and calls
over 120 ms fall from 33 to 22. This remains saved-input process timing rather
than a realtime qualification.

`portable80-manifest.json` verifies every template and CI16 archive member by
SHA-256. `portable80/schedules` contains eleven bounded persistent-context TSV
schedules covering the 80 cases once. The locally materialized CI16 members
under `portable80/fixtures` are ignored by Git; the manifest binds the existing
source archive and every member needed to recreate them.

The location session `scan-fw-3cfdaa6d75762cad` is a different capture from the
portable 80-case cohort. `location-source-inventory` records its complete public
capture metadata: 2,215 dual-receiver visits at 7.5 MS/s and 120 ms, totaling
15,948,000,000 uncompressed bytes. The complete raw session is available in the
read-only store but was not duplicated into this bounded report.
`location-selection` contains only saved visits 276, 830, 1384, and 1938. Its
manifest explicitly marks `complete_scan: false`; the source batch's complete
flag means only that this four-row lag-discovery selection was saved completely.
The four-call host comparison matches five of eight deployed baseline-gate
candidates under the same epoch/acquired-CFO rule and is not a full-scan claim.

`location-templates` freezes the public Qin lower-edge templates at 7.5 MS/s.
The exact SHA-256 is
`8e9f4eaca4a999a3f74b4a74cda5d0b01193941bf5e74a4623ec5a984f8a6f0a`;
the 17-symbol-roll control SHA-256 is
`84b2ae110c3d03f882d1aa410c11eeb2b64a7618b14d491d453f330ee6c70484`.
