# Source-group key view experiment

Isolated research only; production tracking and the deployed application remain
unchanged. `one_per_source` temporarily copies a source-group string for every
candidate and owns another copy for each map entry. The experiment borrows
immutable candidate strings through `std::string_view`, retaining the same
ordered map and rank comparisons. Synthesized `time:` fallback keys remain
owned in a vector whose capacity is reserved before retaining any views.

The control source SHA-256 is
`eeefee63d956a1aeaeb88ee0b2f2560876107a9f5f79e3b5aa28616036d7b96c`.
The research source SHA-256 is
`b56a93a22fb9923b6b7dc24d43fd982cb722bd1dafd2e432d802c914f61d326d`.

Full DS9 tracking output over 11,747 reference observations is byte-identical
between the two host builds, SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`.
The report retains both outputs. The focused test compares 10,000 deterministic
cases against the owning-string algorithm, including empty source IDs,
fallback/explicit-key collisions, negative timestamps, embedded null bytes,
long keys, rank ties and shuffled input. Its initial ASAN/UBSAN run passed.

The four `host-*.json` files are an exploratory ABBA run of the unchanged
prefix benchmark's `--tail-two` profile, using a 96 MiB cache and five-second
cutoffs. Final warm calls were 0.4721/0.5980 seconds for control and
0.4324/0.4532 seconds for research. These noisy shared-host measurements are
not an ARM performance claim. Each benchmark separately checks its cached and
cold result bitwise; that check alone does not compare the two builds.

The independent host CLI comparison also passes all 60 causal five-second DS9
prefixes; `prefix-parity.json` retains every cutoff, candidate count and complete
output digest. Both ARM builds succeeded, with matching local/device binary
hashes. Physical PLUTO+ ABBA results are:

| Run | Final warm reconstruction (s) | Whole benchmark (s) | Peak RSS (KiB) |
| --- | ---: | ---: | ---: |
| Control A1 | 17.610358609 | 106.980996684 | 111092 |
| Research B1 | 16.435260205 | 102.324005516 | 111092 |
| Research B2 | 16.459546664 | 102.349018515 | 111120 |
| Control A2 | 17.574374359 | 107.117517626 | 111092 |

Mean final warm time falls from 17.592366484 to 16.447403435 seconds,
a 6.5083% reduction. Each run contains two causal prefixes and both cold and
cached reconstruction, explaining the larger whole-process time. Every run
passes its internal exact cold/cached comparison and ends with 11,747 input
candidates and 64 tracks. The separate complete public CLI outputs from both
ARM builds are byte-identical to each other and to the host outputs, SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`.

This CPU-only standalone benchmark is not a new capture-concurrent application
freshness qualification. Production integration is separate from this research
artifact; no deployed application was changed by these tests.
