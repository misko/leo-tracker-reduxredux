# DS7/DS8/DS9: all-track symbol census and hierarchical clustering

The [DS10 extension](../2026_09_29_ds10_signal_extension/README.md) is the current
combined DS7–DS10 analysis set: 350 recordings, 21,480 recovered receiver tracks,
updated qualified correlations and repeat-candidate checks. This report and its
DS7–DS9 artifacts remain the frozen baseline.

## Findings

The excerpt census is complete: **199 recordings, 11,870 receiver tracks, and
47,480 recovered frames**, with no track-binding failures or decode exceptions.
Each track contributes four frames from one selected excerpt. This is not a
full-duration decode of every visit in those tracks.

We retained **429,955,200 complex observations**, including **316,003,200
non-pilot observations**. Only **738 tracks** pass the requirement that both
evaluation frames exceed the pilot-coherence gate. The other 11,132 remain in
the exploratory all-track hierarchy with their low-quality status visible.
They are excluded from qualified comparisons, not declared permanently undecodable.

| Dataset | Recordings | Tracks recovered | Tracks passing both pilot checks | Accepted 32-symbol-window candidates |
|---|---:|---:|---:|---:|
| DS7 | 69 | 4,038 | 242 | 563 |
| DS8 | 45 | 2,713 | 154 | 374 |
| DS9 | 85 | 5,119 | 342 | 1,467 |
| Total | 199 | 11,870 | 738 | 2,404 |

Across 25,830 windows from 2,583 individually pilot-qualified evaluation frames,
2,404 word candidates pass the single-receiver checks. Of these, **2,387 exactly
match the known generator**, spanning its 59 nonconstant states. The constant
state is rejected by the shuffled-word gate by construction. The remaining 17
observations comprise five exact bitwise inversions of known patterns, eleven
one-bit deviations, and one two-bit deviation. Polarity is diagnosed without
rewriting the observed bits. None establishes a new message field.

The 2,404 candidates include 458 observations from tracks with only one passing
evaluation frame; the qualified word hierarchies use the remaining **1,946**
observations. Neighboring windows and receivers are dependent, so these are not
counts of independent information units. There are 73 distinct observed strings,
including 14 distinct deviations from the positive-polarity generator.

| Rate | Tracks recovered | Tracks passing both pilot checks | 32-symbol-window candidates | Separate 64-symbol-tail candidates |
|---|---:|---:|---:|---:|
| 5 MS/s | 3,339 | 219 | 5 | 52 |
| 7.5 MS/s | 3,472 | 207 | 336 | 286 |
| 10 MS/s | 5,059 | 312 | 2,063 | 706 |

The two word assays use different lengths and locations and cannot be added
together as independent information. Their difference is especially relevant at
5 MS/s: the longer tail assay yields substantially more accepted candidates.
Short-window word clustering therefore underrepresents the narrowest recordings;
the phase-profile hierarchies still include their pilot-qualified tracks. These
observational counts are not a controlled sample-rate experiment.

No satellite identifier, positioning message, timing field, or FEC-validated
payload has been decoded. These hierarchies organize observed symbol structure;
they do not establish satellite classes.

## Clustering results

The full all-track hierarchy contains **70,442,515 pairwise distances**. Every
recovered track appears in it. The qualified views apply their stated quality
and coverage gates; excluded data are not imputed as matching observations.

| View | Entries | Figure |
|---|---:|---|
| All recovered phase shapes, including insufficient-quality excerpts | 11,870 | [Overview](local/clusters/all_recovered_phase_shapes/hierarchy.png) |
| Pilot-qualified phase shapes | 738 | [Overview](local/clusters/qualified_phase_shapes/hierarchy.png) |
| Upper-edge early symbol profiles | 252 | [Overview](local/clusters/upper_early_profiles/hierarchy.png) |
| Lower-edge early symbol profiles | 486 | [Overview](local/clusters/lower_early_profiles/hierarchy.png) |
| Qualified mean word bits | 367 | [Overview](local/clusters/qualified_mean_word_bits/hierarchy.png) |
| Qualified exact-word distributions | 367 | [Overview](local/clusters/qualified_observed_word_distributions/hierarchy.png) |

In the exact-word distribution view, **94.3% of track pairs have maximum distance**:
their short excerpts have no accepted word in common. The resulting large set of
tied distances makes much of that hierarchy's ordering uninformative. The mean-bit
view provides graded differences, while the early-region views examine other
structure; neither establishes satellite identity. Recording quality, repeated
states, shared receivers/sessions, and sparse temporal sampling remain relevant.

![Complete track hierarchy](local/clusters/all_recovered_phase_shapes/hierarchy.png)

The all-track view includes 11,132 excerpts failing the two-frame pilot gate.
Its branches can describe noise and calibration differences. Color scales show
the observed range; heatmap blocks average neighboring leaves and are not
individual track-pair cells.

![Graded word-bit hierarchy](local/clusters/qualified_mean_word_bits/hierarchy.png)

The word-bit view uses internally consistent candidates from 367 qualified tracks.
Its groups describe similarity of the observed words, not decoded satellite IDs.
The next useful step is longer excerpts and paired-receiver confirmation for
qualified suspected revisits, rather than interpreting these groups as identities.

## Scope and what “decode” means here

This study covers every frozen DS7/DS8/DS9 recording at **at least 5 MS/s**:
69 DS7 recordings, 45 DS8 recordings, and 85 DS9 recordings. The existing public
track exports contain **11,870 receiver tracks with span strictly greater than
three seconds**: 4,038 DS7, 2,713 DS8, and 5,119 DS9 tracks. The track builder also
requires at least six observations. A track's span includes scanner gaps and is
not continuous recorded dwell. Receiver tracks are not unique satellites.

The first complete census uses **one pilot-selected excerpt per eligible track**,
not every recorded visit. The eligible tracks contain 567,622 track-to-visit
memberships; some receiver tracks observe the same visits. Full-duration recovery
of all those visits is a separate, much larger job. This bounded study broadens
coverage to all tracks instead of restricting analysis to a few strong examples.

An entry such as `DS9-F005-T0017` means frozen recording 5 in DS9 and receiver
track index 17 within this study's eligible tracks for that recording. The full
published track digest, receiver number, and session ID are retained alongside it.

“Recovered symbols” means calibrated complex IQ observations on supported
carriers. Real-sign bit planes are stored as observations, without claiming their
modulation is BPSK everywhere. Internally consistent repeating words are labeled
as candidates. No FEC-validated payload, satellite ID, position, or timing field
is claimed.

## Binding and recovery

1. Verify frozen dataset membership, capture manifest, and exported track files.
2. Load acquisition candidates through read-only public storage ports. Check
   capture and analysis digests against the frozen exports.
3. Reconstruct the published trajectory graph with the same three-second,
   six-observation policy. Bind by exact track ID, visit sequence, and observation
   times, then select the strongest acquisition-pilot margin within each track.
   This avoids confusing another candidate in the same visit with the track.
   Track CFO values can include alias adjustments, so nearest raw CFO is not used
   as a substitute for exact candidate membership.
4. Read the selected 20 ms probe excerpt; demodulate its first four complete
   frames. Preserve all supported in-channel carriers inside ±0.45 of the native
   sample rate, including pilots, and all 300 post-SSS OFDM symbols.
5. Apply the existing native-rate pilot retiming and phase calibration. Fit a
   linear complex SSS channel from two calibration frames; reserve two other
   frames for evaluation. A qualified track needs both evaluation frames above
   0.5 held-pilot coherence. Failure applies to this excerpt, not the entire track.
6. In each pilot-qualified evaluation frame, examine ten fixed nonoverlapping
   windows covering symbols 2–301, with 32 symbols per window and 12 in the last.
   Fit a 60-slot word from even symbols and independently
   reconstruct it from odd symbols. Require complete slot coverage, exact
   even/odd agreement, score above 0.25, and score exceeding 99 shuffled-word
   controls. Only afterward compare the word with the known 60-state generator.

The decode receipts also retain an initial fixed 64-symbol tail assay
(symbols 194–257). The whole-frame `windows.json` results drive word-distribution
clustering; the two assays have different window boundaries and counts.

The word check uses one receiver; it is weaker than the earlier paired-receiver
assays. The even/odd agreement and shuffled controls are exploratory checks, not
a CRC, FEC decode, BER estimate, or significance claim. The strict shuffled-word
gate rejects constant all-one/all-zero patterns. Selection happens before
examining unknown data. No radio collection or firmware modification is involved.

## Hierarchies

All hierarchies use average linkage and explicit Euclidean feature geometry.
No missing features are filled with zeros.
Ward linkage has not been run here. It would be a valid sensitivity comparison
on these explicit Euclidean features, but its merge heights have a different meaning.

Each entry retains four frames of 300 OFDM symbols; two frames estimate the channel
and two enter clustering. Each frame has 19–20 carriers at 5 MS/s, 28–29 at
7.5 MS/s, or 38–39 at 10 MS/s in this census, including eight pilots. Thus the
two evaluation frames supply 6,600–7,200, 12,000–12,600, or 18,000–18,600
non-pilot complex measurements respectively. The early-profile view uses only
48 measurements per track (two frames × six symbols × four carriers), averaged
to 24 complex coordinates. These are not counts of independent message bits.

- **All recovered phase shapes:** every successfully recovered track, including
  failed pilot gates. Sixteen circular phase bins describe each of four regions:
  symbols 2–7, 8–33, 34–129, and 130–301. Regions have equal total weight; bins
  are centered on the real axis. Hellinger distance compares distributions.
  This is a waveform-shape census; noise and calibration can dominate its groups.
- **Qualified phase shapes:** the same metric, restricted to qualified tracks.
  This allows comparison across edges, but does not equate their physical carrier
  coordinates or identify message content.
- **Upper/lower early profiles:** separate trees for symbols 2–7, using four fixed
  common data carriers adjacent to each edge's pilots. Mean unit-phasor profiles
  are centered and normalized, giving distance sqrt(2 × (1 − correlation)).
  Qualified tracks missing a required carrier are excluded from this view only.
- **Qualified observed-word distributions:** Hellinger distance over all accepted
  exact word candidates from qualified tracks, including unconfirmed deviations
  from the known family. Up to twenty
  windows come from only two evaluation frames; neighboring windows are dependent,
  profiles can remain sparse, and distances can tie. A tree of these words
  primarily groups observed states, not satellite identity.
- **Qualified mean word bits:** a graded alternative to exact-word categories.
  Average each of the 60 recovered sign positions over accepted windows, then
  compare the mean bit vectors with normalized Euclidean distance. For two
  single-word tracks this equals sqrt(Hamming distance / 60). It avoids treating
  every nonidentical word as equally different, but known sequence structure and
  unequal window counts still confound satellite interpretation.

The full hierarchy and every pairwise distance are saved for each view. Figures
draw every leaf; for more than 160 tracks, heatmaps display averages between
contiguous blocks of ordered leaves. Those overview cells are not individual
track-pair correlations. No arbitrary number of satellite clusters is assumed.

Prior DS7 satellite labels are included only for exact track-ID matches marked
`likely_conditional` by the existing annotation study. Labels are not used to
construct clusters. Other tracks remain unlabeled. Different receivers, overlapping
tracks, repeated visits, recording session, channel, and sample rate are potential
dependencies or confounders. Four-frame excerpts provide only two evaluation
frames, so this survey does not establish stable per-satellite signatures.

## Reproducibility and data retention

Scripts are `census.py`, `decode_tracks.py`, `decode_windows.py`,
`cluster_tracks.py`, and `audit.py`.
The native-rate decoder and published pilot/SSS references are reused unchanged.
Storage access uses the installed repository release
`17484895464c225ebba977487aa36d3d81658bd8`; its scientific Python environment also
supplies the storage contracts. The read-only run uses the `leo` group, four
worker processes, one BLAS thread each, and reduced scheduling priority. It is
bounded by a 30-minute process timeout and writes resumable per-recording receipts.

All raw/derived numerical artifacts stay beneath ignored `local/`:

- `census.json`: complete frozen membership and track ledger.
- `decoded/<unit>/results.json`: selection, provenance, pilot diagnostics,
  errors, and word candidates for every track.
- `decoded/<unit>/track-*.npz`: complex64 soft symbols, FFT bins, receiver
  metadata, and packed real-sign observations. The signs are not decoded payload.
- `decoded/<unit>/windows.json`: whole-frame fixed-window word candidates.
- `audit.json`: completion, counts, source hashes, and recording receipts.
- `clustering.json`: track metadata, quality, coverage, and hierarchy summaries.
- `clusters/<view>/`: full linkage, ordered track CSV, condensed all-pairs
  distances, feature arrays, labels, and overview figure.

`condensed_distances.npy` follows SciPy's `pdist` ordering, with row labels in
`labels.json`; `linkage.npy` follows SciPy's linkage format. The full-distance
artifact is float32 for storage, while clustering uses float64 distances.
`lookup.py --view <view> --track <track-ID>` reads exact neighboring tracks without
expanding the matrix and reports ties. For early-profile views it also converts
distance back to correlation. Ordered CSV leaf zero is at the bottom of the figures.
Tests exercise eligibility boundaries, unknown/missing word positions, independent
symbol disagreement, phase histogram wrap behavior, and distance geometry.
All 13 tests pass, as does Ruff. Numerical artifacts remain local and excluded
from Git. This study has not been committed or published remotely.
