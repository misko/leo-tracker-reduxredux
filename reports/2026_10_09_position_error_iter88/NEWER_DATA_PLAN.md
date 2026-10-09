# Metadata-only plan for a newer DS18+ cohort

This is an unexecuted plan. No inventory, recording mint, analysis, localization
outcome access, retention hold or RF collection was performed to prepare it.
DS16/17/18 identities remain unchanged. The eleven-member POST18-RESERVE remains
closed and outside the proposed successor window.

## Freeze before inventory

Start the new window exactly at POST18-RESERVE's frozen endpoint,
`2026-10-09T02:02:21+00:00`, inclusive. Read the UTC clock once immediately before
inventory and persist that timestamp as the exclusive endpoint T. Freeze and
commit the window, mint-source SHA256, parent manifest/seal SHA256, membership
rule, exposure-search scope, grouping rule and random seed before querying the
recording index. This plan deliberately does not choose T now.

Use a descriptive successor identifier such as `POST18-NEWER-20261009`; do not
rename original datasets or present this as a newly unseen DS19. Admission is
every whole adaptive recording whose start lies in `[start,T)` and whose seal
completion is at or before T. Published and sealed unpublished archives both
qualify. Analysis readiness, localization availability, frequency-fit scores,
signal quality and error cannot gate membership. Preserve unsealed partials and
post-cutoff seals in explicit inventory accounting, separately from admitted
whole recordings. Both receivers remain together.

The current mint uses integer-second endpoint conversion. Freeze a whole-second
UTC T, as the prior mints did, rather than silently losing subsecond precision.
Inventory is not atomic; record observed begin/end times and completion evidence.
An unavailable artifact is an explicit input failure at evaluation, never a
reason to silently remove the assigned member.

## Existing read-only mint and verification

Reuse the unchanged source at
`/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_08_ds17_post_ds16/mint.py`.
It accepts successor identity, parent and boundaries; published metadata comes
through `AdaptiveHopIqStore(..., read_only=True).history_index()` and the store's
metadata ports. Firmware interchange manifests are inventoried in the configured
spool. There is no need to query private PostgreSQL models or localization APIs.
The source already handles archive completion evidence and seals copied metadata.
It does not copy, decompress or rehash raw IQ.

The parent authority is
`/home/mouse9911/gits/leo-hard60-default/reports/2026_10_09_position_error_iter75/local`.
Its manifest SHA256 is
`71e7477408e31449c14f85a7ae87155780e88c2503dc06544ab00a59016483af`.
The mint verifies that parent manifest against its seal and requires the parent's
endpoint to equal the successor start. Independently recheck the original DS18
authority SHA256 `894a6f4b7055e5f6bd602f94ce3acf7f722f204c68c2b521a06dfd6be35a7516`
when constructing the provenance chain. Prior datasets and the existing reserve
remain immutable.

The commands below are templates, not commands executed in this task. Replace
the literal T with the committed clock endpoint; use a new nonexistent output
directory in a report parent writable by the production service account. Read
the effective API service Python source selector before execution and freeze its
value/hash rather than assuming a stale release. The existing production API
virtual environment supplies the metadata adapter dependencies.

```bash
sudo -n -u leo env PYTHONPATH="${FROZEN_API_PYTHONPATH}" \
  /opt/leo-tracker/current-api/.venv/bin/python \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_08_ds17_post_ds16/mint.py mint \
  --dataset-id POST18-NEWER-20261009 --parent-dataset POST18-RESERVE \
  --parent /home/mouse9911/gits/leo-hard60-default/reports/2026_10_09_position_error_iter75/local \
  --start 2026-10-09T02:02:21+00:00 --end T \
  --output /home/mouse9911/gits/leo-hard60-default/reports/NEW_REPORT/local

sudo -n -u leo env PYTHONPATH="${FROZEN_API_PYTHONPATH}" \
  /opt/leo-tracker/current-api/.venv/bin/python \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_08_ds17_post_ds16/mint.py verify \
  --dataset-id POST18-NEWER-20261009 --parent-dataset POST18-RESERVE \
  --parent /home/mouse9911/gits/leo-hard60-default/reports/2026_10_09_position_error_iter75/local \
  --start 2026-10-09T02:02:21+00:00 --end T \
  --output /home/mouse9911/gits/leo-hard60-default/reports/NEW_REPORT/local
```

Verify source seals and totals independently, and check intersections by session
ID and uncompressed-IQ digest with full DS16(63), DS17(51), DS18(34) and
POST18-RESERVE(11). Bind each member's recording manifest digest, IQ digest,
metadata snapshot digest, timestamps, rates, visit counts, source kind and archive
completion evidence. Record exact source/runtime hashes and all missing metadata.
Report all members and exclusions/partials explicitly. No data holds are added.

## Exposure audit before random assignment

Use exact-ID/digest matching that returns only filenames and matched identity
tokens, as in iteration75's `exposure.py`; do not print matching lines containing
localization values. Search both report worktrees and committed deployment
receipts, including ignored/local receipt locations with a separately recorded
search policy. Record inaccessible locations and external notebooks/conversations
as limitations. No match is not proof of unseen validation.

The live rollout diagnostic `scan-fw-7ebf76971ca06c00` is already consumed: its
fitted-c position error was inspected. Flag it and all corresponding acquisition
group members as development if present. Also flag any other live diagnostics
whose localization outcomes have already been inspected; matching only an
inventory, queue receipt or publication timestamp does not itself establish
outcome consumption. Preserve an evidence path and classification rationale for
each exposure rather than guessing. Do not inspect any new position document or
PNG to perform this classification. Keep all eleven existing reserve outcomes
closed throughout.

## Randomized whole-group development and reserve assignment

Freeze the seed string `leo-post18-newer-20261009-groups-v1` and this grouping
policy before inventory. Never split receivers, visits or observations. Form
connected acquisition groups from recorded shared capture/campaign/parent IDs,
duplicate recording-manifest or IQ identities, and a conservative fixed two-hour
UTC capture-start block (`floor(start_utc_ns / 7200e9)`). The time block groups
nearby recordings sharing possible receiver clock/temperature state; it does not
prove independence across blocks. Review metadata-only links for longer shared
acquisitions and union them before final assignment. Document missing campaign
metadata and remaining independence limitations.

Any group with previously consumed positioning evidence is development, with
that forced assignment recorded. For other groups, derive a reproducible random
rank using SHA256 of the frozen seed and canonical sorted member identity hashes;
assign the lowest20% of group ranks to a closed reserve (round down, with at least
one only when five or more unconsumed groups exist), the rest to development.
Publish group identities, group/member counts, seed, ranks, forced-consumption
assignments and manifest/source hashes before opening any new outcomes. This is
a randomized group assignment, not a chronological split. Do not rebalance using
quality, rates, error or fit success. Too few groups means insufficient reserve
size, not permission to split an acquisition or reuse consumed scans as unseen.

Randomization plus metadata grouping does not certify statistical independence.
Expose dependence risks and keep no-match members labeled independence-unproven
until the provenance audit justifies a stronger claim. Development and reserve
still belong to the complete minted cohort; future coverage reports include both.

## Candidate evaluation gate

Minting and splitting alone do not authorize outcome access in this plan. Freeze
the candidate model, B7 control, numerical closure, global hyperparameters,
reference-free association/selection, fallback policy, matched search budgets and
analysis script before development evaluation. Reference coordinates and errors
are evaluation-only. Tune using consumed development groups; freeze the final
candidate before revealing reserved outcomes. Any opened reserve becomes consumed
for subsequent tuning, and any second trial needs that disclosure or a new cohort.

Retain every member in coverage, including missing baseline/candidate inputs and
failed fits. Report separate full-cohort, development and reserve counts plus
DS16/17/18 comparisons: mean/median/p95/worst position error, convergence/fallbacks,
paired regressions and frequency-fit effects. Match c0/fitted-c observations,
candidate banks, priors and budgets; disclose fitted-derived frozen corrections
as conditional calibration. Better residual fit alone is not better localization.
No new RF collection or production-policy change is part of this plan.
