# Coherent carrier fragments remain in the high-coverage result

The saved fitted-c `b1000-profile` result assigns462/693 requested GLRT winners,
leaving231 unassociated. Several leftovers form smooth raw-carrier fragments;
they are not all isolated scatter. This is a descriptive inspection of one
already full-data-fitted development result. Smoothness does not establish a
satellite identity, correct orbit, detection validity or geographic recovery.

All15 immutable memberships and saved association flags were matched by global
observation ID. No prediction, TLE, candidate assignment, station reference,
localization fit, source preparation or held test was used. The one bounded
array audit completed in approximately0.16s; all three owned synthetic tests
pass. Source hashes and all extracted observations are retained.

## Representative remaining fragments

Receiver labels below use the original human-facing RX1/RX2 convention. Times
are seconds from each source's scan start. These examples come from the frozen
automatic extraction, ranked by unassociated count; the complete177-fragment
inventory is in [fragments.json](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_17_dsx01_iteration11/highcoverage_track_audit/fragments.json)
and [fragments.csv](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_17_dsx01_iteration11/highcoverage_track_audit/fragments.csv).
The error columns are departures from a descriptive quadratic in CFO versus
time, **not residuals to a satellite prediction**.

| Window | Lane | Time span s | Unassociated / fragment points | Local CFO span kHz | Quadratic RMS Hz | Leave-one-out RMS Hz |
|---|---|---:|---:|---:|---:|---:|
| 002 | S01 RX1 CH2 |68.536–73.144|8/8|15.754|42.9|74.7|
| 003 | S01 RX1 CH2 |176.416–181.029|9/9|12.369|37.7|59.9|
| 003 | S01 RX1 CH2 |184.229–187.069|6/6|8.486|25.7|46.2|
| 004 | S02 RX1 CH1 |72.781–78.460|9/9|15.738|104.2|177.2|
| 004 | S02 RX1 CH1 |88.045–90.883|6/6|8.759|69.8|133.5|
| 006 | S02 RX2 CH2 |181.745–197.709|13/24|53.459|36.1|43.9|
| 011 | S04 RX2 CH3 |117.208–123.948|10/11|25.044|112.0|162.3|
| 012 | S04 RX1 CH3 |141.340–157.664|24/24|54.172|93.9|105.2|
| 014 | S05 RX1 CH4 |267.558–271.820|5/7|10.552|61.9|125.3|

Window012's long fragment is entirely unassociated while its raw CFO decreases
from−71.153 to−125.326kHz. Window003's two numerical examples decrease
−140.091→−152.460 and−162.164→−170.650kHz respectively; all27 members of that
window remain unassociated. In window006,13 unassociated points occur inside a
24-point smooth fragment; fitting only those13 gives RMS15.9Hz and
leave-one-out RMS27.0Hz. Associated and unassociated points can therefore lie on
the same visually smooth branch without this classifier assigning every point.

Window004's first example contains one raw alias jump, and window011's example
contains six. Their small **local unwrapped** spans must not be confused with
their much larger native min/max spans. No claim that an alias-linked fragment
has a confirmed single emitter follows from these summaries.

## Every requested window

| Window | Source | Assigned / requested | Remaining |
|---|---|---:|---:|
|001|S01|80/86|6|
|002|S01|12/35|23|
|003|S01|0/27|27|
|004|S02|13/44|31|
|005|S02|33/33|0|
|006|S02|34/72|38|
|007|S03|54/54|0|
|008|S03|49/50|1|
|009|S03|34/34|0|
|010|S04|38/46|8|
|011|S04|23/43|20|
|012|S04|25/66|41|
|013|S05|23/28|5|
|014|S05|12/39|27|
|015|S05|32/36|4|
|Total|All5|462/693|231|

The full high-coverage endpoint also leaves5712/20084 context observations
unassociated, as counted by the parent's frozen plot inventory. This audit's
numerical fragmentation covers only the693 requested members; it does not
silently extend their231 denominator to the full recording.

## Extraction and interpretation limits

The unchanged old `model_b.build_tracklets` uses its450Hz circular prediction
gate,45s duration cap and24-point cap. It runs separately within each frozen
window and RX/channel/actual-RF lane, using all window members before annotating
association status. There is no satellite hypothesis or geometry in extraction.
Each row belongs to exactly one fragment. The fixed caps and local linking can
split one visible curve; small fragments are not evidence of noise.

Principal adjacent CFO differences are accumulated only inside each extracted
fragment, using alias period227272.727Hz. This selects a local numerical branch,
not an attested cycle count. A fixed quadratic is summarized for n≥5 and a
linear curve for3≤n<5. All shorter fragments remain in the inventory without
curve statistics. The CSV column `all_quadratic_rms_hz` denotes this prescribed
curve RMS; the JSON's explicit `degree` records the linear fallback. This label
does not change the computation.

Of the231 remaining points,151 occur in fragments containing at least five
total members;119 occur in fragments containing at least five unassociated
members. These overlapping descriptions are not significance tests, detection
rates, independently validated trajectories or a proposed recovery gate. The
membership was already selected for track-like structure, and the CFO-based
linker itself favors continuity. Leave-one-out residuals remain descriptive
within that selected sequence; they are not a new temporal validation study.

The parent's [raw-CFO panel](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_17_dsx01_unassociated_high_coverage/windows_raw_cfo.png),
[folded-CFO panel](/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_17_dsx01_unassociated_high_coverage/windows_folded.png)
and S04 full-channel page were inspected. They support the presence of coherent
leftover stripes, especially003 and012. Windows004/006/011 show why raw and
folded views are both needed: folding can place alias-separated branches close
together and does not prove that they share an emitter. The plots draw no
inferred connecting lines. No model change or further scientific run follows
this inspection.
