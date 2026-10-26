# Single replay mechanism trace

After the primary frozen study, trace exactly the last declared physical slot,
DS24-0011 CH8, both RX, at the existing -24 dB strength. Do not select a new window.
Use identical synthesis/reference power and unchanged historical production search.
Read-only process-local wrappers capture acquisition results and input/output of
the coarse peak retention helper, returning exactly its original eight proposals.
Capture complete production candidates before the historical export filter.
Require exported candidate parity with the saved -24 dB primary results.

For diagnosis only, compute the same NMS ranking out to 256 proposals from the
already computed coarse score maps. Never refine/score/admit those extra proposals.
Report whether the truth timing neighborhood (within five native samples, the
existing NMS timing separation) and CFO neighborhood (within the existing fine
radius 80000 Hz) are present in the original eight or diagnostic 256 nominees.
Report the best local peak in that neighborhood, its coarse score and score rank
before NMS. The wider neighborhood is for tracking coarse basin availability and
does not relax the frozen final identity criterion. This is one paired physical
replay, at most 580 seconds, BLAS1, no raw IQ persistence or new RF.

The exact anchor tests one prespecified timing/CFO rather than searching roughly
21 CFO grid values times13333 timing cells, selecting eight coarse basins and
refining them. An anchor pass is neither deployable acquisition nor evidence of
equal false-alarm rate after a blind search. No threshold/whitening sweep.
