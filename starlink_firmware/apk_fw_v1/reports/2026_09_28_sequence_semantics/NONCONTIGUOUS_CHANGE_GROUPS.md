# Noncontiguous header change groups

## Result

This experiment did **not identify a codeword boundary or decode additional
message bits**. It tests a different question from the earlier contiguous and
rectangular parity searches: do distant signal positions change together in
a way that generalizes to other frames?

Of 157 discovery-selected links, 102 had qualified evaluation data and only
three retained residual correlation of at least 0.8. Most discovery groups
therefore do not provide stable noncontiguous blocks. The three remaining
pairs have substantial qualifications described below.

![Discovery versus evaluation and surviving coordinates](local/header_change_groups.png)

## Data and method

The input is the existing 78-frame full-band **early-symbol subset**, covering
OFDM symbols 2–7, rather than 78 complete frames. Published reference rotations
are removed; the same 1,004 nonpilot carriers and hard-axis quality criterion
as earlier assays are used. This avoids conflating available complete-frame
coverage (13 reference frames) with early-symbol coverage (78 frames).

Frames 0–38 select links; frames 39–77 evaluate them. Consecutive-frame XORs
are formed separately within each partition, giving 38 change observations
per partition and no transition across the partition boundary. A fixed sign
mask cancels in these XORs. Positions must pass discovery quality throughout
and change on 6–32 discovery transitions.

Identical discovery change traces are collapsed to one representative. This
removes exact copy/complement relationships from link discovery, though it can
also collapse distinct true signals that happen to agree in this short sample.
Each trace is centered and projected off the frame-wide mean change rate to
reduce broad common-mode activity. Each representative proposes its strongest
positive residual-correlation neighbor, accepted only at correlation ≥0.8.
These choices are frozen before evaluation. This is grouping by covariance,
not a code decoder or a parity test.

Twenty controls independently rotate evaluation change traces in time,
preserving each trace's count and circular ordering but disrupting alignment.
They use the same quality mask and common-mode treatment. These are descriptive
controls; they do not preserve joint header states or provide calibrated
significance across the large discovery search.

| Quantity | Result |
| --- | ---: |
| Qualified, changing discovery positions | 4,773 |
| Distinct discovery change traces | 4,327 |
| Selected links | 157 |
| Connected discovery groups | 102 |
| Largest group, representative positions | 9 |
| Links with fully qualified evaluation data | 102 |
| Median evaluation residual correlation | 0.207 |
| Evaluation links with correlation ≥0.8 | 3 |
| Corresponding counts across 20 controls | 18 controls: 0; one: 1; one: 2 |

Connected groups are exploratory associations, not firmware-sized codewords.
In particular, group size after collapsing copies cannot be compared directly
with a 114-symbol codeword size.

## The three remaining pairs

Coordinates use native FFT bins and the existing OFDM numbering.

| Pair | Coordinates (symbol, bin) | Discovery / evaluation correlation | Evaluation change counts | Separate raw-recording change counts |
| --- | --- | --- | --- | --- |
| 1 | (2,470), (3,654) | 0.806 / 0.835 | 16,16 of 38 | 1,1 of 6 |
| 2 | (3,595), (3,651) | 0.835 / 1.000 | 5,5 of 38 | 3,3 of 6 |
| 3 | (5,673), (5,733) | 0.880 / 1.000 | 8,8 of 38 | 0,0 of 6 |

All three pairs have zero change disagreements in the six qualified transitions
of the separate seven-frame pilot-referenced raw recording. Pair 3 is constant
there, so its agreement is uninformative. Pair 1 provides only one changing
event, too little for a strong independent claim.

As a post-hoc diagnostic, restrict evaluation to the 18 transitions that keep
the previously discovered shared header-state label unchanged. Pair 1 then
changes only once at each position; pair 2 never changes; pair 3 changes five
times at each position, with no disagreements. Thus most pair-1 activity and
all pair-2 activity occur on known state changes. Pair 3's 60-bin separation
also warrants checking against known periodic structure before interpreting it
as coding. These observations do not establish the causal source of any pair.
The state labels were fitted in earlier all-frame work, so this diagnostic is
not an independent test.

## Interpretation and reproducibility

The result weakens the hypothesis that simple co-change grouping will directly
reveal noncontiguous header codewords in this sample. It does not rule out FEC:
distinct coded bits can have little pairwise correlation, particularly when
the input has substantial entropy. Joint mode changes can also create strong
correlation without defining codeword boundaries. More correlation scans alone
would not resolve that ambiguity.

The first two pairs remain empirical relationships worth retaining, but neither
is a decoded field, generator constraint, or satellite identity. A next coding
test needs a higher-order relation that predicts unused changing bits, or a
firmware-supported mapping; these correlations alone do not supply either.

`header_change_groups.py` records all links, coordinates, controls, raw-transfer
counts, state diagnostics, and input hashes in ignored
`local/header_change_groups.json`, and generates the figure. It does not modify
raw data. Two synthetic tests verify recovery of a noncontiguous noisy pair,
collapse of duplicate traces, and removal of an exact common-mode factor.
Both tests and Ruff pass. The image and numerical output are excluded from Git.

Although selection for this assay uses only its discovery partition, all 78
frames have been studied previously. The later partition is an evaluation
partition for this algorithm, not a pristine project-wide holdout. No new
recordings, large downloads, commits, or remote changes were made.
