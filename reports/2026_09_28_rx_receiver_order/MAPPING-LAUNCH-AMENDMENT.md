# Public observation provenance correction

The first frozen mapping invocation exited 1 after 10.51 seconds, before producing a mapping or matching future detections. Its launch, traceback, resource receipt and exit code are preserved under `mapping-*`.

The adapter had equated public projected candidate IDs with graph observation IDs. The forecast bank stores graph observation IDs, which are a different public identity. The corrected adapter joins each tracklet point through its projected candidate's source group to the corresponding public track graph observation, then verifies the complete frozen observation identity set and exports both IDs.

The corrected adapter also rejects duplicate probe locators instead of silently overwriting a window binding. The lane contract distinguishes exact session/channel/edge/RF from the anchor receiver, since a qualified training calibration explicitly supports the counterpart receiver. These are provenance/interface fixes; the source partitions, candidate bank, calibration thresholds, forecast frequencies and future matching gates remain fixed.

Regression coverage uses distinct candidate and observation IDs and the installed public graph interface. The corrected invocation receives a separate source-hash receipt, `mapping-corrected-launch.json`, before execution. No future outcomes were inspected to choose the correction.
