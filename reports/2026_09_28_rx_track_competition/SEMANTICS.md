# Track competition and single-present-state semantics

## Finding

The current geometry/presence likelihood treats every `(track_id, catalog_number)` component in an
exact RF lane as a mutually exclusive **alternative state**. At a window the hidden state is either
absent or exactly one nominated track-candidate component. The upstream reconstruction and frozen
artifacts do not establish that different mapped tracks are physically exclusive. They also do not
establish that concurrent tracks are different real satellites. Exclusivity is therefore a model
assumption and capacity limitation, not a fact supplied by the public trajectory graph.

This distinction matters for interpreting occupancy, candidate posteriors and geometry scores. The
model answers which single nominated explanation best accounts for a paired candidate set under an
at-most-one-present assumption. It does not estimate the number of simultaneously present emitters
and cannot represent two nominated track states as active together.

## How tracks enter the dataset

The candidate-bank stage reconstructs training-only public tracks and freezes at most three per
recording by latest training end time and track ID, explicitly without consulting candidate scores
([`rx_training_candidate_bank.py`](../../tools/rx_training_candidate_bank.py#L133)). Each selected
track is ranked against the causal catalogue independently; its own top three candidates and
retained catalogue mass are exported
([`rx_training_candidate_bank.py`](../../tools/rx_training_candidate_bank.py#L434)). There is no
cross-track assignment constraint at this stage and no statement that one selected track excludes
another.

The alias mapper then binds each frozen track separately to its own exact public graph points and
observation IDs ([`rx_training_alias_mapping.py`](../../tools/rx_training_alias_mapping.py#L119)).
Its one-to-one checks prevent provenance collapse within a track, but do not declare separate tracks
to be competing physical alternatives.

When the geometry dataset groups mapped tracks into one exact
`(session, channel, edge, actual_RF)` lane, it assigns each track equal mass
`1 / number_of_mapped_tracks` ([`rx_geometry_dataset.py`](../../tools/rx_geometry_dataset.py#L225)).
Within each track it distributes retained mass according to that track's normalized training
likelihood ([`rx_geometry_dataset.py`](../../tools/rx_geometry_dataset.py#L246)). Thus a lane with
two tracks and three candidates per track becomes six track-candidate components in one mixture.
This construction explicitly makes tracks alternatives in the downstream prior; it does not derive
that relationship from reconstruction.

The dataset also creates an `other` component by combining omitted-catalogue mass across tracks
([`rx_geometry_dataset.py`](../../tools/rx_geometry_dataset.py#L276)). `prepare_lanes` removes that
terminal component, conditionally renormalizes only the retained track-candidate components, and
passes that vector to the presence model
([`rx_presence_geometry.py`](../../tools/rx_presence_geometry.py#L55)). Consequently the fitted
presence experiments distinguish absence from the retained nominee mixture, but they do not retain
the dataset's omitted-catalogue branch as a separate hidden state.

## The hidden-state restriction

`initial_log_prior` constructs a vector consisting of one absent state followed by the normalized
candidate states. Occupancy supplies total present mass, which is divided across that one candidate
axis ([`rx_presence_filter.py`](../../tools/rx_presence_filter.py#L29)). The transition matrix either
persists the current single state or refreshes to that same stationary categorical distribution
([`rx_presence_filter.py`](../../tools/rx_presence_filter.py#L46)). No state represents a subset or
combination of tracks.

The joint fitter makes this explicit in array shape: it allocates `max_nominees + 1` states, puts
absence in state zero, and places one candidate in each remaining state
([`rx_joint_geometry_fit.py`](../../tools/rx_joint_geometry_fit.py#L61)). Each candidate-state
emission permits a zero/one signal assignment independently in RX0 and RX1; the four patterns are
`(0,0), (0,1), (1,0), (1,1)`
([`rx_empirical_signal.py`](../../tools/rx_empirical_signal.py#L87)). Extra observed detector
candidates are handled by the background term. There is no emission in which two nominated track
components each contribute a signal in the same receiver window.

Therefore:

- several raw detector candidates may coexist in an observed set, but under a chosen hidden state
  at most one per receiver is assigned to that state's signal and the rest are background;
- the filter can switch from one track-candidate state to another over time, but cannot keep both
  active in the same window;
- “presence probability” is probability that one retained nominee state is active, conditional on
  this model, rather than probability that at least one among an unrestricted collection of
  coexisting emitters is present; and
- nomination posterior weights compare exclusive track-candidate explanations. They are not
  physical source-count probabilities.

## What the frozen artifacts show

The original pilot dataset has 19 eligible lanes and 90 track-candidate components. Ten lanes have
one mapped track, seven have two, and two have three. The DS8 dataset has eight lanes and 36
track-candidate components; four lanes have one mapped track and four have two. Thus the exclusivity
assumption is operative in 9/19 pilot lanes and 4/8 DS8 lanes, rather than being a theoretical edge
case.

Different tracks in the same lane can have training points in the same source window. Counting all
receiver anchors, the pilot's 13 same-lane track pairs share 294 pair-window instances, and DS8's
four pairs share 85. That broad count mixes two materially different structures. A track reconstructed
on RX0 and another on RX1 can be two detector views of one underlying object; their simultaneous
points do not support independent per-track presence.

The stricter exact-same-receiver audit finds four pilot track pairs with 88 shared source windows
and one DS8 pair with nine. Their graph observation IDs and public candidate IDs are distinct within
each shared same-receiver window. This proves only recorded detector multiplicity: the public graph
can retain two distinct same-RX observations and assign them to different tracklets at one sampled
window. It refutes an interpretation that reconstruction itself guarantees exclusivity, but it
still does not distinguish two physical emitters from aliases, clutter or track fragmentation.

The artifacts also attach the same catalogue number to more than one track within some lanes: 14
lane/catalogue instances in the pilot and 9 in DS8. Most are cross-receiver: in the pilot, 13/14
such lane/catalogue instances attach the same catalogue hypothesis to RX0- and RX1-anchored tracks;
in DS8 all 9 do. The remaining pilot instance is a same-receiver duplicate. The downstream model
treats every `(track_id, catalogue)` pair as a distinct exclusive state even when two states name
the same catalogue object. Cross-receiver shared-catalogue pairs are strong deduplication candidates,
not evidence for two independently present targets.

None of these structural facts proves simultaneous physical targets. Separate detector candidates
or reconstructed tracks can arise from clutter, aliases, trajectory fragmentation, repeated
hypotheses, or multiple emitters. There are no decoded common-emitter labels or external satellite
truth labels in these artifacts. The correct conclusion is that coexistence is **allowed by the
upstream representation and unresolved by the evidence**, while the likelihood imposes
exclusivity for tractability.

## Consequence and bounded next correction

The single-state model remains a valid, clearly specified predictive approximation, but its
occupancy and identity posteriors should not be used as multi-target physical claims. A lane with
several reconstructed tracks can be poorly scored when evidence supports more than one component,
and the filter may explain concurrent evidence as background or rapid state switching. Equal track
prior mass also means adding or fragmenting a reconstructed track changes the component prior even
without new physical information.

The competition diagnostic also bounds what extra state capacity could repair. On DS8 held windows,
even the optimistic indicator that **any** retained nominee lies within 500 Hz is only 1.2752% for
RX0 and 0.8369% for RX1, averaged equally by record. Those are post-outcome compatibility ceilings,
not likelihood scores or calibrated probabilities. They show that allowing all current tracks to
be present simultaneously is unlikely by itself to restore the collapsed later frequency alignment:
most held windows have no close retained forecast to activate.

The next priority is therefore deduplication and association semantics, before a multi-target fit.
Construct a forecast-only equivalence audit that groups cross-receiver tracks sharing catalogue,
lane, overlapping prefix epochs and compatible receiver-calibrated trajectories, while preserving
same-receiver distinct observations and uncertainty. Compare the current track-candidate prior with
a grouped physical-hypothesis prior in which receiver views of the same catalogue share one presence
state and contribute paired emissions. This must remain a hypothesis grouping, not a truth label.

Only after that grouping is frozen should a bounded multi-target extension be considered. Candidate
identities within one grouped object remain exclusive; genuinely distinct groups may coexist under
an independent or tightly capped subset state. The omitted-catalogue branch and absence must remain
separate. Calibration-only fitting, held predictive density and explicit complexity control are
required, with no decoded-target or source-count claim. The same-receiver multiplicity establishes
that a coexistence-capable model may be worth testing, while the dominant cross-receiver duplication
and weak held ceilings show why independent presence for every raw track is not yet justified.
