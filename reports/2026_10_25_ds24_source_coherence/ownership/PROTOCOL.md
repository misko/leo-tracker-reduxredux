# Native ownership trace, frozen before the local plots

Use only the archived DS24-0013 observations, tracks and public tracking export.
The three source identities are unchanged: RX2 CH3/T002 (24 IDs), CH4/T000
(43) and CH5/T001 (57). This is an exposed development diagnostic selected
after inspection of the previous prediction residuals, not fresh validation.

Fixed windows: CH3 [210,245] s, CH4 [235,270] s and CH5 [210,270] s.
Keep all native winners and all stored candidate peaks from every original RX2
probe in those channel/time windows. Do not restrict by proximity to 57450 or
any other orbit prediction. The full channel-CFO panel has no response cut;
the detail panel shows the selected owner's CFO range plus a fixed 10 kHz
margin. Preserve every window row in CSV even when outside the detail view.

Reconstruct native IDs/times/winning peaks through the original fast
`evaluate_ds22_merged_tracks.winners` / `frequency_evidence` public adapter and
verify exact agreement with observations.json. Trace each graph index through
its original receiver/channel/actual-RF lane to the same native ID; assert all
graph ownership is unique. Graph values use native CFO minus two periods for
the three selected sources. Apply that SAME shift to every local winner and
archived additional peak, with no nearest-curve wrapping or alias selection.

Mark original graph membership and original baseline accepted membership.
Stored candidates other than the winning gated maximum-margin candidate are
archived additional peaks, not independent observations. Retain their original
gate flags and ranks. A probe with no passing candidate has no public winner;
that absence is reported rather than filled with an alternate peak.

Produce native winner/peak/track CSVs, input hashes, a local ownership figure
and descriptive counts/gaps. No new polynomial or physical fit, orbit score,
point reassignment/deletion, position/GPS read, IQ extraction or RF acquisition.
Metadata/plot computation is capped at 180 seconds, one BLAS thread. Freeze
source, owned tests, this design and input hashes before running the trace.

Preparation01 stopped before processing because the adaptive timing port does
not accept this fast export's clock_anchor schema. Preparation02 corrects only
that adapter choice to the same fast port that originally generated these
observations. The windows, peak policy, ownership and all scientific scope are
unchanged; the first source, protocol and failure are retained.
