# Anchor-only causal continuation fails the preservation gate

The frozen selector removed **one of the 12 extra full anchors** on DS30-0049, an unowned lane, and removed **six of 71 installed-positive anchors**, including five installed owner IDs. All four extra anchors owned in both mixed calibration arms survived. The independent DS30-0016 replay confirmed the false-deletion problem with actual paid alternate ranks available. [Frozen policy](anchor-only-history-protocol.md) · [Signed row replay](measurements/anchor-only-history.json)

## Saved evidence and actual decisions

The authentic generation-2 DS30-0049 packets contain 986 issued visits, 932 admitted stereo visits and 242 full-anchor lanes. The mixed packet carries one measured winner or empty lane. The six-member factorial independently retained both verified full ranks through issued visit 383. The complete DS30-0016 receiver assay retained both ranks and the full original 20 ms callbacks for all 808 issued visits. At their available frontiers, the original strongest 20/8 ms mixed and released full 20 ms continuation paths exactly reproduce both published ordered factor lists on both radios, including empties. [0049 factorial and 0016 selected originals](ds30-0049-receiver-factorial.md) · [0016 raw-factor capture](late-pilot-rescue.md)

| Input and rule | Full-anchor lanes | Installed-positive | Mixed-positive → retained | Extra mixed anchors removed | Extra mixed owners removed | Installed-positive anchors deleted | Exact installed factors displaced |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS30-0049 complete, strongest only | 242 | 71 | 83 → 76 | 1 / 12 | 0 / 4 | 6 | 0 |
| DS30-0049 native frontier, strongest only | 92 | 22 | 30 → 29 | 0 / 8 | 0 / 3 | 1 | 0 |
| DS30-0049 native frontier, paid alternatives | 92 | 22 | 30 → 29 | 0 / 8 | 0 / 3 | 1 | 0 |
| DS30-0016 complete, strongest only | 186 | 58 | 74 → 62 | 2 / 16 | 0 / 2 | 10 | 0 |
| DS30-0016 complete, paid alternatives | 186 | 58 | 74 → 63 | 2 / 16 | 0 / 2 | 9 | 1 |

On 0049 all 71 installed positives were exact mixed matches. Eleven of the 12 extras had insufficient causal history. Each of the four mixed-owned extras had zero usable prior positives inside the last twelve original same-stream opportunities and eight seconds. Three were the first admitted opportunity on their stream. Simply deleting all protected full positives would also remove 13 installed-positive 0049 anchors. The one end-to-end-available deletion was visit 388, radio 0, beyond the raw-alternative frontier. No hidden rank was used or inferred for that visit. The 0049 prefix includes six anchors with both native candidates. None supplies a permitted switch. On 0016, 33 anchors have both measured candidates. The one allowed switch at visit 672, radio 0, retains an actual paid rank-one measurement and displaces the exact installed rank-zero row. It restores no installed factor.

## Runtime scope

The rule uses the released signed continuation vote on the same radio, channel, exact RF and pilot edge. It updates history from every original paid pre-policy input including empty opportunities. It can run before the existing mixed receiver exports its strongest factor. The optional full-candidate branch has both native candidates there on paid two-scan anchors. A reader of published packets can reproduce only the strongest-only branch unless the raw alternatives were saved independently.

Each admitted stereo visit costs two bounded history appends. Positive full anchors inspect at most twelve prior opportunities and evaluate up to two factors per radio. With one stored frequency per prior opportunity, each evaluated factor needs at most 144 seed/prediction comparisons. The actual replays called the vote function on 59 anchors in 932 visits for complete 0049, 18 times in 362 visits with paid alternatives in the 0049 prefix, and 56 times in 713 visits with paid alternatives on 0016. No extra native calls, I/Q reads, position fits, or Gauss measurements were made.

The old held-cycle selector changes the route for an entire recording based on held-anchor occupancy. The older past-anchor policy acts on short factors while preserving every anchor. The held-anchor stationarity audit uses two-sided nearest same-lane tracks and found few forecasts in sparse records. This replay changes only individual anchor decisions, preserving the original paid previous history. Previous paid anchors alone provide even less observed same-stream support at the four problematic times. [Held-cycle selector](anchor-cycle-route.md) · [Past-anchor exposure](anchor-exposure.md) · [Held anchor forecasts](held-anchor-stationarity.md)

The unchanged mixed route remains the tested configuration. A later proposal would need evidence available before the first same-stream detection, or an explicitly delayed local decision using later observations. This replay supplies no measured protection for a delayed decision. Any such rule would need an independent test before a scientific publication.
