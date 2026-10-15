# C059 native full-prior coverage qualification

This zero-localization-fit experiment checks a complete, training-defined source inventory before a proposed coverage search. The original C059 six 25 km disks exclude the configured station; the nearest planar clearance is 112.281 km. Both recently strict continuations remained inside those original disks. Their distant positions therefore cannot establish a global evidence-ranking failure. The configured station is unconfirmed, and no reference coordinates enter the new candidate or seed construction.

The genuine existing A059 coverage authority binds all sixteen accepted original full-view coarse fits at the Cartesian grid `{−150,−50,50,150}²` km. Their candidate banks and the original native bank form a fixed **75-satellite union**. Every coarse location is retained, regardless of score. Local radius `100√2` km around each coarse center covers the original 250 km prior's bounding square; the original global 250 km disk remains active. This is an explicit bank and search-domain intervention, not a nested improvement to the old likelihood or a half-only pipeline.

Two native calibration families are qualified separately:

- Original no-clock native C: project each complete source calibration function into the existing native family and report the residual. Preserve source satellite timing, extend added satellites at the source mean shift, and use the source-derived receiver alias integers.
- Complete native common-clock C: transport the same source function exactly using the original clock nodes and precision. Use the same receiver alias integers and orbital timing as the projected arm. Preserve native branches, waveform weights, sample rate and group calibration.

Eight original-native controls supplement the sixteen coarse functions: all six original raw C-all endpoints, including their failed stationarity labels, and **both** independently strict original-chart/diagonal-chart C059 continuations. Those eight retain their original 25 km disks. Exact native-to-union transport applies no second receiver lift; the clock arm adds an exactly zero clock tail and checks objective, NLL, physical/group gradient and posterior closure. None of these old outcomes is automatically accepted on the changed bank.

The exact numerical inventory is **128 objectives, 80 explicit orbit predictions, 16 calibration projections and zero localization optimizer calls**:

| Unit group | Units | Per-unit objectives | Explicit orbits | Projections |
|---|---:|---:|---:|---:|
| Four coarse source functions | 4 | 24 | 16 | 4 |
| Four original-native controls | 2 | 16 | 8 | 0 |

Each unit has a 120-second internal bound plus independent external TERM/KILL at 135/140 seconds. The finite six-unit wave uses at most four single-threaded workers and a 300-second whole-wave limit. Exclusive directory creation claims each unit before preparation; failed or orphan units cannot be retried. Each source uses only the predeclared original fitter timing margin, at most 1.1 ns in physical satellite timing, with unchanged geography/calibration and stable second initialization. No unrecorded projection or new receiver lift is permitted for native controls.

Source **7402d119f**, with 459 recursively bound local source/test files, was frozen in `ds22-c059-coverage-qualification-v1` before preparation. Eleven component tests passed, including actual synthetic native union transport/zero-clock closure, altered source-domain rejection, complete counts and durable exclusive failure claims. The source authorities are `model-a-ds22-coverage-handoff-v1/DS22-059` and `ds22-missing-c-precondition-control-v1/DS22-059`, all beneath `/srv/bulk/leo-research-ds21-ds22/2026_10_14`.

No localization search, reference join, held or locked evaluation is authorized by this qualification. A later proposed 24-source-per-family search would require these results to pass and a separately frozen fit inventory, budget and selection policy. Scores from different calibration families or different banks must not be ranked as one model's candidates.
