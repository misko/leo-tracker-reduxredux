# Artifact scope and replay requirements

This iteration preserves new research sources, frozen protocols, synthetic
observations/results, later-panel readiness and fit outputs, figures and audit
receipts. `publication_manifest.json` identifies the published bytes. The
publication is a research record, not an operational algorithm release.

The synthetic phase/shape controls reuse the earlier common-noise realizations,
sites and inference pipeline. Their original noisy controls and joint-component
interventions are documented at immutable commit
`5217788f231f9edce40ddca515a636a26bb97659` in
[identity/components](https://github.com/misko/leo-tracker-reduxredux/blob/5217788f231f9edce40ddca515a636a26bb97659/reports/2026_10_25_ds24_identity_components/README.md).
The generating draws, source constants, per-ID noise and actual new observation
archives are distinct from a full raw-IQ simulator or an association-selection
benchmark. Earlier inputs and fitted controls are referenced rather than copied
or refitted here.

The later panel's [readiness report](readiness/FINDINGS.md) documents its exact
eight members and complete public-contract validation. Full tracking-document
SHA256 values were frozen before validation. Every raw authority was reconstructed
from the source inventory and verified native manifest/index metadata. Those
checks did not open IQ payloads or inspect production positions/errors.
The sample is a separate research panel, not a new dataset mint. The checked
research exposure scope and the unverified same-site/no-relocation assumption
remain explicit.

The publication does not duplicate the later scans' full tracking inputs,
ephemeris banks, complete causal TLE archive, or old runtime/source capsules.
Readiness receipts, preparation receipts, protocols and scientific seals bind
the exact external input paths and hashes. A persisted hash is an identity
check, not the corresponding input bytes. No standalone clean restoration or
numerical replay is claimed from this report alone.

The [publication manifest](publication_manifest.json) lists every included file
with its byte count and SHA256. The [external-input inventory](external_inputs.json)
distinguishes omitted preparation/intermediate files from dependencies outside
this study. Final later-panel comparisons, all four cold-control/candidate arm
records per case, and the fresh family-cavity baseline/policy records are
included. The large upstream tracking/bank/history/nomination files and duplicate
ALGO02/native-stage dumps remain external, with their original sealed identities.
The inventory does not make these external bytes publicly downloadable.

The initial failed `validation/RF_seal.json` and terminal audit are preserved as
technical provenance. `validation/RF_seal02.json` is the authoritative successful
RF audit; it uses the separately versioned audit-only legacy phase-history
accessor. The evaluator's freeze, once-run receipt and report seal bind its
subsequent geographic read. Packaging does not repair or overwrite either audit.

The public `TrackingInput` validator comes from
`/home/mouse9911/gits/leo-shared-production-main/src`, while native multirate
manifest/index ports come from the current checkout. Readiness isolates these
validators in separate Python subprocess environments and checks the same full
input hash in both. It never regenerates the tracking input through the IQ-reading
exporter. Exact source modules and setup-only failed attempts are recorded in
the readiness artifacts.

Scientific execution requires the repository `.venv/bin/python`, the pinned
research modules, NumPy/SciPy and existing causal orbital data. The fit supervisor
also uses `/tmp/algo03-feasible-deps`, the original DS25 research engine and
the frozen receiver-control adapter. Use one BLAS/OMP/MKL thread per numerical
worker. Source scripts retain their frozen absolute paths and refuse to
overwrite scientific outputs. A future rerun requires a fresh output location,
the complete matching external inputs and a separately declared budget.

The later comparison is supervised by `validation/runner.py`; its protocol and
matching independent preflight receipt are required before launch. It constructs
a fresh baseline and applies the frozen RX1-rf50 candidate with matched c arms.
Frequency fit, parent-ID preservation, numerical qualification, fallbacks and
geographic evaluation remain separate outcomes. No additional science or
geographic selection is performed merely to package this report.
