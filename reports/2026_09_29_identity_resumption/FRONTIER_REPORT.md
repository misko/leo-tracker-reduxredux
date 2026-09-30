# Starlink header structure and satellite identity: combined experimental findings

September 29, 2026. Existing DS7/DS8/DS9/DS10 only; no new RF collection.

## Abstract

We investigated whether recovered nonpilot signs and phase relationships identify
Starlink satellites or reveal interpretable header fields. The qualified corpus
contains 1,393 deduplicated entries, including 315 conditional satellite labels
and 26 stronger, control-supported associations. No label is an identity decoded
from RF. Frame-disjoint feature comparisons, receiver-consensus tests, temporal
controls, wider-carrier analysis, seconds-separated trajectory samples, and
same-time candidate recovery do not establish a satellite identifier. The most
credible positive observation is reproducible early signal structure within
short excerpts. Its identity specificity and semantic meaning remain unresolved.

## What the measurements represent

Known pilots and the repeated T-code are separated from the early symbols used
for identity tests. The T-code state is a constrained waveform choice; recognizing
it is not decoding a satellite address. The early region studied here comprises
OFDM symbols 2–7. Four common nonpilot carriers provide 24 real signs per frame
across the corpus. A 10-MS/s subset supports 26 common carriers, or 156 signs
per frame. These are noisy observations, not that many independently decoded
information bits. Shared constants, coding, correlation and calibration reduce
their possible information content.

Pilot coherence is a quality proxy, not calibrated SNR or bit-error rate. Receiver
agreement is evidence of reproducible observations, not proof of a field meaning.
All recordings were previously inspected. Held-out splits prevent a particular
fit from using its evaluation samples, but do not constitute new prospective
confirmation. Synchronization can also use pilots throughout an excerpt.

## Ranked conclusions

| Confidence | Conclusion | Evidence and limits |
|---|---|---|
| High for the tested excerpts | The early region contains reproducible structure | Cross-receiver results and frozen stable-sign masks; does not imply identity or plaintext |
| High about the analysis | Session/time controls are essential | Apparent cross-session feature advantages lose support under grouped controls; nearby-observation time is a strong baseline |
| Moderate | The short-term sign lead is not yet satellite-specific | Mixed-instrument same-channel excess exists, but stronger-tier matched comparisons are absent and episode continuity is unresolved |
| Moderate, limited to known tail | Extra carriers are not broadly worse to recover | 506 held-out known-tail frames show about 18–19% disagreement on both core and additional carriers; not early-header BER |
| Low evidential support | A stable header-coordinate profile identifies the source | Lower-edge transfer is weak and fails multiple-comparison correction |
| Unresolved | Specific identity, timing, address, beam or position fields | No verified RF-to-message mapping or independent identity truth; tested simple counters do not survive controls |

### Across satellites and revisits

Strict same-instrument/channel matching yields only one positive comparison with
a matched different-candidate control. Mixed-instrument matching yields 30 such
positive pairs, of which 29 are within a session. Their real-sign similarity
excess is +0.103. Session-preserving exploratory correction gives p=0.048, but
this does not separate identity from episode continuity. Whole-trajectory controls
give p=0.356 and have little power for within-session equality. The stronger
association tier has no supported matched-positive contrast.

In a follow-up retrieval task, same-session/channel sign accuracy is 64.3%,
versus 85.7% for nearest observation time, averaged across seven episodes.
Different-session same-channel retrieval has only two cases and no correct sign
retrievals. Other-channel transfer has five episodes and wide uncertainty. These
small, dependent comparisons do not justify a reusable identity classifier.

The 709-entry 10-MS/s subset expands the signature from 24 to 156 signs. Among
its 14 matched positive pairs, the sign excess falls from +0.104 on the original
carriers to +0.022 on the wider support. This does not prove that additional
carriers lack information; it shows that simple wide-sign similarity did not
strengthen the lead under this protocol.

### Within excerpts and along longer trajectories

Three paired DS10 excerpts each span approximately 120 ms, not a whole long
encounter. Discovery-selected consensus-stable signs reproduce on later RX1
frames at 84.8–95.2%, but many different-candidate controls also agree strongly.
The stable signs are therefore not shown to be source-specific. Simple physical-
frame counter harmonics fail familywise circular-shift controls.

New bounded recovery sampled three points along each of two approximately
28-second trajectories. Their selected points span about 13 seconds per track
and yield 32 qualified frames. Within-minus-between similarity is +0.049 on four
carriers and +0.041 on 26; balanced-partition control ranks are 0.20 and 0.30.
Time alone perfectly separates these two trajectories. This extends measurement
coverage to seconds but does not establish identity persistence.

### Removing the time gap between different candidates

The complete qualified inventory supplies five same-receiver/channel/edge pairs
with different conditional labels and shared recorded visits. All labels are
legacy conditional. The fixed protocol tests three acquisition-margin-selected
shared visits per pair: one pair at 10 MS/s and four at 5 MS/s, for 30 candidate
recoveries in total. No replacement visits were chosen after observing failures.

Only one of the 15 shared visits yields at least two qualified frames for each
candidate. Its 11 common nonpilot carriers supply 66 early signs per frame.
Within-candidate agreement is 82/132, versus 80/132 across candidates. These are
correlated sign comparisons and include common constants; the two-agreement
difference is not evidence of identity. No second usable visit establishes
persistence. Other visits are coverage failures, not negative identity tests.

To audit a methodological alternative, seven identical raw excerpts were replayed
with four-frame instead of longer recovery. Every shared held-out frame retains
the same >0.5 pilot-quality gate outcome. This does not support frame-count
calibration as the main cause of those coverage failures. It does not rule out
all calibration effects or justify relaxing the threshold.

## Firmware and literature constrain interpretation

The existing firmware investigation traces software message parsing and contains
SATAddr, channel/RF state and positioning-related formats. It does not establish
where those software bytes occur in recovered OFDM signs, or the intervening
coding, interleaving and scrambling. SATAddr must not be equated with NORAD ID.
See the [firmware analysis](../../docs/research/starlink-literature/firmware-header-analysis.md).

The reviewed [signal-structure paper](https://arxiv.org/abs/2210.11578),
[timing study](https://arxiv.org/html/2501.05302v1), and
[2026 waveform study](https://www.nature.com/articles/s44459-026-00075-6)
constrain synchronization, timing and predictable waveform structure. They do
not supply a verified mapping for the early message fields in this investigation.
Timing behavior or a repeated pilot is not, by itself, a satellite identity.

Previously tested modulo-60 affine counters, simple state recurrences, arbitrary
CRC/byte/alignment scans and unsupported coding hypotheses were not repeated.
The renewed goal does not turn an old negative scan into a new independent test.

## Requirement audit and remaining frontier

| Requested requirement | Authoritative evidence | Status |
|---|---|---|
| Rank plausible approaches by evidence, feasibility and false positives | [Initial register](PLAN.md), executed results below | Completed for the selected bounded hypotheses |
| Cross-candidate and revisit tests with nuisance controls | [Core report](README.md), [episode controls](EPISODE_CONTROLS.md), [bandwidth extension](BANDWIDTH_EXTENSION.md) | Executed; identity specificity unresolved |
| Within-long-visit structure and receiver consensus | Core report; [seconds-separated samples](LONG_TRACK_EXCERPTS.md) | Executed at available excerpts; continuous multi-second paired decoding not demonstrated |
| Stable positions and predictably changing bits | Core counter/stability tests; [profile transfer](LOWER_PROFILE_TRANSFER.md) | No validated identity or counter field |
| Separate pilots/T-code and account for recovery quality | [Carrier benchmark](CARRIER_RELIABILITY.md), [calibration audit](CALIBRATION_LENGTH.md) | Implemented, with header-BER limitation retained |
| Stronger different-candidate temporal controls | [10-MS/s prototype](SIMULTANEOUS_TRACKS.md), [four 5-MS/s pairs](SIMULTANEOUS_5MS.md) | Executed; one usable matched visit, insufficient repeat coverage |
| Reproducibility, owned tests and preservation | Source/receipt hashes, ignored numerical outputs; 14 component tests pass; 23 initial sealed files unchanged | Verified for this research component |
| Interpretable RF message fields or validated satellite identifier | No qualifying artifact | Not achieved |

The overall goal is not complete. The present evidence supports waveform recovery
and limited repeatable structure, but not a semantic satellite identifier.
The next decoding experiment needs an independent constraint that predicts
observable bits: for example a verified RF coding/field mapping from the allowed
firmware or literature. A stronger identity experiment needs informative existing
observations that break time/beam/receiver confounding and repeat across visits.
Neither a looser quality threshold nor another arbitrary byte/CRC search resolves
those requirements. New RF is outside the authorized scope.

## Reproduction and preservation

Each linked experiment report gives its command, source receipts and method
hashes. Data remain under ignored `local/`. The initial integrity seal was
verified without rewriting it: all 23 original hashes match. Executed source
snapshots preserve recovery provenance when later changes only wrapped lines
or added new explicit targets.

The component suite was rerun successfully (14 tests):

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with pytest pytest -q reports/2026_09_29_identity_resumption
```

The tests cover the numerical helpers and selection/coverage gates, not the
truth of orbit labels or the full RF decoder. Passing tests cannot establish a
satellite field. No commits, deployment, fixture updates or new RF collection
were performed in this resumed investigation.
