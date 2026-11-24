# DS30-0010 held transfer of full-anchor arrival evidence

The new independently held pair reproduces a near-zero stereo phase cluster on short visits. The cluster still cannot separate the installed-positive anchors from successor-only detections. Of the **863 installed-positive full anchors**, **191 lack a simultaneous peer**, and only **178** agree with both held offset estimates at the inherited two-sample tolerance. The 16 successor-owned extra anchors span compatible, incompatible, and absent peer evidence. This closes the previously missing transfer with no new selector. [Original freeze](anchor-arrival-authority-protocol.md) · [Sealed DS30-0010 census](measurements/anchor-arrival-0010.json)

The official generation-1 pair completed on the same raw authority and opportunity roster. Of 6,772 issued visits, 6,764 were admitted in both packets. The official successor audit records 1,694 native full lanes, 11,834 short lanes, an unfiltered receiver decision and zero CFO refinements. There were 940 mixed-positive full anchors, including every installed-positive anchor. Among those 863 shared positives, **828 have exactly the same published full factor**. The signed packets carry selected factors and empty opportunities. This transfer made no inference about any hidden alternate ranks.

| Anchor cohort | Count | With simultaneous peer | Within ±2 samples of both held offsets |
|---|---:|---:|---:|
| Installed-positive | 863 | 672 | 178 |
| Successor-only | 77 | 50 | 14 |
| Successor-only and owned by both successor arms | 16 | 12 | 3 |

Short stereo pairs in the early half give a center of **+0.0324 sample**, with 263 matches among 1,121 independent late pairs. The late half gives **−0.0288 sample**, with 193 matches among 1,016 early pairs. Both estimates exclude all target anchors. Of the 16 owned extras, 9 have a paid peer outside the tolerance of both centers, 4 have no peer, and 3 agree with both centers. Those three are on two stereo visits. Agreement alone leaves same-emitter identity and physical lane delay unverified. The ordinary packet's timing authority is null, as in the earlier physical cases. [Previous physical and simulated authority audit](anchor-arrival-authority.md)

Both successor arms contain **4,126** exact digest-verified owner rows, including 561 full anchors. Among the full anchors, 545 were installed-positive and 79 of those have no mixed peer. The installed manifests report **4,599 owners per arm** and their matching digests. They do not expose those observation IDs; the public scan-point ledger contains signed detections without owner labels. The number of installed-owned anchors lacking a peer therefore remains unavailable on 0010.

All 16 owned extras have at least two nearby paid short observations in the inherited 2.5-second window, but only eight have a two-point earlier secant and eight have a short observation on both sides. This is availability rather than matched-frequency or propagation evidence. The physical sign failure and sparse matched support of the earlier temporal studies still apply. No waveform, catalogue, new receiver callback, or solver was used. [Earlier arrival observability](../single-core-2x/arrival-observability.md) · [Directed donor evidence](directed-donor.md)

The metadata-only adapter binds the official pair, attempts, detector documents, manifests, native callback witness and exact successor owner rows before reporting the comparison. It seals the original frozen observables before joining installed selections or owner rows.

```sh
python -B -m reports.ALGO08.v3.anchor_arrival_0010 \
  /srv/postgres-nvme/leo-ds30-evaluation-20261124/cases/DS30-0010
```
