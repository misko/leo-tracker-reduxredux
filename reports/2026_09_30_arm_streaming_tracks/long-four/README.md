# Four long segments recovered by coarse-seeded curvature but not rolling linear

The exact set difference is references **12, 48, 51, 52**. There are no long
segments recovered only by rolling linear, so these four account for the whole
19/28 versus 23/28 difference. Inputs, gates, reference segmentation, and the
ref-10 exception are unchanged. Durations are server support intervals.

| Ref | Channel/RX | Duration | Matching ARM input | Rolling assigned | Hybrid assigned | Available initial points omitted by rolling |
|---|---|---:|---:|---:|---:|---:|
| 12 | 3/1 | 48.82 s | 69/86 | 64/86 (74.4%) | 69/86 (80.2%) | 5 across first 9.2 s of available matching evidence |
| 48 | 4/1 | 32.29 s | 48/54 | 43/54 (79.6%) | 48/54 (88.9%) | 5 across first 3.1 s |
| 51 | 4/0 | 40.53 s | 59/59 | 45/59 (76.3%) | 59/59 (100%) | 14 across first 8.0 s |
| 52 | 4/1 | 42.74 s | 68/68 | 46/68 (67.6%) | 68/68 (100%) | 22 across first 13.3 s |

All four rolling results pass the in-span purity criterion (100%, 91.5%, 90%,
95.8%, respectively); they fail coverage. Ref 48 needs only one more matching
source to cross the 80% threshold. The missing available sources are all before
the surviving rolling track's first matching source. They are not recovered
in other rolling outputs: union coverage equals the best individual coverage.
The surviving portions reach the final server source in each segment.

Rolling first matching times are 51.447, 202.737, 228.953, and 236.010 s.
The hybrid reaches back to 42.264, 199.590, 220.935, and 222.678 s, respectively.
The rolling implementation extends hypotheses forward and has no retrospective
reassociation step. The hybrid starts from supported coarse segments and traces
both backward and forward. This explains why a later surviving rolling hypothesis
does not automatically reclaim its earlier observations. It does not by itself
isolate why the earlier forward hypotheses failed to survive.

## Direction counterfactual

The same frozen rolling executable and default configuration were run on
time-reversed ARM observations. Candidate identities, CFOs, scores, lanes and
source memberships were unchanged. Support intervals were reversed exactly;
output timestamps and compatibility slopes were restored before strict parsing
and evaluation. No server labels were supplied to the tracker.

| Ref | Reverse-time rolling coverage | Complete under unchanged gates? |
|---|---:|---|
| 12 | 69/86 | Yes |
| 48 | 46/54 | Yes |
| 51 | 4/59 | No |
| 52 | 68/68 | Yes |

This demonstrates direction/initialization sensitivity for three of the four
and rules out interpreting those misses as evidence that local linear fits
cannot represent the curves. Reverse processing is an offline diagnostic, not
a proposed online solution; it does not fix all four and changes other results.
Across the whole reviewed scan it represents 44 segments versus forward 39.

## Active-track capacity counterfactual

A copied-source diagnostic increases only the active hypothesis cap from 24
to 128 per lane. It recovers ref 48 at 48/54 and ref 51 at 59/59, with both
passing purity. Refs 12 and 52 still fail. This isolates bounded hypothesis
competition as a material cause for 48/51. The run emits 921 hypotheses and is
not promoted as a fix. It represents 44 reviewed segments overall.

For refs 12/52 the precise forward loss remains unresolved. The code suppresses
new births when an established hypothesis associates the candidate, and pairs
births only with the immediately preceding group. Those are candidate causes,
along with association/fit decisions; the direction test does not distinguish
them. See [mechanism audit](agent-diagnosis/diagnosis.md).

The useful implementation direction is delayed confirmation with a bounded
observation buffer and retrospective extension, combined with better retention
of distinct tentative tracks. This requires its own correctness tests; no new
tracker implementation or recovery claim is promoted by this audit.

## Evidence

- [Measured-point comparison](comparison.png), [PDF](comparison.pdf); shaded
  regions show the initial portion omitted by rolling.
- `audit.json` binds the binary/input and records per-method match metrics.
- `reverse-observations.tsv`, `reverse-raw.tsv`, `reverse-restored.tsv`, and
  `reverse-evaluation.json` preserve the direction counterfactual.
- Run `../audit_long_four.py` to regenerate this read-only analysis.
