**No unused curved RX2 witness; two noncurved predictive-only candidates.**

The frozen metadata rule finds zero independently selected complete curved RX2
sources with overlapping or adjacent support for the four historical RX1
sources. Two unused noncurved RX2 sources overlap the original discovery time
interval. Both are on a different carrier from every historical reference.
Neither has been compared with 60108 or any other satellite in this inventory.

| Inventory stage | Owners |
| --- | ---: |
| Complete native owners, both receivers | 146 |
| Canonical curved graph owners | 87 |
| Complete RX2 owners | 65 |
| Curved RX2 owners | 38 |
| Unused curved RX2 owners | 3 |
| Unused curved RX2 owners with required time support | 0 |
| Unused noncurved RX2 owners with required time support | 2 |
| Same-carrier eligible witnesses, either role | 0 |

Thirty-five of the 38 curved RX2 owners overlap at least one original accepted
ID; 27 lack overlapping/adjacent time support. These exclusion counts overlap.
All three unused curved sources lack the required time support. No accepted
source is silently removed from the inventory, and no partially used owner is
trimmed into a new witness. Both c arms' complete 3,784-ID accepted ledgers,
including postfit extensions, remain in the output.

The complete secondary pool is:

| RX2 source | Native points | Time interval, s | RF center, GHz |
| --- | ---: | ---: | ---: |
| CH3/T005 | 10 | 56.082349–68.131276 | 11.4403125 |
| CH3/T006 | 9 | 58.920138–69.195002 | 11.4403125 |

Their intervals overlap the already tested 53-point RX1 discovery source,
57.812613–98.196619 s at 11.1903125 GHz. All secondary sources are retained,
without choosing whichever is closest to a predicted CFO. They must remain
predictive-only and never calibrate receiver offsets or drifts. Different
carriers do not imply shared transmitter offsets; the existing source-constant
and joint satellite/radio uncertainty would need to be retained in any later
comparison. Time overlap and receiver diversity do not establish satellite
identity, propagation-path equality or a calibrated independent measurement.

The rule and source hashes were saved before metadata projection: all complete
RX2 curved owners, no overlap with either original accepted-ID union or the
189 previously tested RX1 IDs, and overlapping closed time intervals or adjacent
distinct slices on the sorted union of all archived native-owner times. The
adjacency definition has no fitted seconds threshold. Exact same-carrier
eligibility is separately recorded. Noncurved sources have a distinct secondary
status. Candidate, alias, CFO and assignment-closeness fields never enter the
selection. Graph extraction itself was response-selected, and the historical
RX1 reference sources were label-selected; this is not an RF-blind sample.

The original 53+85+36+15 RX1 owner comparisons are not repeated. Every reference
native-ID order matches the canonical source exactly. The first metadata run
stopped on an integer receiver-enum/string guard mismatch before eligibility
counts. Its source/protocol are preserved. Revision02 only normalizes the
canonical receiver enums 1/2 to output labels RX1/RX2; the scientific eligibility
rule is unchanged. Five revision02 tests pass, including canonical enums,
one-ID whole-owner exclusion, exact time adjacency, CFO/candidate redaction and
predictive-only secondary retention. The successful metadata run took 0.030 s;
both attempts and tests are far below the 120 s metadata-processing cap.

No CFO comparison, new nomination, IQ read, position fit, GPS evaluation,
offset calibration or operational association occurred. A next RF test is a
separate coordinator decision on the frozen complete secondary pool, not an
automatic consequence of availability.

[Protocol02](protocol02.json), [complete inventory](inventory.json),
[compact CSV](inventory.csv), [metadata summary](summary.json),
[initial failure](failure01.json), [inventory seal](seal02.json) and
[summary seal](summary_seal.json) preserve every inclusion/exclusion and source
binding. Historical accepted-ID authority is the already sealed original
ownership ledger, not a rebuilt fit.
