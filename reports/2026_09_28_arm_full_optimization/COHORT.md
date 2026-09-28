# Full-inventory native quality cohort

`cohort.py` selects 64 saved DS7 dwells from the complete 704-row receipt without detector outcomes: the first eight lower and first eight upper metadata rows at each native rate. `cohort_probe` creates one workspace per dwell and emits all 22 receiver/probe results, each with all retained candidates and kernel-only timing from `leo_full_search_result`.

The run records every worker result and error in `rows.jsonl`. The expected inventory is 64 dwells, 1,408 receiver/probe rows, and 11,264 ordered candidates. Sealed original repeat-0 baseline rows supply per-window ordered and one-to-one positive comparisons. Workers default to four and are capped at eight; temporary CI16 files live in an owned temporary directory and are removed on completion.
