# Reference-free pilot receipt audit

This audit reads persisted inference receipts only. Reference coordinates/errors
are not read; all-five-member terminal accuracy reporting remains separate.
No fits, objective evaluations, numerical-source edits or reserve access occurred.

## Member050

Baseline compatible, 2519 verified source hits, no aliases or source exclusions.
The runtime trigger retains the sep50-only failed `point:-72.5:-167.5` at5km
spacing and25km local radius. Prefit qualification uses42 evaluations/0.0877s,
ending KKT1.71548e-5. Fresh bounded postfit uses214 evaluations and fails the
gate at0.00358386;42-evaluation/0.0902s direct refinement qualifies at4.12562e-6.
Fixed positions are unchanged. Fresh correction/postfit/validation totals0.5643s.

Association and all six matched finals qualify. Recovered best raw regional
scores36395.774 fitted-c/36583.204 zero-c lose to member050 ordinary scores
31370.601/32558.055, plus2.20865 calibration penalty.
No recovery winner is substituted. Ordinary region dictionaries are exactly
preserved; candidate B7 vectors exactly equal baseline for both arms. All12
candidate joint-stage arm fits qualify, with no fallback reasons.

## Member026

Baseline source compatibility is eligible with only the explicitly permitted
presentation-module mismatch. Four hundred old-hard60 coarse aliases are recorded;
each is conditional on rebuilt model/saved-objective verification. Runtime trigger
`point:5:105` occurs in all three passes, at10km spacing with25km local radius,
and is correctly deduplicated into one identical model/constraint attempt.

Direct prefit qualification uses83 evaluations in0.1389s across two accepted
rounds, ending KKT0.000172419. Fresh bounded postfit independently qualifies
without extra polish:103 evaluations, KKT0.000808765,0.1828s. Fresh calibration
total is0.1875s, excluding the separate prefit refinement and reconstruction.
Association and all six matched finals qualify.

Recovered best raw scores25939.341 fitted-c/26792.672 zero-c, each with5.69231
calibration penalty, lose to ordinary24110.247/25052.922 plus11.61733 penalty.
Both operational winners remain the ordinary baseline `point:-92.5:-82.5`.
The original region dictionaries are exactly preserved, both candidate endpoint
vectors exactly equal baseline, and candidate fallback reasons are empty.

These are successful numerical-region recoveries with no operational winner change,
not measured position improvements. Such negative selection outcomes are useful
controls: independently qualifying more regions need not replace a better ordinary
model score. Population benefit remains unmeasured until complete frozen reporting.

## Member051 generic-path check

The completed generic candidate discovers `point:-47.5:-62.5` from all three
ordinary passes at5km spacing and deduplicates it once. Direct prefit and postfit
qualification each use46 evaluations, taking0.1243s and0.1196s respectively.
Shared calibration/association and all six matched finals qualify. Both operational
arms select this appended recovered region and finish at B7; all12 joint-stage
arm fits qualify with no fallback reasons. Every original ordinary region remains
exactly preserved. This repeats ac11's earlier consumed diagnostic under the
generic rule, rather than supplying independent validation. No reference position
or error was inspected in this check.

## Terminal006/046 and source integrity

All3078 frozen source/input hashes match at terminal audit. Members006 and046
preserve all original ordinary region dictionaries exactly, and both candidate
endpoint vectors exactly equal their own ordinary-only baseline. No runtime
trigger extraction failure or B7 fallback reason is recorded.

Member006's prefit qualifies after40 evaluations/0.0728s. Its recovered regional
finals have **two independently qualified results out of six**, both zero-timing
starts. The other four return solver success but fail independent stationarity:
zero-c association0.00362576, own-continuation0.00262810;
fitted-c association0.0202498, own-continuation0.00358835.

Member046 qualifies prefit and corrected postfit after42 evaluations each,
taking0.1016s and0.1003s. Its finals have **four qualified results out of six**:
all zero-c starts and fitted-c zero-timing. Fitted-c association0.0196598 and
own-continuation0.00882408 remain unqualified despite solver success.

`reason=None` means no caught exception, not independent convergence. These six
unqualified final attempts must stay visible in summary coverage; they cannot
be counted as successes merely because recovered calibration qualified.
Ordinary fallback preservation remains correct. Extending qualification into final
position fitting would be a different experiment, not an implicit pilot repair.

After all five members became terminal, the separate authorized evaluation report
checked full archived B7 documents for050/051. Its comparison.json records exact
baseline vector parity and zero objective delta in both c arms for both members.
This audit reads those parity fields only; archive integrity and protocol binding
remain documented by the report. The runtime validity findings do not depend on
reference-error selection.
