# Fixed-center short-GLRT CFO feasibility

Stop this approach. Even with the reference-selected window and reference-derived
integer timing supplied as an oracle, neither fixed CFO bank reliably recovers the
packed detector's physical CFO. This is an optimistic timing diagnostic, not a
blind acquisition result.

Two variants were fixed before scores were opened:

- Four centers: `[-300, -100, 100, 300] kHz`.
- Eight centers: `[-350, -250, -150, -50, 50, 150, 250, 350] kHz`.

Each center uses `NativeKnownStateV3`, two frames, no timing recovery, and the
floor of the reference fitted epoch. The selected proposal maximizes the partial
`exact - control` margin. Its physical CFO is the center plus the returned GLRT
residual. Success requires a strict margin above 0.025 and CFO within 8 kHz of the
packed unseeded reference.

## Development evidence

| Variant | Margin positive | CFO within 8 kHz | Joint success | Center-bank CPU / blind fine CPU |
| --- | ---: | ---: | ---: | ---: |
| Four centers | 27/36 | 11/36 | 11/36 | 0.850x outer, 0.652x native |
| Eight centers | 28/36 | 22/36 | 22/36 | 1.715x outer, 1.381x native |

The four-center bank's median absolute CFO error is 226.8 kHz and its maximum is
781.3 kHz. The eight-center median is 306.9 Hz, but 14 of 36 cases still exceed
8 kHz and the maximum reaches 834.7 kHz. The good median therefore hides a large
alias tail. Four centers are cheaper than the existing fine stage but retain only
11 reference CFOs. Eight centers improve retention to 22 while already costing
more than the fine stage they would replace. These costs exclude the existing
fractional/full confirmation that would still be required.

All eight pilot receiver-controls are margin-positive and within 8 kHz for both
banks. The partial two-frame margin also marks 4/8 noise and 3/8 tone controls
positive with four centers, and 5/8 noise and 1/8 tone controls positive with
eight centers. A later full confirmation might reject those proposals, but the
short-bank margin cannot serve as the decision gate used here.

The failure occurs despite truth-supplied timing. An operational path would also
need to acquire the correct window and timing, so it cannot improve this bound.
Development has no established 5 MS/s real-IQ positives; only the fixed 5 MS/s
controls are represented.

Do not add tuned centers, retain extra aliases, or change the short-score threshold
from these results. Keeping multiple CFO aliases would add confirmation work to a
bank that is already slower than fine search at eight centers. A future CFO method
needs independent alias-disambiguating evidence before full GLRT scoring, then a
new preregistered development comparison.

The immutable receipt is `glrt_cfo_results.json`, SHA256
`414271b5ecffcdb2a43f91196c50d7bf7a01eef28127c01dd35e56f85581b80e`.
No holdout IQ or outcomes were opened.
