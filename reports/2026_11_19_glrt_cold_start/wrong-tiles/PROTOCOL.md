# One supplied tile when the correct region is omitted

Test DS29-0082, DS29-0174 and DS29-0247. Match each native recording to one Transfer124 query labeled `missing` using the frozen observation SHA-256, causal catalogue SHA-256 and catalogue timestamp. Verify the byte hashes of the associated Transfer124 observation and catalogue and their original public query. Use the first tile in the declared query order. The selection uses the condition, query order and these identities. Site references are reserved for the scorer after prediction sealing.

| Recording | Frozen missing query | First offered tile |
|---|---|---|
| DS29-0082 | `5ef5a3952fe49b857695d9f63d085ed0` | `0571fcd7dd3f4d1680e933b9c84faacf` |
| DS29-0174 | `707b8121bb30276e1198a559bc78a8c4` | `61bc3d4e9f3d851f7c120af3642f028e` |
| DS29-0247 | `86046e4d1891a089b3df6c82e6879d98` | `491842ce609fc3eb1082cd52bd922723` |

Give the solver the verified full native GLRT candidates, acquisition clock, causal TLE and that one tile. The four-offer query supplies the tile order only. Each solver keeps its earlier supplied-tile policy and search budget. Run and compare the zero and fitted calibration arms. Use the already measured correct-tile prediction from the same solver, release, native recording and causal catalogue. The paired comparison contains no v5 measurement.

Record every attempt. A coordinate issued by an arm under the omitted condition counts as one false publication. A withheld forced coordinate is a diagnostic. Report its error separately. Resolve and preserve all source hashes before runtime. Pin the work to CPUs 6–7 and 22–23 and stop individual calls after 90 seconds. Seal the omitted predictions before reading coordinate truth or scoring error.

| Solver | Frozen source digest |
|---|---|
| Point votes | `f8186edc25eccb52556e22855d3fb870037d64c643f956bd606461de71d02fcf` |
| Rate triplets | `42612cc63e15011d8ec731d87d1c2b90508150fbb78dc9e66e7e4c1fd38920a8` |
| Folded Doppler | `dd6f48e9509fcbfe526a22ad7bc9484588d441b804d57e9e750b8b487ec7cffa` over Python and C bytes in that order |
