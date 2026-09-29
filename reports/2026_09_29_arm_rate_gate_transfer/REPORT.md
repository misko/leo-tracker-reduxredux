# Rate-dependent coarse gate transfer to DS8 and DS9

Both gates reduce emitted candidates on the independent saved-IQ panels, but
neither is lossless relative to an ungated Wave4 control on the same contexts.
The 0.300 variant retains 4,211/5,632 DS8 candidates and 4,330/5,632 DS9
candidates.  It recovers exactly the same DS8 baseline hits as ungated Wave4
and one fewer DS9 hit.  The 0.312 variant retains 3,624 DS8 and 3,689 DS9
candidates, losing one additional DS8 hit and two additional DS9 hits versus
ungated Wave4.

| Variant | Dataset | Candidates emitted | Frozen baseline hits recovered | Delta vs ungated recovery |
|---|---|---:|---:|---:|
| Ungated Wave4 | DS8 | 5,632 | 774/785 | -- |
| Gate 0.300 | DS8 | 4,211 | 774/785 | 0 |
| Gate 0.312 | DS8 | 3,624 | 773/785 | -1 |
| Ungated Wave4 | DS9 | 5,632 | 888/908 | -- |
| Gate 0.300 | DS9 | 4,330 | 887/908 | -1 |
| Gate 0.312 | DS9 | 3,689 | 886/908 | -2 |

The ungated control establishes existing approximation loss: Wave4 itself
misses 11 DS8 and 20 DS9 hits relative to the frozen full-search baseline.
Those losses must not be attributed to the new gate.

| Dataset | Original rate | Frozen baseline hits | Ungated Wave4 | Gate 0.300 | Gate 0.312 |
|---|---:|---:|---:|---:|---:|
| DS8 | 2.5 MS/s | 115 | 115 (1,408 candidates) | 115 (759) | 114 (172) |
| DS8 | 5 MS/s | 203 | 199 (1,408) | 199 (1,408) | 199 (1,408) |
| DS8 | 7.5 MS/s | 218 | 216 (1,408) | 216 (1,129) | 216 (1,129) |
| DS8 | 10 MS/s | 249 | 244 (1,408) | 244 (915) | 244 (915) |
| DS9 | 2.5 MS/s | 275 | 274 (1,408) | 274 (994) | 273 (353) |
| DS9 | 5 MS/s | 259 | 251 (1,408) | 251 (1,408) | 251 (1,408) |
| DS9 | 7.5 MS/s | 170 | 164 (1,408) | 163 (1,033) | 163 (1,033) |
| DS9 | 10 MS/s | 204 | 199 (1,408) | 199 (895) | 199 (895) |

Each row covers eight dwells and 176 receiver/windows.  Recovery uses the
frozen 0.025 margin gate and maximum-cardinality matcher within two original
samples and 8 kHz.  Candidate counts are actual emitted payload lengths, not
logical eight-slot denominators.  Unmatched new positive entries remain
unclassified and are recorded in each `standard-audit.json`.

`results.json` binds every summary, audit, rows file, binary, build receipt,
selection, evaluator, and audit-adapter hash.  The adapter changes only the
loader's inventory rule to accept a self-consistent 0--8 candidates from a
gate; matching thresholds and logic remain frozen.  All runs used local saved
IQ under `/var/tmp/leo-arm-ds89-validation/inputs`.  No ARM execution, RF
collection, or QNAP write occurred.
