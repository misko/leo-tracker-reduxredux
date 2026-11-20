# Saved-recording locator smoke test

The promoted command in `/srv/bulk/leo-dev/pipeline-eval-20261118/clean-checkout` accepted a SHA-256 authenticated DS29-0082 locator and returned `stage_only` with exit code 0. On CPU 3 it authenticated one complete signed chunk with 64 visits, 48 valid windows, 16 exclusions and 108 detector groups. Raw wall was 14.20 seconds. The externally timed command took 19.34 seconds. The locator had no archived native-factor entry. Smoke mode ended at the raw stage and produced no native handoff or position. [Locator, authenticated chunk and terminal receipt](locator-smoke.json)

The promoted build and the complete scored replay used identical native binary and numeric source hashes. This smoke test adds command-line coverage for the locator path. The full-case prediction and score seals contain the measured position comparison. [Complete replay](README.md) · [Report seal](report-seal.json)
