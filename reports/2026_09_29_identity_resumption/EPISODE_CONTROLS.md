# Does early-sign similarity add identity information beyond episode proximity?

The prior batch found an exploratory same-channel sign-similarity excess. This
follow-up tests its practical discrimination and tightens the control population.
It uses the already hash-bound corpus and frozen real-sign features, with no new
RF or model fitting to the query frame. It is a follow-up to a selected lead,
not independent confirmation on pristine observations.

## Exact session and endpoint controls

For each of the 30 previously matched positive pairs, take each observation in
turn as a query. Its second evaluation frame is compared to the first frame of
the positive donor and of different-candidate controls. Each control must share
the positive donor's exact session, edge, channel, rate and receiver, match the
query-relative separation bin and T-state-overlap category, and differ in pilot
coherence by no more than 0.1 from the donor. Same-visit observations are excluded.

Of 60 directed comparisons, 17 have any eligible control; none has three or more.
Their mean positive-minus-control cosine excess is +0.189, with 12 of 17 positive.
These are dependent comparisons with at most two controls each. They preserve
the short-term structure lead but cannot establish satellite identity, statistical
independence or a generalizable classifier. No unsupported cases are assigned
zero effect and counted as negative evidence.

## Candidate retrieval versus metadata-only alternatives

For each labelled query, galleries use the same edge, pilot-coherence gap <=0.1,
and a fixed donor channel/rate/receiver combination. Test separately within the
same session/channel, across sessions on the same channel, and across sessions
on another channel. Exclude every same-visit observation. Require the query's
candidate to appear and at least two other candidate IDs.

Choose one donor per candidate by highest pilot coherence, never by sign score.
Use the query's second reserved frame against each donor's first reserved frame.
Compare three fixed ranking rules: largest sign-feature cosine, smallest time
separation, and smallest absolute CFO difference. Fractional top-choice credit
handles exact ties without selecting the true label. This is offline retrieval;
donors need not precede the query in time.

Multiple receiver/gallery opportunities are averaged within a (session, candidate)
episode before reporting the mean. A seeded 999-draw episode bootstrap describes
uncertainty; it does not resolve noisy orbit labels, dependence across sessions,
model-selection reuse, or the small number of episodes.

| Scope | Gallery cases | Query episodes | Sign retrieval | Nearest time | Nearest CFO | Uniform chance |
|---|---:|---:|---:|---:|---:|---:|
| Same session/channel | 11 | 7 | 64.3% | 85.7% | 28.6% | 28.6% |
| Different session, same channel | 2 | 2 | 0% | 50.0% | 0% | 10.5% |
| Different session/channel | 11 | 5 | 33.3% | 0% | 6.7% | 14.9% |

These are episode-weighted credits, not independent trial accuracies. The 95%
bootstrap interval for sign minus nearest-time credit is −64.3 to +21.4 percentage
points within sessions. Across sessions/channels it is 0 to +73.3 points; sign
minus CFO is 0 to +66.7 points. Both include no improvement. No multiple-comparison
significance claim is made for this exploratory retrieval follow-up.

CFO partly informed the original orbit association, so it is a confound baseline,
not independent identity truth. Neither it nor nearest time is a satellite-ID
decoder. The point is whether the recorded signs demonstrably add discrimination
beyond readily available metadata. This experiment does not establish that yet.

## Consequence

The short-term sign pattern is real enough to investigate as transmission-episode
or beam continuity. We cannot presently promote it to a stable satellite address:
nearest time performs better in the supported within-session comparison, the
same-channel cross-session cases fail, and the cross-channel result is sparse and
uncertain. No new header field or byte mapping follows from these retrieval scores.

`episode_controls.py` saves all galleries, query IDs, directed endpoint comparisons,
scores, metadata baselines, source hashes and summaries to ignored
`local/episode-controls.json`. Two tests cover unbiased handling of score ties
and distinguishing missing T-state information from different T-states. They pass,
as does Ruff. The original batch's scripts, results and fixtures are unchanged.
