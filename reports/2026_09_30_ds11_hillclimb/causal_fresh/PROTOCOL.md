# Verified pre-capture orbit freshness ablation

This experiment is causal. The archived request timestamp is insufficient:
each newly used snapshot must have a matching content digest and a collector
publication receipt strictly before capture start. Existing exports remain
immutable. No post-capture snapshot enters this family.

The metadata inventory, before position fitting, identifies original-panel
indices 10,13,16,27,31. Evaluate all five, including byte changes that are
physically insignificant. The other 27 scans have no selected-element changes
and retain their exact IID results; they are not rerun or counted as wins.
Selection is independent of reference position errors. Completion evidence
qualifies specific snapshots, not a blanket removal of the 505-second guard.

Only candidate position and velocity arrays change. Preserve track membership,
observations, training masks, candidate identity and ordering, full catalogue
divisors, the independent t4/100Hz likelihood, per-track CFO profiling, bounds,
and the four established optimizer starts. Visibility is evaluated normally
under the replacement states. Shortlists remain conditional on the old export;
this is not a test of a freshly generated full catalogue shortlist.

Preparation repropagates each replaced original element at all original
observation times and timing nodes, requiring agreement with the existing bank
within 1e-8km position and 1e-10km/s velocity before producing replacement
arrays. Bind inputs, source bytes, identities, element records, completion
proof and output arrays. Never overwrite original banks. Preparation is capped
at 180 seconds per scan; each four-start fit at 90 seconds; single-thread BLAS.

Use the existing optimizer qualification rules. Report all five attempts,
failures and paired errors; report full-32 coverage, median, mean, P90, maximum
and sub-km yield. Qualification-only fallback, if discussed, must be explicitly
separate from raw model coverage. No reference-based endpoint selection.
The harness common-IID held score uses the original orbit bank and is labeled
accordingly. A fresh-bank predictive score must profile CFO on training data
only and retain the existing held mask.

This sparse deterministic input correction is not subject to the eight-scan
likelihood-family screen, which mostly contains unchanged inputs. A favorable
five-scan result is exploratory: no general performance claim or goal
completion without a separate eligible-scan confirmation. Report unchanged
median or mixed tails honestly; numerical qualification alone is not success.

Offline orbit updates are a separate future experiment and cannot satisfy the
primary causal objective.
