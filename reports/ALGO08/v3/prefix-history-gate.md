# A paid held-anchor prefix before visit thinning

The frozen 512-visit gate retained the guarded full-coverage route on all five saved recordings. It protected North, where every eligible prefix block favored history on both radios. It also retained full coverage on DS30-0008, even though **3,652 short lanes** after the checkpoint were structurally eligible for the fixed mask. Those lanes price at **3.899 CPU s gross** against the **3.490 s** dense target. The actual dense gate skipped zero lanes and cost 9.15 ms. This rule gives no acquisition saving. [Frozen protocol](prefix-history-gate-protocol.md) · [Sealed evidence](measurements/prefix-history-gate.json.gz)

| Original signed input | Complete held cycles per radio | Prefix gain, radio 0 / 1, nats | Original full EOF gain, radio 0 / 1, nats | Prefix action |
|---|---:|---:|---:|---|
| DS30-0008 | 63 | −10.985 / −8.738 | −117.994 / −63.989 | Full guarded |
| North | 64 | +18.938 / +25.525 | +28.366 / +26.345 | Full guarded |
| DS30-0016 | 55 | −9.435 / −7.908 | −15.273 / −8.948 | Full guarded |
| DS30-0057 | 48 | −8.023 / −11.349 | −29.002 / −43.663 | Full guarded |
| South | 64 | +7.120 / +10.296 | +12.510 / +12.521 | Full guarded |

The selector saw only the authentic paid pre-history 20/12 ms observations from issued visits 0–511. The complete packet was authenticated before slicing. Held anchors were erased before the unchanged causal continuation pass and read back only as outcomes. A cycle needed all seven paid donor visits. All cases met the frozen per-stream and per-block count and outcome support requirements. DS30-0008 radio 0 favored history by **1.181 nats on block 2**, with 16 complete held cycles. Weak radio 1 favored history on block 1 and weak radio 0 on blocks 2 and 3. Medium radio 1 favored history on block 2. The unqualified aggregate prefix winner happened to agree with EOF on all five cases. The measured block reversals leave no basis here for dropping the frozen guard. The conservative upper bound from a remaining unknown suffix also spans a possible flip on either radio in every case. [Original held-cycle selector](anchor-cycle-route.md)

| Recording | Paid 20 / 12 ms prefix calls | Prefix native model, CPU s | Measured prefix gate, ms CPU | Post-prefix short lanes / factors omitted if allowed | Potential gross, CPU s | Original whole-input work outside native detector, CPU s |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0008 | 128 / 894 | 1.310 | 9.15 | 3,652 / 1,975 | 3.899 | 15.053 |
| North | 128 / 896 | 1.184 | 7.16 | 400 / 175 | 0.420 | 3.867 |
| DS30-0016 | 116 / 796 | 1.050 | 6.26 | 148 / 55 | 0.146 | 1.805 |
| DS30-0057 | 106 / 714 | 0.978 | 7.33 | 1,104 / 470 | 1.106 | 5.656 |
| South | 128 / 896 | 1.123 | 6.38 | 400 / 116 | 0.399 | 2.714 |

Only the call and omitted-factor counts are exact. The CPU model uses native aperture means from each corresponding complete original acquisition, with original reads, decompression and authentication fully charged. The calls already paid at the checkpoint reduce dense theoretical gross savings from 4.207 to 3.899 CPU s. Charging the observed selector leaves 3.890 CPU s before any other overhead under the unselected counterfactual. The actual original EOF selector took 104.2 ms dense, 6.5 ms weak, 46.8 ms medium and about 8 ms on either simulation. North and South each spent about 4 ms more restoring original history. The guarded branch retains those usual EOF expenses and adds the early check. [Whole-stereo physical mask](whole-stereo-blocks.md)

No actual rollback was necessary. A hypothetical rollback on dense would pay all 3,652 omitted short calls again, estimated at 3.899 CPU s at the original mean with all signed waveforms and chronology available. Replaying those 1,826 omitted stereo windows would need access to 2.922 GB of original 20 ms CI16, or 1.753 GB if restoring only the short region. Any cursor replay, retained storage or decode, signed tail work and final history would add cost. Weak, medium and either simulated branch could require 118.4, 883.2 and 320.0 MB of retained full-window IQ respectively. A restored EOF score cannot use candidates from skipped lanes unless those lanes are actually acquired. The full EOF and skipped factor counts in this report are retrospective diagnostics only.

The test used the already authenticated exact DS30-0057 pre-history packet and the two existing independent simulated recordings. No solver, position reference, detector, new waveform or raw timing was used. Routing on held-anchor evidence alone does not measure position quality after thinning. No route change is supported by this frozen check. Three component tests passed. [Runner](prefix_history_gate.py) · [Tests](../../../tests/pipeline_eval/test_prefix_history_gate.py)
