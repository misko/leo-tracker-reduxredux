# Training-only receiver mapping and recorded detection-order feasibility

This stage recovers the raw-frequency coordinate for the existing frozen 30-track forecast bank and constructs conservative matched-proxy sequences. It does not refit satellite ranks, position, reception coefficients or forecast frequencies. No matched-frequency residual is an independent validation endpoint: matching itself uses frequency.

## Training mapping

Use hash-verified derived caches and the frozen grouped partitions. Drop every non-training probe before public projection/reconstruction. Reproduce the bank's selected track and observation identities exactly. Preserve public tracklet points, native CFO, relative alias integer, receiver, channel, edge, actual RF, and source provenance. Verify the public relation

`normalized_dealiased_hz = (11.2 GHz / actual_RF) * (native_CFO_hz - alias_index * (1 / 4.4 us))`.

Do not choose a new alias integer from future detections. Matching uses a wrapped residual and explicitly leaves the integer ambiguity unresolved.

Estimate RX1-minus-RX0 CFO bias separately for each recording/channel/edge/actual-RF lane using training probes only. Epoch compatibility is modulo 1/750 s with a fixed 2.2 us tolerance. Fix a 5 kHz modal bin, initial median, then one nearest compatible vote per paired training window within 10 kHz of the initial estimate; use the median of those votes. Transfer requires at least ten distinct training windows and median absolute deviation no greater than 2.5 kHz. Preserve counts and failures; no transfer for an unsupported lane. These are proxy pairings, not decoded shared-target identity.

## Future sequence construction

Freeze the mapping artifact before consuming later candidate outcomes. Retain all visible forecast windows with exactly the training track's channel, edge and actual RF. Require both qualified receiver views and a qualified training bias for a dual-receiver sequence. Other lanes, invisible forecasts, missing or inconsistent probes and unsupported transfer are explicit exclusions, never target non-detections.

The frozen forecast includes its anchor receiver's fitted CFO. Convert to native frequency using the track RF scale; apply the training lane's signed RX1-minus-RX0 bias to the other receiver. Match passed raw candidates using a fixed 2.5 kHz gate in canonical normalized frequency with wrapped alias spacing. Keep all matching source-candidate keys rather than choosing the closest future detection. Matching more than one frozen track/candidate hypothesis makes that raw observation ambiguous; ambiguity is not a unique hit or a miss.

Multiple compatible raw candidates for one hypothesis are also ambiguous. A mixture of unique and colliding matches cannot produce a unique hit. Calibration bias and its MAD threshold are in native Hz; the future matching gate is in canonical Hz.

Construct sequences separately for reception and held-frequency periods. A first hit on the first eligible window is left-censored. No hit is right-censored; missing or ambiguous evidence before a first unique hit prevents an uncensored first-hit claim. A same-window first hit on both receivers is tied. Any lag is a lag between recorded proxy hits, not physical beam entry, target identification, calibrated direction or geographic accuracy.

Retain hypothesis-level sequences even when ambiguous, but report unique-hit, ambiguous-hit and no-compatible-hit counts separately. Do not sum duplicated hypotheses as independent events. Candidate weights remain frozen. Do not use the resulting gated residuals to claim held-frequency improvement or update the original bank.

## Execution and acceptance

Read only existing derived caches, bank predictions, grouped partitions and recorded opportunities; no RF, raw IQ or QNAP mutation. One numerical thread, nice 19, 4 GiB address space and a 300-second bound for each serialized stage. Test the installed public mapping interfaces before the real training reconstruction. Freeze source/code/runtime hashes and exact commands, retain failures, and do not expand numerical work or tune thresholds after looking at future matches.

Acceptance requires exact mapping reproduction, no non-training calibration inputs, complete future-window accounting, and explicit ambiguity/censoring. A completed feasibility export is not a positive detection-order result. New association-confidence evidence requires a separately frozen, ungated frequency endpoint and a tested reception model.
