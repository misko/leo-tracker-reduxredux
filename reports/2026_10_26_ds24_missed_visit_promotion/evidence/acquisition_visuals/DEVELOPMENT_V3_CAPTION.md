# Development figure v3: layout correction

Publication uses `reserved_glrt_blocks_v2.png` / `.pdf` together with
`development_glrt_blocks_v3.png` / `.pdf`. All earlier assets remain preserved.

Development v3 reserves additional fixed space above the first row for the main
title and legend. The plotted native owner IDs, times, measured CFO, categories,
intervals, panel counts and axis ranges are exactly equal to v2. Only subplot
spacing changed. Visual inspection confirms that the legend and both first-row
titles are now separated.

**Caption.** Measured CFO in eight nominated development blocks, each restricted
to its exact 24-second interval and selected channel. Columns show RX1/native0
and RX2/native1. Original GLRT points are gray; new points retained in curved
graph support are green, new points in other graph support are orange, and new
points outside the graph are red. Classification uses the full recording.
Native CFO branches are shown as stored without unwrapping, alias correction or
fitted satellite curves. The figure contains 165 original points and 105 new
owners: 69 curved, 19 in other graph support and 17 outside the graph.

`development_layout_v3_manifest.json` binds the corrected figure, source,
unchanged plotted data and exact v2 comparison. No IQ, GPS or position endpoints
were read; all sealed acquisition inputs remain unchanged.
