# C053 clock-enabled selection reversal is driven mainly by the low band

The sealed clock-enabled fits were replayed without optimization or reference-coordinate access. Differences below are closer/earlier minus distant/later negative log likelihood; negative values favor the closer endpoint. Original values come from the prior sealed union-endpoint assignment audit.

| Observations | Original NLL difference | Clock-enabled NLL difference |
|---|---:|---:|
| CH1–4 | +50.006 | −252.754 |
| CH5–8 | +186.497 | +80.162 |
| CH1 | −0.755 | −137.412 |
| CH2 | −11.430 | +34.523 |
| CH3 | −431.990 | −470.305 |
| CH4 | +494.181 | +320.440 |
| CH5 | +102.359 | +97.684 |
| CH6 | +14.165 | −53.557 |
| CH7 | −60.377 | −80.509 |
| CH8 | +130.351 | +116.543 |

The low band changes its preference by about 302.760 NLL units, and the high band's adverse difference falls by about 106.335. Their sum explains the likelihood reversal from +236.503 to −172.593. The remaining high-band preference for the distant solution means the original modeling conflict has not disappeared merely because the combined selector now chooses the closer region.

RX1/CH4 remains a substantial adverse group: its NLL difference falls from +361.493 to +284.962. Its signal mass at the closer endpoint rises from 12.680 to 36.545, but the distant endpoint's signal mass is 85.848. Other changes matter too, including CH1 and CH6. The result does not justify attributing the reversal to one receiver/channel correction alone.

This audit cannot establish that any satellite labels are correct. It identifies score and posterior changes under the tested calibration model. The selected error remains 10.055802 km, with no cohort promotion. A matched likelihood-only low/high ablation is next, retaining the same full-data candidate bank, calibration frame, priors and two starting states. Such a comparison must be labeled conditional because discovery and initialization already used all channels; it is not an independently discovered half-band benchmark.

Validation: saved objective/NLL replay within 1e-7; exact singleton likelihood/posterior closure; satellite/clutter transitions partition every window and NLL; channel, receiver and prespecified 30-second groups reconcile. The nonzero-clock component test and Ruff passed. Source `ea15eb36c`.

Runtime 11.717 seconds; four objective evaluations, four explicit orbit calls, zero optimizer calls. Output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-winner-clock-overlap-053-v1/`. Result SHA256 `87047ef4a23a91ffb1633724d98a1e78f85f48af3a5ce4f77559fa65b2b15e2c`; seal SHA256 `e5a9345811643aa7e4647f9efa12aa71f5a7ec1e2cfad606eac4af9a2ede0ba0`.
