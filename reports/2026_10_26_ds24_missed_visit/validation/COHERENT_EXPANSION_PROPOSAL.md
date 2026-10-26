# Exact lean coherent expansion proposal

Proposal only; root must bind the final metadata target manifest before scoring.
Apply the already sealed round1 scorer/predictor; this is a dependent evidence
expansion, not an extra tuning round. No geography or prior satellite identity
enters nomination.

Rank the twelve development cases by descending newly curved CH5–8 native owner
count, then case ID. This selects **DS24-0097(4)** and **DS24-0011(3)**. Within a
case, rank channel/RX lanes by newly curved owner count, then channel and native
RX. Select at most two distinct channels (the first eligible RX per channel),
so a single channel's two receivers do not consume the entire expansion. Select
the earliest newly curved native owner within each chosen lane as block center;
ties use its stable native observation ID. These are RF/graph-only choices.

That policy gives:

| Case | Channel | Native RX used to nominate | Block center, relative midpoint seconds |
|---|---:|---:|---:|
| DS24-0097 | 5 | 0 | 240.1399799 |
| DS24-0097 | 6 | 1 | 120.0253073 |
| DS24-0011 | 5 | 0 | 119.9573495 |
| DS24-0011 | 7 | 0 | 120.0455051 |

Freeze every same-channel/edge processed visit with midpoint in the half-open
24sinterval[center−12,center+12), ordered by exact native counter. Keep both
recorded RX for each nominated paired window; the nominating RX does not delete
its counterpart. Cap each block at70paired visits by counter order (no quality
substitution); report any clipped boundary. Thus the whole application is at
most280paired windows/560receiver cells across four blocks, similar to the
completed288window screen, with no newly collected RF.

Use the existing sparse12visit/4.5shistory at every target, including original
measured donors in the expanded block when they are causally earlier. Do not
turn newly recovered target CFOs into extra donor measurements or add a new
adaptive recursive tracker in this application. Keep the original rank/mode cap,
fixed±256bank, same-mode point control, disjoint native-frame confirmation,
unchanged frequency scorer and declared earlier-width compatibility. Preserve
all unavailable/failing cells and the complete search exposure. The original
frozen conditional null/phase-coverage limitations still apply.

Every newly opened target needs public source/index/IQ hash, full reader
exhaustion and original paired detector parity. Existing round1center windows
can reuse their verified parity only if exact source/runtime/IQ hashes match.
Deduplicate stable native owners across the original sparse panel and expansion;
an original winner remains unchanged, a prior recovered center is not a second
new point, and donor carry/alternative modes remain conditioning.

Use two independent per-case workers, BLAS1, outer cap580s each, with per-window
checkpoints. The earlier raw12case run handled24paired windows per case in
roughly40–60s; each proposed case has at most140paired windows, suggesting
approximately240–350s per case at the observed rate, within the580scap. Preserve
any cap as incomplete accounting; do not extend, replace or quietly choose a
shorter successful block after outcomes. The final metadata count should be
checked before approving this envelope.

After RF staging, rerun the original graph once per case on original rows plus
the deduplicated additions. Count genuinely new graph/curved native owners,
point gaps,20scurvature span, residual flags, existing-owner losses and noise
reweighting. Then apply full causal-catalogue association under the matched
bounded regional proposal in `POSITION_EXECUTION_PROPOSAL.md`, with the explicit
one-bin noise-floor sensitivity. A denser sequence may add actual Doppler
information; its shared donor-centered frequency grid still requires an honest
precision/dependence limit. Do not force the expanded points onto the old family.
