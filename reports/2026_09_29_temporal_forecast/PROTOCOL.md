# Recent-window versus cumulative-source prediction

Use the existing 24-scan pool per DS7/DS8/DS9, ordered early8, middle8, late8.
Fit a new cumulative early+middle16 location with original q020 and the same
six fixed cold/timing-grid starts. Compare to the existing qualified six-start
early8 and middle8 locations after exact session and training-score replays.
Choose endpoints only by qualified training likelihood.

Predict every late8 scan from each of those three fixed source locations with
the same q020 score, integrating one shared timing offset per target scan.
Require all source scans to end before the first target begins and disjoint
session IDs. No late measurements inform any source fit or model selection.
The late data have been examined in other research; this is a chronological
holdout comparison, not a previously unseen validation dataset.

Report all three datasets, aggregate scores and per-target differences. Source
reference errors are secondary exposed unsurveyed diagnostics, not the selection
criterion. Test whether recency outperforms older or cumulative data; do not
infer a physical drift cause from that comparison alone.

Save cumulative fits before evaluation. Three workers capped at 300 seconds;
retain failures and usual timing quadrature/optimizer qualification gates.
No new RF, production changes or publication.
