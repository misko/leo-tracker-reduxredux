# Additional standard position methods

Completed scanner tracking now produces a separate `scanner-position-methods-v1`
sidecar. The existing sparse position diagnostic is retained unchanged.

Three additional PNGs and a JSON document are exposed in the scan detail panel:

| Method | Input | Model |
| --- | --- | --- |
| Expanded Doppler | Up to 64 reviewed tracks from this scan | Fixed reviewed identity, per-track frequency offsets, equal total robust weight per session/NORAD pass |
| Orbit corrected | Target plus up to 16 earlier completed scans from the same radio within eight hours; at most 128 total tracks | Formal correlated Student-t model with constrained shared satellite orbital phase-rate corrections |
| Identity mixture | Same rolling cohort | Training-conditioned weights over saved review candidates plus an unassigned component |

Selection uses saved review provenance, not the four-row full-association table.
History tracks are selected round-robin across sessions, in longest-support order.
The target receives its own track allowance first. Duplicate observation IDs are
excluded rather than counted twice. Tracks above the explicit 512-observation
work bound are excluded with reasons; observations within admitted tracks are
retained. The original review training/evaluation partition is reproduced.

These are conditional, stationary-position diagnostics. The candidate shortlist
was screened at a configured observer site, contains at most five reviewed
identities per track, and is not a certified full-catalogue search. Mixture
weights are model-dependent, not calibrated identity probabilities. No calibrated
position fix is claimed. Correlated receiver copies do not constitute independent
physical passes. All work reuses existing recordings; this process collects no RF.

The user-supplied report reference is latitude `37.84903264307456`, longitude
`-122.4856541910174`. It is used only after numerical fitting to calculate
horizontal great-circle error in metres. It is not the differently located
observer preset used for catalogue screening. This is a reference comparison,
not a survey accuracy claim or live GPS reading. Altitude is fixed at zero metres
in the position model; no vertical position estimate is reported.

Missing support, unqualified UTC, nonconvergence, weak geometry, and failed exact
orbit verification produce explicit status PNGs and null coordinates/errors.
The orbit approximation uses five propagated states (nominal, +/-1 s and +/-2 s)
with quartic interpolation, retaining the quadratic path for older research callers.
It must agree with exact SGP4 at the fitted corrections
within 0.2 Hz maximum; that tolerance is not adjusted to obtain a position.

The JSON contains coordinates, reference error, residuals, candidate weights,
fit/evaluation membership, selected observation IDs, limits, source digests,
exclusions and numerical diagnostics. The first completed cohort is frozen with
the scan's sidecar. Later-arriving history does not silently rewrite published
evidence. A policy change requires a new analysis version.

Read endpoints:

```
/api/v1/scanner/tracking/{session_id}/position-methods
/api/v1/scanner/tracking/{session_id}/position-methods/{method}.png?sha256={artifact_digest}
```

The tracking queue requires both the existing tracking product and these
additional artifacts before declaring the job complete. A recent completed
tracking product with a missing sidecar is eligible for bounded backfill.

To replay without writing production artifacts:

```bash
OPENBLAS_NUM_THREADS=1 python -m leo.cli.scan_position_methods \
  --bulk-root /srv/bulk/leo --tle-root /var/lib/leo/tle \
  --session-id scan-fw-e3bc0741ecf02704 --output-root /tmp/position-replay
```

The output root must exist and be writable. Production workers create only the
new local namespace with their normal ownership. QNAP remains read-only.
