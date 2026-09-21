# Visit 678 second-source neighbor screen

This bounded follow-up examines the second phase-blind pair found at visit 678
of `scan-hop-34c0b0e1ae062f97`. It uses twenty shared-visit indices nearest 678
on the selected long track. Visit 678 is reproduced; the other nineteen visits
were not part of the preceding twelve-visit replay. Selection uses visit
distance only and does not use phase, coherence, or result quality.

The selected visits are `622, 642, 654, 658, 670, 678, 690, 698, 702, 706,
709, 719, 723, 726, 729, 733, 739, 743, 746, 749`. Bounded delay controls at
visits 622, 709, and 749 all selected zero samples.

Nineteen visits contain one corrected dual-receiver pair. Only visit 678
contains two. The nearest screened visits before and after it, 670 and 690,
contain one pair. The secondary path therefore has one observed visit in this
twenty-visit screen; no multi-visit duration or trajectory is established.

At visit 678, the selected long-track path begins at 40 ms within the visit and
uses candidate ranks RX0=2 and RX1=0 with integer epoch sample 1818. Its RX0
tracking CFO is 455071.85 Hz. The isolated secondary path begins at 80 ms and
uses candidate ranks RX0=0 and RX1=2 with integer epoch sample 1697. Its RX0
tracking CFO is 339691.36 Hz. The corresponding corrected-pair resultants are
0.9538 and 0.9565; phase standard errors are 4.04° and 3.92°; exact-to-control
floors are 14.76 and 13.70.

The secondary 80 ms path is absent as a dual pair from the persisted tracking
projection and consequently has no published trajectory identity. This is an
isolated same-visit raw-analysis candidate for matched-pilot follow-up. This
screen does not run matched-pilot double differences and makes no geometric
phase claim. The generic tool's legacy `double_differences` value remains an
asynchronous-centroid diagnostic only.

Files:

- `scan-hop-34c0b0e1ae062f97.visit678-neighbors.raw-coherence.json`: complete generic-tool result
- `scan-hop-34c0b0e1ae062f97.visit678-neighbors.raw-coherence.png`: rendered result
- `summary.json`: visit timeline, exact seed paths, controls, and interpretation
