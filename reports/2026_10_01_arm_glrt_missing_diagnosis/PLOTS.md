# CFO versus time for the cutoff ablation

`cfo-cutoff-comparison.png` / `.pdf` show the same 85 replayed dwells and both
receivers in all columns. Left: original ARM passing detections. Middle:
cutoff-disabled evaluated candidates, including gray points rejected by the
final GLRT margin gate. Right: cutoff-disabled passing candidates only.
Hollow circles are passing server candidates; green indicates server CFO
agreement and orange crosses indicate no such agreement. Bottom ticks mark
the selected replay times. Unmarked gaps are not cutoff-disabled scan results.

| Candidate entries across 170 receiver windows | Original | Coarse cutoff disabled |
|---|---:|---:|
| Evaluated | 342 | 1,360 |
| Rejected by final margin gate | 9 | 715 |
| Passed final margin >=0.025 | 333 | 645 |
| Passing with server CFO agreement | 318 | 544 |
| Passing without server CFO agreement | 15 | 101 |

Agreement means same visit and receiver, with circular CFO difference
normalized to 11.2 GHz <=2.5 kHz. This is not one-to-one matching and has no
epoch gate; counts include duplicate candidate hypotheses, not unique signals.
Orange entries are not proven noise or false positives. The deliberately
selected missing-detection dwells cannot estimate a full-scan false-positive
rate. Raw CFO in the overview is not dealiased, and channels are combined
within each receiver; an agreeing candidate may appear on another CFO alias.

`cfo-recovered-track-zooms.png` / `.pdf` show the five target server tracks,
their existing ARM detections, and the 67 newly recovered source detections.
Only target-matching points are shown in those zooms. CFO aliases are aligned
to the reference solely for display. The zooms show detection availability,
not newly reconstructed track membership. Extra candidates remain visible in
the overview.

Run `plot_cfo.py` with the scientific Python environment to regenerate both
figures and `plot-counts.json`. No new detector run or threshold change was
performed to generate these plots.
