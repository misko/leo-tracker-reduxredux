# Earlier-record candidate support under identical catalogue rosters

Freeze the nine nonoverlapping eight-scan q020 panels: 72 recordings and 4,328
bank-eligible tracks. Use original training candidate distributions, unchanged
by the subsequent four-scan refinement. No held values select support.

Candidate identity keys are (baseline snapshot digest, catalogue size, bank row).
The bank exporter preserves the baseline catalogue order when replacing element
sets; therefore identical baseline snapshots permit row comparison. Different
snapshots are incompatible here, even if row numbers or sizes happen to match.
This establishes catalogue-row identity only, never detected-satellite identity.

For every target track, consider strictly earlier recordings with the same
roster. Report two scopes: any earlier scan, and earlier scans outside the
target's eight-scan panel. Report both unrestricted receiver/RF and identical
receiver plus exact RF. Do not count multiple tracks in one scan as independent
donor recordings. Support requires at least two distinct eligible donor scans.

Report target conditional candidate mass supported by donor raw candidate lists,
and by donor signal-responsibility times conditional-candidate weight >=0.5.
Also report whether the target conditional MAP has that stronger donor support,
using smallest catalogue row to break ties. These are descriptive support
thresholds, not identity assertions, calibrated probabilities or fitted priors.
Retain targets with zero donor support in all denominators.

The original positions and weights use whole-panel training data. Thus even
other-record support within a panel is not independent validation of a future
correction. Different-panel donors remove that particular shared-fit dependence,
but the site and previous studies are exposed. No correction or accuracy result
is produced by this census. Missing cross-snapshot mappings remain unavailable.

Six synthetic tests cover distinct donors, chronological exclusion, snapshot
collisions, panel/receiver isolation, weak/background donors and duplicate scans.
Run one bounded metadata/NPZ-index child, 90s timeout, AS4GiB, BLAS1/nice19,
available memory >=5GiB. No trajectory-array materialization, propagation, new RF,
raw IQ, provider fetches, archive reads or production changes. Preserve failures.
