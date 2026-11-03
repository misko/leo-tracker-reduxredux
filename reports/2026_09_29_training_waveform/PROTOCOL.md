# Training-selected matched waveform frequency test

Freeze before selection. In each of nine eight-scan target panels, take the first
chronological recording at >=5 MS/s. For each RX select the eligible bank track
with earliest training-observation time (track ID breaks ties), then its earliest
training observation. No pilot margin, held visit, waveform quality or geographic
error selects an excerpt. Upstream track construction and frozen panel membership
already used the full recordings; this does not repair those inherited conditions.

Bind selected observations back to the public candidate projection and reconstructed
track. Read only their existing 20-ms probes via the public read-only IQ port.
Demodulate first eight complete frames using cached acquisition epoch/frequency,
with no data-dependent phase/timing correction. Keep published in-band pilots
inside 0.45*sample_rate of capture center, requiring at least two carriers.
Record all selection/extraction/demodulation failures; do not replace them.

Compare cached frequency (zero residual), short-pilot residual frequency fitted
on symbols2–65, and long-pilot residual fitted on22–221. One frequency per excerpt
across eight frames, independent complex gains per frame/carrier, no interframe
phase assumption. Fixed residual search [-1500,1500] Hz, 25-Hz grid, refine within
neighboring grid points. Retain endpoints and mark boundary estimates.

For all arms fit gains on the same symbols22–221 and predict held symbols222–301.
Report all frame NMSE, equal-excerpt means, frequency changes and bounds; no
quality filtering. This is a research comparison, not an exact reimplementation
of deployed GLRT64, independent Doppler truth or localization evaluation.
Extraction120s and numerical replay120s, one process/thread each; no new RF.
