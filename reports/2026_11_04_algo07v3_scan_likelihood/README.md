# ALGO07v3: independent scan scoring

The [scan likelihood](../../src/leo/analysis/localization_v3/scan.py) now runs
without historical ALGO workers. On three DS26 replay scans it reproduces the
original scan context and every scored array/value in the exercised cases
exactly. **The position optimizer, ordered recovery and publication remain
unfinished; full-pipeline timing and localization parity are not yet available.**

This follows the [causal-preparation implementation and measured preparation
speedup](../2026_11_04_algo07v3_preparation/README.md). That report's 1.60× speedup
applies only to preparation; this scoring extraction makes no new speed claim.

## Extracted behavior

The component accepts prepared graph tracks, an orbit bank, nominal elements,
noise evidence, observation origin and an explicit regional coordinate origin.
It owns its input arrays and has no archive/storage/CLI imports. It constructs
track time indexes, whitening and receiver bases, orbital geometry and the
native curved-track set. Methods preserve the original receiver/band offset and
linear drift, optional RF coefficient, phase-shifted orbit prediction, alias
profiling, residual noise gates, elevation checks, curvature-based ownership and
orbital derivatives. Linear tracks can receive independently supported
calibration but do not establish that calibration themselves.

The preparation screening centre and position search centre must remain distinct
when the optimizer is connected. This component receives its coordinate origin
explicitly; it introduces no site-specific constant or satellite selection.

## Exact comparisons

| DS26 scan | Context and geometry | Three scoring states | Orbital derivatives |
|---|---|---|---|
| 0002 | Exact | Exact | Exact |
| 0084 | Exact | Exact | Exact |
| 0102 | Exact | Exact | Exact |

The [external oracle runner](../../tools/check_algo07v3_scan_likelihood.py) runs
the installed `FreshScan` in its original Python environment and the extracted
component in a separate process using only the newly prepared inputs. Candidate
runs hide `/opt` in a private read-only mount namespace and install an audit hook
rejecting legacy imports, subprocess launches and historical runtime reads.
The original implementation is used solely by the external reference process.

The declared scoring cases use eight hardware coefficients with c=0, nine with
a nonzero c plus receiver smooth terms, and the latter with three nonzero phase
shifts. These are **fixed test states, not optimized c=0/fitted-c solutions**.
Every native track is scored. The comparison covers all returned nominations,
candidate costs, alias values, residuals/innovations, compatibility flags,
predicted frequencies, elevations, phase derivatives and total objective.
Context fields include every geometry array, time/index/group, whitening matrix,
receiver basis, element record and initial coefficient. Orbital finite-difference
derivatives are checked for the first catalogue member.

Arrays are fingerprinted by complete byte content, dtype and shape; floating
scalars preserve their exact hexadecimal representation. Serialized fingerprints
match byte-for-byte, with no numeric tolerance. The roughly 2.3 MB raw fingerprint
files for each side remain in `/srv/bulk/leo/research/algo07v3-20261104`; their
hashes and code/input receipts are recorded in [comparison.json](comparison.json).
This is component evidence on three replay cases, not full DS26 localization
qualification. The track-only denominator remains 158 exact available members
out of 159 total, as recorded in the preparation report.

## Verification and next integration

The expanded focused suite has **84 passing tests**. New tests cover receiver
and band indexing, linear drift/RF coefficient, aliases, ownership of mutable
inputs, independent support for linear tracks, below-horizon rejection,
structured residuals that pass the RMS bound but fail the noise gate, exact
orbital epoch preservation and completeness of numerical fingerprints. Ruff
passes. No production service or scientific gate changed.

Next comes the marginal position likelihood and its initial search: extract the
original orbit-mode construction, radio/phase priors, hierarchical likelihood,
fresh candidate discovery and phase-refreshed optimizer into v3 components.
Previous elements will be explicit evidence rather than historical file paths.
Candidate ordering, both calibration arms and acceptance/fallback policies must
remain identical before optimizing them. The full standalone engine and 10×
complete-path target remain active requirements.
