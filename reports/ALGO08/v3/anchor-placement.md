# One-in-eight causal full-anchor placement

The tested lagged-occupancy rule adds one installed-owned signed match on the
fully observed DS30-0049 prefix and loses one on the independently observed
DS30-0016 stratum, relative to periodic anchors. Moving every full call to the
last slot gives a larger improvement on 0049 at the same call count. The
adaptive schedule also reduces the complete held-anchor witnesses on 0049
from 44 to 20 per radio. Retain periodic placement for the existing receiver.
[Frozen rule and scopes](anchor-placement-protocol.md) · [Sealed schedules and readout](measurements/anchor-placement.json.gz)

## Matched callback budgets

Every complete block has eight admitted stereo visits in the same
`(pilot edge, channel, actual RF)` stream. The original rule pays full at the
first visit. The fixed-late control pays full at the last. The adaptive rule
buys full on the first opportunity after two immediately preceding short
visits were empty on both radios within eight seconds, or uses the last slot
when the block's full call is still available. It checks only the earlier
paid outputs and current acquisition metadata. Full and short calls stay
stereo, and every included lane receives one detector call.

| Scope, complete cycles | Full / short lane calls | Signed reference matches, periodic / fixed late / adaptive | Installed-owner matches, periodic / fixed late / adaptive | Best same-budget hindsight matches / owners |
| --- | ---: | ---: | ---: | ---: |
| 0049, 352 stereo visits | 88 / 616 | 125 / 129 / 126 of 178 | 73 / 77 / 74 of 95 | 148 / 86 |
| 0016 paired stratum, 592 stereo visits | 148 / 1,036 | 242 / 247 / 247 of 365 | 86 / 84 / 85 of 93 | 291 / 90 |

A signed match uses 250 Hz original signed CFO and two fractional samples
on the existing 13,333-sample search circle. The installed owner readouts
are identical for the fixed-zero and fitted calibration rosters on these
scopes. The adaptive policy on 0049 gained seven signed matches and lost
six relative to periodic, with two gained and one lost among owners. It
recovered one of seven originally emptied owner lanes and neither of two
displaced owners. Fixed late recovered three of the seven emptied owners,
and matched four more owner lanes overall. On 0016 adaptive gained
13 matches and lost eight. Among original owners it recovered one of five
displaced lanes and lost two other matches. Counts refer to retained signed
factors on archived owner opportunities.

The hindsight ceiling scores each stereo opportunity's two observed full
results against its two observed short results. Each complete block picks
the largest net signed match gain over the all-short block. Optimizing only
for 0049 formerly empty owners could restore six of seven. Optimizing only
for its displaced owners could restore both. The corresponding 0016
displaced-owner ceiling is four of five. The separate maxima can require
different full calls. They bound the explicitly measured pre-held matching
objectives.

## Native cost on the measured operands

The clock sums use the archived native CPU at the selected aperture on
each lane. They exclude new policy overhead and other process costs.

| Scope, complete cycles | Periodic | Fixed late | Adaptive | Additional cost if adaptive also paid short first | Short-first total vs periodic |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0049 prefix | 732.209 ms | 738.704 ms | 721.802 ms | 76.515 ms | +66.107 ms |
| 0016 paired stratum | 1,241.407 ms | 1,217.357 ms | 1,223.167 ms | 129.559 ms | +111.320 ms |

The causal rule needs zero current-lane short-first calls. The table prices
the hypothetical two-callback implementation as separate native calls at
the adaptive rule's selected full lanes. The 0049 incomplete tails
contribute two full stereo visits under periodic and zero under fixed
late or adaptive. In the 0016 paired stratum, the incomplete tails
contribute six, zero and two full stereo visits in the same order. Equal
call counts hold on the complete cycles above.

## Chronology and limits of the held transfer

The 0049 factorial has genuine dual-aperture data on all 724 admitted lanes
of the six-member prefix and reproduces the original aperture diagonals.
Replaying the released causal Continuation on every selected row in order
produced 73 / 75 / 72 installed-owner matches for periodic, fixed late and
adaptive across that full prefix. The original fixed-role held log-score
gains reproduced the existing receipt at −7.066 / −0.166 on RX0 / RX1.
Fixed late had 37 complete held witnesses per radio. Adaptive had 20 and
skipped 17 more per radio because another full call came before seven
short donors. Its diagnostic held gains were −3.751 / +3.621. The deployed
whole-record selector indexes fixed modulo-eight roles, so this diagnostic
alone cannot qualify an adaptive receiver.

The complete 0016 archive has 1,240 genuine dual-aperture lanes and 186
full-anchor lanes without a measured 8 ms alternate. Its independent replay
groups eight actually paired stereo visits and breaks the occupancy
history at every gap in original stream slots. If every missing original
anchor were demoted, 1,410 later lanes could refer to one of those unmeasured
short inputs within the released 12-opportunity, eight-second history.
An unknown predecessor differs from a measured empty. The held result
therefore covers the observed paired-opportunity stratum. It has no
complete 0016 continuation or position readout.

Full 0049 likewise lacks dual-aperture raw results outside its 724-lane
factorial prefix. The prior 0008 and 0169 first-member assays supplied
112/128 and 86/102 paired lanes. Existing ordinary installed/mixed
publications such as 0086 provide selected detector factors under their
original roles. They cannot recover the alternate raw candidates or replay
their causal predecessor histories after relocation. The two evaluated
physical captures are separate acquisitions from the same roof.
[Earlier fixed-phase audit](staggered-anchors.md) · [Measured aperture arrays](ds30-0049-receiver-factorial.md) · [Measured independent strata](late-pilot-rescue.md)

The schedule was frozen at `bbf901c5b`. The readout source is
`b2f84209a`. Five component tests passed. The sealed prediction SHA-256 is
`a423a180e0a98108fefd0559a4e0d27c28d399c2f7aab0c950fd5c511231db91`
and the result SHA-256 is
`6676b69043fd1fbf129736eee286028acd21406215d23dd7a2e5087690a0c7d6`.
Only previously saved arrays and the installed Continuation component were
opened. Zero waveform, detector, solver or benchmark jobs were launched.
