# DS21-039 saved-point selector comparison

The all-first selector retains the combined-view minimum that the original low-first selector excludes. This is a verified selection difference, not a new position estimate. The 0.5 km target remains unmet.

The [prespecified control](DISCOVERY_SELECTOR_CONTROL_PROTOCOL.md) completed in **4.680387 seconds**, using the same 100 saved fitted-c discovery points, zero preparation calls and zero optimizer calls. Original selection reproduced the parent's full selected rows exactly. No held observations or reference coordinates were accessed. The component and runner passed 22 tests; source and parent bindings are validated by the completed-terminal reader.

| Selection order | Three selected centers, east/north km | Candidate union |
| --- | --- | --- |
| Original: low, high, all | (-112.5, -87.5); (-75, 225); (-125, -75) | 39 |
| Alternative: all, low, high | (-106.25, -93.75); (-118.75, -93.75); (-75, 225) | 36 |

The original low winner blocks the all/high minimum at a distance of 8.838835 km under the unchanged 12.5 km separation rule. All-first retains that minimum; it blocks the low minimum and records the high minimum as a duplicate. Its second center is exactly 12.5 km from the first and therefore remains eligible. Both conditions still include the distant (-75, 225) fallback; reordering does not eliminate every questionable proposal.

The first selected point's saved all-view training objective changes from 35,275.917467 to 34,593.563198. These are saved point-specific fits and candidate sets, not a common-support likelihood comparison or evidence of better localization.

The two selected candidate unions share 33 satellites. All-first adds 52606, 62824 and 67629, and omits 48019, 56915, 58009, 58094, 59889 and 62844. These changes arise from the same union rule applied to different selected points. A downstream comparison must preserve and report this induced pool difference.

Next, both conditions require the same five initialization stages and A/B/C fitting budgets in separate namespaces. A qualified legacy-parent adapter is being implemented. Neither condition has downstream localization results yet, and the historical final fit cannot substitute for a matched control.

## Reproducibility

Local receipt namespace: `reports/2026_10_13_ds21_039_root_cause/local/discovery-selector-control-v1`. Source implementation: commit `43ed6632b`. Protocol was published before execution at remote-main commit `ab414ea20`.

| Receipt | SHA-256 |
| --- | --- |
| Protocol | `c89e15d658cf4ed0c4140a0d388e183afa7b969bcf3d1750578a5c8fad88986a` |
| Terminal | `b7a72e8914d36c7a4fce4a0a3a15d3b0ba30c4ffe00792af460232fb853fb3c0` |
| Launch | `95c7a833e8c24f39cc155fd448164d989fa14b1fe733a104633b9d29978f2ca8` |
| Termination | `12adc964e9dc8b270110ba4ad0fcacf0241061aa3e0bc53c39c2ca31e001877c` |
