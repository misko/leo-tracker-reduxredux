# Full-aperture recheck opportunities after measured short empties

A causal check after a supported carrier reached **5 of 44** missed installed owners per calibration arm on development DS30-0049. The same number of evenly spaced checks within the same streams reached **6**. On the second radio the rule reached **0 of 21** missed owners. Complete DS30-0016 had no missed installed owners on measured short empties. The first original members of DS30-0163 and DS30-0008 triggered no checks. The frozen rule did not meet the condition for a live trial. [Protocol](empty-short-recheck-protocol.md) · [Sealed candidate-only plan](measurements/empty-short-recheck-plan.json.gz) · [Scored receipt](measurements/empty-short-recheck-score.json.gz)

| Original scope | Measured short calls | Short empties | Checks | Missed installed factors reached / possible | Even / uniform expected | Missed installed owners reached / possible, each arm | Even / uniform expected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0049, complete, development | 1,622 | 1,105 | 95 | 11 / 104 | 8 / 8.96 | 5 / 44 | 6 / 6.10 |
| DS30-0016, complete | 1,240 | 808 | 76 | 12 / 79 | 12 / 7.02 | 0 / 0 | 0 / 0 |
| DS30-0163, first original member | 94 | 62 | 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| DS30-0008, first original member | 112 | 51 | 0 | 0 / 2 | 0 / 0 | 0 / 0 | 0 / 0 |

All missed installed factors in these scopes were singleton factors. The comparison joins the same original visit, antenna, channel and hardware start counter, with unchanged RF, exclusions and clocks. Complete-case ownership is the original installed map in each arm, verified against its official owner digest. DS30-0049 uses 320 ordered rows per arm from the independent saved installed replay, which reproduced both the original native and terminal digests. The member rows join to their complete installed publications by exact original prefix parity. The member results cover the issued prefixes only. [Corrected DS30-0049 raw pair](ds30-paired-evaluation.md) · [DS30-0016 stock repeat](measurements/stock-raw-repeat-0016.json.gz) · [DS30-0163 original owner join](measurements/first-member-0163-owner-join.json)

## Causal evidence and antenna coverage

The detector uses its original unfiltered measured stream, with the pre-held packet digest reconstructed exactly. Each empty is considered once. The same lane must have a positive at its immediately preceding admitted opportunity, with three released signed continuation votes against evidence inside the last 12 opportunities and eight hardware seconds at the empty. Full anchors and short attempts both advance history. An empty anchor has already paid for full detection and consumes the opportunity. Previous rescue work scheduled unmeasured omissions or rechecked already-positive short lanes. Both concern different exposure. [Earlier mask recovery](causal-mask-recovery.md) · [Earlier positive-lane recheck](live-full-recheck.md)

The DS30-0049 schedule used **80 of 95 checks on radio 0** despite that radio having 437 short empties versus 668 on radio 1. It reached five owned opportunities on radio 0 across channels 5, 7 and 8. It spent all 15 radio 1 checks on channels 1–3, where none of the missing installed factors was owned. The 21 missed installed owners on radio 1 were on channels 6, 7 and 8, with 9, 6 and 6 respectively. Those three streams got zero checks. The evenly spaced comparison shares the same per-stream allocation, so it also misses those 21 owners. DS30-0016 used 48 checks on radio 0 and 28 on radio 1, reaching 8 of 46 and 4 of 33 missed installed factors respectively. The rule uses one threshold for every stream. It allocates more checks to streams with already established signed support.

The dense first-member archive used the generic 8 ms binary in its original mixed process. Every one of its 112 short lanes matched the separately measured sparse binary's complete raw-factor byte fingerprint. The match binds the original compressed member, manifest and all 64 original window hashes, then re-encodes each typed factor into its original 40-byte ABI layout. Both sources included the same exact empty lanes and signed factors. The full anchors use the same original installed full binary. [Dense original comparison](original-dense-intake.md) · [Exact sparse transfer](short-rank.md)

## Price and evidence boundary

| Scope | Measured full CPU per lane | Measured short CPU per lane | Full / short | Projected added native CPU |
| --- | ---: | ---: | ---: | ---: |
| DS30-0049 | 3.595 ms | 1.074 ms | 3.35× | 0.341 s |
| DS30-0016 | 2.516 ms | 0.814 ms | 3.09× | 0.191 s |
| DS30-0163, first member | 1.963 ms | 0.812 ms | 2.42× | 0 s |
| DS30-0008, first member | 2.516–3.109 ms from sealed donors | 0.839 ms on the original sparse member | 3.00–3.71× modeled | 0 s |

Full-call prices from captured acquisition are same-case anchor means where available. The short cost has already been paid at each trigger. The proposed charge is the added full-call CPU using that mean, with trigger, verification and downstream effects unmeasured. No new CPU or end-to-end speedup was benchmarked. [Physical sparse native clocks](attested-sparse-budget.md) · [Dense short-lane CPU](short-rank.md)

On DS30-0049, **84 of 95** checks had no installed selected factor. On DS30-0016 the count was **64 of 76**. These are oracle-negative checks. Installed continuation can discard genuine full alternatives, and a live dual detector with different preceding evidence can emit a different factor. The independently attested DS30-0163 alternatives cover 52 admitted original lanes, all outside the trigger set. No nominated lane has actual dual-detector recheck evidence. The observed counts describe opportunities to recover named selected measurements or previously owned support. New scientific assignments, both position errors and live recheck clocks remain unmeasured.

The trigger was frozen at `dc035beaf`. The candidate-only seal at `bafa221ee` expands to SHA-256 `ea0a0e20afcf29d86385ab23e2f348890313027be8cc56527807ed61cf1b9b47`. One offline score attempt used the wrong nested filename for the dense installed packet. The corrected scorer uses the authenticated installed publication path. The pre-scoring plan and all inputs were retained. The final score expands to SHA-256 `8f3fbd0722d25477aa4eec12d92a8087ea5f221a4a4e647871cfa6ae11a79dd1`. Six component tests passed. The reducer has only `plan` and `score` actions and reads existing typed packets and receipts. [Reducer](empty_short_recheck_score.py) · [Component tests](../../../tests/pipeline_eval/test_empty_short_recheck.py)
