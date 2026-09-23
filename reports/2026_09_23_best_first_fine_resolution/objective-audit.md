# 12.5 km selected-cell objective audit

This audit reads the frozen 34-track parent-linear baseline finalists. It does
not use truth data and does not recommend retaining or removing any track. The
search objective is the represented-second weighted mean of
`min(held-out RMS, 800 Hz)^2`, with unmatched tracks assigned 800 Hz.

| Selected cell | Capped objective RMS | Matched uncapped RMS | Tracks at or above cap | Top 3 / top 5 capped loss share |
| --- | ---: | ---: | ---: | ---: |
| Sacramento `(-93.75, -81.25)` km | 185.01 Hz | 190.92 Hz | 1 | 70.72% / 76.12% |
| Reno `(-243.75, -181.25)` km | 184.51 Hz | 188.55 Hz | 1 | 72.78% / 77.50% |

The same track, `…acd59c9a`, supplies 62.05% of Sacramento's capped loss and
62.39% of Reno's. Its held-out RMS is 840.75 Hz and 827.92 Hz respectively,
so the 800 Hz cap is active in both locations. It selects NORAD 67453 at the
`+5 s` tau boundary in both. The loss surface is therefore concentrated, but
not wholly determined, by this one capped boundary-tau track; the full fixed
34-track objective remains the reported search criterion.

At these two selected cells, that track contributes its fixed capped term rather
than its larger uncapped residual. Its high floor alone is not a reason to drop
the track, and this audit does not infer whether it is capped at neighboring
cells or how it changes their ranking.

| City | Next four capped-loss contributors after `…acd59c9a` |
| --- | --- |
| Sacramento | `…87b046af` 4.86%, `…4ec0a3dd` 3.81%, `…ac52c365` 2.84%, `…9381492d` 2.56% |
| Reno | `…9381492d` 5.37%, `…87b046af` 5.03%, `…6771ee2c` 2.43%, `…ac52c365` 2.28% |

There are no unmatched tracks at either finalist. Sacramento has six and Reno
has six tau-boundary fits; eight distinct tracks are on a boundary in at least
one city. Of 34 selected best-candidate identities, 29 NORAD choices match
between cities; five differ. Tau choices match for 21 tracks. The full track
IDs, held-out and capped residuals, loss shares, candidate identities, tau
flags, source digests, and cross-city comparison are in `objective-audit.json`.
