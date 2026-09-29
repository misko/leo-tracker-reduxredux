# Exact proposal rank-table and top-four selection

The proposal precomputes the exact float expression `rank/(z-1)` once per
workspace and reuses those values for the three percentile-rank additions.
Combined top-four selection now performs four linear local-maximum passes,
using the prior descending score/index order and five-native-sample circular
exclusion without sorting every peak.

Host, ASan/UBSan, and ARM cross-builds passed. The rank test covers all rates,
flat scores, equal-score ties, wraparound, and circular exclusion against the
retained sort-based reference. No ARM binary was run.

The full 704-dwell host audit emitted all 123,904 candidates and recovered
19,226 / 19,581 frozen standard hits. This is a quality/audit result only;
no runtime conclusion is drawn from the host execution.

Direct parity compared all 123,904 ordered JSON candidate objects with the
sealed wave3 host cohort: zero objects differed. The enclosing rows have
different hashes because timing fields differ.

The existing stable radix sort moves an 8-byte ranked record four times from
source to scratch and back: about 64 bytes per element of record traffic.
Two stable 16-bit passes can preserve the same `score_key` ordering exactly,
but require two 65,536-entry count/position tables. With `size_t` tables that
is about 1 MiB of stack/cache footprint per pass; even 32-bit tables require
512 KiB. At the 4,096–16,384 proposal lengths, clearing and scanning those
large histograms can outweigh the two avoided record passes and risks cache
pressure on Cortex-A9. It is algorithmically exact if implemented carefully,
but has no measured advantage yet and was not implemented.
