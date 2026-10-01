# Host curvature membership audit

The frozen membership gates compare canonical measured sources, not the TRACK
row's final linear compatibility summary. The maintained 63 server segments are
a comparison segmentation and do not provide independent satellite identity.

| input / acceleration bound | output tracks | one-to-one complete | reference segments with any complete output | merge-displaced references | supported references without a complete output | input-limited references | unmatched outputs |
|---|---:|---:|---:|---:|---:|---:|---:|
| server / 0 | 42 | 36 | 46 | 10 | 17 | 0 | 6 |
| server / 125 | 42 | 36 | 46 | 10 | 17 | 0 | 6 |
| server / 250 | 42 | 36 | 46 | 10 | 17 | 0 | 6 |
| server / 500 | 42 | 36 | 46 | 10 | 17 | 0 | 6 |
| ARM / 0 | 55 | 35 | 44 | 9 | 8 | 11 | 20 |
| ARM / 125 | 54 | 36 | 45 | 9 | 7 | 11 | 18 |
| ARM / 250 | 55 | 37 | 46 | 9 | 6 | 11 | 18 |
| ARM / 500 | 56 | 37 | 46 | 9 | 6 | 11 | 19 |

On ARM observations, curvature allowance 250 represents two more reference
segments than the otherwise identical zero-acceleration association: references
23 and 31 move from supported-without-complete-output to complete membership
edges. The one-to-one result rises from 35 to 37, while references represented
by any complete output rise from 44 to 46. Bound 500 adds no represented
reference and adds one unmatched output. This is an association comparison, not
a physical-identity result.

For ARM bound 250, the 26 references outside the conservative one-to-one result
separate into three evidence classes: 11 cannot reach 80% reference coverage
from any ARM input candidates under the same-source 2500 Hz gate; nine have a
complete output but lose one-to-one assignment because that output also
completely represents another server segment; and six have adequate input
evidence but no individually complete output. Union across fragments reaches
80% source coverage for 48 references, two more than have an individually
complete output (references 10 and 35).

The nine merge-displaced references are compatible with longer nonlinear arcs
joining server linear segments. They are kept visible and are not counted as
extra one-to-one recoveries. Likewise, unmatched outputs are not called false
positives because neither server segmentation nor this evaluator provides an
independent satellite label.

The server branch is insensitive in membership counts across acceleration
bounds: all four cases produce 36 one-to-one complete references and 46
references with any complete output. Their TSV bytes differ, so this statement
is limited to the frozen membership criteria.

`reference_support_interval_occupancy` measures the union of short detector
integration intervals and is roughly 3% at the median; it is not continuity.
The separately reported consistent-source center span is about 99.9% at the
median for server and ARM bound-250 matched references, which shows the sparse
source evidence reaches across most of each matched reference interval.

The secondary linear-fit diagnostic is intentionally non-primary. For ARM bound
250 it reports 17 strict and 38 relaxed associations, while membership reports
37 one-to-one complete references and 46 represented by any complete output.
The difference demonstrates why a final straight-line fit cannot decide curved
membership recovery.
