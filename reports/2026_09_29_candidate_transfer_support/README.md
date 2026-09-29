# Same-roster satellite-candidate transfer has insufficient coverage

**No target candidate has raw support in two strictly earlier scans under the
same-roster rule.** This holds across all 4,328 bank-eligible tracks in 72
distinct recordings. No satellite-specific correction is fitted or promoted.
The result is limited to these panels and roster keys; it is not evidence that
physical satellites never repeat across the complete DS7/DS8/DS9 corpus.

The nine nonoverlapping eight-scan panels use **10 baseline catalogue snapshots**.
Different snapshots cannot safely be joined by bank row number. Identical
baseline snapshots preserve catalogue ordering under the bank exporter's
contract, even when newer element sets replace a row's orbital parameters.
This permits catalogue-row comparison, not independent detection identity.

There are 8,182 distinct (snapshot, catalogue size, row) keys in the retained
banks. Of those, **8,070 occur in one scan and 112 in two scans; none occurs in
three**. Thus the frozen requirement of two earlier donor scans plus a target
is impossible for these keys, independently of posterior-weight thresholds.
The full per-target census and an independent inverted-set audit agree.

| Dataset | Target scans | Target tracks | Scans with ≥2 earlier same-roster scans | Tracks with two-donor candidate support |
|---|---:|---:|---:|---:|
| DS7 | 24 | 1,434 | 15 | 0 |
| DS8 | 24 | 1,434 | 20 | 0 |
| DS9 | 24 | 1,460 | 18 | 0 |

Having earlier scans from the same catalogue does not imply that they contain
the target's candidate. Results remain zero when all receivers/RFs are allowed,
so receiver/RF matching is not causing this outcome. Requiring donors outside
the target panel also yields zero.

## One-donor sensitivity, explicitly posthoc

After the frozen two-donor result was zero, [overlap.py](overlap.py) inspected
one-donor support. This changes no primary gate, fits no correction and is not
confirmatory validation. It uses any receiver/RF and the same chronological and
roster restrictions. The 112 repeated rows span eight scan pairs, all across
DS7-late to DS8-early or DS8-late to DS9-early, separated by **91.84–99.05 min**.

| Target dataset | Mean conditional mass with raw one-donor support | Mean mass with strong one-donor support | Target MAP supported by strong donor |
|---|---:|---:|---:|
| DS7 | 0% | 0% | 0/1,434 |
| DS8 | 0.5882% | 3.75e-22% | 0/1,434 |
| DS9 | 1.5784% | 0.2741% | 4/1,460 |

Strong means donor signal responsibility times conditional candidate weight
is at least 0.5. Means retain all target tracks, including zeros. Conditional
mass is a descriptive model quantity, not a probability that an association is
correct. Raw overlap is broader than agreement among favored candidates. All
one-donor support is outside the target panel in this dataset selection.

These four DS9 MAP matches are too narrow a population to demonstrate a general
DS7/DS8/DS9 correction. They remain available as diagnostic cases, without
turning model agreement into asserted physical satellite identity.

## Decision and next step

Do not fit a pooled satellite correction to this sparse same-roster subset.
First resolve physical catalogue-number mappings across snapshots through
existing authoritative metadata, then census the full authorized datasets
before choosing a transferable model. This avoids treating catalogue rollover
as absence of physical recurrence. [Next investigation](NEXT.md).

The earlier DS7 orbit-hierarchy gate used different tracking projections and a
different admission rule, and also lacked independently asserted identities.
The earlier slope studies concerned receiver/time nuisance, not verified
satellite-specific donor corrections. This census neither contradicts nor
supersedes those calibration limitations.

## Verification and limits

Six synthetic tests passed before launch. One child exited zero in **2.41 s**,
peak RSS **48,344 KiB**, under a 90 s timeout and 4 GiB address-space cap.
The independent auditor reconstructed all 17,312 target/scope/RF support rows
using inverted candidate-to-record sets, then verified masses, MAP flags,
denominators and input/execution hashes. The posthoc scan-multiplicity analysis
independently explains why the two-donor support is zero.

Candidate weights come from training at the original eight-scan fitted
positions; no held value decides support. Within-panel donor/target weights
share fitted geometry and cannot validate an independent correction. Even
cross-panel comparisons come from an exposed, previously explored site.
Provider-source metadata is retained, but no new archive or provider query was
made. Only candidate-ID arrays were read from the NPZs; no trajectory arrays,
raw IQ, propagation, RF collection or production changes were needed.

No geographic fit, accuracy improvement or sub-km resolution is claimed.

[Complete frozen tables and visualization](RESULTS.md), [summary](summary.json),
[one-donor diagnostic](one-donor-diagnostic.json), [protocol](PROTOCOL.md),
[tests](tests.log), [complete evidence hashes](evidence-sha256.json).
