# Frozen held-recording forecast application

This applies the existing R01 and R02 methods to the twelve validation scans
in the sealed split. It authorizes metadata and earlier-donor forecasts only.
No target response evaluation, IQ scoring, geography, recovered donors or
localization is part of this preparation.

Select exactly the R01 panel: CH1/4 controls and CH5–8, native-counter
fractions .2/.4/.6/.8 of the full processed-probe start-counter extent, nearest
RX0 channel visit with earlier-counter tie break, both receivers on the same
visit and edge. Keep all 288 requested paired slots and 576 receiver cells,
including unavailable cases. Histories are precisely the frozen R01 last
12 strictly earlier same-channel/RX/edge visits within 4.5 s. The predictor,
candidate ranks, modes, gates, rates, widths and primary ordering are unchanged.

Tracking exports are parsed to select metadata and original earlier histories.
Target candidate fields are excluded from panel target metadata and never
evaluated. A previous panel target may later serve as an original donor under
the same causal rule; this is shared acquisition exposure, not a new independent
observation. No target evaluation archive is created.

R01 forecasts are serialized and reloaded before the exact original native
metadata enrichment. Stream-generation labels and integer hardware generations
are distinct. Native target/donor metadata uses the same public index mapper;
no IQ is opened. Source files and protocol hashes bind both methods. The R02
transform consumes only enriched R01 primary forecasts and donor histories,
using its unchanged five-donor/span/conditioning policy and unchanged CFO.
Consistent linear, quadratic/fallback and descriptive legacy controls remain
separate. Historical constant epochs have the nominal midpoint-effective
interpretation from R02, and the original R01 adapter remains distinct.

Freeze panel and source protocol before forecasts; seal both forecast artifacts
before any future scoring. Owned tests exercise metadata-only target selection,
causal history truncation and the JSON alias boundary. Audit all cells with
fresh frozen-method predictions, target-field redaction, exact native mapping
and R02 primary/CFO/legacy parity. Preserve failures. Each command is bounded
to 580 seconds with BLAS1. This is held out from this revision only; recordings
were exposed to older studies and share the original acquisition location.
