# Causal orbit-history coverage for recent blind positioning

Orbit-history coverage is sufficient to investigate orbital-error corrections:
54,962 of 55,127 catalogue occurrences (99.701%) have an eligible predecessor.
This is a coverage result, **not a new position estimate or a propagation
accuracy certificate**. No satellite identities or receiver coordinates are
fitted in this audit.

The five recent 300-second scans contain 11,109 distinct catalogue objects.
The exporter read 620 archive snapshots collected before the last capture.
For each scan, both the element epoch and its first collection must precede
that scan. The current element must match the scan's causal catalogue exactly;
a later revision at the same epoch does not erase an earlier available version.
The predecessor must be older by 1–72 hours. All 165 unsupported occurrences
fail that gap criterion and receive an explicit zero nominal phase fallback;
there are no missing current causal elements.

The frozen prior was trained before every target scan. Its rate uncertainty
remains 0.09176615913014215 seconds/hour. The audit now rejects a prior whose
training cutoff is at or after the earliest scan, or whose uncertainty is not
finite and positive. These checks do not change the saved valid inventory.

## Why exact propagation is the next gate

| Scan suffix | Supported / total | Median element age (h) | Maximum age (h) | Largest phase perturbation at ±0.25 s/h (s) |
|---|---:|---:|---:|---:|
| 1d05092feaa8f7d5 | 11,078 / 11,109 | 12.08 | 227.16 | 56.79 |
| e3bc0741ecf02704 | 11,078 / 11,109 | 12.25 | 227.32 | 56.83 |
| 3bee6be6e987a34f | 11,078 / 11,109 | 13.42 | 228.49 | 57.12 |
| 64e06d86f4746e55 | 11,078 / 11,109 | 14.42 | 229.50 | 57.37 |
| e201d79ba3234e2e | 10,650 / 10,691 | 24.46 | 90.09 | 22.52 |

These ages describe supported catalogue occurrences, not posterior-weighted
likely satellites. Ages are evaluated at capture start; perturbations exclude
the predicted nominal phase. For 54,961 of 54,962 supported occurrences, the
allowed rate boundary lies outside a ±1-second phase stencil. That does not
prove interpolation fails, but prevents assuming that a local quadratic
approximation is accurate over the whole correction range. A separate exact
propagation audit must check Doppler error and visibility before the corrections
enter the joint fit. Regional candidate pruning also needs to account for
orbital corrections rather than inheriting nominal-state support blindly.

## Evidence and reproduction

- [Original coverage receipt](coverage-v2.json.gz): original JSON compressed
  without changing its contents; includes per-candidate causal timestamps.
- [Age summary](age-summary.json): capture-start age quantiles and rate-bound
  perturbations derived from that receipt.
- [Publication verification](verification.json): content hashes and independently
  checked timestamp/prior invariants.
- Exporter: `tools/research/audit_recent_causal_phase_prior.py`.
- Tests: `tests/tools/test_audit_recent_causal_phase_prior.py` — 10 passing;
  Ruff passes for both files.

With the retained public TLE archive and the published input bundle extracted:

```bash
.venv/bin/python tools/research/audit_recent_causal_phase_prior.py \
  --evidence /path/to/recent-regional-evidence-v1 \
  --tle-archive /var/lib/leo/tle \
  --prior reports/artifacts/2026_09_21_formal_orbit_model/prior-analysis.json \
  --output /tmp/recent-causal-history-replay.json
.venv/bin/python -m pytest tests/tools/test_audit_recent_causal_phase_prior.py -q
```

The evidence bundle is
`reports/2026_09_22_joint_blind_geometry/evidence/recent-inputs.tar.gz`.
Archive read permission is required. The receipt records the archive cutoff and
source digests; a changed archive may change replay coverage. The original run
predates the added prior guard, and publication verified that its inputs pass
that guard. No new RF collection or production changes were made.
