# Scoring-contract diagnostic

TG11-v1's failed four-visit experiment remains failed. Its native final statistic
is not the same computation as the current scanner's GLRT-64. This distinction
must be resolved before attributing the additional detection to acquisition
quality or a physical false alarm.

The frozen native profile enables `LEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1`.
`native_presence/presence.c:621` enables this only for final scoring, and line
645 selects symbols 152..215 on odd frames, with an early-region fallback when
the late region would exceed the aperture. Other frames use symbols 2..65.
The current repository's `conditioned_glrt64_score` always selects symbols
2..65 on every supporting frame. Both use 64 symbols, but from different data.

Native blind acquisition also fits/removes tone nuisance before final scoring,
and uses fractional interpolation. The guided native point path ingests raw
samples without that blind nuisance fit. The current scanner's point scorer
uses raw samples and integer epochs. Thus the diagnostic must not describe a
single numerical difference as an FP32 error without isolating these choices.

The next diagnostic re-evaluates frozen native hypotheses with the current
point scorer, including adjacent integer epochs where needed, and compares
them with native raw guided scoring. It includes both the disputed visit and
known matching positives. Results remain diagnostic: they do not erase the
failed comparator gate or establish which signal is physically present.

A possible follow-up is to use native acquisition strictly to propose timing
and frequency, while accepting detections only through the current canonical
raw-sample GLRT statistic. That is a new detector experiment requiring a new
frozen design, control evaluation, paired complete-call timing and real-data
agreement checks. Cache predictions would require the same fresh confirmation.
