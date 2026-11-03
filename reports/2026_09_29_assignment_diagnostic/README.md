# Largest predictive losses retain the same satellite candidate

All twenty selected tracks retain the same leading physical catalogue number
under the fixed N24 position and the equal N8 position mixture. Their minimum
conditional candidate probability is **0.999188**, and the largest change in
the complete conditional candidate distribution is **0.0008125** in total
variation. For these tracks, the prediction loss is associated with poorer
Doppler fit at a stable leading assignment, not a changed leading candidate.
The candidates are model hypotheses, not externally established identities.

| Diagnostic | Result |
|---|---:|
| Selected tracks / target scans | 20 / 5 |
| Same leading catalogue number in both models | 20 / 20 |
| Same number with probability ≥0.9 in both | 20 / 20 |
| Minimum probability conditional on signal | 99.9188% |
| Maximum candidate-distribution total variation | 0.0008125 |
| Distinct scan/candidate groups | 12 |

These tracks were frozen from the previous diagnostic's twenty largest
negative contributions. They account for 27.2% of gross negative track
contribution, not all losses. Eleven come from DS9_0. This targeted sample
does not estimate the assignment-error rate of the entire corpus.

## Shared candidates across observations

The following multi-track groups occur within the selected twenty; counts
are not counts of all available tracks for those candidates.

| Target | Catalogue number | Selected tracks | RXs | RF centers (GHz) | Track contribution |
|---|---:|---:|---|---|---:|
| DS9_0 | 58221 | 5 | 0, 1 | 10.71, 10.96, 11.21 | −104.430 |
| DS9_0 | 66447 | 3 | 0, 1 | 10.71, 11.21 | −80.249 |
| DS8_1 | 68334 | 2 | 1 | 10.94, 11.44 | −36.972 |
| DS7_0 | 65916 | 2 | 0, 1 | 11.21 | −32.096 |

Contributions are natural-log units from the prior posterior-dependent
attribution, not causal exclusion effects or metres. The same candidate's
appearance on multiple receivers/bands motivates testing errors shared by
candidate, while preserving uncertainty about the physical source.

## Implication for the next model

For these losses, simply expanding assignment flexibility or rejecting more
tracks does not address the observed stable-candidate Doppler mismatch. A
useful next experiment would compare residual *shape* across receivers and
RF channels for matched candidates, using source-only estimation and separate
target prediction. If transferable structure is present, test a constrained
orbit/measurement perturbation shared by that candidate, rather than free
per-track slopes that can absorb receiver-position information.

This is not a recommendation to repeat the earlier shared-slope model:
[that experiment](../2026_09_29_shared_candidate_slope/README.md) improved
some likelihood scores without consistent geographic gains. A new correction
needs evidence of transfer and an identifiable physical constraint first.
Stable assignments at alternative locations alone cannot distinguish orbit
error, measurement bias, or receiver-location error. No new geographic
improvement is claimed here.

## Method and validation

The [protocol](PROTOCOL.md) and [manifest](manifest.json) froze the twenty
tracks before candidate scoring. The complete-scan posterior over timing
and, for N8, location component is retained: we did not independently choose
the best timing or location for each selected track. Candidate-plus-background
responsibilities are averaged over that posterior, then normalized conditional
on signal. Physical catalogue numbers come from the previously audited
catalogue_recurrence mapping, with slot count and uniqueness checked per track.

Every target passed the unchanged 32/64-node stability gates. Maximum
candidate-probability difference was 5.45e−15, maximum evidence difference
2.92e−11, and all leading labels were stable. Replay against the earlier
32-node evidence differed by at most 7.28e−12. Candidate probabilities summed
to the independently evaluated signal responsibility within 5.69e−14.
Runtime scalar track-score replay was exact at the checked offsets. A separate
real-input test compared each candidate's batched probability with the scalar
oracle at five timing offsets and four positions; it passed. Ruff passed.

All five subprocesses exited successfully; the longest took 41.3 seconds,
with 159.1 summed numerical seconds. The cap was 180 seconds per target and
three concurrent workers. Source evidence and artifact hashes were verified.
No tracks were removed, no locations were refitted, and no RF or production
changes were made. See the [complete track table](TABLE.md),
[summary](summary.json), and per-target probability arrays for the evidence.

The retained banks are site-conditioned, these are previously explored data,
and the inherited geographic reference is unsurveyed. Near-unit conditional
probabilities can be overconfident when the true source is absent or the model
is wrong; they are not independent satellite identification or sub-km proof.

## Reproduction

Outputs are created exclusively to preserve completed evidence. Run in a fresh
archived-run context, not over existing outputs.

```bash
python3 reports/2026_09_29_assignment_diagnostic/study.py prepare
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_assignment_diagnostic -v
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_assignment_diagnostic/study.py batch
python3 reports/2026_09_29_assignment_diagnostic/summarize.py
```
