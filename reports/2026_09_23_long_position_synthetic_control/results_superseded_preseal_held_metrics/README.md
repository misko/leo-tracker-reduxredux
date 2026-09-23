# Superseded first fit publication

This directory preserves the first executed fit attempt for provenance. The
optimizer itself used only training rows, and the held-frequency perturbation
audit passed, but `fit.executed.py` calculated and included per-track held RMS
values in the sealed `inference.json`. That disclosure contradicted the frozen
post-seal-only evaluation rule.

The main report reruns the identical fixed generation and fit settings with
held metrics calculated only after inference is sealed. Do not use the results
in this directory as the current publication. `SOURCES.executed.sha256` is the
hash manifest that existed with this attempt; the bindings inside the JSON
artifacts identify the exact executed fitter and materialization.
