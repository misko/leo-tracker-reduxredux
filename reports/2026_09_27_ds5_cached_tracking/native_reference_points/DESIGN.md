# Reference-coordinate scoring diagnostic

The preceding turn made progress by completing an isolated two-candidate
experiment with 132 development cases. It did not recover any of twelve
application-relative receiver identity losses. Inspection of every positive
captured candidate pair shows that none of those twelve rows contains an
unselected reference-matching native pair. The next useful question is whether
the native final statistic accepts a reference hypothesis when explicitly given
its timing and scoring frequency.

## Fixed selection before scoring

Use `../native_candidates/results.real.json` with SHA-256
`335a4bb946ede0c350511920641f5ee7b1ebe56e7768200f83ff3402f45aa1cb`.
Include all twelve receiver rows where K2 blind lost reference association.
Add the first two retained receiver rows per rate in receipt order as positive
anchors. Use the frozen development adapter; never open reserved IQ.

For each receiver, select the application pair with largest minimum member
margin, breaking ties by original inventory index. Also select the strongest
pair whose acquired/scoring AND physical CFO are both within +/-400 kHz, if
one exists. Deduplicate identical selections. This second selection is an
alias/physical-frequency contrast, not an API-support test. Resolve each member
back to its exact full-application candidate by probe, local epoch, physical
CFO and margin, retaining acquired CFO, residual, rank and all original scores.
Preserve membership and selected coordinates in the source lock before scoring.

All twelve strongest pairs have acquired CFO within +/-400 kHz. Some physical
frequencies exceed that band because the application adds a residual near
112 kHz. V3 guided scoring accepts a finite expected physical CFO whose distance
from scoring CFO is no more than half the symbol sampling frequency
(0.5 / 4.4 microseconds), and its V2 scoring call requires acquired CFO within
400 kHz. V3 replaces the absolute physical-frequency status bit with an
innovation check. Physical CFO outside 400 kHz is not by itself unsupported.

## Fixed calls and assessment

At each selected pair member, make one current Python `conditioned_glrt64_score`
call on the same raw receiver/probe at the stored integer epoch and acquired
CFO. Check its exact/control/margin and residual/physical frequency against the
stored application candidate with explicit numerical tolerances. Mismatch is
an integrity failure, not an opportunity to select another candidate.

Make one unchanged TG11 guided point call at the same epoch and acquired CFO,
with expected physical CFO equal to the recorded application physical CFO.
Keep status, support, bounds, fractional flag, exact/control score, margin and
independently measured physical CFO. If the API returns no observation, preserve
that outcome with the actual support predicate rather than inventing a negative
score. Do not silently wrap frequency, clamp residuals or tune a threshold.

For each pair, report both raw margin passage and full native acceptance
(status zero, valid bounds/support, >=2 frames, fractional complete, margin
>=0.025), then same-receiver nonoverlap, mutual physical CFO <=8 kHz and
association to the reference at 2 us/8 kHz. An input timing coordinate is not
an independently fitted timing estimate. Expected physical CFO is oracle input
here; this experiment does not provide a causal hypothesis generator.

The native guided path scores raw samples. It does not perform blind nuisance
tone removal or independent timing acquisition. Thus acceptance demonstrates a
usable raw native point at a supplied coordinate, not that tone-conditioned
blind scoring is equivalent. Rejection may involve symbol profile/statistic,
frequency residual, support or API bounds and must be described at that scope.

## Execution and integrity

Freeze this design, runner/tests, selected membership/coordinates, the preceding
receipt and its 74 source files, current Python scorer, frozen TG11 binary and
all its build dependencies before outcomes. Keep the original artifacts
unchanged. Write a separate immutable diagnostic receipt even on failure.

Run at most 120 seconds on P-core 0 with all numerical thread counts one, one
DSP campaign at a time. Loading/hash/init are outside individual point timings;
capture every point outcome. Verify input immutability and all source hashes
after execution. No full application rerun, parameter sweep, RF collection,
QNAP write, validation generation, production change or deployment occurs.

Report diagnostic point timings only. Oracle-supplied hypotheses and omitted
search make them unsuitable as end-to-end detector speedup claims. A complete
diagnostic changes the next implementation choice; it does not itself fulfill
the 10x objective or qualify receiver accuracy.
